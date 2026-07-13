from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from wealthsimple_agent.config import get_settings
from wealthsimple_agent.engine import AgentDependencies, build_order_intents, build_signals, empty_portfolio
from wealthsimple_agent.fees import FeeModel
from wealthsimple_agent.market.yfinance_provider import fetch_daily_bars, latest_close
from wealthsimple_agent.news.rss import fetch_rss
from wealthsimple_agent.risk import RiskLimits
from wealthsimple_agent.portal.router import router as portal_router


_WEB_DIR = Path(__file__).resolve().parents[1] / "web"
_STATIC_DIR = _WEB_DIR / "static"

app = FastAPI(title="Forge Desk — Trading Recommendation Portal", version="0.2.0")
app.include_router(portal_router)

if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
def portal_home() -> FileResponse:
    return FileResponse(_WEB_DIR / "index.html")


class SignalsRequest(BaseModel):
    tickers: list[str] = Field(min_length=1)
    lookback_days: Optional[int] = Field(default=None, ge=5, le=365)
    rss_urls: list[str] = Field(default_factory=list)
    starting_cash: float = Field(default=10_000.0, gt=0)


class SignalsResponse(BaseModel):
    as_of: datetime
    signals: list
    order_intents: list


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/signals", response_model=SignalsResponse)
def signals(req: SignalsRequest) -> SignalsResponse:
    settings = get_settings()
    lookback = req.lookback_days or settings.default_lookback_days

    tickers = [t.strip().upper() for t in req.tickers if t and t.strip()]
    bars_by_ticker = fetch_daily_bars(tickers, lookback_days=lookback)

    news_items = []
    for url in req.rss_urls:
        try:
            news_items.extend(fetch_rss(url))
        except Exception:
            continue
    # MVP: apply same news bucket to all tickers unless user provides ticker-specific feeds.
    news_by_ticker = {t: news_items for t in tickers}

    deps = AgentDependencies(
        settings=settings,
        fee_model=FeeModel(fee_per_trade=settings.fee_per_trade, fee_pct_notional=settings.fee_pct_notional),
        risk_limits=RiskLimits(
            max_position_pct_of_equity=settings.max_position_pct_of_equity,
            per_trade_risk_pct=settings.per_trade_risk_pct,
            max_daily_loss_pct=settings.max_daily_loss_pct,
        ),
    )

    sigs = build_signals(
        tickers=tickers,
        price_bars_by_ticker=bars_by_ticker,
        news_by_ticker=news_by_ticker,
        deps=deps,
    )
    latest_px = {t: latest_close(bars_by_ticker.get(t, [])) for t in tickers}
    latest_px = {k: v for k, v in latest_px.items() if v is not None}

    portfolio = empty_portfolio(starting_cash=req.starting_cash)
    intents = build_order_intents(signals=sigs, portfolio=portfolio, latest_price_by_ticker=latest_px, deps=deps)

    now = datetime.now(tz=timezone.utc)
    return SignalsResponse(
        as_of=now,
        signals=[s.model_dump() for s in sigs],
        order_intents=[i.model_dump() for i in intents],
    )

