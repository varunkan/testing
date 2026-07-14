from datetime import date, timedelta

from wealthsimple_agent.models import PriceBar
from wealthsimple_agent.strategy.accuracy import measure_accuracy


def _uptrend(n: int = 80) -> list[PriceBar]:
    start = date(2026, 1, 1)
    px = 100.0
    out = []
    for i in range(n):
        px *= 1.01
        out.append(
            PriceBar(
                ticker="AAPL",
                day=start + timedelta(days=i),
                open=px,
                high=px * 1.02,
                low=px * 0.98,
                close=px,
                volume=1_000_000,
            )
        )
    return out


def test_accuracy_measures_uptrend():
    bars = _uptrend(120)
    rep = measure_accuracy(bars=bars, horizon_days=3, threshold_pct=0.01, min_lookback=40)
    assert rep.samples > 0
    # In a clean uptrend, buy signals should be mostly correct.
    assert rep.hit_rate > 0.5
    assert rep.avg_forward_return > 0


def test_accuracy_returns_disclaimer():
    bars = _uptrend(120)
    rep = measure_accuracy(bars=bars, horizon_days=3, threshold_pct=0.01, min_lookback=40)
    assert "not" in rep.disclaimer.lower() or "guarantee" in rep.disclaimer.lower()


def test_accuracy_cost_adjusted_rate():
    bars = _uptrend(120)
    rep = measure_accuracy(bars=bars, horizon_days=3, threshold_pct=0.01, min_lookback=40)
    assert rep.cost_adjusted_hit_rate >= 0.0
    assert rep.avg_signal_return > 0


def _downtrend(n: int = 80) -> list[PriceBar]:
    start = date(2026, 1, 1)
    px = 100.0
    out = []
    for i in range(n):
        px *= 0.99
        out.append(
            PriceBar(
                ticker="AAPL",
                day=start + timedelta(days=i),
                open=px,
                high=px * 1.02,
                low=px * 0.98,
                close=px,
                volume=1_000_000,
            )
        )
    return out


def test_accuracy_sells_in_downtrend():
    bars = _downtrend(120)
    rep = measure_accuracy(bars=bars, horizon_days=3, threshold_pct=0.01, min_lookback=40)
    assert rep.samples > 0
    # In a clean downtrend, sell signals should be mostly correct.
    assert rep.hit_rate > 0.5
    assert rep.avg_forward_return < 0
