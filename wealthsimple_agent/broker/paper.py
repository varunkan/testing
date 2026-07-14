from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

from wealthsimple_agent.fees import FeeModel, estimate_slippage_cost
from wealthsimple_agent.models import OrderIntent, PortfolioSnapshot, Position


@dataclass
class _Pos:
    ticker: str
    quantity: float = 0.0
    avg_price: float = 0.0  # includes fees in cost basis
    opened_day: Optional[date] = None


class PaperBroker:
    """
    Minimal paper broker:
    - market fills at latest price +/- slippage
    - fees applied per trade + pct notional
    - avg_price includes costs to make realized P&L more realistic
    - tracks opened_day per position for time-based exits
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

    @property
    def positions(self) -> dict[str, _Pos]:
        return dict(self._positions)

    def add_cash(self, amount: float) -> None:
        self._cash += float(amount)

    def _fill_price(self, *, side: str, px: float) -> float:
        bps = self._slippage_bps / 10_000.0
        if side == "buy":
            return px * (1.0 + bps)
        return px * (1.0 - bps)

    def get_portfolio(
        self,
        *,
        latest_price_by_ticker: dict[str, float],
        as_of: Optional[datetime] = None,
    ) -> PortfolioSnapshot:
        now = as_of or datetime.now(tz=timezone.utc)
        positions: list[Position] = []
        equity = float(self._cash)
        for t, pos in sorted(self._positions.items()):
            if pos.quantity <= 0:
                continue
            positions.append(
                Position(
                    ticker=t,
                    quantity=pos.quantity,
                    avg_price=pos.avg_price,
                    opened_day=pos.opened_day,
                )
            )
            px = latest_price_by_ticker.get(t)
            if px is not None:
                equity += float(px) * float(pos.quantity)
        return PortfolioSnapshot(as_of=now, cash=float(self._cash), equity=float(equity), positions=positions)

    def execute(
        self,
        *,
        intents: list[OrderIntent],
        latest_price_by_ticker: dict[str, float],
        as_of: Optional[datetime] = None,
        day: Optional[date] = None,
    ) -> None:
        now = as_of or datetime.now(tz=timezone.utc)
        trade_day = day or now.date()
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
                if pos.opened_day is None:
                    pos.opened_day = trade_day
                pos.quantity = new_qty
                self._positions[t] = pos

                self._trades.append(
                    {
                        "ts": now.isoformat(),
                        "day": trade_day.isoformat(),
                        "ticker": t,
                        "side": "buy",
                        "qty": qty,
                        "px": fill_px,
                        "fees": fees,
                    }
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
                    pos.opened_day = None
                self._positions[t] = pos
                self._realized_pnl += pnl

                self._trades.append(
                    {
                        "ts": now.isoformat(),
                        "day": trade_day.isoformat(),
                        "ticker": t,
                        "side": "sell",
                        "qty": qty,
                        "px": fill_px,
                        "fees": fees,
                        "pnl": pnl,
                    }
                )

    def hydrate(
        self,
        *,
        cash: float,
        realized_pnl: float,
        positions: list[Position],
    ) -> None:
        """Restore broker state from a persisted snapshot."""
        self._cash = float(cash)
        self._realized_pnl = float(realized_pnl)
        self._positions = {
            p.ticker.upper(): _Pos(
                ticker=p.ticker.upper(),
                quantity=float(p.quantity),
                avg_price=float(p.avg_price),
                opened_day=p.opened_day,
            )
            for p in positions
            if p.quantity > 0
        }
