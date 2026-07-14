from __future__ import annotations

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from wealthsimple_agent.models import NewsItem


_analyzer = SentimentIntensityAnalyzer()


def sentiment_compound(text: str) -> float:
    if not text:
        return 0.0
    scores = _analyzer.polarity_scores(text)
    return float(scores.get("compound", 0.0))


def score_news(items: list[NewsItem]) -> float:
    """
    Returns a single sentiment score in [-1, 1] from a list of news items.
    """
    if not items:
        return 0.0
    vals: list[float] = []
    for it in items:
        blob = " ".join([x for x in [it.title, it.summary] if x])
        vals.append(sentiment_compound(blob))
    return sum(vals) / max(1, len(vals))

