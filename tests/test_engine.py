from datetime import date, datetime, timezone

from wealthsimple_agent.config import Settings
from wealthsimple_agent.engine import AgentDependencies, build_order_intents, build_signals
from wealthsimple_agent.fees import FeeModel
from wealthsimple_agent.models import NewsItem, PortfolioSnapshot, PriceBar, Signal
from wealthsimple_agent.risk import RiskLimits


def test_signals_and_intents_happy_path():
    settings = Settings(
        min_confidence_to_trade=0.0,
        slippage_bps=0.0,
        fee_per_trade=0.0,
        fee_pct_notional=0.0,
        max_position_pct_of_equity=0.25,
    )
    deps = AgentDependencies(
        settings=settings,
        fee_model=FeeModel(),
        risk_limits=RiskLimits(max_position_pct_of_equity=0.25, per_trade_risk_pct=0.01, max_daily_loss_pct=0.03),
    )

    t = "AAPL"
    bars = []
    px = 100.0
    for i in range(30):
        px *= 1.015
        bars.append(
            PriceBar(
                ticker=t,
                day=date(2026, 1, 1 + i),
                open=px * 0.99,
                high=px * 1.02,
                low=px * 0.98,
                close=px,
                volume=1_000_000,
            )
        )
    bars_by_ticker = {t: bars}
    news_by_ticker = {t: [NewsItem(title="Strong earnings beat expectations")]}

    sigs = build_signals(tickers=[t], price_bars_by_ticker=bars_by_ticker, news_by_ticker=news_by_ticker, deps=deps)
    assert len(sigs) == 1
    assert sigs[0].ticker == t
    assert sigs[0].action == "buy"
    assert sigs[0].confidence > 0.4

    portfolio = PortfolioSnapshot(
        as_of=datetime.now(tz=timezone.utc),
        cash=10_000,
        equity=10_000,
        positions=[],
    )
    latest_px = {t: float(bars[-1].close)}
    intents = build_order_intents(signals=sigs, portfolio=portfolio, latest_price_by_ticker=latest_px, deps=deps)
    assert intents, "Expected at least one order intent for a strong upward move"
    assert intents[0].action == "buy"
    assert intents[0].quantity > 0


def test_sell_intent_requires_position():
    settings = Settings(min_confidence_to_trade=0.0, slippage_bps=0.0)
    deps = AgentDependencies(settings=settings, fee_model=FeeModel(), risk_limits=RiskLimits())

    sigs = [Signal(ticker="MSFT", action="sell", confidence=1.0, score=-1.0, rationale="forced")]

    portfolio = PortfolioSnapshot(
        as_of=datetime.now(tz=timezone.utc),
        cash=10_000,
        equity=10_000,
        positions=[],
    )
    intents = build_order_intents(
        signals=sigs, portfolio=portfolio, latest_price_by_ticker={"MSFT": 100.0}, deps=deps
    )
    assert intents == []

