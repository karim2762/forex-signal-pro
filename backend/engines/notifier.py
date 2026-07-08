"""
notifier.py
------------
Sends signal alerts to Telegram. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
as environment variables (see README). Only fires when a pair's action
CHANGES from its last known state, so you don't get spammed every refresh.
"""

import os
import requests

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Tracks last-notified action per pair so we only alert on change
_last_notified = {}


def _send_telegram(text: str) -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, data={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "Markdown"
        }, timeout=8)
        return resp.ok
    except Exception:
        return False


def notify_if_changed(signal) -> bool:
    """signal is a signal_engine.Signal instance. Returns True if a notification was sent."""
    prev = _last_notified.get(signal.pair)
    if prev == signal.action:
        return False  # no change, stay quiet

    _last_notified[signal.pair] = signal.action

    if signal.action == "NEUTRAL":
        return False  # don't notify on neutral, only actionable/risk states

    emoji = {"BUY": "🟢", "SELL": "🔴", "STAND ASIDE": "⚠️"}.get(signal.action, "ℹ️")
    text = (
        f"{emoji} *{signal.pair}* → *{signal.action}*\n"
        f"Confidence: {signal.confidence}%\n"
        f"Trend: {signal.trend_consensus.upper()} ({signal.trend_strength_pct}%)\n"
        f"News: {signal.news_label} ({signal.news_sentiment})\n"
        f"_{signal.rationale}_"
    )
    return _send_telegram(text)


def is_configured() -> bool:
    return bool(BOT_TOKEN and CHAT_ID)
