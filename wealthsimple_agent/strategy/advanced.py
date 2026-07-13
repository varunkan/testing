from __future__ import annotations

import math
from dataclasses import dataclass

from wealthsimple_agent.models import NewsItem, PriceBar, Signal
from wealthsimple_agent.news.sentiment import score_news


def _squash(x: float) -> float:
    return math.tanh(x)


def _safe_div(a: float, b: float, default: float = 0.0) -> float:
    if b == 0:
        return default
    return a / b


def _closes(bars: list[PriceBar]) -> list[float]:
    return [float(b.close) for b in bars]


def _returns(closes: list[float]) -> list[float]:
    out: list[float] = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        out.append(0.0 if prev == 0 else (closes[i] / prev) - 1.0)
    return out


def _sma(vals: list[float], window: int) -> float | None:
    if len(vals) < window or window <= 0:
        return None
    chunk = vals[-window:]
    return sum(chunk) / len(chunk)


def _ema(vals: list[float], window: int) -> float | None:
    if len(vals) < window or window <= 0:
        return None
    alpha = 2.0 / (window + 1.0)
    ema = vals[0]
    for v in vals[1:]:
        ema = alpha * v + (1.0 - alpha) * ema
    return ema


def _stdev(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
    return math.sqrt(max(0.0, var))


def _rsi(closes: list[float], window: int = 14) -> float | None:
    if len(closes) < window + 1:
        return None
    gains = 0.0
    losses = 0.0
    for i in range(-window, 0):
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gains += diff
        else:
            losses -= diff
    if losses == 0:
        return 100.0
    rs = gains / losses
    return 100.0 - (100.0 / (1.0 + rs))


def _max_drawdown(closes: list[float]) -> float:
    peak = None
    mdd = 0.0
    for c in closes:
        if peak is None or c > peak:
            peak = c
        if peak and peak > 0:
            mdd = max(mdd, (peak - c) / peak)
    return mdd


@dataclass(frozen=True)
class FactorSnapshot:
    momentum_short: float
    momentum_med: float
    trend: float
    rsi_signal: float
    breakout: float
    mean_reversion: float
    vol_penalty: float
    volume_thrust: float
    sentiment: float
    regime: str  # "trend" | "chop" | "unknown"
    realized_vol: float


def compute_factors(*, bars: list[PriceBar], news: list[NewsItem]) -> FactorSnapshot | None:
    if len(bars) < 5:
        return None

    closes = _closes(bars)
    rets = _returns(closes)
    last = closes[-1]

    # Momentum horizons
    short_n = min(5, len(closes) - 1)
    med_n = min(20, len(closes) - 1)
    mom_s = _squash(((last / closes[-1 - short_n]) - 1.0) * 8.0) if short_n > 0 else 0.0
    mom_m = _squash(((last / closes[-1 - med_n]) - 1.0) * 4.0) if med_n > 0 else 0.0

    # Trend: price vs SMA + EMA slope proxy
    sma10 = _sma(closes, min(10, len(closes)))
    sma20 = _sma(closes, min(20, len(closes)))
    ema12 = _ema(closes, min(12, len(closes)))
    trend_raw = 0.0
    if sma10 and sma20 and sma20 != 0:
        trend_raw += _squash(((sma10 / sma20) - 1.0) * 20.0)
    if ema12 and sma20 and sma20 != 0:
        trend_raw += _squash(((ema12 / sma20) - 1.0) * 15.0)
    if sma20 and sma20 != 0:
        trend_raw += _squash(((last / sma20) - 1.0) * 10.0)
    trend = _squash(trend_raw / 2.0)

    # RSI (mapped so mid=50 is neutral; oversold boosts buy, overbought boosts sell)
    rsi = _rsi(closes, window=min(14, len(closes) - 1))
    if rsi is None:
        rsi_signal = 0.0
    else:
        # Positive when oversold (buy), negative when overbought (sell)
        rsi_signal = _squash((50.0 - rsi) / 15.0)

    # Breakout vs recent high/low range
    window = min(20, len(bars))
    recent = bars[-window:]
    hi = max(float(b.high) for b in recent)
    lo = min(float(b.low) for b in recent)
    rng = max(1e-9, hi - lo)
    # Near highs -> breakout long; near lows -> breakdown short
    breakout = _squash(((last - lo) / rng - 0.5) * 3.0)

    # Mean reversion vs SMA (contrarian, used lightly in chop)
    mean_rev = 0.0
    if sma20 and sma20 != 0:
        mean_rev = _squash(-((last / sma20) - 1.0) * 12.0)

    # Realized volatility (annualized-ish daily std)
    vol_window = rets[-min(20, len(rets)) :] if rets else []
    realized_vol = _stdev(vol_window)
    # Penalize extremely high vol for confidence / sizing later
    vol_penalty = _squash(max(0.0, realized_vol - 0.02) * 40.0)  # 0..1-ish

    # Volume thrust (if available)
    vols = [float(b.volume) for b in bars if b.volume is not None]
    volume_thrust = 0.0
    if len(vols) >= 6:
        recent_v = sum(vols[-3:]) / 3.0
        base_v = sum(vols[-6:-3]) / 3.0
        if base_v > 0:
            volume_thrust = _squash(((recent_v / base_v) - 1.0) * 2.0) * (1.0 if mom_s >= 0 else -1.0)

    sentiment = float(score_news(news))

    # Regime: trending if |trend| high and drawdown not chaotic
    mdd = _max_drawdown(closes[-min(30, len(closes)) :])
    if abs(trend) > 0.25 and mdd < 0.12:
        regime = "trend"
    elif realized_vol > 0.025 and abs(trend) < 0.15:
        regime = "chop"
    else:
        regime = "unknown"

    return FactorSnapshot(
        momentum_short=float(mom_s),
        momentum_med=float(mom_m),
        trend=float(trend),
        rsi_signal=float(rsi_signal),
        breakout=float(breakout),
        mean_reversion=float(mean_rev),
        vol_penalty=float(vol_penalty),
        volume_thrust=float(volume_thrust),
        sentiment=float(sentiment),
        regime=regime,
        realized_vol=float(realized_vol),
    )


def _weights_for_regime(regime: str) -> dict[str, float]:
    if regime == "trend":
        return {
            "momentum_short": 0.18,
            "momentum_med": 0.18,
            "trend": 0.22,
            "breakout": 0.14,
            "rsi_signal": 0.05,
            "mean_reversion": 0.02,
            "volume_thrust": 0.08,
            "sentiment": 0.13,
        }
    if regime == "chop":
        return {
            "momentum_short": 0.08,
            "momentum_med": 0.06,
            "trend": 0.08,
            "breakout": 0.08,
            "rsi_signal": 0.22,
            "mean_reversion": 0.22,
            "volume_thrust": 0.06,
            "sentiment": 0.20,
        }
    return {
        "momentum_short": 0.14,
        "momentum_med": 0.14,
        "trend": 0.16,
        "breakout": 0.12,
        "rsi_signal": 0.10,
        "mean_reversion": 0.08,
        "volume_thrust": 0.08,
        "sentiment": 0.18,
    }


def generate_advanced_signal(
    *,
    ticker: str,
    bars: list[PriceBar],
    news: list[NewsItem],
    trade_score_threshold: float = 0.12,
) -> Signal:
    """
    Multi-factor signal engine:
    - short/medium momentum, trend, RSI, breakout, mean-reversion
    - volume thrust, news sentiment
    - regime-aware factor weights (trend vs chop)
    - confidence from |score|, factor agreement, and inverse volatility
    """
    factors = compute_factors(bars=bars, news=news)
    if factors is None:
        return Signal(
            ticker=ticker,
            action="hold",
            confidence=0.0,
            score=0.0,
            rationale="Insufficient history for advanced factors.",
        )

    weights = _weights_for_regime(factors.regime)
    components = {
        "momentum_short": factors.momentum_short,
        "momentum_med": factors.momentum_med,
        "trend": factors.trend,
        "breakout": factors.breakout,
        "rsi_signal": factors.rsi_signal,
        "mean_reversion": factors.mean_reversion,
        "volume_thrust": factors.volume_thrust,
        "sentiment": factors.sentiment,
    }

    score = sum(weights[k] * components[k] for k in weights)
    # Soft-penalize extreme vol in the score magnitude
    score *= 1.0 - 0.35 * factors.vol_penalty
    score = max(-1.0, min(1.0, float(score)))

    # Factor agreement: fraction of factors with the same sign as score
    if abs(score) < 1e-9:
        agreement = 0.0
    else:
        sign = 1.0 if score > 0 else -1.0
        agrees = sum(1 for v in components.values() if v * sign > 0.05)
        agreement = agrees / max(1, len(components))

    # Confidence: magnitude + agreement - vol penalty
    confidence = 0.35 + 0.40 * abs(score) + 0.30 * agreement - 0.25 * factors.vol_penalty
    confidence = max(0.0, min(0.99, float(confidence)))

    if score >= trade_score_threshold and confidence >= 0.45:
        action = "buy"
    elif score <= -trade_score_threshold and confidence >= 0.45:
        action = "sell"
    else:
        action = "hold"

    rationale = (
        f"adv score={score:.3f} conf={confidence:.2f} regime={factors.regime} "
        f"momS={factors.momentum_short:.2f} momM={factors.momentum_med:.2f} "
        f"trend={factors.trend:.2f} brk={factors.breakout:.2f} rsi={factors.rsi_signal:.2f} "
        f"mr={factors.mean_reversion:.2f} vol={factors.realized_vol:.3f} "
        f"sent={factors.sentiment:.2f} agree={agreement:.2f}"
    )
    return Signal(
        ticker=ticker,
        action=action,
        confidence=confidence,
        score=score,
        rationale=rationale,
    )


def estimate_expected_edge(signal: Signal, *, realized_vol: float | None = None) -> float:
    """
    Map signal strength to an expected move estimate used for fee gates / sizing.
    Stronger scores and confidence imply larger expected edge; high vol caps optimism.
    """
    base = max(0.0, abs(float(signal.score))) * (0.015 + 0.035 * float(signal.confidence))
    if realized_vol is not None:
        # Don't claim edge much larger than a fraction of recent vol.
        base = min(base, max(0.004, realized_vol * 1.5))
    return float(base)


def dynamic_exit_levels(*, realized_vol: float, base_tp: float, base_sl: float) -> tuple[float, float]:
    """
    Widen TP/SL when volatility is high; tighten when quiet.
    """
    vol = max(0.0, float(realized_vol))
    scale = 1.0 + min(2.0, vol / 0.015)
    tp = max(0.01, float(base_tp) * scale)
    sl = max(0.008, float(base_sl) * min(scale, 1.8))
    return tp, sl
