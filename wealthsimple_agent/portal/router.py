from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from wealthsimple_agent.models import UserCreate, UserLogin, UserSettings
from wealthsimple_agent.portal.monthly import compute_monthly_progress
from wealthsimple_agent.portal.paper_trading import (
    PaperTradeRequest,
    ResetPaperRequest,
    execute_test_trade,
    portfolio_snapshot,
    reset_paper_account,
)
from wealthsimple_agent.portal.runner import DEFAULT_UNIVERSE, PortalConfig, run_daily
from wealthsimple_agent.portal.store import Store

router = APIRouter(prefix="/portal", tags=["portal"])

_DEFAULT_DB = Path("portal.db")
_api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


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
    use_persona_council: bool = Field(default=True)
    universe: list[str] = Field(default_factory=lambda: list(DEFAULT_UNIVERSE))
    rss_urls: list[str] = Field(default_factory=list)
    db_path: str = Field(default=str(_DEFAULT_DB))


class DailyRunRequest(BaseModel):
    day: Optional[date] = None
    config: PortalConfigModel = Field(default_factory=PortalConfigModel)


def _extract_api_key(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return authorization.strip()


def _get_store(db_path: str) -> Store:
    return Store(db_path)


def _get_current_user(
    authorization: Optional[str] = Security(_api_key_header),
    db_path: str = str(_DEFAULT_DB),
) -> dict:
    key = _extract_api_key(authorization)
    if not key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header. Use Bearer <api_key>.",
        )
    with _get_store(db_path) as store:
        user = store.get_user_by_api_key(api_key=key)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )
    return user


CurrentUser = Depends(_get_current_user)


# ---- Auth ----

@router.post("/auth/signup", summary="Create a new user account")
def signup(req: UserCreate, db_path: str = str(_DEFAULT_DB)) -> dict:
    try:
        with _get_store(db_path) as store:
            user = store.create_user(username=req.username, password=req.password)
        return user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/auth/login", summary="Log in and get API key")
def login(req: UserLogin, db_path: str = str(_DEFAULT_DB)) -> dict:
    try:
        with _get_store(db_path) as store:
            user = store.authenticate_user(username=req.username, password=req.password)
        return user
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e


@router.get("/auth/me", summary="Current user info")
def me(user: dict = CurrentUser) -> dict:
    return user


@router.post("/auth/auto-invest", summary="Toggle auto-invest for the current user")
def set_auto_invest(
    req: UserSettings,
    user: dict = CurrentUser,
    db_path: str = str(_DEFAULT_DB),
) -> dict:
    with _get_store(db_path) as store:
        store.set_auto_invest(user_id=user["id"], auto_invest=req.auto_invest)
        updated = store.get_user_by_api_key(api_key=user["api_key"])
    return {"auto_invest": updated["auto_invest"]}


# ---- Daily run ----

@router.post("/daily", summary="Run one portal trading day for the current user")
def run_daily_endpoint(
    req: DailyRunRequest = Body(default_factory=DailyRunRequest),
    user: dict = CurrentUser,
) -> dict:
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
        use_persona_council=req.config.use_persona_council,
        universe=[t.strip().upper() for t in req.config.universe if t.strip()],
        rss_urls=list(req.config.rss_urls),
    )
    with _get_store(req.config.db_path) as store:
        report = run_daily(user_id=user["id"], cfg=cfg, store=store, day=req.day)
    return report.as_dict()


@router.post("/daily/auto", summary="Auto-run daily session for the current user")
def run_daily_auto(
    user: dict = CurrentUser,
    db_path: str = str(_DEFAULT_DB),
    daily_budget: float = 100.0,
    target_pct: float = 10.0,
) -> dict:
    cfg = PortalConfig(
        daily_budget=daily_budget,
        monthly_target_pct=target_pct,
    )
    with _get_store(db_path) as store:
        report = run_daily(user_id=user["id"], cfg=cfg, store=store)
    return report.as_dict()


# ---- Recommendations & trades ----

@router.get("/recommendations/{day}", summary="List recommendations for a given day")
def recommendations(
    day: date,
    user: dict = CurrentUser,
    db_path: str = str(_DEFAULT_DB),
) -> list[dict]:
    with _get_store(db_path) as store:
        return store.recommendations_for_day(user_id=user["id"], day=day)


@router.get("/trades/{year_month}", summary="List trades for a given YYYY-MM month")
def trades(
    year_month: str,
    user: dict = CurrentUser,
    db_path: str = str(_DEFAULT_DB),
) -> list[dict]:
    with _get_store(db_path) as store:
        return store.trades_in_month(user_id=user["id"], year_month=year_month)


@router.get("/daily-report/{day}", summary="Full daily report: recommendations + trades + P&L")
def daily_report(
    day: date,
    user: dict = CurrentUser,
    db_path: str = str(_DEFAULT_DB),
) -> dict:
    with _get_store(db_path) as store:
        recs = store.recommendations_for_day(user_id=user["id"], day=day)
        trades = [
            t for t in store.trades_in_month(user_id=user["id"], year_month=day.strftime("%Y-%m"))
            if t["day"] == day.isoformat()
        ]
        total_pnl = sum(float(t["pnl"] or 0) for t in trades)
        return {
            "day": day.isoformat(),
            "user_id": user["id"],
            "username": user["username"],
            "recommendations": recs,
            "trades": trades,
            "trade_count": len(trades),
            "realized_pnl_day": total_pnl,
            "disclaimer": "Paper trading only. P&L includes realized sell trades for the day.",
        }


@router.get("/trades", summary="Recent paper trades for current user (optional month filter)")
def trades_recent(
    user: dict = CurrentUser,
    year_month: Optional[str] = None,
    db_path: str = str(_DEFAULT_DB),
    limit: int = 50,
) -> list[dict]:
    ym = year_month or date.today().strftime("%Y-%m")
    with _get_store(db_path) as store:
        rows = store.trades_in_month(user_id=user["id"], year_month=ym)
    return rows[-max(1, min(limit, 500)) :]


# ---- Performance ----

@router.get("/monthly/{year_month}", summary="Monthly performance vs aspirational target")
def monthly(
    year_month: str,
    user: dict = CurrentUser,
    db_path: str = str(_DEFAULT_DB),
    daily_budget: float = 100.0,
    target_pct: float = 10.0,
) -> dict:
    with _get_store(db_path) as store:
        realized = store.realized_pnl_in_month(user_id=user["id"], year_month=year_month)
        days_run = store.days_run_in_month(user_id=user["id"], year_month=year_month)
        sell_count, win_count = store.sell_trade_stats(user_id=user["id"], year_month=year_month)
        capital = store.capital_added_in_month(
            user_id=user["id"], year_month=year_month, daily_budget=daily_budget
        )
        state = store.load_broker_state(user_id=user["id"])
        equity = 0.0
        cash = 0.0
        if state:
            cash = float(state["cash"])
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
    user: dict = CurrentUser,
    db_path: str = str(_DEFAULT_DB),
    daily_budget: float = 100.0,
    target_pct: float = 10.0,
) -> dict:
    return monthly(year_month, user=user, db_path=db_path, daily_budget=daily_budget, target_pct=target_pct)


# ---- Paper / test trading ----

@router.get("/portfolio", summary="Current paper (test) portfolio for the current user")
def get_portfolio(
    user: dict = CurrentUser,
    db_path: str = str(_DEFAULT_DB),
) -> dict:
    with _get_store(db_path) as store:
        return portfolio_snapshot(store, user_id=user["id"])


@router.post("/test-trade", summary="Execute a single paper/test trade for the current user")
def test_trade(
    req: PaperTradeRequest,
    user: dict = CurrentUser,
) -> dict:
    try:
        with _get_store(req.db_path) as store:
            return execute_test_trade(store, user_id=user["id"], req=req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/paper/reset", summary="Reset paper account cash/positions for the current user")
def paper_reset(
    req: ResetPaperRequest = Body(default_factory=ResetPaperRequest),
    user: dict = CurrentUser,
) -> dict:
    with _get_store(req.db_path) as store:
        return reset_paper_account(store, user_id=user["id"], starting_cash=req.starting_cash)


# ---- Accuracy / personas / universes ----

from wealthsimple_agent.market.yfinance_provider import fetch_daily_bars
from wealthsimple_agent.strategy.accuracy import measure_accuracy
from wealthsimple_agent.strategy.personas import gather_opinions
from wealthsimple_agent.strategy.universes import list_presets, resolve_universe


@router.get("/universes", summary="List available universe presets and sizes")
def universes() -> dict:
    return {"presets": list_presets()}


@router.get("/accuracy/{ticker}", summary="Measured historical hit-rate for the signal engine")
def accuracy(
    ticker: str,
    horizon_days: int = 5,
    threshold_pct: float = 0.01,
    lookback_days: int = 180,
) -> dict:
    t = ticker.strip().upper()
    bars = fetch_daily_bars([t], lookback_days=lookback_days).get(t, [])
    if not bars or len(bars) < 50:
        return {
            "ticker": t,
            "samples": 0,
            "hit_rate": 0.0,
            "disclaimer": "Not enough history to measure accuracy yet.",
        }
    rep = measure_accuracy(
        bars=bars,
        horizon_days=horizon_days,
        threshold_pct=threshold_pct,
        min_lookback=40,
    )
    return rep.__dict__


@router.get("/personas/{ticker}", summary="Analyst & market-driver persona opinions for a ticker")
def personas(
    ticker: str,
    lookback_days: int = 90,
) -> dict:
    t = ticker.strip().upper()
    bars = fetch_daily_bars([t], lookback_days=lookback_days).get(t, [])
    if not bars or len(bars) < 30:
        return {
            "ticker": t,
            "opinions": [],
            "disclaimer": "Not enough history to gather persona opinions yet.",
        }
    opinions = gather_opinions(ticker=t, bars=bars, news=[])
    return {
        "ticker": t,
        "opinions": [op.as_dict() for op in opinions],
        "disclaimer": (
            "Personas are stylized interpretations of price/volume/news factors. "
            "They do not replace real fundamental analysis."
        ),
    }
