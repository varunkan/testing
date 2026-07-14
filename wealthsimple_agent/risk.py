from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskLimits:
    max_position_pct_of_equity: float = 0.25
    per_trade_risk_pct: float = 0.01
    max_daily_loss_pct: float = 0.03


def size_buy_quantity(
    *,
    cash: float,
    equity: float,
    price: float,
    confidence: float,
    limits: RiskLimits,
) -> float:
    """
    Simple sizing rule:
    - cap each position to max_position_pct_of_equity
    - scale target notional linearly with confidence
    """
    price = float(price)
    if price <= 0:
        return 0.0

    equity = max(0.0, float(equity))
    cash = max(0.0, float(cash))
    confidence = min(1.0, max(0.0, float(confidence)))

    max_notional = equity * float(limits.max_position_pct_of_equity)
    target_notional = max_notional * confidence
    affordable_notional = min(target_notional, cash)
    qty = affordable_notional / price
    return max(0.0, qty)

