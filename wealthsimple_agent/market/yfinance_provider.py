from __future__ import annotations

from datetime import date, timedelta

import yfinance as yf

from wealthsimple_agent.models import PriceBar


def fetch_daily_bars(
    tickers: list[str],
    *,
    lookback_days: int = 30,
) -> dict[str, list[PriceBar]]:
    """
    Best-effort daily OHLCV via yfinance.
    """
    tickers = [t.strip().upper() for t in tickers if t and t.strip()]
    if not tickers:
        return {}

    start = date.today() - timedelta(days=int(lookback_days) * 2)  # buffer for weekends/holidays
    data = yf.download(
        tickers=tickers,
        start=start.isoformat(),
        auto_adjust=False,
        group_by="ticker",
        progress=False,
        threads=True,
    )

    out: dict[str, list[PriceBar]] = {t: [] for t in tickers}

    # yfinance returns different shapes for 1 vs many tickers.
    if len(tickers) == 1:
        t = tickers[0]
        df = data
        for idx, row in df.tail(lookback_days).iterrows():
            day = idx.date()
            out[t].append(
                PriceBar(
                    ticker=t,
                    day=day,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row.get("Volume")) if "Volume" in row and row.get("Volume") is not None else None,
                )
            )
        return out

    for t in tickers:
        if t not in data.columns.get_level_values(0):
            continue
        df = data[t]
        for idx, row in df.tail(lookback_days).iterrows():
            out[t].append(
                PriceBar(
                    ticker=t,
                    day=idx.date(),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row.get("Volume")) if "Volume" in row and row.get("Volume") is not None else None,
                )
            )
    return out


def latest_close(bars: list[PriceBar]) -> float | None:
    if not bars:
        return None
    return float(bars[-1].close)

