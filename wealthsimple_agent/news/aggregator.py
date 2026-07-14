from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional
from urllib.parse import quote_plus

import requests

from wealthsimple_agent.models import NewsItem
from wealthsimple_agent.news.rss import fetch_rss


# Curated set of major financial RSS feeds that do not require an API key.
DEFAULT_RSS_FEEDS = [
    "http://feeds.marketwatch.com/marketwatch/topstories/",
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "https://seekingalpha.com/feed.xml",
    "https://news.google.com/rss",
]

NewsSource = Callable[[list[str]], list[NewsItem]]


def _parse_iso_or_ts(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # Finnhub and some yfinance data are Unix timestamps (seconds).
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except Exception:
            return None
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(text)
        except Exception:
            pass
        # Try common formats.
        for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                return datetime.strptime(text, fmt)
            except Exception:
                continue
    return None


def _dedupe(items: list[NewsItem]) -> list[NewsItem]:
    seen: set[str] = set()
    out: list[NewsItem] = []
    for it in items:
        key = (it.link or "").strip() or f"{it.source}:{it.title}"
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out


def _assign_tickers(items: list[NewsItem], tickers: list[str]) -> dict[str, list[NewsItem]]:
    """Map news items to the tickers they explicitly mention."""
    mapping: dict[str, list[NewsItem]] = {t: [] for t in tickers}
    if not tickers:
        return mapping

    # Build a single regex that matches any ticker as a whole word.
    escaped = [re.escape(t) for t in tickers]
    pattern = re.compile(r"\b(" + "|".join(escaped) + r")\b", re.IGNORECASE)

    for it in items:
        text = " ".join([x for x in [it.title, it.summary, it.link] if x]).upper()
        mentioned = {m.upper() for m in pattern.findall(text)}
        # Merge with any tickers already tagged by the source (e.g., yfinance).
        tagged = mentioned | set(it.tickers or [])
        it.tickers = sorted(tagged)
        for t in tagged:
            if t in mapping:
                mapping[t].append(it)
    return mapping


def _filter_age(items: list[NewsItem], max_age_hours: int) -> list[NewsItem]:
    if max_age_hours <= 0:
        return items
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=max_age_hours)
    out: list[NewsItem] = []
    for it in items:
        if it.published_at is None or it.published_at >= cutoff:
            out.append(it)
    return out


def fetch_rss_feeds(
    urls: Optional[list[str]] = None,
    *,
    max_age_hours: int = 48,
    timeout_s: float = 10.0,
) -> list[NewsItem]:
    """Fetch a list of RSS/Atom feeds and return normalized NewsItems."""
    urls = urls or DEFAULT_RSS_FEEDS
    out: list[NewsItem] = []
    for url in urls:
        try:
            items = fetch_rss(url, timeout_s=timeout_s)
            for it in items:
                it.source = f"rss:{it.source}"
            out.extend(items)
        except Exception:
            continue
    return _filter_age(_dedupe(out), max_age_hours)


def fetch_yahoo_news(
    tickers: list[str],
    *,
    max_age_hours: int = 48,
) -> list[NewsItem]:
    """Fetch Yahoo Finance ticker-level news via yfinance."""
    import yfinance as yf

    out: list[NewsItem] = []
    for t in tickers:
        try:
            ticker = yf.Ticker(t)
            for item in ticker.news or []:
                published = _parse_iso_or_ts(item.get("published_at"))
                related = item.get("relatedTickers") or []
                out.append(
                    NewsItem(
                        source="yahoo",
                        title=str(item.get("title", "")).strip(),
                        link=item.get("link"),
                        published_at=published,
                        summary=(str(item.get("summary", "")).strip() or None),
                        tickers=[str(x).upper() for x in related if x],
                    )
                )
        except Exception:
            continue
    return _filter_age(_dedupe(out), max_age_hours)


def fetch_google_news(
    tickers: list[str],
    *,
    max_age_hours: int = 48,
    timeout_s: float = 10.0,
) -> list[NewsItem]:
    """Fetch Google News RSS searches for each ticker."""
    out: list[NewsItem] = []
    for t in tickers:
        try:
            query = quote_plus(f"{t} stock")
            url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
            items = fetch_rss(url, timeout_s=timeout_s)
            for it in items:
                it.source = "google_news"
                # Google News RSS sometimes puts the source in the title after a dash.
                out.append(it)
        except Exception:
            continue
    return _filter_age(_dedupe(out), max_age_hours)


def fetch_finnhub_news(
    tickers: list[str],
    api_key: str,
    *,
    max_age_hours: int = 48,
    timeout_s: float = 10.0,
) -> list[NewsItem]:
    """Fetch company news from Finnhub (requires API key)."""
    if not api_key:
        return []
    out: list[NewsItem] = []
    today = datetime.now(tz=timezone.utc)
    week_ago = today - timedelta(days=7)
    for t in tickers:
        try:
            url = (
                "https://finnhub.io/api/v1/company-news"
                f"?symbol={t}&from={week_ago:%Y-%m-%d}&to={today:%Y-%m-%d}"
                f"&token={api_key}"
            )
            resp = requests.get(url, timeout=timeout_s)
            resp.raise_for_status()
            for item in resp.json():
                published = _parse_iso_or_ts(item.get("datetime"))
                out.append(
                    NewsItem(
                        source="finnhub",
                        title=str(item.get("headline", "")).strip(),
                        link=item.get("url"),
                        published_at=published,
                        summary=(str(item.get("summary", "")).strip() or None),
                        tickers=[t],
                    )
                )
        except Exception:
            continue
    return _filter_age(_dedupe(out), max_age_hours)


def fetch_newsapi_news(
    tickers: list[str],
    api_key: str,
    *,
    max_age_hours: int = 48,
    timeout_s: float = 10.0,
) -> list[NewsItem]:
    """Fetch news from NewsAPI (requires API key)."""
    if not api_key:
        return []
    out: list[NewsItem] = []
    for t in tickers:
        try:
            url = (
                "https://newsapi.org/v2/everything"
                f"?q={quote_plus(t)}&language=en&sortBy=publishedAt&pageSize=20"
                f"&apiKey={api_key}"
            )
            resp = requests.get(url, timeout=timeout_s)
            resp.raise_for_status()
            data = resp.json()
            for item in data.get("articles", []):
                published = _parse_iso_or_ts(item.get("publishedAt"))
                source_name = item.get("source", {}).get("name", "newsapi")
                out.append(
                    NewsItem(
                        source=f"newsapi:{source_name}",
                        title=str(item.get("title", "")).strip(),
                        link=item.get("url"),
                        published_at=published,
                        summary=(str(item.get("description", "")).strip() or None),
                        tickers=[t],
                    )
                )
        except Exception:
            continue
    return _filter_age(_dedupe(out), max_age_hours)


def _fetch_from_source(
    source: str,
    tickers: list[str],
    *,
    rss_urls: Optional[list[str]] = None,
    finnhub_key: Optional[str] = None,
    newsapi_key: Optional[str] = None,
    max_age_hours: int = 48,
    timeout_s: float = 10.0,
) -> list[NewsItem]:
    try:
        if source == "rss":
            return fetch_rss_feeds(urls=rss_urls, max_age_hours=max_age_hours, timeout_s=timeout_s)
        if source == "yahoo":
            return fetch_yahoo_news(tickers, max_age_hours=max_age_hours)
        if source == "google":
            return fetch_google_news(tickers, max_age_hours=max_age_hours, timeout_s=timeout_s)
        if source == "finnhub":
            return fetch_finnhub_news(tickers, finnhub_key, max_age_hours=max_age_hours, timeout_s=timeout_s)
        if source == "newsapi":
            return fetch_newsapi_news(tickers, newsapi_key, max_age_hours=max_age_hours, timeout_s=timeout_s)
    except Exception:
        return []
    return []


DEFAULT_NEWS_SOURCES = ["rss", "yahoo", "google"]


def aggregate_news(
    tickers: list[str],
    *,
    news_sources: Optional[list[str]] = None,
    rss_urls: Optional[list[str]] = None,
    finnhub_key: Optional[str] = None,
    newsapi_key: Optional[str] = None,
    max_age_hours: int = 48,
    timeout_s: float = 10.0,
) -> dict[str, list[NewsItem]]:
    """
    Pull news from all configured sources and map each item to the tickers it mentions.

    Sources are run in order; failures in one source do not block the others.
    """
    tickers = [t.strip().upper() for t in tickers if t.strip()]
    sources = news_sources or DEFAULT_NEWS_SOURCES

    all_items: list[NewsItem] = []
    for source in sources:
        items = _fetch_from_source(
            source,
            tickers,
            rss_urls=rss_urls,
            finnhub_key=finnhub_key,
            newsapi_key=newsapi_key,
            max_age_hours=max_age_hours,
            timeout_s=timeout_s,
        )
        all_items.extend(items)

    all_items = _dedupe(all_items)
    return _assign_tickers(all_items, tickers)
