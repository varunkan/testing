from __future__ import annotations

import math

from wealthsimple_agent.models import NewsItem, PriceBar, Signal
from wealthsimple_agent.news.sentiment import score_news


def _pct_change(a: float, b: float) -> float:
    if a == 0:
        return 0.0
    return (b / a) - 1.0


def _squash(x: float) -> float:
    # maps large magnitude inputs to [-1, 1]
    return math.tanh(x)


def generate_signal(
    *,
    ticker: str,
    bars: list[PriceBar],
    news: list[NewsItem],
    momentum_weight: float = 0.6,
    sentiment_weight: float = 0.4,
    trade_score_threshold: float = 0.15,
) -> Signal:
    """
    Baseline strategy:
    - momentum: recent close vs first close (lookback window)
    - sentiment: VADER compound averaged over provided news items
    """
    if len(bars) < 2:
        return Signal(
            ticker=ticker,
            action="hold",
            confidence=0.0,
            score=0.0,
            rationale="Insufficient price history for momentum feature.",
        )

    mom_raw = _pct_change(float(bars[0].close), float(bars[-1].close))
    mom = _squash(mom_raw * 3.0)  # scale into a more responsive range

    sent = score_news(news)
    score = (momentum_weight * mom) + (sentiment_weight * sent)
    score = max(-1.0, min(1.0, float(score)))

    confidence = max(0.0, min(1.0, 0.5 + 0.5 * abs(score)))

    if score >= trade_score_threshold:
        action = "buy"
    elif score <= -trade_score_threshold:
        action = "sell"
    else:
        action = "hold"

    rationale = (
        f"score={score:.3f} (momentum={mom:.3f}, sentiment={sent:.3f}); "
        f"mom_raw={mom_raw:.3%}; threshold={trade_score_threshold:.2f}"
    )
    return Signal(ticker=ticker, action=action, confidence=confidence, score=score, rationale=rationale)

