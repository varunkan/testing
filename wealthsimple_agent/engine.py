from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from wealthsimple_agent.config import Settings
from wealthsimple_agent.fees import FeeModel, estimate_slippage_cost
from wealthsimple_agent.models import NewsItem, OrderIntent, PortfolioSnapshot, Signal
from wealthsimple_agent.risk import RiskLimits, size_buy_quantity
from wealthsimple_agent.strategy.baseline import generate_signal
from wealthsimple_agent.strategy.advanced import estimate_expected_edge


@dataclass(frozen=True)
class AgentDependencies:
    settings: Settings
    fee_model: FeeModel
    risk_limits: RiskLimits


def build_signals(
    *,
    tickers: list[str],
    price_bars_by_ticker: dict[str, list],
    news_by_ticker: dict[str, list[NewsItem]],
    deps: AgentDependencies,
) -> list[Signal]:
    out: list[Signal] = []
    for t in tickers:
        bars = price_bars_by_ticker.get(t, [])
        news = news_by_ticker.get(t, [])
        out.append(generate_signal(ticker=t, bars=bars, news=news))
    return out


def build_order_intents(
    *,
    signals: list[Signal],
    portfolio: PortfolioSnapshot,
    latest_price_by_ticker: dict[str, float],
    deps: AgentDependencies,
) -> list[OrderIntent]:
    """
    Turns signals into order intents with a conservative fee+slippage check.
    """
    s = deps.settings
    limits = deps.risk_limits

    positions = {p.ticker.upper(): p for p in portfolio.positions}
    cash = float(portfolio.cash)
    equity = float(portfolio.equity)

    intents: list[OrderIntent] = []
    for sig in signals:
        t = sig.ticker.upper()
        if sig.action == "hold":
            continue
        if sig.confidence < s.min_confidence_to_trade:
            continue
        px = latest_price_by_ticker.get(t)
        if px is None or px <= 0:
            continue

        if sig.action == "buy":
            qty = size_buy_quantity(
                cash=cash,
                equity=equity,
                price=px,
                confidence=sig.confidence,
                limits=limits,
            )
            if qty <= 0:
                continue

            fees = deps.fee_model.estimate_fees(price=px, quantity=qty)
            slip = estimate_slippage_cost(price=px, quantity=qty, slippage_bps=s.slippage_bps)
            total_cost = fees + slip

            # Expected edge from advanced model mapping.
            expected_return_pct = estimate_expected_edge(sig)
            expected_profit = (px * qty) * expected_return_pct

            if expected_profit <= (total_cost * 1.25):
                # Skip trades where the model edge doesn't clear costs with margin.
                continue

            intents.append(
                OrderIntent(
                    ticker=t,
                    action="buy",
                    quantity=qty,
                    limit_price=None,
                    confidence=sig.confidence,
                    expected_edge=expected_return_pct,
                    estimated_fees=total_cost,
                )
            )
            cash -= px * qty  # reserve cash to avoid oversizing multiple buys

        elif sig.action == "sell":
            pos = positions.get(t)
            if not pos or pos.quantity <= 0:
                continue
            qty = float(pos.quantity)
            fees = deps.fee_model.estimate_fees(price=px, quantity=qty)
            slip = estimate_slippage_cost(price=px, quantity=qty, slippage_bps=s.slippage_bps)
            total_cost = fees + slip

            intents.append(
                OrderIntent(
                    ticker=t,
                    action="sell",
                    quantity=qty,
                    limit_price=None,
                    confidence=sig.confidence,
                    expected_edge=estimate_expected_edge(sig),
                    estimated_fees=total_cost,
                )
            )

    return intents


def empty_portfolio(*, starting_cash: float) -> PortfolioSnapshot:
    now = datetime.now(tz=timezone.utc)
    return PortfolioSnapshot(as_of=now, cash=float(starting_cash), equity=float(starting_cash), positions=[])

