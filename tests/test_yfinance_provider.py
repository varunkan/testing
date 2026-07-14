from datetime import date, timedelta

import pandas as pd
import pytest

from wealthsimple_agent.market.yfinance_provider import _get, fetch_daily_bars, latest_close
from wealthsimple_agent.models import PriceBar


def test_get_flat_row():
    row = pd.Series({"Open": 100.0, "High": 102.0, "Low": 99.0, "Close": 101.0, "Volume": 1_000_000})
    assert _get(row, "Close") == 101.0
    assert _get(row, "Volume") == 1_000_000


def test_get_multiindex_row():
    row = pd.Series({
        ("Open", "AAPL"): 100.0,
        ("High", "AAPL"): 102.0,
        ("Low", "AAPL"): 99.0,
        ("Close", "AAPL"): 101.0,
        ("Volume", "AAPL"): 1_000_000,
    })
    assert _get(row, "Close", ticker="AAPL") == 101.0
    assert _get(row, "Close") == 101.0


def test_get_missing_key_raises():
    row = pd.Series({"Open": 100.0})
    with pytest.raises(KeyError):
        _get(row, "Close")


def test_latest_close():
    bars = [
        PriceBar(ticker="AAPL", day=date(2026, 1, 1), open=100, high=101, low=99, close=100, volume=1000),
        PriceBar(ticker="AAPL", day=date(2026, 1, 2), open=101, high=102, low=100, close=101, volume=1000),
    ]
    assert latest_close(bars) == 101.0
    assert latest_close([]) is None


def test_fetch_daily_bars_empty():
    assert fetch_daily_bars([]) == {}


def test_fetch_daily_bars_invalid_ticker_stripped():
    # yfinance may fail or return empty for fake tickers; function should not crash.
    out = fetch_daily_bars(["   ", "INVALID_TICKER_XYZ"])
    assert "INVALID_TICKER_XYZ" in out
    # Bars may be empty because the ticker is fake, but key is present.
