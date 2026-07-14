from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from wealthsimple_agent.models import Action, NewsItem, PriceBar, Signal
from wealthsimple_agent.strategy.advanced import compute_factors, generate_advanced_signal


@dataclass(frozen=True)
class Persona:
    """A stylized market participant with a preferred factor lens."""

    name: str
    style: str
    sector_focus: tuple[str, ...]
    weights: dict[str, float]
    # Bias adjusts how easily the persona flips to buy/sell. Positive = more bullish threshold.
    score_threshold: float = 0.10
    confidence_floor: float = 0.50

    def evaluate(
        self,
        *,
        ticker: str,
        bars: list[PriceBar],
        news: list[NewsItem],
    ) -> "Opinion":
        """Return this persona's directional opinion on a single ticker."""
        factors = compute_factors(bars=bars, news=news)
        if factors is None:
            return Opinion(
                persona=self.name,
                style=self.style,
                direction="hold",
                score=0.0,
                confidence=0.0,
                rationale="Insufficient history for this persona's analysis.",
            )

        components = {
            "momentum_short": factors.momentum_short,
            "momentum_med": factors.momentum_med,
            "trend": factors.trend,
            "rsi_signal": factors.rsi_signal,
            "breakout": factors.breakout,
            "mean_reversion": factors.mean_reversion,
            "volume_thrust": factors.volume_thrust,
            "sentiment": factors.sentiment,
            "macd": factors.macd,
            "adx": factors.adx,
            "sharpe": factors.sharpe,
        }
        score = sum(self.weights.get(k, 0.0) * components[k] for k in components)
        # Volatility penalty is applied softly
        score *= 1.0 - 0.25 * factors.vol_penalty
        score = max(-1.0, min(1.0, float(score)))

        if abs(score) < 1e-9:
            agreement = 0.0
        else:
            sign = 1.0 if score > 0 else -1.0
            agrees = sum(1 for v in components.values() if v * sign > 0.05)
            agreement = agrees / max(1, len(components))

        confidence = 0.30 + 0.40 * abs(score) + 0.30 * agreement - 0.25 * factors.vol_penalty
        confidence = max(0.0, min(0.99, float(confidence)))

        if score >= self.score_threshold and confidence >= self.confidence_floor:
            direction: Action = "buy"
        elif score <= -self.score_threshold and confidence >= self.confidence_floor:
            direction = "sell"
        else:
            direction = "hold"

        rationale = (
            f"{self.name} ({self.style}): score={score:.2f} conf={confidence:.2f} "
            f"momS={factors.momentum_short:.2f} trend={factors.trend:.2f} "
            f"rsi={factors.rsi_signal:.2f} sent={factors.sentiment:.2f} agree={agreement:.2f}"
        )
        return Opinion(
            persona=self.name,
            style=self.style,
            direction=direction,
            score=score,
            confidence=confidence,
            rationale=rationale,
        )


@dataclass(frozen=True)
class Opinion:
    """One persona's view on a ticker."""

    persona: str
    style: str
    direction: Action
    score: float
    confidence: float
    rationale: str

    def as_dict(self) -> dict:
        return {
            "persona": self.persona,
            "style": self.style,
            "direction": self.direction,
            "score": self.score,
            "confidence": self.confidence,
            "rationale": self.rationale,
        }


# Persona definitions: each captures a different investment style / sector lens.
# Weights are over the same factor components produced by compute_factors.

VALUE_INVESTOR = Persona(
    name="Value Investor",
    style="fundamental / deep value",
    sector_focus=("all",),
    weights={
        "mean_reversion": 0.35,
        "rsi_signal": 0.25,
        "trend": 0.10,
        "sentiment": 0.15,
        "momentum_med": 0.05,
        "sharpe": 0.10,
    },
    score_threshold=0.12,
    confidence_floor=0.55,
)

GROWTH_INVESTOR = Persona(
    name="Growth Investor",
    style="fundamental / growth",
    sector_focus=("all",),
    weights={
        "momentum_short": 0.20,
        "momentum_med": 0.25,
        "trend": 0.20,
        "breakout": 0.15,
        "volume_thrust": 0.10,
        "sentiment": 0.10,
    },
    score_threshold=0.18,
    confidence_floor=0.55,
)

QUALITY_DIVIDEND_INVESTOR = Persona(
    name="Quality & Dividend Investor",
    style="fundamental / income & quality",
    sector_focus=("all",),
    weights={
        "trend": 0.30,
        "sharpe": 0.25,
        "rsi_signal": 0.15,
        "sentiment": 0.15,
        "mean_reversion": 0.10,
        "volume_thrust": 0.05,
    },
    score_threshold=0.12,
    confidence_floor=0.55,
)

MOMENTUM_TRADER = Persona(
    name="Momentum Trader",
    style="technical / momentum",
    sector_focus=("all",),
    weights={
        "momentum_short": 0.30,
        "momentum_med": 0.25,
        "volume_thrust": 0.20,
        "trend": 0.15,
        "macd": 0.10,
    },
    score_threshold=0.18,
    confidence_floor=0.55,
)

CONTRARIAN = Persona(
    name="Contrarian",
    style="behavioral / mean reversion",
    sector_focus=("all",),
    weights={
        "mean_reversion": 0.35,
        "rsi_signal": 0.25,
        "sentiment": -0.20,  # negative sentiment is a positive for contrarians
        "momentum_short": -0.10,
        "breakout": -0.10,
    },
    score_threshold=0.15,
    confidence_floor=0.55,
)

TECH_ANALYST = Persona(
    name="Tech Sector Analyst",
    style="sector / technology & growth",
    sector_focus=("AAPL", "MSFT", "AMZN", "NVDA", "META", "GOOGL", "GOOG", "TSLA", "NFLX", "ADBE", "CRM", "ORCL", "SAP", "SNOW", "NOW", "PANW", "CRWD", "ZS", "DDOG", "NET", "MDB", "TEAM", "SHOP", "SHOP.TO", "CSU.TO", "KXS.TO", "OTEX.TO", "GIB.A.TO"),
    weights={
        "momentum_short": 0.20,
        "momentum_med": 0.20,
        "trend": 0.15,
        "breakout": 0.15,
        "volume_thrust": 0.15,
        "sentiment": 0.10,
        "sharpe": 0.05,
    },
    score_threshold=0.16,
    confidence_floor=0.55,
)

ENERGY_MATERIALS_ANALYST = Persona(
    name="Energy & Materials Analyst",
    style="sector / cyclical commodities",
    sector_focus=("XOM", "CVX", "COP", "SLB", "OXY", "CNQ.TO", "SU.TO", "ENB.TO", "TRP.TO", "CVE.TO", "IMO.TO", "TOU.TO", "PPL.TO", "ABX.TO", "FNV.TO", "AEM.TO", "WPM.TO", "NTR.TO", "LUN.TO", "K.TO"),
    weights={
        "breakout": 0.25,
        "momentum_med": 0.20,
        "mean_reversion": 0.15,
        "trend": 0.15,
        "volume_thrust": 0.15,
        "sentiment": 0.10,
    },
    score_threshold=0.16,
    confidence_floor=0.55,
)

FINANCIALS_ANALYST = Persona(
    name="Financials Analyst",
    style="sector / banks & insurers",
    sector_focus=("JPM", "BAC", "WFC", "GS", "MS", "RY.TO", "TD.TO", "BNS.TO", "BMO.TO", "CM.TO", "NA.TO", "MFC.TO", "SLF.TO", "POW.TO", "GWO.TO", "IAG.TO", "IFC.TO"),
    weights={
        "trend": 0.30,
        "sharpe": 0.25,
        "rsi_signal": 0.15,
        "sentiment": 0.15,
        "mean_reversion": 0.10,
        "volume_thrust": 0.05,
    },
    score_threshold=0.12,
    confidence_floor=0.55,
)

CONSUMER_HEALTHCARE_ANALYST = Persona(
    name="Consumer & Healthcare Analyst",
    style="sector / staples & healthcare",
    sector_focus=("WMT", "COST", "PG", "KO", "PEP", "JNJ", "PFE", "UNH", "L.TO", "MRU.TO", "DOL.TO", "ATD.TO", "EMP-A.TO", "CTC.A.TO", "WN.TO", "QSR.TO", "SAP.TO"),
    weights={
        "trend": 0.25,
        "sharpe": 0.20,
        "rsi_signal": 0.15,
        "sentiment": 0.15,
        "momentum_med": 0.15,
        "mean_reversion": 0.10,
    },
    score_threshold=0.12,
    confidence_floor=0.55,
)

# Market-driver personas: participants whose behavior moves prices.

RETAIL_TRADER = Persona(
    name="Retail / Social Media Trader",
    style="market driver / sentiment & FOMO",
    sector_focus=("all",),
    weights={
        "sentiment": 0.35,
        "volume_thrust": 0.25,
        "breakout": 0.20,
        "momentum_short": 0.20,
    },
    score_threshold=0.20,
    confidence_floor=0.55,
)

QUANT_FUND = Persona(
    name="Quantitative Fund",
    style="market driver / systematic factors",
    sector_focus=("all",),
    weights={
        "momentum_short": 0.15,
        "momentum_med": 0.15,
        "trend": 0.15,
        "mean_reversion": 0.15,
        "sharpe": 0.20,
        "macd": 0.10,
        "adx": 0.10,
    },
    score_threshold=0.15,
    confidence_floor=0.55,
)

INSTITUTIONAL_INVESTOR = Persona(
    name="Institutional Investor",
    style="market driver / large-cap trend",
    sector_focus=("all",),
    weights={
        "trend": 0.30,
        "momentum_med": 0.25,
        "sharpe": 0.20,
        "sentiment": 0.15,
        "volume_thrust": 0.10,
    },
    score_threshold=0.15,
    confidence_floor=0.55,
)

ACTIVIST_INVESTOR = Persona(
    name="Activist Investor",
    style="market driver / undervalued catalyst",
    sector_focus=("all",),
    weights={
        "mean_reversion": 0.30,
        "rsi_signal": 0.25,
        "sentiment": -0.15,  # negative sentiment = opportunity
        "adx": 0.15,
        "momentum_med": 0.10,
        "sharpe": 0.05,
    },
    score_threshold=0.18,
    confidence_floor=0.55,
)

DEFAULT_PERSONAS: list[Persona] = [
    VALUE_INVESTOR,
    GROWTH_INVESTOR,
    QUALITY_DIVIDEND_INVESTOR,
    MOMENTUM_TRADER,
    CONTRARIAN,
    TECH_ANALYST,
    ENERGY_MATERIALS_ANALYST,
    FINANCIALS_ANALYST,
    CONSUMER_HEALTHCARE_ANALYST,
    RETAIL_TRADER,
    QUANT_FUND,
    INSTITUTIONAL_INVESTOR,
    ACTIVIST_INVESTOR,
]


def gather_opinions(
    *,
    ticker: str,
    bars: list[PriceBar],
    news: list[NewsItem],
    personas: list[Persona] | None = None,
) -> list[Opinion]:
    """Evaluate all active personas and return their opinions."""
    personas = personas or DEFAULT_PERSONAS
    return [p.evaluate(ticker=ticker, bars=bars, news=news) for p in personas]


def consensus_signal(
    *,
    ticker: str,
    bars: list[PriceBar],
    news: list[NewsItem],
    personas: list[Persona] | None = None,
    base_weight: float = 0.55,
    persona_weight: float = 0.45,
    trade_score_threshold: float = 0.18,
) -> Signal:
    """
    Blend the advanced multi-factor engine with a council of personas.

    The base engine contributes 55% of the final score; the persona council contributes 45%.
    This makes the recommendation more interpretable and less dependent on any single factor lens.
    """
    base = generate_advanced_signal(ticker=ticker, bars=bars, news=news, trade_score_threshold=trade_score_threshold)
    opinions = gather_opinions(ticker=ticker, bars=bars, news=news, personas=personas)

    if not opinions:
        return base

    # Weighted average of persona scores. Sector-relevant personas get a small boost if the
    # ticker is in their focus list; otherwise all personas are weighted equally.
    total_score = 0.0
    total_weight = 0.0
    for op in opinions:
        w = 1.2 if (op.style.startswith("sector") and ticker.upper() in _persona_sector_tickers(op.persona)) else 1.0
        total_score += w * op.score
        total_weight += w
    persona_score = total_score / max(1e-9, total_weight)

    final_score = base_weight * base.score + persona_weight * persona_score
    final_score = max(-1.0, min(1.0, final_score))

    # Confidence is the average of the base engine and the average persona confidence,
    # with a small bonus when persona agreement is high.
    avg_persona_conf = sum(op.confidence for op in opinions) / len(opinions)
    if abs(final_score) < 1e-9:
        persona_agreement = 0.0
    else:
        sign = 1.0 if final_score > 0 else -1.0
        persona_agreement = sum(1 for op in opinions if op.score * sign > 0.05) / len(opinions)
    final_confidence = 0.6 * base.confidence + 0.4 * avg_persona_conf + 0.1 * persona_agreement
    final_confidence = max(0.0, min(0.99, final_confidence))

    # Decision rule mirrors the advanced engine but uses the blended score.
    if final_score >= trade_score_threshold and final_confidence >= 0.55:
        action: Action = "buy"
    elif final_score <= -trade_score_threshold and final_confidence >= 0.55:
        action = "sell"
    else:
        action = "hold"

    # Build a compact rationale showing who is driving the consensus.
    bulls = [op.persona for op in opinions if op.direction == "buy"]
    bears = [op.persona for op in opinions if op.direction == "sell"]
    bulls_str = f"bulls={','.join(bulls[:3])}{'...' if len(bulls) > 3 else ''}" if bulls else "bulls=none"
    bears_str = f"bears={','.join(bears[:3])}{'...' if len(bears) > 3 else ''}" if bears else "bears=none"

    rationale = (
        f"consensus score={final_score:.3f} conf={final_confidence:.2f} "
        f"base={base.score:.2f} personas={persona_score:.2f} "
        f"{bulls_str} {bears_str}"
    )
    return Signal(
        ticker=ticker,
        action=action,
        confidence=final_confidence,
        score=final_score,
        rationale=rationale,
    )


# Helper to resolve sector-focus tickers for a persona by name. Used in consensus weighting.
_PERSONA_SECTOR_TICKERS: dict[str, set[str]] = {}


def _persona_sector_tickers(name: str) -> set[str]:
    if not _PERSONA_SECTOR_TICKERS:
        for p in DEFAULT_PERSONAS:
            _PERSONA_SECTOR_TICKERS[p.name] = {t.upper() for t in p.sector_focus}
    return _PERSONA_SECTOR_TICKERS.get(name, set())
