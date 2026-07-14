"""
Near-real-time quotes via yfinance intraday data.

yfinance provides 1-minute bars during market hours (typically delayed by up to
~15 minutes depending on the exchange). This is the closest to "live" that a
free, keyless data source offers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import yfinance as yf


@dataclass
class LiveQuote:
    ticker: str
    price: float
    day_open: Optional[float]
    change_pct: Optional[float]  # vs day open
    as_of: datetime

    def as_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "price": self.price,
            "day_open": self.day_open,
            "change_pct": self.change_pct,
            "as_of": self.as_of.isoformat(),
        }


def _last_valid(series) -> Optional[float]:
    try:
        s = series.dropna()
        if s.empty:
            return None
        return float(s.iloc[-1])
    except Exception:
        return None


def _first_valid(series) -> Optional[float]:
    try:
        s = series.dropna()
        if s.empty:
            return None
        return float(s.iloc[0])
    except Exception:
        return None


def fetch_live_quotes(tickers: list[str]) -> dict[str, LiveQuote]:
    """
    Batch-fetch the latest intraday price for each ticker.
    Falls back to the most recent daily close when intraday data is missing
    (e.g. market closed, thin symbols).
    """
    tickers = [t.strip().upper() for t in tickers if t and t.strip()]
    if not tickers:
        return {}

    now = datetime.now(tz=timezone.utc)
    out: dict[str, LiveQuote] = {}

    try:
        data = yf.download(
            tickers=tickers,
            period="1d",
            interval="1m",
            auto_adjust=False,
            group_by="ticker",
            progress=False,
            threads=True,
        )
    except Exception:
        data = None

    import pandas as pd

    def _series(df, ticker: str, col: str):
        try:
            if isinstance(df.columns, pd.MultiIndex):
                if ticker in df.columns.get_level_values(0):
                    return df[ticker][col]
                if col in df.columns.get_level_values(0):
                    return df[col][ticker]
                return None
            return df[col]
        except Exception:
            return None

    if data is not None and not getattr(data, "empty", True):
        for t in tickers:
            close = _series(data, t, "Close")
            opn = _series(data, t, "Open")
            if close is None:
                continue
            price = _last_valid(close)
            day_open = _first_valid(opn) if opn is not None else None
            if price is None or price <= 0:
                continue
            change = (price - day_open) / day_open if day_open else None
            out[t] = LiveQuote(ticker=t, price=price, day_open=day_open, change_pct=change, as_of=now)

    # Fallback for tickers with no intraday data: last daily close.
    missing = [t for t in tickers if t not in out]
    if missing:
        try:
            daily = yf.download(
                tickers=missing,
                period="5d",
                interval="1d",
                auto_adjust=False,
                group_by="ticker",
                progress=False,
                threads=True,
            )
            if daily is not None and not getattr(daily, "empty", True):
                for t in missing:
                    close = _series(daily, t, "Close")
                    if close is None:
                        continue
                    price = _last_valid(close)
                    if price is None or price <= 0:
                        continue
                    out[t] = LiveQuote(ticker=t, price=price, day_open=None, change_pct=None, as_of=now)
        except Exception:
            pass

    return out


def is_market_hours(now: Optional[datetime] = None) -> bool:
    """
    Rough US/Canada equity market hours check: 13:30–20:00 UTC, Mon–Fri.
    (9:30am–4:00pm Eastern; ignores holidays and DST edge cases.)
    """
    now = now or datetime.now(tz=timezone.utc)
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    return 13 * 60 + 30 <= minutes < 20 * 60
