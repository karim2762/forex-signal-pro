"""
calendar_engine.py
--------------------
Fetches the weekly economic calendar (NFP, CPI, rate decisions, etc.) from
ForexFactory's public JSON feed - no API key needed. If that feed is ever
unreachable, this degrades gracefully to an empty list rather than crashing
the app.
"""

import requests
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List

CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

CURRENCY_TO_PAIRS = {
    "USD": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD", "XAUUSD"],
    "EUR": ["EURUSD"],
    "GBP": ["GBPUSD"],
    "JPY": ["USDJPY"],
    "CHF": ["USDCHF"],
    "AUD": ["AUDUSD"],
    "CAD": ["USDCAD"],
    "NZD": ["NZDUSD"],
}


@dataclass
class CalendarEvent:
    title: str
    country: str
    date: str
    impact: str  # High / Medium / Low
    forecast: str
    previous: str
    hours_away: float


def fetch_calendar() -> List[CalendarEvent]:
    events: List[CalendarEvent] = []
    try:
        resp = requests.get(CALENDAR_URL, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        raw = resp.json()
        now = datetime.now(timezone.utc)
        for e in raw:
            try:
                event_date = datetime.fromisoformat(e.get("date", "").replace("Z", "+00:00"))
            except Exception:
                continue
            hours_away = round((event_date - now).total_seconds() / 3600, 1)
            events.append(CalendarEvent(
                title=e.get("title", ""),
                country=e.get("country", ""),
                date=e.get("date", ""),
                impact=e.get("impact", "Low"),
                forecast=str(e.get("forecast", "")),
                previous=str(e.get("previous", "")),
                hours_away=hours_away,
            ))
    except Exception:
        return []
    return events


def upcoming_high_impact(events: List[CalendarEvent], window_hours: float = 24.0) -> List[CalendarEvent]:
    """High-impact events within the next `window_hours` (or that just passed, -2h)."""
    return [
        e for e in events
        if e.impact.lower() == "high" and -2.0 <= e.hours_away <= window_hours
    ]


def calendar_risk_for_pair(pair: str, events: List[CalendarEvent], window_hours: float = 6.0) -> dict:
    """
    Returns a risk flag for a pair based on imminent high-impact events for
    the currencies involved. Used to dampen/withhold signals around news
    events, since price action gets unreliable and spreads widen.
    """
    relevant_currencies = [c for c, pairs in CURRENCY_TO_PAIRS.items() if pair.upper() in pairs]
    imminent = [
        e for e in events
        if e.country in relevant_currencies and e.impact.lower() == "high"
        and -0.5 <= e.hours_away <= window_hours
    ]
    return {
        "high_risk": len(imminent) > 0,
        "events": [e.title for e in imminent],
        "next_event_hours": min([e.hours_away for e in imminent], default=None),
    }
