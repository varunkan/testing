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
from wealthsimple_agent.portal.runner import DEFAULT_UNIVERSE, PortalConfig, run_daily
from wealthsimple_agent.portal.store import Store


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


portal_app = typer.Typer(add_completion=False, help="Daily recommendation portal (paper trading).")
app.add_typer(portal_app, name="portal")


@portal_app.command("daily")
def portal_daily(
    daily_budget: float = typer.Option(100.0, "--daily-budget", min=1.0),
    monthly_target_pct: float = typer.Option(0.30, "--monthly-target-pct", min=0.0, max=2.0),
    take_profit_pct: float = typer.Option(0.03, "--take-profit-pct", min=0.001),
    stop_loss_pct: float = typer.Option(0.02, "--stop-loss-pct", min=0.001),
    max_hold_days: int = typer.Option(5, "--max-hold-days", min=1, max=30),
    max_new_buys: int = typer.Option(3, "--max-new-buys", min=1, max=10),
    min_confidence: float = typer.Option(0.6, "--min-confidence", min=0.0, max=1.0),
    universe: list[str] = typer.Option(None, "--universe", help="Tickers to consider"),
    rss_url: list[str] = typer.Option(None, "--rss-url", help="RSS feed URL(s)"),
    db_path: str = typer.Option("portal.db", "--db-path"),
):
    cfg = PortalConfig(
        daily_budget=daily_budget,
        monthly_target_pct=monthly_target_pct,
        take_profit_pct=take_profit_pct,
        stop_loss_pct=stop_loss_pct,
        max_hold_days=max_hold_days,
        max_new_buys_per_day=max_new_buys,
        min_confidence_to_buy=min_confidence,
        universe=[t.strip().upper() for t in (universe or DEFAULT_UNIVERSE) if t.strip()],
        rss_urls=list(rss_url or []),
    )
    with Store(db_path) as store:
        report = run_daily(cfg=cfg, store=store)
    rprint(json.dumps(report.as_dict(), indent=2))


@portal_app.command("monthly")
def portal_monthly(
    year_month: str = typer.Option(..., "--month", help="YYYY-MM"),
    daily_budget: float = typer.Option(100.0, "--daily-budget", min=1.0),
    db_path: str = typer.Option("portal.db", "--db-path"),
):
    from wealthsimple_agent.portal.monthly import compute_monthly_progress

    with Store(db_path) as store:
        realized = store.realized_pnl_in_month(year_month=year_month)
        days_run = store.days_run_in_month(year_month=year_month)
        progress = compute_monthly_progress(
            year_month=year_month,
            daily_budget=daily_budget,
            target_pct=0.30,
            planned_trading_days=21,
            realized_pnl=realized,
            days_run=days_run,
        )
        trades = store.trades_in_month(year_month=year_month)
    rprint(
        json.dumps(
            {
                "progress": progress.as_dict(),
                "trades": trades,
                "disclaimer": "Target is aspirational and not guaranteed. Trading involves risk of loss.",
            },
            indent=2,
        )
    )


@portal_app.command("history")
def portal_history(
    day: str = typer.Option(..., "--day", help="YYYY-MM-DD"),
    db_path: str = typer.Option("portal.db", "--db-path"),
):
    from datetime import date as _date

    with Store(db_path) as store:
        recs = store.recommendations_for_day(day=_date.fromisoformat(day))
    rprint(json.dumps(recs, indent=2))


def main() -> None:
    app()


if __name__ == "__main__":
    main()

