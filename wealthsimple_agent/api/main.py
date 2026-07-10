from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field

from wealthsimple_agent.config import get_settings
from wealthsimple_agent.engine import AgentDependencies, build_order_intents, build_signals, empty_portfolio
from wealthsimple_agent.fees import FeeModel
from wealthsimple_agent.market.yfinance_provider import fetch_daily_bars, latest_close
from wealthsimple_agent.news.rss import fetch_rss
from wealthsimple_agent.risk import RiskLimits
from wealthsimple_agent.portal.router import router as portal_router


app = FastAPI(title="Wealthsimple Trading Agent (Signals)", version="0.1.0")
app.include_router(portal_router)


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

