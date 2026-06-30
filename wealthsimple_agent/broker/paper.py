from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from wealthsimple_agent.fees import FeeModel, estimate_slippage_cost
from wealthsimple_agent.models import OrderIntent, PortfolioSnapshot, Position


@dataclass
class _Pos:
    ticker: str
    quantity: float = 0.0
    avg_price: float = 0.0  # includes fees in cost basis


class PaperBroker:
    """
    Minimal paper broker:
    - market fills at latest price +/- slippage
    - fees applied per trade + pct notional
    - avg_price includes costs to make realized P&L more realistic
    """

    def __init__(self, *, starting_cash: float, fee_model: FeeModel, slippage_bps: float = 5.0):
        self._cash = float(starting_cash)
        self._fee_model = fee_model
        self._slippage_bps = float(slippage_bps)
        self._positions: dict[str, _Pos] = {}
        self._realized_pnl = 0.0
        self._trades: list[dict] = []

    @property
    def realized_pnl(self) -> float:
        return float(self._realized_pnl)

    @property
    def trades(self) -> list[dict]:
        return list(self._trades)

    def _fill_price(self, *, side: str, px: float) -> float:
        bps = self._slippage_bps / 10_000.0
        if side == "buy":
            return px * (1.0 + bps)
        return px * (1.0 - bps)

    def get_portfolio(self, *, latest_price_by_ticker: dict[str, float]) -> PortfolioSnapshot:
        now = datetime.now(tz=timezone.utc)
        positions: list[Position] = []
        equity = float(self._cash)
        for t, pos in sorted(self._positions.items()):
            if pos.quantity <= 0:
                continue
            positions.append(Position(ticker=t, quantity=pos.quantity, avg_price=pos.avg_price))
            px = latest_price_by_ticker.get(t)
            if px is not None:
                equity += float(px) * float(pos.quantity)
        return PortfolioSnapshot(as_of=now, cash=float(self._cash), equity=float(equity), positions=positions)

    def execute(self, *, intents: list[OrderIntent], latest_price_by_ticker: dict[str, float]) -> None:
        now = datetime.now(tz=timezone.utc)
        for intent in intents:
            t = intent.ticker.upper()
            px = latest_price_by_ticker.get(t)
            if px is None or px <= 0:
                continue

            if intent.action == "buy":
                qty = float(intent.quantity)
                fill_px = self._fill_price(side="buy", px=float(px))
                fees = self._fee_model.estimate_fees(price=fill_px, quantity=qty) + estimate_slippage_cost(
                    price=float(px), quantity=qty, slippage_bps=self._slippage_bps
                )
                cost = (fill_px * qty) + fees
                if cost > self._cash:
                    continue

                self._cash -= cost
                pos = self._positions.get(t) or _Pos(ticker=t)
                new_qty = pos.quantity + qty
                if new_qty > 0:
                    pos.avg_price = ((pos.avg_price * pos.quantity) + cost) / new_qty
                pos.quantity = new_qty
                self._positions[t] = pos

                self._trades.append(
                    {"ts": now.isoformat(), "ticker": t, "side": "buy", "qty": qty, "px": fill_px, "fees": fees}
                )

            elif intent.action == "sell":
                pos = self._positions.get(t)
                if not pos or pos.quantity <= 0:
                    continue
                qty = min(float(intent.quantity), float(pos.quantity))
                fill_px = self._fill_price(side="sell", px=float(px))
                fees = self._fee_model.estimate_fees(price=fill_px, quantity=qty) + estimate_slippage_cost(
                    price=float(px), quantity=qty, slippage_bps=self._slippage_bps
                )
                proceeds = (fill_px * qty) - fees
                cost_basis = pos.avg_price * qty
                pnl = proceeds - cost_basis

                self._cash += proceeds
                pos.quantity -= qty
                if pos.quantity <= 1e-12:
                    pos.quantity = 0.0
                self._positions[t] = pos
                self._realized_pnl += pnl

                self._trades.append(
                    {"ts": now.isoformat(), "ticker": t, "side": "sell", "qty": qty, "px": fill_px, "fees": fees, "pnl": pnl}
                )

