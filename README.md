# Forex Signal Pro

A real-time forex signal system that combines **news sentiment**, **economic calendar risk**, and **multi-timeframe trend consensus** (the same voting logic as your Pine Script "Multi-Timeframe Trend Dashboard Pro") into one BUY / SELL / NEUTRAL / STAND ASIDE signal per pair — served on a live web dashboard, with Telegram push alerts.

> ⚠️ Not financial advice. This is a decision-support tool, not an auto-trader. Always confirm signals with your own analysis before risking capital.

---

## What it does

- **News engine** — pulls headlines from free RSS feeds (ForexLive, FXStreet, Investing.com, DailyFX), scores each headline with VADER sentiment plus a forex-specific lexicon (hawkish/dovish, rate hikes/cuts, risk-on/off), and filters relevance per currency pair.
- **Economic calendar engine** — pulls the weekly economic calendar (NFP, CPI, central bank decisions) from ForexFactory's public feed, flags high-impact events, and tells the signal engine to **stand aside** if a major release is imminent (spreads widen and price gets unreliable right around news).
- **Trend engine** — for each pair, evaluates 5 timeframes (15m/30m/1h/4h/1d) using 4 methods (EMA crossover, Supertrend, ADX+EMA filter, VWAP bias), then takes a majority vote per timeframe and an overall consensus — same structure as your TradingView indicator.
- **Signal engine** — combines trend (65% weight) + news sentiment (35% weight) into a final confidence score, and overrides everything with "STAND ASIDE" around high-impact news.
- **Dashboard** — live-updating web UI (dark trading-terminal aesthetic) showing signal cards, live news feed, and the calendar.
- **Telegram notifier** — sends a push alert only when a pair's signal *changes*, so you're not spammed every refresh cycle.

## Project structure

```
forex-signal-pro/
├── backend/
│   ├── main.py                 # FastAPI app + background refresh scheduler
│   ├── static/index.html       # Dashboard (single file, no build step)
│   └── engines/
│       ├── news_engine.py      # RSS fetch + sentiment scoring
│       ├── calendar_engine.py  # Economic calendar fetch + risk flagging
│       ├── trend_engine.py     # Multi-timeframe trend consensus
│       ├── signal_engine.py    # Combines everything into final signal
│       └── notifier.py         # Telegram alerts
├── requirements.txt
└── README.md
```

## Setup

```bash
cd forex-signal-pro
pip install -r requirements.txt
```

### Run it

```bash
uvicorn backend.main:app --reload --port 8000
```

Open **http://localhost:8000** — the dashboard loads immediately and refreshes every 30 seconds in the browser (the backend itself re-pulls news/calendar/price data every 5 minutes, configurable via `REFRESH_INTERVAL_SECONDS` in `main.py`).

### Telegram alerts (optional)

1. Message **@BotFather** on Telegram → `/newbot` → copy the token it gives you.
2. Message **@userinfobot** to get your numeric chat ID.
3. Set environment variables before running:

```bash
export TELEGRAM_BOT_TOKEN="123456:ABC-your-token"
export TELEGRAM_CHAT_ID="123456789"
uvicorn backend.main:app --reload --port 8000
```

You'll get a message like this whenever a pair's signal changes:

```
🟢 EURUSD → BUY
Confidence: 62.4%
Trend: BULL (80.0%)
News: bullish (0.31)
Trend consensus BULL (80.0% of timeframes) aligned with positive news sentiment (0.31).
```

## API endpoints

| Endpoint | Returns |
|---|---|
| `GET /api/signals` | All 8 pairs' current signals |
| `GET /api/signals/{pair}` | e.g. `/api/signals/EURUSD` |
| `GET /api/news` | Latest scored headlines |
| `GET /api/calendar` | Upcoming economic events |
| `GET /api/status` | System health, Telegram config status |
| `POST /api/refresh` | Force an immediate data refresh |

Pairs tracked: `EURUSD, GBPUSD, USDJPY, USDCHF, AUDUSD, USDCAD, NZDUSD, XAUUSD` (gold, via Yahoo Finance futures proxy `GC=F`).

## Tuning the signal logic

- **`signal_engine.py` → `SIGNAL_WEIGHTS`** — change the trend vs. news balance (defaults 65/35).
- **`signal_engine.py` → `CONFIDENCE_BUY_THRESHOLD` / `CONFIDENCE_SELL_THRESHOLD`** — how strong the combined score must be before it fires a BUY/SELL instead of NEUTRAL (default ±0.20).
- **`calendar_engine.py` → `calendar_risk_for_pair(window_hours=6.0)`** — how far ahead of a high-impact event the system goes into STAND ASIDE.
- **`news_engine.py` → `FEEDS`** — add/remove RSS sources. Add `HAWKISH_TERMS` / `DOVISH_TERMS` for sharper keyword sensitivity.
- **`trend_engine.py` → `TIMEFRAMES`** — add/remove timeframes, or change EMA/Supertrend/ADX periods to match your Pine Script settings exactly.

## Notes on data sources

Everything here runs on **free, no-API-key sources**:
- Price data: Yahoo Finance via `yfinance`
- News: public RSS feeds
- Economic calendar: ForexFactory's public JSON feed

These are fine for personal/dashboard use but aren't SLA-backed — if you want production-grade reliability, swap in a paid feed (e.g. Alpha Vantage, Finnhub, or a broker's own price API) by editing `trend_engine.py`'s `get_trend_consensus()`.

## Deploying so it's always on

For 24/7 signals (not just while your laptop is open):
- **Simplest**: a small VPS (DigitalOcean/Hetzner droplet, ~$5/mo) running `uvicorn` behind `systemd`, or in a `screen`/`tmux` session.
- Since you already deploy FastAPI to Vercel for the student portal — note Vercel's serverless functions aren't ideal for a long-running background scheduler like this one (it needs a persistent process to poll every 5 min). A small VPS or a host like Railway/Render (which supports persistent workers) is a better fit for this specific app.

## Extending further

- Add more pairs by adding entries to `PAIR_TICKERS` in `trend_engine.py` and `PAIR_CURRENCIES`/`CURRENCY_TO_PAIRS` in `news_engine.py`/`calendar_engine.py`.
- Swap the keyword-based news scoring for an LLM-based sentiment pass (e.g. call Claude on each headline batch) for more nuanced reads — happy to wire that in if you want it.
- Add a backtesting module that replays historical trend+news alignment to sanity-check the weight settings before trusting them live.
