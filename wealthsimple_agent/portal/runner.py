from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

from wealthsimple_agent.broker.paper import PaperBroker
from wealthsimple_agent.config import Settings
from wealthsimple_agent.engine import AgentDependencies
from wealthsimple_agent.fees import FeeModel
from wealthsimple_agent.market.yfinance_provider import fetch_daily_bars, latest_close
from wealthsimple_agent.models import NewsItem, OrderIntent, PriceBar, Signal
from wealthsimple_agent.news.rss import fetch_rss
from wealthsimple_agent.portal.monthly import compute_monthly_progress
from wealthsimple_agent.portal.store import Store
from wealthsimple_agent.risk import RiskLimits
from wealthsimple_agent.strategy.baseline import generate_consensus_signal, generate_signal
from wealthsimple_agent.strategy.advanced import (
    compute_factors,
    dynamic_exit_levels,
    estimate_expected_edge,
)
from wealthsimple_agent.strategy.personas import gather_opinions
from wealthsimple_agent.strategy.universes import resolve_universe


DEFAULT_UNIVERSE = ["@nasdaq100", "@tsx60"]


@dataclass
class PortalConfig:
    daily_budget: float = 100.0
    monthly_target_pct: float = 10.0  # 10x capital this month (aspirational, NOT guaranteed)
    take_profit_pct: float = 0.04
    stop_loss_pct: float = 0.02
    max_hold_days: int = 7
    max_new_buys_per_day: int = 4
    min_confidence_to_buy: float = 0.55
    planned_trading_days_per_month: int = 21
    lookback_days: int = 90
    use_persona_council: bool = True
    universe: list[str] = field(default_factory=lambda: list(DEFAULT_UNIVERSE))
    rss_urls: list[str] = field(default_factory=list)


@dataclass
class Recommendation:
    ticker: str
    action: str  # buy | sell | hold
    confidence: float
    score: float
    quantity: float
    limit_price: Optional[float]
    expected_edge: float
    estimated_fees: float
    rationale: str
    reason: str  # e.g. "top-ranked buy", "take-profit exit", "stop-loss exit", "time exit"
    persona_opinions: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "action": self.action,
            "confidence": self.confidence,
            "score": self.score,
            "quantity": self.quantity,
            "limit_price": self.limit_price,
            "expected_edge": self.expected_edge,
            "estimated_fees": self.estimated_fees,
            "rationale": self.rationale,
            "reason": self.reason,
            "persona_opinions": self.persona_opinions,
        }


@dataclass
class DailyReport:
    day: date
    budget_added: float
    recommendations: list[Recommendation]
    trades_executed: list[dict]
    portfolio_after: dict
    monthly_progress: dict

    def as_dict(self) -> dict:
        return {
            "day": self.day.isoformat(),
            "budget_added": self.budget_added,
            "recommendations": [r.as_dict() for r in self.recommendations],
            "trades_executed": self.trades_executed,
            "portfolio_after": self.portfolio_after,
            "monthly_progress": self.monthly_progress,
        }


def _deps(settings: Optional[Settings] = None) -> AgentDependencies:
    s = settings or Settings()
    return AgentDependencies(
        settings=s,
        fee_model=FeeModel(fee_per_trade=s.fee_per_trade, fee_pct_notional=s.fee_pct_notional),
        risk_limits=RiskLimits(
            max_position_pct_of_equity=s.max_position_pct_of_equity,
            per_trade_risk_pct=s.per_trade_risk_pct,
            max_daily_loss_pct=s.max_daily_loss_pct,
        ),
    )


def _build_exit_intents(
    *,
    positions: list,
    latest_px: dict[str, float],
    bars_by_ticker: dict[str, list[PriceBar]],
    cfg: PortalConfig,
    day: date,
) -> list[tuple[OrderIntent, str]]:
    """Generate sell intents for positions hitting TP / SL / time exits (vol-aware)."""
    out: list[tuple[OrderIntent, str]] = []
    for p in positions:
        if p.quantity <= 0:
            continue
        px = latest_px.get(p.ticker)
        if px is None or px <= 0:
            continue
        pnl_pct = (float(px) - float(p.avg_price)) / float(p.avg_price) if p.avg_price else 0.0
        days_held = (day - p.opened_day).days if p.opened_day else 0

        factors = compute_factors(bars=bars_by_ticker.get(p.ticker, []), news=[])
        realized_vol = factors.realized_vol if factors else 0.015
        tp, sl = dynamic_exit_levels(
            realized_vol=realized_vol,
            base_tp=cfg.take_profit_pct,
            base_sl=cfg.stop_loss_pct,
        )

        # Also exit early if advanced model flips strongly bearish.
        sig = generate_signal(ticker=p.ticker, bars=bars_by_ticker.get(p.ticker, []), news=[])
        model_exit = sig.action == "sell" and sig.confidence >= 0.7 and days_held >= 1

        if pnl_pct >= tp:
            reason = f"take-profit exit (+{pnl_pct:.2%}, tp={tp:.2%}, vol={realized_vol:.3f})"
        elif pnl_pct <= -sl:
            reason = f"stop-loss exit ({pnl_pct:.2%}, sl={sl:.2%}, vol={realized_vol:.3f})"
        elif model_exit:
            reason = f"model-exit ({sig.rationale[:80]})"
        elif days_held >= cfg.max_hold_days:
            reason = f"time exit ({days_held}d, pnl={pnl_pct:.2%})"
        else:
            continue

        out.append(
            (
                OrderIntent(
                    ticker=p.ticker,
                    action="sell",
                    quantity=float(p.quantity),
                    limit_price=None,
                    confidence=1.0,
                    expected_edge=max(0.0, pnl_pct),
                    estimated_fees=0.0,
                ),
                reason,
            )
        )
    return out


def _ranked_buy_signals(
    *,
    universe: list[str],
    bars_by_ticker: dict[str, list[PriceBar]],
    news_by_ticker: dict[str, list[NewsItem]],
    cfg: PortalConfig,
) -> list[Signal]:
    sigs: list[Signal] = []
    signal_fn = generate_consensus_signal if cfg.use_persona_council else generate_signal
    for t in universe:
        bars = bars_by_ticker.get(t, [])
        news = news_by_ticker.get(t, [])
        sig = signal_fn(ticker=t, bars=bars, news=news)
        if sig.action == "buy" and sig.confidence >= cfg.min_confidence_to_buy:
            sigs.append(sig)
    # Rank by confidence-weighted score (edge proxy)
    sigs.sort(key=lambda s: (s.confidence * max(0.0, s.score), s.confidence, s.score), reverse=True)
    return sigs


def _allocate_budget(
    *,
    cash_available: float,
    signals: list[Signal],
    latest_px: dict[str, float],
    max_buys: int,
    buffer: float = 0.99,
) -> list[tuple[Signal, float]]:
    """
    Power-allocate cash toward highest confidence × score ideas.
    """
    selected = signals[:max_buys]
    if not selected:
        return []
    weights = [max(1e-6, (s.confidence**1.5) * max(0.05, s.score)) for s in selected]
    total_w = sum(weights)
    out: list[tuple[Signal, float]] = []
    for s, w in zip(selected, weights):
        px = latest_px.get(s.ticker)
        if px is None or px <= 0:
            continue
        notional = (w / total_w) * float(cash_available) * float(buffer)
        qty = notional / float(px)
        if qty > 0:
            out.append((s, qty))
    return out


def run_daily(
    *,
    cfg: PortalConfig,
    store: Store,
    day: Optional[date] = None,
    bars_by_ticker: Optional[dict[str, list[PriceBar]]] = None,
    news_by_ticker: Optional[dict[str, list[NewsItem]]] = None,
    settings: Optional[Settings] = None,
) -> DailyReport:
    """
    One portal trading day:
      1. Add the daily budget to cash.
      2. Evaluate exits on existing positions (TP / SL / time).
      3. Rank buy signals from the universe and allocate today's budget.
      4. Execute sells first, then buys via the paper broker.
      5. Persist broker state, recommendations, and trades.
      6. Return a DailyReport with recommendations and monthly progress.
    """
    day = day or date.today()
    deps = _deps(settings)
    fee_model = deps.fee_model

    # Load or create broker
    state = store.load_broker_state()
    broker = PaperBroker(starting_cash=0.0, fee_model=fee_model, slippage_bps=deps.settings.slippage_bps)
    if state:
        broker.hydrate(cash=state["cash"], realized_pnl=state["realized_pnl"], positions=state["positions"])

    # Fresh daily budget
    broker.add_cash(cfg.daily_budget)

    # Resolve universe presets (e.g. "@nasdaq100", "@tsx60") into concrete tickers
    universe = resolve_universe(cfg.universe)
    if not universe:
        universe = resolve_universe(DEFAULT_UNIVERSE)

    # Fetch data if not injected
    if bars_by_ticker is None:
        lookback = max(cfg.lookback_days, deps.settings.default_lookback_days)
        bars_by_ticker = fetch_daily_bars(universe, lookback_days=lookback)
    if news_by_ticker is None:
        items: list[NewsItem] = []
        for url in cfg.rss_urls:
            try:
                items.extend(fetch_rss(url))
            except Exception:
                continue
        news_by_ticker = {t: items for t in universe}

    latest_px: dict[str, float] = {}
    for t in universe:
        px = latest_close(bars_by_ticker.get(t, []))
        if px is not None:
            latest_px[t] = px

    portfolio = broker.get_portfolio(latest_price_by_ticker=latest_px)

    # Exits (volatility-aware + model flip)
    exit_intents = _build_exit_intents(
        positions=portfolio.positions,
        latest_px=latest_px,
        bars_by_ticker=bars_by_ticker,
        cfg=cfg,
        day=day,
    )
    sell_intents: list[OrderIntent] = []
    recommendations: list[Recommendation] = []
    for intent, reason in exit_intents:
        sell_intents.append(intent)
        recommendations.append(
            Recommendation(
                ticker=intent.ticker,
                action="sell",
                confidence=intent.confidence,
                score=0.0,
                quantity=intent.quantity,
                limit_price=intent.limit_price,
                expected_edge=intent.expected_edge,
                estimated_fees=fee_model.estimate_fees(price=latest_px[intent.ticker], quantity=intent.quantity),
                rationale=reason,
                reason=reason,
            )
        )

    # Execute sells first (frees up cash)
    trades_before = len(broker.trades)
    if sell_intents:
        broker.execute(intents=sell_intents, latest_price_by_ticker=latest_px, day=day)
    new_sell_trades = broker.trades[trades_before:]
    trades_before = len(broker.trades)

    # Buys: rank and allocate within available cash
    buy_signals = _ranked_buy_signals(
        universe=universe,
        bars_by_ticker=bars_by_ticker,
        news_by_ticker=news_by_ticker,
        cfg=cfg,
    )
    available_cash = broker.get_portfolio(latest_price_by_ticker=latest_px).cash
    allocations = _allocate_budget(
        cash_available=available_cash,
        signals=buy_signals,
        latest_px=latest_px,
        max_buys=cfg.max_new_buys_per_day,
    )

    buy_intents: list[OrderIntent] = []
    for sig, qty in allocations:
        px = latest_px[sig.ticker]
        fees = fee_model.estimate_fees(price=px, quantity=qty) + (
            (px * qty) * (deps.settings.slippage_bps / 10_000.0)
        )
        factors = compute_factors(bars=bars_by_ticker.get(sig.ticker, []), news=news_by_ticker.get(sig.ticker, []))
        edge = estimate_expected_edge(sig, realized_vol=factors.realized_vol if factors else None)
        # Skip buys that don't clear costs with margin.
        if (px * qty) * edge <= fees * 1.15:
            continue
        opinions: list[dict] = []
        if cfg.use_persona_council:
            opinions = [
                op.as_dict()
                for op in gather_opinions(
                    ticker=sig.ticker,
                    bars=bars_by_ticker.get(sig.ticker, []),
                    news=news_by_ticker.get(sig.ticker, []),
                )
            ]
        intent = OrderIntent(
            ticker=sig.ticker,
            action="buy",
            quantity=qty,
            limit_price=None,
            confidence=sig.confidence,
            expected_edge=edge,
            estimated_fees=fees,
        )
        buy_intents.append(intent)
        recommendations.append(
            Recommendation(
                ticker=sig.ticker,
                action="buy",
                confidence=sig.confidence,
                score=sig.score,
                quantity=qty,
                limit_price=None,
                expected_edge=edge,
                estimated_fees=fees,
                rationale=sig.rationale,
                reason="top-ranked consensus signal within daily budget" if cfg.use_persona_council else "top-ranked advanced signal within daily budget",
                persona_opinions=opinions,
            )
        )

    if buy_intents:
        broker.execute(intents=buy_intents, latest_price_by_ticker=latest_px, day=day)
    new_buy_trades = broker.trades[trades_before:]

    all_new_trades = list(new_sell_trades) + list(new_buy_trades)

    # Persist
    portfolio_after = broker.get_portfolio(latest_price_by_ticker=latest_px)
    store.save_broker_state(
        cash=portfolio_after.cash,
        realized_pnl=broker.realized_pnl,
        positions=portfolio_after.positions,
    )
    for rec in recommendations:
        store.save_recommendation(day=day, rec=rec.as_dict())
    for t in all_new_trades:
        store.save_trade(day=day, trade=t)

    # Monthly progress (default goal: double capital this month)
    year_month = day.strftime("%Y-%m")
    realized_in_month = store.realized_pnl_in_month(year_month=year_month)
    days_run = store.days_run_in_month(year_month=year_month)
    sell_count, win_count = store.sell_trade_stats(year_month=year_month)
    capital = store.capital_added_in_month(year_month=year_month, daily_budget=cfg.daily_budget)
    progress = compute_monthly_progress(
        year_month=year_month,
        daily_budget=cfg.daily_budget,
        target_pct=cfg.monthly_target_pct,
        planned_trading_days=cfg.planned_trading_days_per_month,
        realized_pnl=realized_in_month,
        days_run=days_run,
        capital_invested=capital,
        trades_count=sell_count,
        winning_trades=win_count,
        equity=float(portfolio_after.equity),
        cash=float(portfolio_after.cash),
    )

    return DailyReport(
        day=day,
        budget_added=cfg.daily_budget,
        recommendations=recommendations,
        trades_executed=all_new_trades,
        portfolio_after=portfolio_after.model_dump(mode="json"),
        monthly_progress=progress.as_dict(),
    )
