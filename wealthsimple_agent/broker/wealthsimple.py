from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from wealthsimple_agent.broker.base import Broker
from wealthsimple_agent.models import OrderIntent, PortfolioSnapshot


@dataclass(frozen=True)
class WealthsimpleStub(Broker):
    """
    Stub connector.

    Wealthsimple automated order placement requires an official, supported API.
    This class exists to keep the architecture pluggable without resorting to fragile UI automation.
    """

    def get_portfolio(self, *, latest_price_by_ticker: dict[str, float]) -> PortfolioSnapshot:
        raise NotImplementedError(
            "Wealthsimple portfolio fetch is not implemented. "
            "Use PaperBroker or implement an official API connector."
        )

    def execute(self, *, intents: list[OrderIntent], latest_price_by_ticker: dict[str, float]) -> None:
        raise NotImplementedError(
            "Wealthsimple live execution is intentionally disabled. "
            "Export order intents to CSV for manual execution, or implement an official broker API connector."
        )


def export_order_intents_csv(intents: list[OrderIntent], *, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["ticker", "action", "quantity", "limit_price", "confidence", "expected_edge", "estimated_fees"],
        )
        w.writeheader()
        for it in intents:
            w.writerow(it.model_dump())

