from __future__ import annotations

from datetime import date, timedelta

import yfinance as yf

from wealthsimple_agent.models import PriceBar


def _get(row, key: str, ticker: str | None = None) -> float:
    """Robustly extract an OHLCV value from a yfinance row (handles MultiIndex + flat)."""
    if ticker is not None:
        try:
            return float(row[(key, ticker)])
        except (KeyError, TypeError, ValueError):
            pass
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        pass
    # Fallback: scan index for an exact match (string or tuple containing key)
    idx = list(row.index) if hasattr(row, "index") else []
    for label in idx:
        try:
            if isinstance(label, tuple):
                if label and label[0] == key:
                    return float(row[label])
            elif label == key:
                return float(row[label])
        except (TypeError, ValueError):
            continue
    raise KeyError(key)


def fetch_daily_bars(
    tickers: list[str],
    *,
    lookback_days: int = 30,
) -> dict[str, list[PriceBar]]:
    """
    Best-effort daily OHLCV via yfinance. Robust to single/multi-ticker shapes.
    """
    tickers = [t.strip().upper() for t in tickers if t and t.strip()]
    if not tickers:
        return {}

    start = date.today() - timedelta(days=int(lookback_days) * 2)
    data = yf.download(
        tickers=tickers,
        start=start.isoformat(),
        auto_adjust=False,
        group_by="ticker",
        progress=False,
        threads=True,
    )
    if data is None or data.empty:
        return {t: [] for t in tickers}

    out: dict[str, list[PriceBar]] = {t: [] for t in tickers}
    is_multi = len(tickers) > 1
    multi_index = isinstance(data.columns, __import__("pandas").MultiIndex)

    def _volume(row, ticker: str | None) -> float | None:
        try:
            v = _get(row, "Volume", ticker)
            return float(v)
        except (KeyError, TypeError, ValueError):
            return None

    if is_multi or multi_index:
        for t in tickers:
            try:
                df = data[t] if t in data.columns.get_level_values(0) else None
            except Exception:
                df = None
            if df is None or getattr(df, "empty", True):
                continue
            for idx, row in df.tail(lookback_days).iterrows():
                try:
                    out[t].append(
                        PriceBar(
                            ticker=t,
                            day=idx.date(),
                            open=_get(row, "Open", None),
                            high=_get(row, "High", None),
                            low=_get(row, "Low", None),
                            close=_get(row, "Close", None),
                            volume=_volume(row, None),
                        )
                    )
                except (KeyError, TypeError, ValueError):
                    continue
        return out

    # Single ticker, flat columns
    t = tickers[0]
    for idx, row in data.tail(lookback_days).iterrows():
        try:
            out[t].append(
                PriceBar(
                    ticker=t,
                    day=idx.date(),
                    open=_get(row, "Open", None),
                    high=_get(row, "High", None),
                    low=_get(row, "Low", None),
                    close=_get(row, "Close", None),
                    volume=_volume(row, None),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return out


def latest_close(bars: list[PriceBar]) -> float | None:
    if not bars:
        return None
    return float(bars[-1].close)
