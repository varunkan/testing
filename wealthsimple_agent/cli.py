from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

import typer
from rich import print as rprint

from wealthsimple_agent.backtest import run_daily_backtest
from wealthsimple_agent.config import get_settings
from wealthsimple_agent.engine import AgentDependencies, build_order_intents, build_signals, empty_portfolio
from wealthsimple_agent.fees import FeeModel
from wealthsimple_agent.market.yfinance_provider import fetch_daily_bars, latest_close
from wealthsimple_agent.news.rss import fetch_rss
from wealthsimple_agent.risk import RiskLimits
from wealthsimple_agent.broker.paper import PaperBroker


app = typer.Typer(add_completion=False, help="Wealthsimple Trading Agent (signals + paper trading).")


def _deps() -> AgentDependencies:
    s = get_settings()
    return AgentDependencies(
        settings=s,
        fee_model=FeeModel(fee_per_trade=s.fee_per_trade, fee_pct_notional=s.fee_pct_notional),
        risk_limits=RiskLimits(
            max_position_pct_of_equity=s.max_position_pct_of_equity,
            per_trade_risk_pct=s.per_trade_risk_pct,
            max_daily_loss_pct=s.max_daily_loss_pct,
        ),
    )


@app.command()
def signals(
    tickers: list[str] = typer.Option(..., "--tickers", help="Tickers like AAPL MSFT"),
    news_rss: list[str] = typer.Option(None, "--news-rss", help="RSS feed URL(s) to ingest"),
    lookback_days: Optional[int] = typer.Option(None, "--lookback-days", min=5, max=365),
    starting_cash: float = typer.Option(10_000.0, "--starting-cash", min=1.0),
    pretty: bool = typer.Option(True, "--pretty/--no-pretty"),
):
    deps = _deps()
    lookback = lookback_days or deps.settings.default_lookback_days
    tickers = [t.strip().upper() for t in tickers if t and t.strip()]

    bars_by_ticker = fetch_daily_bars(tickers, lookback_days=lookback)

    items = []
    for url in news_rss or []:
        try:
            items.extend(fetch_rss(url))
        except Exception:
            continue
    news_by_ticker = {t: items for t in tickers}

    sigs = build_signals(
        tickers=tickers,
        price_bars_by_ticker=bars_by_ticker,
        news_by_ticker=news_by_ticker,
        deps=deps,
    )
    latest_px = {t: latest_close(bars_by_ticker.get(t, [])) for t in tickers}
    latest_px = {k: v for k, v in latest_px.items() if v is not None}

    portfolio = empty_portfolio(starting_cash=starting_cash)
    intents = build_order_intents(signals=sigs, portfolio=portfolio, latest_price_by_ticker=latest_px, deps=deps)

    payload = {
        "as_of": datetime.now(tz=timezone.utc).isoformat(),
        "signals": [s.model_dump() for s in sigs],
        "order_intents": [i.model_dump() for i in intents],
    }

    if pretty:
        rprint(json.dumps(payload, indent=2))
    else:
        print(json.dumps(payload))


@app.command("paper-run")
def paper_run(
    tickers: list[str] = typer.Option(..., "--tickers"),
    news_rss: list[str] = typer.Option(None, "--news-rss"),
    lookback_days: Optional[int] = typer.Option(None, "--lookback-days", min=5, max=365),
    starting_cash: float = typer.Option(10_000.0, "--starting-cash", min=1.0),
):
    deps = _deps()
    lookback = lookback_days or deps.settings.default_lookback_days
    tickers = [t.strip().upper() for t in tickers if t and t.strip()]

    bars_by_ticker = fetch_daily_bars(tickers, lookback_days=lookback)
    latest_px = {t: latest_close(bars_by_ticker.get(t, [])) for t in tickers}
    latest_px = {k: v for k, v in latest_px.items() if v is not None}

    items = []
    for url in news_rss or []:
        try:
            items.extend(fetch_rss(url))
        except Exception:
            continue
    news_by_ticker = {t: items for t in tickers}

    broker = PaperBroker(starting_cash=starting_cash, fee_model=deps.fee_model, slippage_bps=deps.settings.slippage_bps)
    portfolio = broker.get_portfolio(latest_price_by_ticker=latest_px)
    sigs = build_signals(
        tickers=tickers,
        price_bars_by_ticker=bars_by_ticker,
        news_by_ticker=news_by_ticker,
        deps=deps,
    )
    intents = build_order_intents(signals=sigs, portfolio=portfolio, latest_price_by_ticker=latest_px, deps=deps)

    broker.execute(intents=intents, latest_price_by_ticker=latest_px)
    new_portfolio = broker.get_portfolio(latest_price_by_ticker=latest_px)

    rprint(
        json.dumps(
            {
                "signals": [s.model_dump() for s in sigs],
                "order_intents": [i.model_dump() for i in intents],
                "portfolio_before": portfolio.model_dump(),
                "portfolio_after": new_portfolio.model_dump(),
                "realized_pnl": broker.realized_pnl,
                "trades": broker.trades,
            },
            indent=2,
        )
    )


@app.command()
def backtest(
    tickers: list[str] = typer.Option(..., "--tickers"),
    lookback_days: Optional[int] = typer.Option(None, "--lookback-days", min=5, max=365),
    starting_cash: float = typer.Option(10_000.0, "--starting-cash", min=1.0),
):
    deps = _deps()
    tickers = [t.strip().upper() for t in tickers if t and t.strip()]
    res = run_daily_backtest(tickers=tickers, deps=deps, starting_cash=starting_cash, lookback_days=lookback_days)
    rprint(
        json.dumps(
            {
                "start_equity": res.start_equity,
                "end_equity": res.end_equity,
                "total_return_pct": res.total_return_pct,
                "max_drawdown_pct": res.max_drawdown_pct,
                "num_trades": res.num_trades,
                "realized_pnl": res.realized_pnl,
            },
            indent=2,
        )
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()

