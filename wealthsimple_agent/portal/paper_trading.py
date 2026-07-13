from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

from wealthsimple_agent.broker.paper import PaperBroker
from wealthsimple_agent.config import get_settings
from wealthsimple_agent.fees import FeeModel
from wealthsimple_agent.market.yfinance_provider import fetch_daily_bars, latest_close
from wealthsimple_agent.models import OrderIntent
from wealthsimple_agent.portal.store import Store


class PaperTradeRequest(BaseModel):
    ticker: str = Field(min_length=1)
    action: Literal["buy", "sell"]
    quantity: float = Field(gt=0)
    # Optional override price for offline/tests; otherwise fetched live.
    price: Optional[float] = Field(default=None, gt=0)
    db_path: str = "portal.db"
    # If buying and cash is short, optionally top up paper cash (test funding).
    fund_if_needed: bool = True


class ResetPaperRequest(BaseModel):
    starting_cash: float = Field(default=1_000.0, gt=0)
    db_path: str = "portal.db"


def _fee_model() -> FeeModel:
    s = get_settings()
    return FeeModel(fee_per_trade=s.fee_per_trade, fee_pct_notional=s.fee_pct_notional)


def _slippage() -> float:
    return float(get_settings().slippage_bps)


def load_paper_broker(store: Store, *, starting_cash: float = 0.0) -> PaperBroker:
    broker = PaperBroker(starting_cash=starting_cash, fee_model=_fee_model(), slippage_bps=_slippage())
    state = store.load_broker_state()
    if state:
        broker.hydrate(cash=state["cash"], realized_pnl=state["realized_pnl"], positions=state["positions"])
    return broker


def persist_broker(store: Store, broker: PaperBroker, *, latest_px: dict[str, float]) -> None:
    portfolio = broker.get_portfolio(latest_price_by_ticker=latest_px)
    store.save_broker_state(
        cash=portfolio.cash,
        realized_pnl=broker.realized_pnl,
        positions=portfolio.positions,
    )


def resolve_price(ticker: str, *, override: Optional[float] = None) -> float:
    t = ticker.strip().upper()
    if override is not None and override > 0:
        return float(override)
    bars = fetch_daily_bars([t], lookback_days=5)
    px = latest_close(bars.get(t, []))
    if px is None or px <= 0:
        raise ValueError(f"Could not fetch a price for {t}")
    return float(px)


def portfolio_snapshot(store: Store, *, price_overrides: Optional[dict[str, float]] = None) -> dict:
    broker = load_paper_broker(store)
    state = store.load_broker_state()
    tickers = [p.ticker for p in (state["positions"] if state else [])]
    latest_px: dict[str, float] = dict(price_overrides or {})
    missing = [t for t in tickers if t not in latest_px]
    if missing:
        try:
            bars = fetch_daily_bars(missing, lookback_days=5)
            for t in missing:
                px = latest_close(bars.get(t, []))
                if px is not None:
                    latest_px[t] = float(px)
        except Exception:
            # Fall back to cost basis for mark if market data unavailable.
            for p in state["positions"] if state else []:
                latest_px.setdefault(p.ticker, float(p.avg_price))

    portfolio = broker.get_portfolio(latest_price_by_ticker=latest_px)
    return {
        "mode": "paper",
        "cash": portfolio.cash,
        "equity": portfolio.equity,
        "realized_pnl": broker.realized_pnl,
        "positions": [p.model_dump(mode="json") for p in portfolio.positions],
        "marks": latest_px,
        "as_of": datetime.now(tz=timezone.utc).isoformat(),
    }


def execute_test_trade(store: Store, req: PaperTradeRequest) -> dict:
    """
    Execute a single paper (test) trade against the persisted PaperBroker state.
    """
    ticker = req.ticker.strip().upper()
    action = req.action.lower()
    qty = float(req.quantity)
    px = resolve_price(ticker, override=req.price)

    broker = load_paper_broker(store)
    latest_px = {ticker: px}

    # Include marks for other open positions so equity stays sensible after save.
    state = store.load_broker_state()
    if state:
        for p in state["positions"]:
            latest_px.setdefault(p.ticker, float(p.avg_price))

    portfolio_before = broker.get_portfolio(latest_price_by_ticker=latest_px)
    if action == "buy" and req.fund_if_needed:
        needed = px * qty * 1.01
        if portfolio_before.cash < needed:
            broker.add_cash(needed - portfolio_before.cash)
    intent = OrderIntent(
        ticker=ticker,
        action="buy" if action == "buy" else "sell",
        quantity=qty,
        limit_price=None,
        confidence=1.0,
        expected_edge=0.0,
        estimated_fees=_fee_model().estimate_fees(price=px, quantity=qty),
    )

    trades_before = len(broker.trades)
    day = date.today()
    broker.execute(intents=[intent], latest_price_by_ticker=latest_px, day=day)
    new_trades = broker.trades[trades_before:]

    if not new_trades:
        raise ValueError(
            "Trade was not filled. For buys, check cash; for sells, check that you hold the ticker."
        )

    for t in new_trades:
        store.save_trade(day=day, trade=t)
    persist_broker(store, broker, latest_px=latest_px)

    portfolio = broker.get_portfolio(latest_price_by_ticker=latest_px)
    return {
        "mode": "paper",
        "status": "filled",
        "trade": new_trades[-1],
        "portfolio": {
            "cash": portfolio.cash,
            "equity": portfolio.equity,
            "realized_pnl": broker.realized_pnl,
            "positions": [p.model_dump(mode="json") for p in portfolio.positions],
        },
    }


def reset_paper_account(store: Store, *, starting_cash: float) -> dict:
    broker = PaperBroker(starting_cash=float(starting_cash), fee_model=_fee_model(), slippage_bps=_slippage())
    persist_broker(store, broker, latest_px={})
    return {
        "mode": "paper",
        "status": "reset",
        "cash": float(starting_cash),
        "equity": float(starting_cash),
        "realized_pnl": 0.0,
        "positions": [],
    }
