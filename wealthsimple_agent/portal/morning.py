"""
Morning briefing workflow.

Every morning the user deposits an amount. The agent then proposes:
  1. Rotation sells — positions that hit exits or whose signal is now weaker
     than the best new opportunities, freeing capital for better ideas.
  2. Buy proposals — the highest-conviction consensus picks for today's
     capital (deposit + cash + estimated sell proceeds).

Nothing executes until the user approves the plan (or a subset of it).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

from wealthsimple_agent.config import get_settings
from wealthsimple_agent.market.yfinance_provider import fetch_daily_bars, latest_close
from wealthsimple_agent.models import NewsItem, OrderIntent, PriceBar
from wealthsimple_agent.news.aggregator import aggregate_news
from wealthsimple_agent.portal.paper_trading import load_paper_broker, persist_broker
from wealthsimple_agent.portal.runner import DEFAULT_UNIVERSE, _allocate_budget
from wealthsimple_agent.portal.store import Store
from wealthsimple_agent.strategy.advanced import compute_factors, dynamic_exit_levels, estimate_expected_edge
from wealthsimple_agent.strategy.baseline import generate_consensus_signal
from wealthsimple_agent.strategy.universes import resolve_universe

# Compounded daily growth needed for 10x over ~21 trading days: 10^(1/21) - 1.
REQUIRED_DAILY_GROWTH_FOR_10X = 10 ** (1 / 21) - 1

# A held position is proposed for rotation when the best new candidate's
# strength (confidence × score) beats it by at least this margin.
ROTATION_MARGIN = 0.15


@dataclass
class PlanItem:
    ticker: str
    action: str  # buy | sell
    quantity: float
    price: float
    notional: float
    confidence: float
    score: float
    expected_edge: float
    estimated_fees: float
    reason: str
    rationale: str
    persona_opinions: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "action": self.action,
            "quantity": self.quantity,
            "price": self.price,
            "notional": self.notional,
            "confidence": self.confidence,
            "score": self.score,
            "expected_edge": self.expected_edge,
            "estimated_fees": self.estimated_fees,
            "reason": self.reason,
            "rationale": self.rationale,
            "persona_opinions": self.persona_opinions,
        }


def _signal_strength(sig) -> float:
    return float(sig.confidence) * max(0.0, float(sig.score))


def build_morning_plan(
    store: Store,
    *,
    user_id: int,
    deposit: float,
    universe: Optional[list[str]] = None,
    max_buys: int = 4,
    min_confidence_to_buy: float = 0.55,
    take_profit_pct: float = 0.04,
    stop_loss_pct: float = 0.02,
    max_hold_days: int = 7,
    lookback_days: int = 90,
    day: Optional[date] = None,
    bars_by_ticker: Optional[dict[str, list[PriceBar]]] = None,
    news_by_ticker: Optional[dict[str, list[NewsItem]]] = None,
) -> dict:
    """
    Deposit `deposit` into the user's paper account, then build (but do NOT
    execute) today's plan: rotation sells + best buy proposals.
    """
    day = day or date.today()
    settings = get_settings()

    # 1. Deposit the morning amount.
    broker = load_paper_broker(store, user_id=user_id)
    if deposit > 0:
        broker.add_cash(float(deposit))
        store.add_deposit(user_id=user_id, day=day, amount=float(deposit))

    state = store.load_broker_state(user_id=user_id)
    held = list(state["positions"]) if state else []
    held_tickers = [p.ticker for p in held]

    # 2. Resolve universe and fetch data.
    tickers = resolve_universe(universe or DEFAULT_UNIVERSE)
    if not tickers:
        tickers = resolve_universe(DEFAULT_UNIVERSE)
    all_tickers = sorted(set(tickers) | set(held_tickers))

    if bars_by_ticker is None:
        bars_by_ticker = fetch_daily_bars(all_tickers, lookback_days=lookback_days)
    if news_by_ticker is None:
        # Batched RSS only here to keep the morning plan fast; per-ticker
        # sources still run in the full daily session.
        news_by_ticker = aggregate_news(
            all_tickers,
            news_sources=["rss"],
            rss_urls=settings.rss_feeds or None,
            max_age_hours=settings.news_max_age_hours,
            timeout_s=settings.news_timeout_s,
        )

    latest_px: dict[str, float] = {}
    for t in all_tickers:
        px = latest_close(bars_by_ticker.get(t, []))
        if px is not None and px > 0:
            latest_px[t] = float(px)

    # 3. Rank buy candidates from the universe (exclude already-held names).
    candidates = []
    for t in tickers:
        if t in held_tickers or t not in latest_px:
            continue
        sig = generate_consensus_signal(
            ticker=t, bars=bars_by_ticker.get(t, []), news=news_by_ticker.get(t, [])
        )
        if sig.action == "buy" and sig.confidence >= min_confidence_to_buy:
            candidates.append(sig)
    candidates.sort(key=_signal_strength, reverse=True)
    best_candidate_strength = _signal_strength(candidates[0]) if candidates else 0.0

    # 4. Propose sells: hard exits (TP/SL/time/model flip) and rotations into
    #    stronger ideas.
    sell_items: list[PlanItem] = []
    for p in held:
        px = latest_px.get(p.ticker)
        if px is None or p.quantity <= 0:
            continue
        pnl_pct = (px - float(p.avg_price)) / float(p.avg_price) if p.avg_price else 0.0
        days_held = (day - p.opened_day).days if p.opened_day else 0

        factors = compute_factors(bars=bars_by_ticker.get(p.ticker, []), news=[])
        realized_vol = factors.realized_vol if factors else 0.015
        tp, sl = dynamic_exit_levels(
            realized_vol=realized_vol, base_tp=take_profit_pct, base_sl=stop_loss_pct
        )

        sig = generate_consensus_signal(
            ticker=p.ticker,
            bars=bars_by_ticker.get(p.ticker, []),
            news=news_by_ticker.get(p.ticker, []),
        )
        strength = _signal_strength(sig) if sig.action == "buy" else 0.0

        if pnl_pct >= tp:
            reason = f"take-profit (+{pnl_pct:.1%}) — lock the gain and redeploy"
        elif pnl_pct <= -sl:
            reason = f"stop-loss ({pnl_pct:.1%}) — cut the loss before it compounds"
        elif sig.action == "sell" and sig.confidence >= 0.6:
            reason = f"signal turned bearish ({sig.confidence:.0%} confidence) — rotate out"
        elif days_held >= max_hold_days:
            reason = f"held {days_held}d with {pnl_pct:+.1%} — free the capital"
        elif candidates and best_candidate_strength >= strength + ROTATION_MARGIN and days_held >= 1:
            reason = (
                f"rotation — {candidates[0].ticker} looks stronger "
                f"({best_candidate_strength:.2f} vs {strength:.2f}); sell to fund it"
            )
        else:
            continue

        sell_items.append(
            PlanItem(
                ticker=p.ticker,
                action="sell",
                quantity=float(p.quantity),
                price=px,
                notional=px * float(p.quantity),
                confidence=float(sig.confidence),
                score=float(sig.score),
                expected_edge=max(0.0, pnl_pct),
                estimated_fees=0.0,
                reason=reason,
                rationale=sig.rationale,
            )
        )

    # 5. Propose buys with deposit + cash + estimated sell proceeds.
    cash_now = float(state["cash"]) if state else float(deposit)
    est_proceeds = sum(item.notional for item in sell_items)
    investable = cash_now + est_proceeds

    buy_items: list[PlanItem] = []
    allocations = _allocate_budget(
        cash_available=investable,
        signals=candidates,
        latest_px=latest_px,
        max_buys=max_buys,
    )
    for sig, qty in allocations:
        px = latest_px[sig.ticker]
        factors = compute_factors(
            bars=bars_by_ticker.get(sig.ticker, []), news=news_by_ticker.get(sig.ticker, [])
        )
        edge = estimate_expected_edge(sig, realized_vol=factors.realized_vol if factors else None)
        buy_items.append(
            PlanItem(
                ticker=sig.ticker,
                action="buy",
                quantity=float(qty),
                price=px,
                notional=px * float(qty),
                confidence=float(sig.confidence),
                score=float(sig.score),
                expected_edge=float(edge),
                estimated_fees=0.0,
                reason="highest-conviction consensus pick for today's capital",
                rationale=sig.rationale,
            )
        )

    # Persist deposited cash (positions unchanged until user approves).
    persist_broker(store, user_id=user_id, broker=broker, latest_px=latest_px)

    return {
        "day": day.isoformat(),
        "deposit": float(deposit),
        "cash_after_deposit": cash_now,
        "estimated_sell_proceeds": est_proceeds,
        "investable_if_approved": investable,
        "sells": [i.as_dict() for i in sell_items],
        "buys": [i.as_dict() for i in buy_items],
        "goal": {
            "monthly_target": "10x",
            "required_daily_growth_pct": REQUIRED_DAILY_GROWTH_FOR_10X,
            "note": (
                "10x in a month needs ≈"
                f"{REQUIRED_DAILY_GROWTH_FOR_10X:.1%} compounded growth every trading day. "
                "That is an extreme, aspirational goal — the plan ranks the strongest "
                "ideas available, but no strategy can guarantee it."
            ),
        },
        "disclaimer": "Nothing is executed until you approve. Paper trading only.",
    }


def execute_morning_plan(
    store: Store,
    *,
    user_id: int,
    items: list[dict],
    day: Optional[date] = None,
    price_overrides: Optional[dict[str, float]] = None,
) -> dict:
    """
    Execute the approved subset of a morning plan as paper fills.
    Sells run first so their proceeds fund the buys.
    """
    day = day or date.today()
    broker = load_paper_broker(store, user_id=user_id)
    state = store.load_broker_state(user_id=user_id)

    tickers = sorted({str(i["ticker"]).strip().upper() for i in items})
    latest_px: dict[str, float] = dict(price_overrides or {})
    missing = [t for t in tickers if t not in latest_px]
    if missing:
        bars = fetch_daily_bars(missing, lookback_days=5)
        for t in missing:
            px = latest_close(bars.get(t, []))
            if px is not None and px > 0:
                latest_px[t] = float(px)
    # Keep marks for other held positions so persisted equity stays sensible.
    for p in state["positions"] if state else []:
        latest_px.setdefault(p.ticker, float(p.avg_price))

    def _to_intent(item: dict) -> Optional[OrderIntent]:
        t = str(item["ticker"]).strip().upper()
        if t not in latest_px:
            return None
        return OrderIntent(
            ticker=t,
            action="buy" if str(item["action"]).lower() == "buy" else "sell",
            quantity=float(item["quantity"]),
            limit_price=None,
            confidence=float(item.get("confidence", 1.0)),
            expected_edge=float(item.get("expected_edge", 0.0)),
            estimated_fees=float(item.get("estimated_fees", 0.0)),
        )

    sells = [i for i in items if str(i["action"]).lower() == "sell"]
    buys = [i for i in items if str(i["action"]).lower() == "buy"]

    trades_before = len(broker.trades)
    now = datetime.now(tz=timezone.utc)
    for batch in (sells, buys):
        intents = [x for x in (_to_intent(i) for i in batch) if x is not None]
        if intents:
            broker.execute(intents=intents, latest_price_by_ticker=latest_px, day=day, as_of=now)

    new_trades = broker.trades[trades_before:]
    for t in new_trades:
        store.save_trade(user_id=user_id, day=day, trade=t)
    persist_broker(store, user_id=user_id, broker=broker, latest_px=latest_px)

    portfolio = broker.get_portfolio(latest_price_by_ticker=latest_px)
    return {
        "day": day.isoformat(),
        "executed": new_trades,
        "executed_count": len(new_trades),
        "skipped_count": len(items) - len(new_trades),
        "portfolio": {
            "cash": portfolio.cash,
            "equity": portfolio.equity,
            "realized_pnl": broker.realized_pnl,
            "positions": [p.model_dump(mode="json") for p in portfolio.positions],
        },
        "disclaimer": "Paper fills only — place real orders manually in your brokerage app.",
    }
