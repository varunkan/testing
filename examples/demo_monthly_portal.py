"""
End-to-end demo of the daily recommendation portal.

Simulates ~21 trading days with synthetic price history (no network required),
runs the portal each morning with a $100 daily budget, and prints performance
toward the aspirational DOUBLE (100%) monthly goal ($2,100 on $100 x 21 days).

Run:
    PYTHONPATH=. python3 examples/demo_monthly_portal.py
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from wealthsimple_agent.models import PriceBar
from wealthsimple_agent.portal.runner import PortalConfig, run_daily
from wealthsimple_agent.portal.store import Store


UNIVERSE = ["AAPL", "NVDA", "MSFT"]
START = date(2026, 7, 1)
TRADING_DAYS = 21


def synth_bars(ticker: str, up_to_day: date, *, drift: float, start_price: float) -> list[PriceBar]:
    """Deterministic daily bars with a per-day drift, ending on `up_to_day`."""
    bars: list[PriceBar] = []
    d = START - timedelta(days=30)
    price = start_price
    while d <= up_to_day:
        bars.append(
            PriceBar(
                ticker=ticker,
                day=d,
                open=price,
                high=price * 1.01,
                low=price * 0.99,
                close=price,
                volume=1_000_000,
            )
        )
        price = price * (1.0 + drift)
        d += timedelta(days=1)
    return bars


def main() -> None:
    db = Path("portal_demo.db")
    if db.exists():
        db.unlink()

    cfg = PortalConfig(
        daily_budget=100.0,
        monthly_target_pct=1.0,  # double
        take_profit_pct=0.03,
        stop_loss_pct=0.02,
        max_hold_days=5,
        max_new_buys_per_day=2,
        min_confidence_to_buy=0.6,
        universe=UNIVERSE,
        rss_urls=[],
    )

    drifts = {"AAPL": 0.010, "NVDA": 0.015, "MSFT": 0.0005}
    starts = {"AAPL": 100.0, "NVDA": 400.0, "MSFT": 300.0}

    day = START
    trading_day_count = 0
    print(f"=== Portal demo: ${cfg.daily_budget}/day, DOUBLE goal ({cfg.monthly_target_pct:.0%}) ===\n")

    with Store(db) as store:
        for _ in range(TRADING_DAYS):
            bars_by_ticker = {
                t: synth_bars(t, day, drift=drifts[t], start_price=starts[t]) for t in UNIVERSE
            }
            report = run_daily(
                cfg=cfg,
                store=store,
                day=day,
                bars_by_ticker=bars_by_ticker,
                news_by_ticker={t: [] for t in UNIVERSE},
            )
            trading_day_count += 1
            recs = ", ".join(f"{r.action.upper()} {r.ticker} x{r.quantity:.3f}" for r in report.recommendations)
            mp = report.monthly_progress
            print(
                f"Day {trading_day_count:2d} ({day}) | recs: {recs or '-'} | "
                f"P&L ${mp['realized_pnl']:.2f} / ${mp['target_profit']:.0f} "
                f"({mp['progress_pct']*100:.1f}% of double) | ROI {mp['roi_pct']*100:.1f}%"
            )
            day += timedelta(days=1)

        year_month = START.strftime("%Y-%m")
        realized = store.realized_pnl_in_month(year_month=year_month)
        days_run = store.days_run_in_month(year_month=year_month)

    target = cfg.monthly_target_pct * cfg.daily_budget * cfg.planned_trading_days_per_month
    print("\n=== Final performance (double goal) ===")
    print(json.dumps(
        {
            "month": year_month,
            "days_run": days_run,
            "daily_budget": cfg.daily_budget,
            "goal": "double (100% ROI on planned capital)",
            "target_profit": target,
            "realized_pnl": round(realized, 2),
            "progress_pct_of_double": round(realized / target * 100, 2) if target else 0,
            "disclaimer": "Aspirational target, not guaranteed. Paper trading only.",
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
