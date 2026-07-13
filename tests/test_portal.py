from datetime import date, timedelta
from pathlib import Path

from wealthsimple_agent.models import NewsItem, PriceBar
from wealthsimple_agent.portal.monthly import compute_monthly_progress
from wealthsimple_agent.portal.runner import PortalConfig, run_daily
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
    user = store.create_user(username=f"tester_{date.today().isoformat()}", password="password123")
    return user["id"]


def test_monthly_progress_math():
    # Double goal: 100% of (100*21) = $2100; $420 realized => 20% of goal, ROI on $700 capital = 60%
    p = compute_monthly_progress(
        year_month="2026-07",
        daily_budget=100.0,
        target_pct=1.0,
        planned_trading_days=21,
        realized_pnl=420.0,
        days_run=7,
        capital_invested=700.0,
        trades_count=10,
        winning_trades=6,
        equity=900.0,
        cash=200.0,
    )
    assert p.target_profit == 2100.0
    assert abs(p.progress_pct - 0.20) < 1e-9
    assert abs(p.roi_pct - 0.60) < 1e-9
    assert abs(p.win_rate - 0.60) < 1e-9
    assert p.as_dict()["goal_label"] == "1×"


def test_run_daily_persists_and_progresses(tmp_path: Path):
    db = tmp_path / "portal.db"
    cfg = PortalConfig(
        daily_budget=100.0,
        monthly_target_pct=1.0,
        take_profit_pct=0.10,  # high so we don't exit immediately
        stop_loss_pct=0.20,
        max_hold_days=10,
        max_new_buys_per_day=2,
        min_confidence_to_buy=0.0,  # accept any buy signal in the test
        universe=["AAPL", "MSFT"],
        rss_urls=[],
    )

    day = date(2026, 7, 1)
    # Strong uptrend on AAPL -> buy signal; flat/slight down on MSFT
    bars = {
        "AAPL": _bars("AAPL", day - timedelta(days=20), 21, [100 + i * 2 for i in range(21)]),
        "MSFT": _bars("MSFT", day - timedelta(days=20), 21, [300 - i * 0.5 for i in range(21)]),
    }
    news = {"AAPL": [NewsItem(title="Apple earnings beat expectations")], "MSFT": []}

    with Store(db) as store:
        user_id = _user_id(store)
        report = run_daily(
            user_id=user_id,
            cfg=cfg,
            store=store,
            day=day,
            bars_by_ticker=bars,
            news_by_ticker=news,
        )

    # Should have at least one buy recommendation within the $100 budget.
    assert report.budget_added == 100.0
    buys = [r for r in report.recommendations if r.action == "buy"]
    assert buys, "Expected at least one buy recommendation for an uptrending ticker"
    total_notional = sum(r.quantity * 100.0 for r in buys)  # rough notional check
    assert total_notional <= 105.0  # within budget + small tolerance

    assert report.monthly_progress["target_profit"] == 2100.0
    assert report.monthly_progress["target_pct"] == 1.0
    assert report.monthly_progress["days_run"] == 1
    assert "roi_pct" in report.monthly_progress
    assert "capital_invested" in report.monthly_progress

    # Persistence: a second run should reload broker state (no crash, fresh budget added).
    with Store(db) as store:
        report2 = run_daily(
            user_id=user_id,
            cfg=cfg,
            store=store,
            day=day + timedelta(days=1),
            bars_by_ticker=bars,
            news_by_ticker=news,
        )
    assert report2.monthly_progress["days_run"] == 2
    assert report2.monthly_progress["capital_invested"] == 200.0


def test_take_profit_exit_triggers_sell(tmp_path: Path):
    db = tmp_path / "portal.db"
    cfg = PortalConfig(
        daily_budget=100.0,
        take_profit_pct=0.03,
        stop_loss_pct=0.20,
        max_hold_days=10,
        max_new_buys_per_day=1,
        min_confidence_to_buy=0.0,
        universe=["AAPL"],
        rss_urls=[],
    )

    day0 = date(2026, 7, 1)
    # Day 0: uptrend -> buy near 140
    bars_day0 = {
        "AAPL": _bars("AAPL", day0 - timedelta(days=10), 11, [100 + i * 4 for i in range(11)]),
    }
    with Store(db) as store:
        user_id = _user_id(store)
        run_daily(
            user_id=user_id,
            cfg=cfg,
            store=store,
            day=day0,
            bars_by_ticker=bars_day0,
            news_by_ticker={"AAPL": []},
        )

    # Day 1: price jumps well above cost basis -> take-profit exit
    day1 = day0 + timedelta(days=1)
    bars_day1 = {
        "AAPL": _bars("AAPL", day0 - timedelta(days=10), 12, [100 + i * 4 for i in range(11)] + [160]),
    }
    with Store(db) as store:
        report = run_daily(
            user_id=user_id,
            cfg=cfg,
            store=store,
            day=day1,
            bars_by_ticker=bars_day1,
            news_by_ticker={"AAPL": []},
        )

    sells = [r for r in report.recommendations if r.action == "sell"]
    assert sells, "Expected a take-profit sell recommendation"
    assert "take-profit" in sells[0].reason
    # Realized P&L should be positive and reflected in monthly progress.
    assert report.monthly_progress["realized_pnl"] > 0.0


def test_user_accounts_and_persistence(tmp_path: Path):
    db = tmp_path / "portal.db"
    with Store(db) as store:
        u1 = store.create_user(username="alice", password="secret123")
        u2 = store.create_user(username="bob", password="secret456")

        # Each user should have independent broker state.
        store.ensure_broker_state(user_id=u1["id"], starting_cash=1000.0)
        store.ensure_broker_state(user_id=u2["id"], starting_cash=500.0)

        s1 = store.load_broker_state(user_id=u1["id"])
        s2 = store.load_broker_state(user_id=u2["id"])
        assert s1["cash"] == 1000.0
        assert s2["cash"] == 500.0

        # Auth should work
        logged_in = store.authenticate_user(username="alice", password="secret123")
        assert logged_in["api_key"] == u1["api_key"]

        # Wrong password should fail
        try:
            store.authenticate_user(username="alice", password="wrong")
            assert False, "expected auth failure"
        except ValueError:
            pass
