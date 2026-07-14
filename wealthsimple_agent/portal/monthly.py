from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MonthlyProgress:
    """
    Performance snapshot toward an aspirational monthly goal.

    Default aspirational goal is set in the portal configuration (e.g. 10× capital).
    This is NOT a guarantee — markets can lose money.
    """

    year_month: str
    daily_budget: float
    planned_trading_days: int
    target_pct: float  # 1.0 = double
    target_profit: float
    realized_pnl: float
    progress_pct: float  # realized / target_profit (toward the goal)
    days_run: int
    capital_invested: float
    roi_pct: float  # realized_pnl / capital_invested
    trades_count: int
    winning_trades: int
    win_rate: float
    equity: float
    cash: float

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
            "capital_invested": self.capital_invested,
            "roi_pct": self.roi_pct,
            "trades_count": self.trades_count,
            "winning_trades": self.winning_trades,
            "win_rate": self.win_rate,
            "equity": self.equity,
            "cash": self.cash,
            "goal_label": "10×" if abs(self.target_pct - 10.0) < 1e-9 else ("5×" if abs(self.target_pct - 5.0) < 1e-9 else ("2×" if abs(self.target_pct - 2.0) < 1e-9 else ("1×" if abs(self.target_pct - 1.0) < 1e-9 else f"{self.target_pct:.0%}"))),
            "disclaimer": "Aspirational target, not guaranteed. Past paper results do not predict future returns.",
        }


def compute_monthly_progress(
    *,
    year_month: str,
    daily_budget: float,
    target_pct: float,
    planned_trading_days: int,
    realized_pnl: float,
    days_run: int,
    capital_invested: float | None = None,
    trades_count: int = 0,
    winning_trades: int = 0,
    equity: float = 0.0,
    cash: float = 0.0,
) -> MonthlyProgress:
    """
    Maps an aspirational monthly return target onto dollars + ROI tracking.

    For "double every month", use target_pct=1.0:
      target_profit = 1.0 * (daily_budget * planned_trading_days)
      i.e. earn back 100% of planned monthly capital.
    """
    planned_capital = float(daily_budget) * int(planned_trading_days)
    invested = float(capital_invested) if capital_invested is not None else float(daily_budget) * int(days_run)
    target_profit = float(target_pct) * planned_capital
    progress_pct = (float(realized_pnl) / target_profit) if target_profit > 0 else 0.0
    roi_pct = (float(realized_pnl) / invested) if invested > 0 else 0.0
    win_rate = (float(winning_trades) / float(trades_count)) if trades_count > 0 else 0.0

    return MonthlyProgress(
        year_month=year_month,
        daily_budget=float(daily_budget),
        planned_trading_days=int(planned_trading_days),
        target_pct=float(target_pct),
        target_profit=float(target_profit),
        realized_pnl=float(realized_pnl),
        progress_pct=float(progress_pct),
        days_run=int(days_run),
        capital_invested=float(invested),
        roi_pct=float(roi_pct),
        trades_count=int(trades_count),
        winning_trades=int(winning_trades),
        win_rate=float(win_rate),
        equity=float(equity),
        cash=float(cash),
    )
