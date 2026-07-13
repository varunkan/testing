from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from wealthsimple_agent.models import Position


_SCHEMA = """
CREATE TABLE IF NOT EXISTS broker_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    cash REAL NOT NULL,
    realized_pnl REAL NOT NULL,
    positions_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT NOT NULL,
    ticker TEXT NOT NULL,
    action TEXT NOT NULL,
    confidence REAL NOT NULL,
    score REAL NOT NULL,
    quantity REAL NOT NULL,
    limit_price REAL,
    expected_edge REAL NOT NULL,
    estimated_fees REAL NOT NULL,
    rationale TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT NOT NULL,
    ts TEXT NOT NULL,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL,
    qty REAL NOT NULL,
    px REAL NOT NULL,
    fees REAL NOT NULL,
    pnl REAL
);

CREATE INDEX IF NOT EXISTS idx_recommendations_day ON recommendations(day);
CREATE INDEX IF NOT EXISTS idx_trades_day ON trades(day);
"""


class Store:
    """
    SQLite-backed persistence for the portal.
    Stores broker state, daily recommendations, and executed trades.
    """

    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- broker state ----
    def save_broker_state(self, *, cash: float, realized_pnl: float, positions: list[Position]) -> None:
        payload = [
            {
                "ticker": p.ticker,
                "quantity": p.quantity,
                "avg_price": p.avg_price,
                "opened_day": p.opened_day.isoformat() if p.opened_day else None,
            }
            for p in positions
        ]
        self._conn.execute(
            """
            INSERT INTO broker_state (id, cash, realized_pnl, positions_json, updated_at)
            VALUES (1, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                cash=excluded.cash,
                realized_pnl=excluded.realized_pnl,
                positions_json=excluded.positions_json,
                updated_at=excluded.updated_at
            """,
            (float(cash), float(realized_pnl), json.dumps(payload), datetime.now(tz=timezone.utc).isoformat()),
        )
        self._conn.commit()

    def load_broker_state(self) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT cash, realized_pnl, positions_json FROM broker_state WHERE id = 1"
        ).fetchone()
        if not row:
            return None
        positions = [Position(**p) for p in json.loads(row["positions_json"])]
        return {
            "cash": float(row["cash"]),
            "realized_pnl": float(row["realized_pnl"]),
            "positions": positions,
        }

    # ---- recommendations ----
    def save_recommendation(self, *, day: date, rec: dict) -> None:
        self._conn.execute(
            """
            INSERT INTO recommendations
            (day, ticker, action, confidence, score, quantity, limit_price, expected_edge, estimated_fees, rationale, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                day.isoformat(),
                rec["ticker"],
                rec["action"],
                float(rec["confidence"]),
                float(rec["score"]),
                float(rec["quantity"]),
                rec.get("limit_price"),
                float(rec["expected_edge"]),
                float(rec["estimated_fees"]),
                rec["rationale"],
                rec["reason"],
                datetime.now(tz=timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()

    def recommendations_for_day(self, *, day: date) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM recommendations WHERE day = ? ORDER BY id ASC", (day.isoformat(),)
        ).fetchall()
        return [dict(r) for r in rows]

    def days_run_in_month(self, *, year_month: str) -> int:
        rows = self._conn.execute(
            "SELECT DISTINCT day FROM recommendations WHERE substr(day, 1, 7) = ?", (year_month,)
        ).fetchall()
        return len(rows)

    # ---- trades ----
    def save_trade(self, *, day: date, trade: dict) -> None:
        self._conn.execute(
            """
            INSERT INTO trades (day, ts, ticker, side, qty, px, fees, pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                day.isoformat(),
                trade.get("ts"),
                trade["ticker"],
                trade["side"],
                float(trade["qty"]),
                float(trade["px"]),
                float(trade["fees"]),
                float(trade["pnl"]) if trade.get("pnl") is not None else None,
            ),
        )
        self._conn.commit()

    def trades_in_month(self, *, year_month: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM trades WHERE substr(day, 1, 7) = ? ORDER BY id ASC", (year_month,)
        ).fetchall()
        return [dict(r) for r in rows]

    def realized_pnl_in_month(self, *, year_month: str) -> float:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(pnl), 0.0) AS total FROM trades WHERE substr(day, 1, 7) = ? AND side = 'sell'",
            (year_month,),
        ).fetchone()
        return float(row["total"])

    def sell_trade_stats(self, *, year_month: str) -> tuple[int, int]:
        """Returns (sell_trades_count, winning_sells_count)."""
        rows = self._conn.execute(
            "SELECT pnl FROM trades WHERE substr(day, 1, 7) = ? AND side = 'sell'",
            (year_month,),
        ).fetchall()
        total = len(rows)
        wins = sum(1 for r in rows if r["pnl"] is not None and float(r["pnl"]) > 0)
        return total, wins

    def capital_added_in_month(self, *, year_month: str, daily_budget: float) -> float:
        """Approximate capital deployed = daily_budget × distinct days with recommendations."""
        return float(daily_budget) * float(self.days_run_in_month(year_month=year_month))
