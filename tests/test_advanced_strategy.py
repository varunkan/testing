from datetime import date, timedelta

from wealthsimple_agent.models import NewsItem, PriceBar
from wealthsimple_agent.strategy.advanced import (
    compute_factors,
    dynamic_exit_levels,
    estimate_expected_edge,
    generate_advanced_signal,
)
from wealthsimple_agent.strategy.baseline import generate_signal


def _uptrend_bars(ticker: str = "AAPL", n: int = 40) -> list[PriceBar]:
    start = date(2026, 1, 1)
    out: list[PriceBar] = []
    px = 100.0
    for i in range(n):
        px = px * 1.012
        d = start + timedelta(days=i)
        out.append(
            PriceBar(
                ticker=ticker,
                day=d,
                open=px * 0.99,
                high=px * 1.02,
                low=px * 0.98,
                close=px,
                volume=1_000_000 + i * 10_000,
            )
        )
    return out


def test_advanced_signal_buys_strong_uptrend():
    bars = _uptrend_bars()
    news = [NewsItem(title="Record growth and strong earnings beat")]
    sig = generate_advanced_signal(ticker="AAPL", bars=bars, news=news)
    assert sig.action == "buy"
    assert sig.confidence > 0.5
    assert sig.score > 0
    assert "regime=" in sig.rationale


def test_baseline_delegates_to_advanced():
    bars = _uptrend_bars()
    a = generate_advanced_signal(ticker="AAPL", bars=bars, news=[])
    b = generate_signal(ticker="AAPL", bars=bars, news=[])
    assert a.action == b.action
    assert abs(a.score - b.score) < 1e-9


def test_factor_snapshot_and_dynamic_exits():
    bars = _uptrend_bars()
    factors = compute_factors(bars=bars, news=[])
    assert factors is not None
    assert factors.realized_vol >= 0.0
    tp, sl = dynamic_exit_levels(realized_vol=0.03, base_tp=0.04, base_sl=0.02)
    assert tp > 0.04
    assert sl >= 0.02


def test_expected_edge_scales_with_confidence():
    bars = _uptrend_bars()
    sig = generate_advanced_signal(ticker="AAPL", bars=bars, news=[])
    edge = estimate_expected_edge(sig, realized_vol=0.02)
    assert edge > 0
    assert edge <= 0.05
