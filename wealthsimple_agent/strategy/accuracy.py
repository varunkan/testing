from __future__ import annotations

from dataclasses import dataclass

from wealthsimple_agent.models import PriceBar
from wealthsimple_agent.strategy.baseline import generate_signal


@dataclass(frozen=True)
class AccuracyReport:
    ticker: str
    samples: int
    correct: int
    hit_rate: float
    avg_forward_return: float
    horizon_days: int
    threshold_pct: float
    disclaimer: str


def measure_accuracy(
    *,
    bars: list[PriceBar],
    horizon_days: int = 5,
    threshold_pct: float = 0.01,
    min_lookback: int = 40,
) -> AccuracyReport:
    """
    Honest backtest of the signal engine on a single ticker's history.

    For each day i with enough history, generate a signal using bars[:i],
    then check the forward return over `horizon_days`.
    A buy is "correct" if forward return >= threshold_pct.
    A sell is "correct" if forward return <= -threshold_pct.
    Holds are excluded from the sample.
    """
    closes = [float(b.close) for b in bars]
    samples = 0
    correct = 0
    fwd_returns: list[float] = []

    for i in range(min_lookback, len(bars) - horizon_days):
        window = bars[: i + 1]
        sig = generate_signal(ticker=bars[i].ticker, bars=window, news=[])
        if sig.action == "hold":
            continue
        fwd = (closes[i + horizon_days] / closes[i]) - 1.0
        fwd_returns.append(fwd)
        samples += 1
        if sig.action == "buy" and fwd >= threshold_pct:
            correct += 1
        elif sig.action == "sell" and fwd <= -threshold_pct:
            correct += 1

    hit_rate = (correct / samples) if samples > 0 else 0.0
    avg_fwd = (sum(fwd_returns) / len(fwd_returns)) if fwd_returns else 0.0

    return AccuracyReport(
        ticker=bars[0].ticker if bars else "",
        samples=samples,
        correct=correct,
        hit_rate=hit_rate,
        avg_forward_return=avg_fwd,
        horizon_days=horizon_days,
        threshold_pct=threshold_pct,
        disclaimer=(
            "Historical hit-rate on past data. NOT a guarantee of future accuracy. "
            "Past performance does not predict future results."
        ),
    )
