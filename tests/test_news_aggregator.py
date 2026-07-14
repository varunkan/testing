"""Tests for the multi-source news aggregator."""

from datetime import datetime, timedelta, timezone

from wealthsimple_agent.models import NewsItem
from wealthsimple_agent.news.aggregator import (
    _assign_tickers,
    _dedupe,
    _filter_age,
    aggregate_news,
)


def test_assign_tickers_maps_by_text():
    items = [
        NewsItem(source="rss", title="AAPL and MSFT report earnings", summary="Both tech giants beat"),
        NewsItem(source="yahoo", title="Tesla deliveries miss", link="https://example.com/tsla"),
        NewsItem(source="google", title="Fed raises rates"),
    ]
    mapping = _assign_tickers(items, ["AAPL", "MSFT", "TSLA"])
    assert len(mapping["AAPL"]) == 1
    assert len(mapping["MSFT"]) == 1
    assert len(mapping["TSLA"]) == 1
    # The first item mentions two tickers; both should be tagged.
    assert set(mapping["AAPL"][0].tickers) == {"AAPL", "MSFT"}


def test_assign_tickers_uses_source_tickers():
    item = NewsItem(source="yahoo", title="Earnings surprise", tickers=["AAPL"])
    mapping = _assign_tickers([item], ["AAPL", "TSLA"])
    assert len(mapping["AAPL"]) == 1
    assert len(mapping["TSLA"]) == 0


def test_dedupe_by_link():
    items = [
        NewsItem(source="rss", title="A", link="https://example.com/x"),
        NewsItem(source="yahoo", title="B", link="https://example.com/x"),
    ]
    assert len(_dedupe(items)) == 1


def test_filter_age_keeps_recent_items():
    now = datetime.now(tz=timezone.utc)
    old = NewsItem(source="rss", title="old", published_at=now - timedelta(hours=50))
    recent = NewsItem(source="rss", title="recent", published_at=now - timedelta(hours=1))
    assert len(_filter_age([old, recent], max_age_hours=48)) == 1
    assert _filter_age([old, recent], max_age_hours=48)[0].title == "recent"


def test_aggregate_news_collects_from_all_sources(monkeypatch):
    fake_rss = [NewsItem(source="rss", title="AAPL up")]
    fake_yahoo = [NewsItem(source="yahoo", title="MSFT up")]
    fake_google = [NewsItem(source="google", title="TSLA down")]

    monkeypatch.setattr(
        "wealthsimple_agent.news.aggregator.fetch_rss_feeds", lambda *args, **kwargs: fake_rss
    )
    monkeypatch.setattr(
        "wealthsimple_agent.news.aggregator.fetch_yahoo_news", lambda *args, **kwargs: fake_yahoo
    )
    monkeypatch.setattr(
        "wealthsimple_agent.news.aggregator.fetch_google_news", lambda *args, **kwargs: fake_google
    )

    result = aggregate_news(
        ["AAPL", "MSFT", "TSLA"],
        news_sources=["rss", "yahoo", "google"],
    )
    assert len(result["AAPL"]) == 1
    assert result["AAPL"][0].source == "rss"
    assert len(result["MSFT"]) == 1
    assert result["MSFT"][0].source == "yahoo"
    assert len(result["TSLA"]) == 1
    assert result["TSLA"][0].source == "google"


def test_aggregate_news_empty_tickers():
    result = aggregate_news([], news_sources=["rss"])
    assert result == {}
