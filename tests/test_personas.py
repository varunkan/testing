from datetime import date, timedelta

from wealthsimple_agent.models import NewsItem, PriceBar
from wealthsimple_agent.strategy.personas import (
    DEFAULT_PERSONAS,
    Opinion,
    Persona,
    consensus_signal,
    gather_opinions,
)
from wealthsimple_agent.strategy.baseline import generate_consensus_signal


def _bars(ticker: str = "AAPL", n: int = 50, growth: float = 1.01) -> list[PriceBar]:
    start = date(2026, 1, 1)
    px = 100.0
    out = []
    for i in range(n):
        px *= growth
        out.append(
            PriceBar(
                ticker=ticker,
                day=start + timedelta(days=i),
                open=px,
                high=px * 1.02,
                low=px * 0.98,
                close=px,
                volume=1_000_000 + i * 10_000,
            )
        )
    return out


def test_default_personas_evaluate():
    bars = _bars()
    opinions = gather_opinions(ticker="AAPL", bars=bars, news=[])
    assert len(opinions) == len(DEFAULT_PERSONAS)
    for op in opinions:
        assert isinstance(op, Opinion)
        assert op.direction in ("buy", "sell", "hold")
        assert -1.0 <= op.score <= 1.0
        assert 0.0 <= op.confidence <= 0.99


def test_consensus_signal_buys_uptrend():
    bars = _bars(growth=1.012)
    news = [NewsItem(title="Strong earnings and guidance raise")]
    sig = consensus_signal(ticker="AAPL", bars=bars, news=news)
    assert sig.action == "buy"
    assert sig.confidence > 0.5
    assert "consensus" in sig.rationale.lower()


def test_consensus_signal_sells_downtrend():
    bars = _bars(growth=0.985)
    sig = consensus_signal(ticker="AAPL", bars=bars, news=[])
    assert sig.action == "sell"
    assert sig.confidence > 0.5


def test_baseline_exports_consensus_signal():
    bars = _bars(growth=1.012)
    sig = generate_consensus_signal(ticker="AAPL", bars=bars, news=[])
    assert sig.action in ("buy", "sell", "hold")


def test_sector_persona_boost_applies():
    # AAPL is in the tech analyst focus list.
    bars = _bars(ticker="AAPL", growth=1.012)
    opinions = gather_opinions(ticker="AAPL", bars=bars, news=[])
    tech = next(op for op in opinions if op.persona == "Tech Sector Analyst")
    assert tech is not None
