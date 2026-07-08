"""
news_engine.py
---------------
Pulls forex-relevant headlines from free public RSS feeds and scores each
headline for sentiment using VADER plus a forex-specific keyword lexicon
(hawkish/dovish, rate hikes/cuts, inflation, risk-on/off, etc).

No paid API key required. Add more feeds to FEEDS as you like.
"""

import feedparser
import time
from dataclasses import dataclass, field
from typing import List
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

FEEDS = {
    "ForexLive": "https://www.forexlive.com/feed/news",
    "FXStreet": "https://www.fxstreet.com/rss/news",
    "Investing.com FX": "https://www.investing.com/rss/news_1.rss",
    "DailyFX": "https://www.dailyfx.com/feeds/all",
}

# Forex-specific lexicon boosts. Positive = bullish for the base/quote currency
# mentioned; VADER alone misses finance-specific jargon so we nudge scores.
HAWKISH_TERMS = ["hawkish", "rate hike", "raises rates", "tightening", "inflation surge",
                  "strong jobs", "rate increase", "higher for longer"]
DOVISH_TERMS = ["dovish", "rate cut", "cuts rates", "easing", "recession", "weak jobs",
                 "stimulus", "rate decrease", "slowdown"]
RISK_OFF_TERMS = ["war", "conflict", "crisis", "sell-off", "selloff", "crash", "geopolitical tension"]
RISK_ON_TERMS = ["rally", "risk appetite", "optimism", "record high", "strong growth"]

_analyzer = SentimentIntensityAnalyzer()

PAIR_CURRENCIES = {
    "EURUSD": ["EUR", "ECB", "euro", "eurozone"],
    "GBPUSD": ["GBP", "BOE", "bank of england", "pound", "sterling"],
    "USDJPY": ["JPY", "BOJ", "bank of japan", "yen"],
    "USDCHF": ["CHF", "SNB", "swiss", "franc"],
    "AUDUSD": ["AUD", "RBA", "australian dollar", "aussie"],
    "USDCAD": ["CAD", "BOC", "bank of canada", "loonie"],
    "NZDUSD": ["NZD", "RBNZ", "kiwi", "new zealand dollar"],
    "XAUUSD": ["gold", "XAU", "bullion"],
}

ALWAYS_RELEVANT = ["fed", "federal reserve", "fomc", "powell", "usd", "dollar", "treasury", "cpi", "nfp"]


@dataclass
class NewsItem:
    source: str
    title: str
    link: str
    published: str
    sentiment_score: float  # -1 (very bearish) to +1 (very bullish), for USD-centric framing
    label: str  # bullish / bearish / neutral
    tags: List[str] = field(default_factory=list)


def _score_headline(title: str) -> float:
    text = title.lower()
    base = _analyzer.polarity_scores(title)["compound"]  # -1..1 general sentiment

    boost = 0.0
    for term in HAWKISH_TERMS:
        if term in text:
            boost += 0.25
    for term in DOVISH_TERMS:
        if term in text:
            boost -= 0.25
    for term in RISK_OFF_TERMS:
        if term in text:
            boost -= 0.15
    for term in RISK_ON_TERMS:
        if term in text:
            boost += 0.15

    score = max(-1.0, min(1.0, base * 0.5 + boost))
    return round(score, 3)


def _label(score: float) -> str:
    if score >= 0.15:
        return "bullish"
    if score <= -0.15:
        return "bearish"
    return "neutral"


def fetch_news(limit_per_feed: int = 12) -> List[NewsItem]:
    items: List[NewsItem] = []
    for source, url in FEEDS.items():
        try:
            parsed = feedparser.parse(url)
            for entry in parsed.entries[:limit_per_feed]:
                title = entry.get("title", "").strip()
                if not title:
                    continue
                score = _score_headline(title)
                published = entry.get("published", entry.get("updated", ""))
                items.append(NewsItem(
                    source=source,
                    title=title,
                    link=entry.get("link", ""),
                    published=published,
                    sentiment_score=score,
                    label=_label(score),
                ))
        except Exception:
            continue
    return items


def news_for_pair(pair: str, all_news: List[NewsItem]) -> List[NewsItem]:
    """Filter fetched news to items relevant to a given currency pair."""
    keywords = [k.lower() for k in PAIR_CURRENCIES.get(pair.upper(), [])] + ALWAYS_RELEVANT
    relevant = []
    for item in all_news:
        text = item.title.lower()
        if any(k in text for k in keywords):
            relevant.append(item)
    return relevant


def pair_sentiment_score(pair: str, all_news: List[NewsItem]) -> float:
    """Average sentiment of relevant headlines, -1..1. 0 if no relevant news found."""
    relevant = news_for_pair(pair, all_news)
    if not relevant:
        return 0.0
    return round(sum(i.sentiment_score for i in relevant) / len(relevant), 3)
