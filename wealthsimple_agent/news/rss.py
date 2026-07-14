from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import feedparser
import requests

from wealthsimple_agent.models import NewsItem


def _parse_datetime(entry: dict) -> Optional[datetime]:
    # feedparser provides multiple possible keys; keep best-effort.
    for key in ("published_parsed", "updated_parsed"):
        if key in entry and entry[key] is not None:
            try:
                dt = datetime(*entry[key][:6], tzinfo=timezone.utc)
                return dt
            except Exception:
                continue
    return None


def fetch_rss(url: str, *, timeout_s: float = 10.0) -> list[NewsItem]:
    resp = requests.get(
        url,
        timeout=timeout_s,
        headers={"User-Agent": "wealthsimple-agent/0.1 (+https://example.invalid)"},
    )
    resp.raise_for_status()
    feed = feedparser.parse(resp.text)

    out: list[NewsItem] = []
    for entry in feed.entries or []:
        out.append(
            NewsItem(
                source="rss",
                title=str(entry.get("title", "")).strip(),
                link=entry.get("link"),
                published_at=_parse_datetime(entry),
                summary=(str(entry.get("summary", "")).strip() or None),
            )
        )
    return out

