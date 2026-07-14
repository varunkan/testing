from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import bcrypt

from wealthsimple_agent.models import Position


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    api_key TEXT NOT NULL UNIQUE,
    auto_invest INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS broker_state (
    user_id INTEGER PRIMARY KEY,
    cash REAL NOT NULL,
    realized_pnl REAL NOT NULL,
    positions_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
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
    persona_opinions_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    day TEXT NOT NULL,
    ts TEXT NOT NULL,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL,
    qty REAL NOT NULL,
    px REAL NOT NULL,
    fees REAL NOT NULL,
    pnl REAL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS deposits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    day TEXT NOT NULL,
    amount REAL NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_recommendations_user_day ON recommendations(user_id, day);
CREATE INDEX IF NOT EXISTS idx_trades_user_day ON trades(user_id, day);
CREATE INDEX IF NOT EXISTS idx_trades_user_month ON trades(user_id, substr(day, 1, 7));
CREATE INDEX IF NOT EXISTS idx_deposits_user_month ON deposits(user_id, substr(day, 1, 7));
"""


class Store:
    """
    SQLite-backed persistence for the portal, now multi-user.
    Each user has their own broker state, recommendations, and trades.
    """

    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._migrate_legacy_data()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- migration ----
    def _migrate_legacy_data(self) -> None:
        """If old single-user tables exist, migrate data to a default user."""
        # Check if old tables exist without user_id column.
        old_tables = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('broker_state', 'recommendations', 'trades')"
        ).fetchall()
        if not old_tables:
            return

        # If the new multi-user schema is already in place, do nothing.
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(broker_state)")}
        if "user_id" in cols:
            return

        # Legacy schema detected. Rename old tables, recreate schema, and migrate.
        self._conn.execute("ALTER TABLE broker_state RENAME TO broker_state_old")
        self._conn.execute("ALTER TABLE recommendations RENAME TO recommendations_old")
        self._conn.execute("ALTER TABLE trades RENAME TO trades_old")
        self._conn.commit()

        self._conn.executescript(_SCHEMA)
        self._conn.commit()

        default_api_key = "legacy-default-" + secrets.token_urlsafe(16)
        self._conn.execute(
            "INSERT INTO users (username, password_hash, api_key, auto_invest, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                "legacy_user",
                _hash_password(secrets.token_urlsafe(16)),
                default_api_key,
                0,
                datetime.now(tz=timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()
        user_id = self._conn.execute(
            "SELECT id FROM users WHERE username = ?", ("legacy_user",)
        ).fetchone()["id"]

        self._conn.execute(
            "INSERT INTO broker_state (user_id, cash, realized_pnl, positions_json, updated_at) "
            "SELECT ?, cash, realized_pnl, positions_json, updated_at FROM broker_state_old",
            (user_id,),
        )
        self._conn.execute(
            "INSERT INTO recommendations (user_id, day, ticker, action, confidence, score, quantity, limit_price, expected_edge, estimated_fees, rationale, reason, created_at) "
            "SELECT ?, day, ticker, action, confidence, score, quantity, limit_price, expected_edge, estimated_fees, rationale, reason, created_at FROM recommendations_old",
            (user_id,),
        )
        self._conn.execute(
            "INSERT INTO trades (user_id, day, ts, ticker, side, qty, px, fees, pnl, created_at) "
            "SELECT ?, day, ts, ticker, side, qty, px, fees, pnl, created_at FROM trades_old",
            (user_id,),
        )
        self._conn.commit()

    # ---- users ----
    def create_user(self, *, username: str, password: str) -> dict:
        if self._conn.execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)
        ).fetchone():
            raise ValueError("Username already exists")
        api_key = "fd_" + secrets.token_urlsafe(32)
        self._conn.execute(
            "INSERT INTO users (username, password_hash, api_key, auto_invest, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                username,
                _hash_password(password),
                api_key,
                0,
                datetime.now(tz=timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT id, username, api_key, auto_invest, created_at FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        return {
            "id": row["id"],
            "username": row["username"],
            "api_key": row["api_key"],
            "auto_invest": bool(row["auto_invest"]),
            "created_at": row["created_at"],
        }

    def authenticate_user(self, *, username: str, password: str) -> dict:
        row = self._conn.execute(
            "SELECT id, username, password_hash, api_key, auto_invest, created_at FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if not row or not _verify_password(password, row["password_hash"]):
            raise ValueError("Invalid username or password")
        return {
            "id": row["id"],
            "username": row["username"],
            "api_key": row["api_key"],
            "auto_invest": bool(row["auto_invest"]),
            "created_at": row["created_at"],
        }

    def get_user_by_api_key(self, *, api_key: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, username, api_key, auto_invest, created_at FROM users WHERE api_key = ?",
            (api_key,),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "username": row["username"],
            "api_key": row["api_key"],
            "auto_invest": bool(row["auto_invest"]),
            "created_at": row["created_at"],
        }

    def set_auto_invest(self, *, user_id: int, auto_invest: bool) -> None:
        self._conn.execute(
            "UPDATE users SET auto_invest = ? WHERE id = ?",
            (1 if auto_invest else 0, user_id),
        )
        self._conn.commit()

    # ---- broker state ----
    def save_broker_state(self, *, user_id: int, cash: float, realized_pnl: float, positions: list[Position]) -> None:
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
            INSERT INTO broker_state (user_id, cash, realized_pnl, positions_json, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                cash=excluded.cash,
                realized_pnl=excluded.realized_pnl,
                positions_json=excluded.positions_json,
                updated_at=excluded.updated_at
            """,
            (user_id, float(cash), float(realized_pnl), json.dumps(payload), datetime.now(tz=timezone.utc).isoformat()),
        )
        self._conn.commit()

    def load_broker_state(self, *, user_id: int) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT cash, realized_pnl, positions_json FROM broker_state WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            return None
        positions = [Position(**p) for p in json.loads(row["positions_json"])]
        return {
            "cash": float(row["cash"]),
            "realized_pnl": float(row["realized_pnl"]),
            "positions": positions,
        }

    def ensure_broker_state(self, *, user_id: int, starting_cash: float = 0.0) -> dict:
        state = self.load_broker_state(user_id=user_id)
        if state:
            return state
        self.save_broker_state(
            user_id=user_id,
            cash=starting_cash,
            realized_pnl=0.0,
            positions=[],
        )
        return self.load_broker_state(user_id=user_id)

    # ---- recommendations ----
    def save_recommendation(self, *, user_id: int, day: date, rec: dict) -> None:
        self._conn.execute(
            """
            INSERT INTO recommendations
            (user_id, day, ticker, action, confidence, score, quantity, limit_price, expected_edge, estimated_fees, rationale, reason, persona_opinions_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
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
                json.dumps(rec.get("persona_opinions")) if rec.get("persona_opinions") else None,
                datetime.now(tz=timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()

    def recommendations_for_day(self, *, user_id: int, day: date) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM recommendations WHERE user_id = ? AND day = ? ORDER BY id ASC",
            (user_id, day.isoformat()),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if d.get("persona_opinions_json"):
                d["persona_opinions"] = json.loads(d["persona_opinions_json"])
                del d["persona_opinions_json"]
            out.append(d)
        return out

    def days_run_in_month(self, *, user_id: int, year_month: str) -> int:
        rows = self._conn.execute(
            "SELECT DISTINCT day FROM recommendations WHERE user_id = ? AND substr(day, 1, 7) = ?",
            (user_id, year_month),
        ).fetchall()
        return len(rows)

    # ---- trades ----
    def save_trade(self, *, user_id: int, day: date, trade: dict) -> None:
        self._conn.execute(
            """
            INSERT INTO trades (user_id, day, ts, ticker, side, qty, px, fees, pnl, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                day.isoformat(),
                trade.get("ts") or datetime.now(tz=timezone.utc).isoformat(),
                trade["ticker"],
                trade["side"],
                float(trade["qty"]),
                float(trade["px"]),
                float(trade["fees"]),
                float(trade["pnl"]) if trade.get("pnl") is not None else None,
                datetime.now(tz=timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()

    def trades_in_month(self, *, user_id: int, year_month: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM trades WHERE user_id = ? AND substr(day, 1, 7) = ? ORDER BY id ASC",
            (user_id, year_month),
        ).fetchall()
        return [dict(r) for r in rows]

    def realized_pnl_in_month(self, *, user_id: int, year_month: str) -> float:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(pnl), 0.0) AS total FROM trades WHERE user_id = ? AND substr(day, 1, 7) = ? AND side = 'sell'",
            (user_id, year_month),
        ).fetchone()
        return float(row["total"])

    def sell_trade_stats(self, *, user_id: int, year_month: str) -> tuple[int, int]:
        """Returns (sell_trades_count, winning_sells_count)."""
        rows = self._conn.execute(
            "SELECT pnl FROM trades WHERE user_id = ? AND substr(day, 1, 7) = ? AND side = 'sell'",
            (user_id, year_month),
        ).fetchall()
        total = len(rows)
        wins = sum(1 for r in rows if r["pnl"] is not None and float(r["pnl"]) > 0)
        return total, wins

    def capital_added_in_month(self, *, user_id: int, year_month: str, daily_budget: float) -> float:
        """Capital deployed = daily_budget × days run (auto flow) + explicit morning deposits."""
        auto = float(daily_budget) * float(self.days_run_in_month(user_id=user_id, year_month=year_month))
        return auto + self.deposits_in_month(user_id=user_id, year_month=year_month)

    # ---- deposits ----
    def add_deposit(self, *, user_id: int, day: date, amount: float) -> None:
        self._conn.execute(
            "INSERT INTO deposits (user_id, day, amount, created_at) VALUES (?, ?, ?, ?)",
            (user_id, day.isoformat(), float(amount), datetime.now(tz=timezone.utc).isoformat()),
        )
        self._conn.commit()

    def deposits_in_month(self, *, user_id: int, year_month: str) -> float:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(amount), 0.0) AS total FROM deposits WHERE user_id = ? AND substr(day, 1, 7) = ?",
            (user_id, year_month),
        ).fetchone()
        return float(row["total"])
