# Wealthsimple Trading Agent (Signals + Paper Trading)

This repository scaffolds a **trading agent** that:

- Ingests **market news** (RSS/news feeds) and **price history**
- Produces **trade signals** with a **confidence score**
- Allocates a **daily budget** based on confidence and risk limits
- Simulates execution via a **paper broker** and computes **P&L after fees**

It intentionally **does not place live orders on Wealthsimple** by default.
Wealthsimple execution is implemented as a **stub connector** because fully automated trading requires an **official, supported broker API**.

## What you can do today

- Run the agent locally to generate **buy/sell intents**
- Run **paper trading** and a simple **daily-bar backtest**
- Export order intents for manual execution
- Run the **daily recommendation portal**: every morning it deploys a fixed budget (e.g. $100/day) across ranked buy ideas, manages exits (take-profit / stop-loss / time), and tracks **monthly progress toward an aspirational target**
- Use the **Forge Desk iOS app** (`ios/`) — SwiftUI UI for goals, morning tickets, and monthly progress (demo mode works offline)

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip3 install -r requirements.txt
```

## Quickstart (CLI)

```bash
python3 -m wealthsimple_agent.cli signals --tickers AAPL MSFT --news-rss "https://feeds.finance.yahoo.com/rss/2.0/headline?s=AAPL&region=US&lang=en-US"
python3 -m wealthsimple_agent.cli paper-run --tickers AAPL MSFT --starting-cash 10000
```

### Daily recommendation portal

Run one portal day (deploys the daily budget, records recommendations + paper trades in `portal.db`):

```bash
python3 -m wealthsimple_agent.cli portal daily --daily-budget 100 --universe AAPL MSFT GOOGL
```

Check monthly progress (realized P&L vs aspirational target):

```bash
python3 -m wealthsimple_agent.cli portal monthly --month 2026-07 --daily-budget 100
```

See what was recommended on a given day:

```bash
python3 -m wealthsimple_agent.cli portal history --day 2026-07-01
```

## iOS app (Forge Desk)

SwiftUI client for the portal. See [`ios/README.md`](ios/README.md).

```bash
cd ios
brew install xcodegen   # once
./bootstrap_xcode.sh
open ForgeDesk.xcodeproj
```

Demo mode is on by default (no backend required). To use live recommendations, run the API above and point Settings → API base URL at it.
## Quickstart (API)

```bash
uvicorn wealthsimple_agent.api.main:app --reload --port 8000
```

Then call:
- `GET /health`
- `POST /signals`
- `POST /portal/daily` — run one portal trading day
- `GET /portal/recommendations/{day}` — recommendations for a day
- `GET /portal/trades/{year_month}` — trades for a month
- `GET /portal/monthly/{year_month}` — monthly progress toward target

## How the daily portal works

Each portal day:
1. Adds the **daily budget** (e.g. $100) to deployable cash.
2. Evaluates **exits** on existing positions: take-profit, stop-loss, and time-based exits.
3. Ranks **buy signals** from the configured universe by confidence + edge.
4. Allocates today's budget across the top buys (confidence-weighted, fee/slippage-buffered).
5. Executes sells first (frees cash), then buys via the paper broker.
6. Persists broker state, recommendations, and trades to SQLite (`portal.db`).
7. Reports **monthly progress** toward the aspirational target.

The monthly target is computed as `target_pct × daily_budget × planned_trading_days`
(e.g. 30% × $100 × 21 days = $630). Progress is `realized_pnl / target_profit`.

## Safety / important notes

- This code is **educational scaffolding**, not financial advice.
- **Profit targets are aspirational and not guaranteed.** Trading involves risk of loss;
  a 30%/month goal is extremely aggressive and unlikely to be achieved consistently.
- You must validate **fees, spreads, FX**, and **slippage** for your account/instruments.
- The portal runs in **paper trading** mode. Live automated execution on Wealthsimple is
  **not supported** without an official, sanctioned broker API (see `broker/wealthsimple.py`).
- If you pursue automated execution, confirm **legal/compliance** requirements in your jurisdiction.
