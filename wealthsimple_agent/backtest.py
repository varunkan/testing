from __future__ import annotations

from dataclasses import dataclass

from wealthsimple_agent.broker.paper import PaperBroker
from wealthsimple_agent.engine import AgentDependencies, build_order_intents
from wealthsimple_agent.market.yfinance_provider import fetch_daily_bars
from wealthsimple_agent.models import PriceBar
from wealthsimple_agent.strategy.baseline import generate_signal


@dataclass(frozen=True)
class BacktestResult:
    start_equity: float
    end_equity: float
    total_return_pct: float
    max_drawdown_pct: float
    num_trades: int
    realized_pnl: float


def _max_drawdown(equity_curve: list[float]) -> float:
    peak = None
    mdd = 0.0
    for v in equity_curve:
        if peak is None or v > peak:
            peak = v
        if peak and peak > 0:
            dd = (peak - v) / peak
            mdd = max(mdd, dd)
    return mdd


def run_daily_backtest(
    *,
    tickers: list[str],
    deps: AgentDependencies,
    starting_cash: float = 10_000.0,
    lookback_days: int | None = None,
) -> BacktestResult:
    """
    Minimal daily-bar backtest on recent history fetched via yfinance.
    News is not replayed historically here (useful extension point).
    """
    lookback = int(lookback_days or deps.settings.default_lookback_days)
    # Pull enough history to have multiple decision points.
    bars_by_ticker = fetch_daily_bars(tickers, lookback_days=max(lookback * 6, 90))

    broker = PaperBroker(
        starting_cash=starting_cash,
        fee_model=deps.fee_model,
        slippage_bps=deps.settings.slippage_bps,
    )

    # Align days by the first ticker that has bars.
    any_bars = next((v for v in bars_by_ticker.values() if v), [])
    days = [b.day for b in any_bars]
    equity_curve: list[float] = []

    for i in range(len(days)):
        day = days[i]
        latest_px: dict[str, float] = {}
        window_by_ticker: dict[str, list[PriceBar]] = {}

        for t in tickers:
            bars = bars_by_ticker.get(t, [])
            bars = [b for b in bars if b.day <= day]
            if not bars:
                continue
            latest_px[t] = float(bars[-1].close)
            window_by_ticker[t] = bars[max(0, len(bars) - lookback) :]

        portfolio = broker.get_portfolio(latest_price_by_ticker=latest_px)

        # Generate per-ticker signals from the rolling window.
        signals = [
            generate_signal(ticker=t, bars=window_by_ticker.get(t, []), news=[])
            for t in tickers
        ]
        intents = build_order_intents(
            signals=signals,
            portfolio=portfolio,
            latest_price_by_ticker=latest_px,
            deps=deps,
        )
        broker.execute(intents=intents, latest_price_by_ticker=latest_px)
        equity_curve.append(broker.get_portfolio(latest_price_by_ticker=latest_px).equity)

    start_equity = float(starting_cash)
    end_equity = float(equity_curve[-1]) if equity_curve else float(starting_cash)
    total_return_pct = (end_equity / start_equity - 1.0) if start_equity else 0.0

    return BacktestResult(
        start_equity=start_equity,
        end_equity=end_equity,
        total_return_pct=total_return_pct,
        max_drawdown_pct=_max_drawdown(equity_curve),
        num_trades=len(broker.trades),
        realized_pnl=float(broker.realized_pnl),
    )

