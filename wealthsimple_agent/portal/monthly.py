from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MonthlyProgress:
    year_month: str
    daily_budget: float
    planned_trading_days: int
    target_pct: float
    target_profit: float
    realized_pnl: float
    progress_pct: float
    days_run: int

    def as_dict(self) -> dict:
        return {
            "year_month": self.year_month,
            "daily_budget": self.daily_budget,
            "planned_trading_days": self.planned_trading_days,
            "target_pct": self.target_pct,
            "target_profit": self.target_profit,
            "realized_pnl": self.realized_pnl,
            "progress_pct": self.progress_pct,
            "days_run": self.days_run,
        }


def compute_monthly_progress(
    *,
    year_month: str,
    daily_budget: float,
    target_pct: float,
    planned_trading_days: int,
    realized_pnl: float,
    days_run: int,
) -> MonthlyProgress:
    """
    Maps an aspirational monthly target (e.g. 30%) onto a concrete dollar goal.

    NOTE: `target_pct` is an ASPIRATIONAL target, not a guarantee.
    The dollar goal is target_pct * (daily_budget * planned_trading_days).
    """
    target_profit = float(target_pct) * float(daily_budget) * int(planned_trading_days)
    progress_pct = (float(realized_pnl) / target_profit) if target_profit > 0 else 0.0
    return MonthlyProgress(
        year_month=year_month,
        daily_budget=float(daily_budget),
        planned_trading_days=int(planned_trading_days),
        target_pct=float(target_pct),
        target_profit=float(target_profit),
        realized_pnl=float(realized_pnl),
        progress_pct=float(progress_pct),
        days_run=int(days_run),
    )
