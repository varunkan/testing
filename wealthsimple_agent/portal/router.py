from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from wealthsimple_agent.portal.runner import DEFAULT_UNIVERSE, PortalConfig, run_daily
from wealthsimple_agent.portal.store import Store
from wealthsimple_agent.portal.paper_trading import (
    ResetPaperRequest,
    PaperTradeRequest,
    execute_test_trade,
    portfolio_snapshot,
    reset_paper_account,
)

router = APIRouter(prefix="/portal", tags=["portal"])


_DEFAULT_DB = Path("portal.db")


class PortalConfigModel(BaseModel):
    daily_budget: float = Field(default=100.0, gt=0)
    monthly_target_pct: float = Field(default=10.0, ge=0.0, le=10.0)
    take_profit_pct: float = Field(default=0.04, gt=0.0)
    stop_loss_pct: float = Field(default=0.02, gt=0.0)
    max_hold_days: int = Field(default=7, ge=1, le=30)
    max_new_buys_per_day: int = Field(default=4, ge=1, le=10)
    min_confidence_to_buy: float = Field(default=0.55, ge=0.0, le=1.0)
    planned_trading_days_per_month: int = Field(default=21, ge=1, le=31)
    lookback_days: int = Field(default=90, ge=20, le=365)
    universe: list[str] = Field(default_factory=lambda: list(DEFAULT_UNIVERSE))
    rss_urls: list[str] = Field(default_factory=list)
    db_path: str = Field(default=str(_DEFAULT_DB))


class DailyRunRequest(BaseModel):
    day: Optional[date] = None
    config: PortalConfigModel = Field(default_factory=PortalConfigModel)


@router.post("/daily", summary="Run one portal trading day (recommendations + paper execution)")
def run_daily_endpoint(req: DailyRunRequest = Body(default_factory=DailyRunRequest)) -> dict:
    cfg = PortalConfig(
        daily_budget=req.config.daily_budget,
        monthly_target_pct=req.config.monthly_target_pct,
        take_profit_pct=req.config.take_profit_pct,
        stop_loss_pct=req.config.stop_loss_pct,
        max_hold_days=req.config.max_hold_days,
        max_new_buys_per_day=req.config.max_new_buys_per_day,
        min_confidence_to_buy=req.config.min_confidence_to_buy,
        planned_trading_days_per_month=req.config.planned_trading_days_per_month,
        lookback_days=req.config.lookback_days,
        universe=[t.strip().upper() for t in req.config.universe if t.strip()],
        rss_urls=list(req.config.rss_urls),
    )
    with Store(req.config.db_path) as store:
        report = run_daily(cfg=cfg, store=store, day=req.day)
    return report.as_dict()


@router.get("/recommendations/{day}", summary="List recommendations for a given day")
def recommendations(day: date, db_path: str = str(_DEFAULT_DB)) -> list[dict]:
    with Store(db_path) as store:
        return store.recommendations_for_day(day=day)


@router.get("/trades/{year_month}", summary="List trades for a given YYYY-MM month")
def trades(year_month: str, db_path: str = str(_DEFAULT_DB)) -> list[dict]:
    with Store(db_path) as store:
        return store.trades_in_month(year_month=year_month)


@router.get("/monthly/{year_month}", summary="Monthly performance vs double-money (or custom) target")
def monthly(
    year_month: str,
    db_path: str = str(_DEFAULT_DB),
    daily_budget: float = 100.0,
    target_pct: float = 10.0,
) -> dict:
    with Store(db_path) as store:
        from wealthsimple_agent.portal.monthly import compute_monthly_progress

        realized = store.realized_pnl_in_month(year_month=year_month)
        days_run = store.days_run_in_month(year_month=year_month)
        sell_count, win_count = store.sell_trade_stats(year_month=year_month)
        capital = store.capital_added_in_month(year_month=year_month, daily_budget=daily_budget)
        state = store.load_broker_state()
        equity = 0.0
        cash = 0.0
        if state:
            cash = float(state["cash"])
            # Mark-to-market without live prices: cash + cost basis of positions as floor.
            equity = cash + sum(float(p.quantity) * float(p.avg_price) for p in state["positions"])
        progress = compute_monthly_progress(
            year_month=year_month,
            daily_budget=daily_budget,
            target_pct=float(target_pct),
            planned_trading_days=21,
            realized_pnl=realized,
            days_run=days_run,
            capital_invested=capital,
            trades_count=sell_count,
            winning_trades=win_count,
            equity=equity,
            cash=cash,
        )
    return progress.as_dict()


@router.get("/performance/{year_month}", summary="Alias for monthly performance tracking")
def performance(
    year_month: str,
    db_path: str = str(_DEFAULT_DB),
    daily_budget: float = 100.0,
    target_pct: float = 10.0,
) -> dict:
    return monthly(year_month, db_path=db_path, daily_budget=daily_budget, target_pct=target_pct)


# ---- Paper / test trading ----

@router.get("/portfolio", summary="Current paper (test) portfolio")
def get_portfolio(db_path: str = str(_DEFAULT_DB)) -> dict:
    with Store(db_path) as store:
        return portfolio_snapshot(store)


@router.post("/test-trade", summary="Execute a single paper/test trade")
def test_trade(req: PaperTradeRequest) -> dict:
    try:
        with Store(req.db_path) as store:
            return execute_test_trade(store, req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/paper/reset", summary="Reset paper account cash/positions")
def paper_reset(req: ResetPaperRequest = Body(default_factory=ResetPaperRequest)) -> dict:
    with Store(req.db_path) as store:
        return reset_paper_account(store, starting_cash=req.starting_cash)


@router.get("/trades", summary="Recent paper trades (optional month filter)")
def trades_recent(year_month: Optional[str] = None, db_path: str = str(_DEFAULT_DB), limit: int = 50) -> list[dict]:
    ym = year_month or date.today().strftime("%Y-%m")
    with Store(db_path) as store:
        rows = store.trades_in_month(year_month=ym)
    return rows[-max(1, min(limit, 500)) :]
