"""
signal_engine.py
------------------
Combines:
  - Multi-timeframe trend consensus (price action)
  - News sentiment score (headlines)
  - Economic calendar risk (imminent high-impact events)
into one final signal: BUY / SELL / NEUTRAL / STAND ASIDE, with a
confidence score. Weights are tunable via SIGNAL_WEIGHTS.
"""

from dataclasses import dataclass, asdict
from typing import List, Optional

from .trend_engine import get_trend_consensus, PAIR_TICKERS
from .news_engine import NewsItem, pair_sentiment_score
from .calendar_engine import CalendarEvent, calendar_risk_for_pair

# Relative importance of each input. Must sum to 1.0 across trend+news.
SIGNAL_WEIGHTS = {
    "trend": 0.65,
    "news": 0.35,
}

CONFIDENCE_BUY_THRESHOLD = 0.20
CONFIDENCE_SELL_THRESHOLD = -0.20


@dataclass
class Signal:
    pair: str
    action: str          # BUY / SELL / NEUTRAL / STAND ASIDE
    confidence: float     # 0-100
    trend_consensus: str
    trend_strength_pct: float
    news_sentiment: float
    news_label: str
    calendar_high_risk: bool
    calendar_events: List[str]
    timeframe_votes: dict
    rationale: str


def _trend_to_score(consensus: str, strength_pct: float) -> float:
    """Map trend consensus into -1..1 score, scaled by strength."""
    if consensus == "bull":
        return strength_pct / 100
    if consensus == "bear":
        return -strength_pct / 100
    return 0.0


def build_signal(pair: str, all_news: List[NewsItem], calendar_events: List[CalendarEvent]) -> Signal:
    pair = pair.upper()

    trend = get_trend_consensus(pair)
    trend_score = _trend_to_score(trend.consensus, trend.strength_pct)

    news_score = pair_sentiment_score(pair, all_news)

    combined = (trend_score * SIGNAL_WEIGHTS["trend"]) + (news_score * SIGNAL_WEIGHTS["news"])
    confidence = round(min(100.0, abs(combined) * 100), 1)

    risk = calendar_risk_for_pair(pair, calendar_events)

    if risk["high_risk"]:
        action = "STAND ASIDE"
        rationale = (
            f"High-impact event within {risk['next_event_hours']}h "
            f"({', '.join(risk['events'][:2])}); volatility risk overrides trend/news signal."
        )
    elif combined >= CONFIDENCE_BUY_THRESHOLD:
        action = "BUY"
        rationale = (
            f"Trend consensus {trend.consensus.upper()} ({trend.strength_pct}% of timeframes) "
            f"aligned with {'positive' if news_score >= 0 else 'mixed'} news sentiment ({news_score})."
        )
    elif combined <= CONFIDENCE_SELL_THRESHOLD:
        action = "SELL"
        rationale = (
            f"Trend consensus {trend.consensus.upper()} ({trend.strength_pct}% of timeframes) "
            f"aligned with {'negative' if news_score <= 0 else 'mixed'} news sentiment ({news_score})."
        )
    else:
        action = "NEUTRAL"
        rationale = "Trend and news signals are weak or conflicting; no clear edge."

    return Signal(
        pair=pair,
        action=action,
        confidence=confidence,
        trend_consensus=trend.consensus,
        trend_strength_pct=trend.strength_pct,
        news_sentiment=news_score,
        news_label="bullish" if news_score >= 0.15 else "bearish" if news_score <= -0.15 else "neutral",
        calendar_high_risk=risk["high_risk"],
        calendar_events=risk["events"],
        timeframe_votes=trend.timeframe_votes,
        rationale=rationale,
    )


def build_all_signals(all_news: List[NewsItem], calendar_events: List[CalendarEvent]) -> List[Signal]:
    return [build_signal(pair, all_news, calendar_events) for pair in PAIR_TICKERS.keys()]
