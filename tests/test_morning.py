"""Tests for the morning briefing workflow: deposit -> plan -> approve -> execute."""

from datetime import date, timedelta
from pathlib import Path

from wealthsimple_agent.models import PriceBar
from wealthsimple_agent.portal.morning import build_morning_plan, execute_morning_plan
from wealthsimple_agent.portal.store import Store


def _bars(ticker: str, start: date, days: int, closes: list[float]) -> list[PriceBar]:
    out: list[PriceBar] = []
    for i in range(days):
        d = start + timedelta(days=i)
        c = closes[i] if i < len(closes) else closes[-1]
        out.append(
            PriceBar(
                ticker=ticker,
                day=d,
                open=c,
                high=c * 1.01,
                low=c * 0.99,
                close=c,
                volume=1_000_000,
            )
        )
    return out


def _user_id(store: Store) -> int:
    user = store.create_user(username="morning_tester", password="password123")
    return user["id"]


def test_morning_plan_deposits_and_proposes_buys(tmp_path: Path):
    db = tmp_path / "portal.db"
    day = date(2026, 7, 1)
    bars = {
        "AAPL": _bars("AAPL", day - timedelta(days=30), 31, [100 + i * 2 for i in range(31)]),
        "MSFT": _bars("MSFT", day - timedelta(days=30), 31, [300 - i * 0.5 for i in range(31)]),
    }

    with Store(db) as store:
        user_id = _user_id(store)
        plan = build_morning_plan(
            store,
            user_id=user_id,
            deposit=200.0,
            universe=["AAPL", "MSFT"],
            min_confidence_to_buy=0.0,
            day=day,
            bars_by_ticker=bars,
            news_by_ticker={"AAPL": [], "MSFT": []},
        )

        assert plan["deposit"] == 200.0
        assert plan["cash_after_deposit"] == 200.0
        # Uptrending AAPL should be proposed as a buy; nothing held yet, so no sells.
        assert plan["sells"] == []
        assert any(b["ticker"] == "AAPL" for b in plan["buys"])
        assert plan["goal"]["required_daily_growth_pct"] > 0.10

        # Deposit persists even before approving anything.
        state = store.load_broker_state(user_id=user_id)
        assert state["cash"] == 200.0
        assert store.deposits_in_month(user_id=user_id, year_month="2026-07") == 200.0


def test_morning_execute_fills_approved_items(tmp_path: Path):
    db = tmp_path / "portal.db"
    day = date(2026, 7, 1)

    with Store(db) as store:
        user_id = _user_id(store)
        store.ensure_broker_state(user_id=user_id, starting_cash=500.0)

        result = execute_morning_plan(
            store,
            user_id=user_id,
            items=[{"ticker": "AAPL", "action": "buy", "quantity": 2.0}],
            day=day,
            price_overrides={"AAPL": 100.0},
        )
        assert result["executed_count"] == 1
        assert result["portfolio"]["positions"][0]["ticker"] == "AAPL"
        assert result["portfolio"]["cash"] < 500.0

        # Now sell it at a profit via the same execute path.
        result2 = execute_morning_plan(
            store,
            user_id=user_id,
            items=[{"ticker": "AAPL", "action": "sell", "quantity": 2.0}],
            day=day + timedelta(days=1),
            price_overrides={"AAPL": 110.0},
        )
        assert result2["executed_count"] == 1
        assert result2["portfolio"]["positions"] == []
        assert result2["portfolio"]["realized_pnl"] > 0.0


def test_morning_plan_suggests_rotation_sell(tmp_path: Path):
    db = tmp_path / "portal.db"
    day = date(2026, 7, 10)

    # Held position: downtrending; universe candidate: strongly uptrending.
    bars = {
        "WEAK": _bars("WEAK", day - timedelta(days=30), 31, [100 - i * 1.5 for i in range(31)]),
        "STRONG": _bars("STRONG", day - timedelta(days=30), 31, [50 + i * 2 for i in range(31)]),
    }

    with Store(db) as store:
        user_id = _user_id(store)
        store.ensure_broker_state(user_id=user_id, starting_cash=100.0)
        # Buy WEAK a few days ago at a higher price than today's.
        execute_morning_plan(
            store,
            user_id=user_id,
            items=[{"ticker": "WEAK", "action": "buy", "quantity": 1.0}],
            day=day - timedelta(days=3),
            price_overrides={"WEAK": 80.0},
        )
        # Fund cash so a buy proposal is possible too.
        plan = build_morning_plan(
            store,
            user_id=user_id,
            deposit=100.0,
            universe=["STRONG"],
            min_confidence_to_buy=0.0,
            stop_loss_pct=0.02,
            day=day,
            bars_by_ticker=bars,
            news_by_ticker={"WEAK": [], "STRONG": []},
        )

        # WEAK is deep underwater (bought at 80, now ~55) -> stop-loss/rotation sell.
        assert plan["sells"], "Expected a sell proposal for the losing position"
        assert plan["sells"][0]["ticker"] == "WEAK"
        # STRONG should be proposed as a buy funded by deposit + sell proceeds.
        assert any(b["ticker"] == "STRONG" for b in plan["buys"])
        assert plan["investable_if_approved"] > plan["cash_after_deposit"]
