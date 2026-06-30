from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeeModel:
    fee_per_trade: float = 0.0
    fee_pct_notional: float = 0.0

    def estimate_fees(self, *, price: float, quantity: float) -> float:
        notional = float(price) * float(quantity)
        return float(self.fee_per_trade) + (float(self.fee_pct_notional) * notional)


def estimate_slippage_cost(*, price: float, quantity: float, slippage_bps: float) -> float:
    """
    Conservative execution cost estimate in currency units.
    slippage_bps = basis points applied to notional.
    """
    notional = float(price) * float(quantity)
    return notional * (float(slippage_bps) / 10_000.0)

