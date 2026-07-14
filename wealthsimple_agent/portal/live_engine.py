"""
Always-on live signal engine with a self-healing scan loop.

The engine continuously re-scans the universe throughout the day:
  - during market hours it scans frequently (default every 15 minutes),
  - off-hours it slows down (default every 60 minutes),
  - failures never kill the loop: errors are recorded, the interval backs off
    exponentially, and the next successful scan resets the failure state,
  - a watchdog detects a stale cache (no successful scan for 3× the interval)
    and forces an immediate rescan.

Users get "what should I do right now" answers from the cached scan, so login
is instant even though the underlying data work is heavy.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

from wealthsimple_agent.market.live import LiveQuote, fetch_live_quotes, is_market_hours
from wealthsimple_agent.market.yfinance_provider import fetch_daily_bars
from wealthsimple_agent.models import PriceBar
from wealthsimple_agent.strategy.baseline import generate_consensus_signal
from wealthsimple_agent.strategy.universes import resolve_universe


DEFAULT_SCAN_UNIVERSE = ["@nasdaq100", "@tsx60"]


@dataclass
class Opportunity:
    ticker: str
    action: str  # buy | sell
    confidence: float
    score: float
    price: float
    change_pct: Optional[float]
    rationale: str
    as_of: str

    def as_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "action": self.action,
            "confidence": self.confidence,
            "score": self.score,
            "price": self.price,
            "change_pct": self.change_pct,
            "rationale": self.rationale,
            "as_of": self.as_of,
        }


@dataclass
class EngineHealth:
    running: bool = False
    scans_completed: int = 0
    consecutive_failures: int = 0
    last_scan_started_at: Optional[str] = None
    last_success_at: Optional[str] = None
    last_error: Optional[str] = None
    last_scan_duration_s: Optional[float] = None
    current_interval_s: float = 0.0
    market_open: bool = False
    self_heals: int = 0

    def as_dict(self) -> dict:
        return {
            "running": self.running,
            "scans_completed": self.scans_completed,
            "consecutive_failures": self.consecutive_failures,
            "last_scan_started_at": self.last_scan_started_at,
            "last_success_at": self.last_success_at,
            "last_error": self.last_error,
            "last_scan_duration_s": self.last_scan_duration_s,
            "current_interval_s": self.current_interval_s,
            "market_open": self.market_open,
            "self_heals": self.self_heals,
        }


class LiveEngine:
    """
    Singleton-style engine. `scan_once()` is synchronous and testable;
    `run_forever()` is the asyncio loop that FastAPI starts on boot.
    """

    def __init__(
        self,
        *,
        universe: Optional[list[str]] = None,
        min_confidence: float = 0.55,
        market_interval_s: float = 15 * 60,
        offhours_interval_s: float = 60 * 60,
        lookback_days: int = 90,
        bars_fetcher: Callable[..., dict[str, list[PriceBar]]] = fetch_daily_bars,
        quotes_fetcher: Callable[[list[str]], dict[str, LiveQuote]] = fetch_live_quotes,
    ):
        self.universe_spec = universe or list(DEFAULT_SCAN_UNIVERSE)
        self.min_confidence = min_confidence
        self.market_interval_s = market_interval_s
        self.offhours_interval_s = offhours_interval_s
        self.lookback_days = lookback_days
        self._bars_fetcher = bars_fetcher
        self._quotes_fetcher = quotes_fetcher

        self._lock = threading.Lock()
        self.health = EngineHealth()
        self._opportunities: list[Opportunity] = []
        self._quotes: dict[str, LiveQuote] = {}
        self._bars: dict[str, list[PriceBar]] = {}
        self._stop = False

    # ---- data access (thread-safe snapshots) ----

    def opportunities(self) -> list[dict]:
        with self._lock:
            return [o.as_dict() for o in self._opportunities]

    def quotes(self, tickers: Optional[list[str]] = None) -> dict[str, dict]:
        with self._lock:
            snapshot = dict(self._quotes)
        if tickers is not None:
            wanted = {t.strip().upper() for t in tickers}
            snapshot = {k: v for k, v in snapshot.items() if k in wanted}
        return {k: v.as_dict() for k, v in snapshot.items()}

    def quote_prices(self) -> dict[str, float]:
        with self._lock:
            return {k: v.price for k, v in self._quotes.items()}

    def bars(self) -> dict[str, list[PriceBar]]:
        with self._lock:
            return dict(self._bars)

    # ---- scanning ----

    def scan_once(self) -> int:
        """One full scan: bars + live quotes + consensus signals. Returns #opportunities."""
        started = datetime.now(tz=timezone.utc)
        self.health.last_scan_started_at = started.isoformat()
        self.health.market_open = is_market_hours(started)

        tickers = resolve_universe(self.universe_spec)
        bars = self._bars_fetcher(tickers, lookback_days=self.lookback_days)
        quotes = self._quotes_fetcher(tickers)

        opportunities: list[Opportunity] = []
        as_of = datetime.now(tz=timezone.utc).isoformat()
        for t in tickers:
            tbars = bars.get(t, [])
            if len(tbars) < 30:
                continue
            quote = quotes.get(t)
            price = quote.price if quote else (float(tbars[-1].close) if tbars else None)
            if price is None or price <= 0:
                continue
            sig = generate_consensus_signal(ticker=t, bars=tbars, news=[])
            if sig.action in ("buy", "sell") and sig.confidence >= self.min_confidence:
                opportunities.append(
                    Opportunity(
                        ticker=t,
                        action=sig.action,
                        confidence=float(sig.confidence),
                        score=float(sig.score),
                        price=float(price),
                        change_pct=quote.change_pct if quote else None,
                        rationale=sig.rationale,
                        as_of=as_of,
                    )
                )

        opportunities.sort(key=lambda o: o.confidence * max(0.0, o.score), reverse=True)

        with self._lock:
            self._opportunities = opportunities
            self._quotes = quotes
            self._bars = bars

        finished = datetime.now(tz=timezone.utc)
        self.health.last_scan_duration_s = (finished - started).total_seconds()
        self.health.last_success_at = finished.isoformat()
        self.health.scans_completed += 1
        self.health.consecutive_failures = 0
        self.health.last_error = None
        return len(opportunities)

    def refresh_quotes_only(self, extra_tickers: Optional[list[str]] = None) -> None:
        """Lightweight refresh of live prices (used between full scans)."""
        tickers = resolve_universe(self.universe_spec)
        if extra_tickers:
            tickers = sorted(set(tickers) | {t.strip().upper() for t in extra_tickers})
        quotes = self._quotes_fetcher(tickers)
        if quotes:
            with self._lock:
                self._quotes.update(quotes)

    def _next_interval(self) -> float:
        base = self.market_interval_s if is_market_hours() else self.offhours_interval_s
        if self.health.consecutive_failures > 0:
            # Exponential backoff capped at 4x the base interval.
            backoff = min(2 ** self.health.consecutive_failures, 4)
            return base * backoff
        return base

    def _is_stale(self) -> bool:
        if not self.health.last_success_at:
            return False
        try:
            last = datetime.fromisoformat(self.health.last_success_at)
        except ValueError:
            return True
        age = (datetime.now(tz=timezone.utc) - last).total_seconds()
        return age > 3 * max(self.health.current_interval_s, 60.0)

    def _self_heal(self) -> None:
        """Reset caches and failure counters so the next scan starts clean."""
        with self._lock:
            self._opportunities = []
        self.health.consecutive_failures = 0
        self.health.self_heals += 1

    async def run_forever(self) -> None:
        """Self-healing background loop. Never raises; never exits until stopped."""
        self.health.running = True
        while not self._stop:
            try:
                await asyncio.to_thread(self.scan_once)
            except Exception as e:  # noqa: BLE001 — the loop must survive anything
                self.health.consecutive_failures += 1
                self.health.last_error = f"{type(e).__name__}: {e}"
                if self.health.consecutive_failures >= 5:
                    self._self_heal()

            self.health.current_interval_s = self._next_interval()
            slept = 0.0
            while slept < self.health.current_interval_s and not self._stop:
                await asyncio.sleep(min(5.0, self.health.current_interval_s - slept))
                slept += 5.0
                if self._is_stale():
                    break
        self.health.running = False

    def stop(self) -> None:
        self._stop = True


_engine: Optional[LiveEngine] = None


def get_live_engine() -> LiveEngine:
    global _engine
    if _engine is None:
        _engine = LiveEngine()
    return _engine
