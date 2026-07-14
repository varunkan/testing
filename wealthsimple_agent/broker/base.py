from __future__ import annotations

from abc import ABC, abstractmethod

from wealthsimple_agent.models import OrderIntent, PortfolioSnapshot


class Broker(ABC):
    @abstractmethod
    def get_portfolio(self, *, latest_price_by_ticker: dict[str, float]) -> PortfolioSnapshot:
        raise NotImplementedError

    @abstractmethod
    def execute(self, *, intents: list[OrderIntent], latest_price_by_ticker: dict[str, float]) -> None:
        raise NotImplementedError

