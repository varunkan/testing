from pathlib import Path

from wealthsimple_agent.portal.paper_trading import (
    PaperTradeRequest,
    execute_test_trade,
    portfolio_snapshot,
    reset_paper_account,
)
from wealthsimple_agent.portal.store import Store


def test_paper_buy_sell_and_portfolio(tmp_path: Path):
    db = tmp_path / "paper.db"
    with Store(db) as store:
        reset = reset_paper_account(store, starting_cash=1_000.0)
        assert reset["cash"] == 1_000.0
        assert reset["positions"] == []

        buy = execute_test_trade(
            store,
            PaperTradeRequest(
                ticker="AAPL",
                action="buy",
                quantity=2.0,
                price=100.0,
                db_path=str(db),
                fund_if_needed=False,
            ),
        )
        assert buy["status"] == "filled"
        assert buy["trade"]["side"] == "buy"
        assert buy["trade"]["ticker"] == "AAPL"
        assert buy["portfolio"]["cash"] < 1_000.0
        assert any(p["ticker"] == "AAPL" for p in buy["portfolio"]["positions"])

        snap = portfolio_snapshot(store, price_overrides={"AAPL": 110.0})
        assert snap["mode"] == "paper"
        assert snap["equity"] > snap["cash"]

        sell = execute_test_trade(
            store,
            PaperTradeRequest(
                ticker="AAPL",
                action="sell",
                quantity=2.0,
                price=110.0,
                db_path=str(db),
            ),
        )
        assert sell["status"] == "filled"
        assert sell["trade"]["side"] == "sell"
        assert sell["trade"]["pnl"] is not None
        assert sell["trade"]["pnl"] > 0
        assert sell["portfolio"]["positions"] == []


def test_sell_without_position_fails(tmp_path: Path):
    db = tmp_path / "paper.db"
    with Store(db) as store:
        reset_paper_account(store, starting_cash=500.0)
        try:
            execute_test_trade(
                store,
                PaperTradeRequest(ticker="MSFT", action="sell", quantity=1.0, price=300.0, db_path=str(db)),
            )
            assert False, "expected ValueError"
        except ValueError as e:
            assert "not filled" in str(e).lower() or "hold" in str(e).lower()
