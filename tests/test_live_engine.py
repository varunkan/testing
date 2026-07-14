"""Tests for the self-healing live engine and one-click execution helpers."""

import asyncio
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from wealthsimple_agent.market.live import LiveQuote, is_market_hours
from wealthsimple_agent.models import PriceBar
from wealthsimple_agent.portal.live_engine import LiveEngine
from wealthsimple_agent.portal.paper_trading import PaperTradeRequest, execute_test_trade
from wealthsimple_agent.portal.store import Store


def _bars(ticker: str, start: date, days: int, closes: list[float]) -> list[PriceBar]:
    out: list[PriceBar] = []
    for i in range(days):
        d = start + timedelta(days=i)
        c = closes[i] if i < len(closes) else closes[-1]
        out.append(
            PriceBar(
                ticker=ticker, day=d, open=c, high=c * 1.01, low=c * 0.99, close=c, volume=1_000_000
            )
        )
    return out


def _fake_bars_fetcher(bars_map):
    def fetch(tickers, *, lookback_days=90):
        return {t: bars_map.get(t, []) for t in tickers}

    return fetch


def _fake_quotes_fetcher(prices):
    def fetch(tickers):
        now = datetime.now(tz=timezone.utc)
        return {
            t: LiveQuote(ticker=t, price=prices[t], day_open=prices[t] * 0.99, change_pct=0.01, as_of=now)
            for t in tickers
            if t in prices
        }

    return fetch


def test_scan_finds_buy_opportunities():
    day = date(2026, 7, 1)
    bars_map = {
        "UP": _bars("UP", day - timedelta(days=40), 41, [100 + i * 2 for i in range(41)]),
        "FLAT": _bars("FLAT", day - timedelta(days=40), 41, [200.0] * 41),
    }
    engine = LiveEngine(
        universe=["UP", "FLAT"],
        min_confidence=0.0,
        bars_fetcher=_fake_bars_fetcher(bars_map),
        quotes_fetcher=_fake_quotes_fetcher({"UP": 182.0, "FLAT": 200.0}),
    )
    count = engine.scan_once()
    assert count >= 1
    ops = engine.opportunities()
    assert any(o["ticker"] == "UP" and o["action"] == "buy" for o in ops)
    # Live quote price should be attached to the opportunity.
    up = next(o for o in ops if o["ticker"] == "UP")
    assert up["price"] == 182.0
    assert engine.health.scans_completed == 1
    assert engine.health.last_error is None


def test_engine_self_heals_after_failures():
    calls = {"n": 0}

    def failing_fetcher(tickers, *, lookback_days=90):
        calls["n"] += 1
        raise RuntimeError("data provider down")

    engine = LiveEngine(
        universe=["UP"],
        bars_fetcher=failing_fetcher,
        quotes_fetcher=_fake_quotes_fetcher({}),
        market_interval_s=0.01,
        offhours_interval_s=0.01,
    )

    async def run_briefly():
        task = asyncio.create_task(engine.run_forever())
        await asyncio.sleep(0.3)
        engine.stop()
        await asyncio.wait_for(task, timeout=10)

    asyncio.run(run_briefly())

    assert engine.health.consecutive_failures >= 1 or engine.health.self_heals >= 1
    assert engine.health.last_error is not None
    assert "data provider down" in engine.health.last_error
    assert engine.health.running is False  # exited cleanly on stop


def test_backoff_interval_grows_with_failures():
    engine = LiveEngine(universe=["UP"], market_interval_s=100, offhours_interval_s=100)
    engine.health.consecutive_failures = 0
    base = engine._next_interval()
    engine.health.consecutive_failures = 2
    assert engine._next_interval() == base * 4
    engine.health.consecutive_failures = 10  # capped at 4x
    assert engine._next_interval() == base * 4


def test_market_hours_helper():
    monday_open = datetime(2026, 7, 13, 15, 0, tzinfo=timezone.utc)
    monday_closed = datetime(2026, 7, 13, 22, 0, tzinfo=timezone.utc)
    saturday = datetime(2026, 7, 18, 15, 0, tzinfo=timezone.utc)
    assert is_market_hours(monday_open) is True
    assert is_market_hours(monday_closed) is False
    assert is_market_hours(saturday) is False


def test_one_click_trade_at_live_price(tmp_path: Path):
    db = tmp_path / "portal.db"
    with Store(db) as store:
        user = store.create_user(username="live_tester", password="password123")
        store.ensure_broker_state(user_id=user["id"], starting_cash=200.0)

        # One-click buy: $100 notional at live price 50 -> 2 shares.
        result = execute_test_trade(
            store,
            user_id=user["id"],
            req=PaperTradeRequest(ticker="UP", action="buy", quantity=2.0, price=50.0, fund_if_needed=False),
        )
        assert result["status"] == "filled"
        assert result["portfolio"]["positions"][0]["ticker"] == "UP"

        # One-click sell at a higher live price books profit.
        result2 = execute_test_trade(
            store,
            user_id=user["id"],
            req=PaperTradeRequest(ticker="UP", action="sell", quantity=2.0, price=60.0, fund_if_needed=False),
        )
        assert result2["status"] == "filled"
        assert result2["portfolio"]["realized_pnl"] > 0.0
