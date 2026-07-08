"""
main.py
--------
FastAPI backend for Forex Signal Pro.

Run locally:
    uvicorn backend.main:app --reload --port 8000

Then open http://localhost:8000 for the dashboard.
"""

import time
from pathlib import Path
from threading import Lock

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from apscheduler.schedulers.background import BackgroundScheduler

from backend.engines import news_engine, calendar_engine, signal_engine, notifier
from backend.engines.trend_engine import PAIR_TICKERS

app = FastAPI(title="Forex Signal Pro API")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ---- In-memory cache (refreshed by background scheduler) ----
_cache = {
    "news": [],
    "calendar": [],
    "signals": [],
    "last_updated": None,
}
_lock = Lock()

REFRESH_INTERVAL_SECONDS = 300  # 5 minutes - keep well within free RSS/API rate limits


def refresh_data():
    try:
        news = news_engine.fetch_news()
        cal = calendar_engine.fetch_calendar()
        signals = signal_engine.build_all_signals(news, cal)

        with _lock:
            _cache["news"] = news
            _cache["calendar"] = cal
            _cache["signals"] = signals
            _cache["last_updated"] = time.time()

        for s in signals:
            notifier.notify_if_changed(s)
    except Exception as e:
        print(f"[refresh_data] error: {e}")


scheduler = BackgroundScheduler()
scheduler.add_job(refresh_data, "interval", seconds=REFRESH_INTERVAL_SECONDS, next_run_time=None)


@app.on_event("startup")
def startup():
    refresh_data()  # populate cache immediately on boot
    scheduler.start()


@app.get("/")
def root():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/signals")
def get_signals():
    with _lock:
        return {
            "last_updated": _cache["last_updated"],
            "signals": [s.__dict__ for s in _cache["signals"]],
        }


@app.get("/api/signals/{pair}")
def get_signal(pair: str):
    with _lock:
        for s in _cache["signals"]:
            if s.pair == pair.upper():
                return s.__dict__
    return {"error": f"No data for {pair.upper()}. Supported: {list(PAIR_TICKERS.keys())}"}


@app.get("/api/news")
def get_news():
    with _lock:
        return {
            "last_updated": _cache["last_updated"],
            "news": [n.__dict__ for n in _cache["news"][:60]],
        }


@app.get("/api/calendar")
def get_calendar():
    with _lock:
        events = _cache["calendar"]
    high_impact = calendar_engine.upcoming_high_impact(events, window_hours=48)
    return {
        "last_updated": _cache["last_updated"],
        "high_impact_upcoming": [e.__dict__ for e in high_impact],
        "all_events": [e.__dict__ for e in events],
    }


@app.get("/api/status")
def get_status():
    return {
        "last_updated": _cache["last_updated"],
        "telegram_configured": notifier.is_configured(),
        "pairs_tracked": list(PAIR_TICKERS.keys()),
        "refresh_interval_seconds": REFRESH_INTERVAL_SECONDS,
    }


@app.post("/api/refresh")
def force_refresh():
    refresh_data()
    return {"status": "refreshed", "last_updated": _cache["last_updated"]}
