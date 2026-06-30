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

## Quickstart (API)

```bash
uvicorn wealthsimple_agent.api.main:app --reload --port 8000
```

Then call:
- `GET /health`
- `POST /signals`

## Safety / important notes

- This code is **educational scaffolding**, not financial advice.
- You must validate **fees, spreads, FX**, and **slippage** for your account/instruments.
- If you pursue automated execution, confirm **legal/compliance** requirements in your jurisdiction.
