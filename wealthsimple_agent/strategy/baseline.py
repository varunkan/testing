from __future__ import annotations

from wealthsimple_agent.models import NewsItem, PriceBar, Signal
from wealthsimple_agent.strategy.advanced import generate_advanced_signal


def generate_signal(
    *,
    ticker: str,
    bars: list[PriceBar],
    news: list[NewsItem],
    momentum_weight: float = 0.6,  # kept for API compatibility; unused by advanced engine
    sentiment_weight: float = 0.4,
    trade_score_threshold: float = 0.12,
) -> Signal:
    """
    Default signal generator — multi-factor advanced engine.
    """
    _ = (momentum_weight, sentiment_weight)
    return generate_advanced_signal(
        ticker=ticker,
        bars=bars,
        news=news,
        trade_score_threshold=trade_score_threshold,
    )
