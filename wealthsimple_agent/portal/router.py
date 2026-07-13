from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from wealthsimple_agent.portal.runner import DEFAULT_UNIVERSE, PortalConfig, run_daily
from wealthsimple_agent.portal.store import Store


router = APIRouter(prefix="/portal", tags=["portal"])


_DEFAULT_DB = Path("portal.db")


class PortalConfigModel(BaseModel):
    daily_budget: float = Field(default=100.0, gt=0)
    monthly_target_pct: float = Field(default=0.30, ge=0.0, le=2.0)
    take_profit_pct: float = Field(default=0.03, gt=0.0)
    stop_loss_pct: float = Field(default=0.02, gt=0.0)
    max_hold_days: int = Field(default=5, ge=1, le=30)
    max_new_buys_per_day: int = Field(default=3, ge=1, le=10)
    min_confidence_to_buy: float = Field(default=0.6, ge=0.0, le=1.0)
    planned_trading_days_per_month: int = Field(default=21, ge=1, le=31)
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


@router.get("/monthly/{year_month}", summary="Monthly progress toward aspirational target")
def monthly(
    year_month: str,
    db_path: str = str(_DEFAULT_DB),
    daily_budget: float = 100.0,
    target_pct: float = 0.30,
) -> dict:
    with Store(db_path) as store:
        from wealthsimple_agent.portal.monthly import compute_monthly_progress

        realized = store.realized_pnl_in_month(year_month=year_month)
        days_run = store.days_run_in_month(year_month=year_month)
        progress = compute_monthly_progress(
            year_month=year_month,
            daily_budget=daily_budget,
            target_pct=float(target_pct),
            planned_trading_days=21,
            realized_pnl=realized,
            days_run=days_run,
        )
    return progress.as_dict()
