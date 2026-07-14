from __future__ import annotations

from datetime import datetime, date
from typing import Literal, Optional

from pydantic import BaseModel, Field


Action = Literal["buy", "sell", "hold"]


class NewsItem(BaseModel):
    source: str = Field(default="rss")
    title: str
    link: Optional[str] = None
    published_at: Optional[datetime] = None
    summary: Optional[str] = None
    tickers: list[str] = Field(default_factory=list)


class PriceBar(BaseModel):
    ticker: str
    day: date
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None


class Signal(BaseModel):
    ticker: str
    action: Action
    confidence: float = Field(ge=0.0, le=1.0)
    score: float
    rationale: str


class OrderIntent(BaseModel):
    ticker: str
    action: Literal["buy", "sell"]
    quantity: float = Field(gt=0)
    limit_price: Optional[float] = Field(default=None, gt=0)
    confidence: float = Field(ge=0.0, le=1.0)
    expected_edge: float
    estimated_fees: float


class Position(BaseModel):
    ticker: str
    quantity: float
    avg_price: float
    opened_day: Optional[date] = None


class PortfolioSnapshot(BaseModel):
    as_of: datetime
    cash: float
    equity: float
    positions: list[Position]


class User(BaseModel):
    id: int
    username: str
    api_key: str
    auto_invest: bool = False
    created_at: datetime


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=6)


class UserLogin(BaseModel):
    username: str
    password: str


class UserSettings(BaseModel):
    auto_invest: bool = False

