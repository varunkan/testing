from __future__ import annotations
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WS_AGENT_", extra="ignore")

    # Core behavior
    default_lookback_days: int = Field(default=90, ge=5, le=365)
    min_confidence_to_trade: float = Field(default=0.65, ge=0.0, le=1.0)

    # Execution modeling
    fee_per_trade: float = Field(default=0.0, ge=0.0)
    fee_pct_notional: float = Field(default=0.0, ge=0.0)
    slippage_bps: float = Field(default=5.0, ge=0.0)

    # Risk limits
    max_position_pct_of_equity: float = Field(default=0.25, ge=0.0, le=1.0)
    max_daily_loss_pct: float = Field(default=0.03, ge=0.0, le=1.0)
    per_trade_risk_pct: float = Field(default=0.01, ge=0.0, le=1.0)

    # News ingestion
    news_sources: list[str] = Field(default_factory=lambda: ["rss", "yahoo", "google"])
    rss_feeds: list[str] = Field(default_factory=list)
    finnhub_api_key: Optional[str] = None
    newsapi_key: Optional[str] = None
    news_max_age_hours: int = Field(default=48, ge=1, le=168)
    news_timeout_s: float = Field(default=10.0, ge=1.0, le=60.0)

    # Deployment
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])


def get_settings() -> Settings:
    return Settings()

