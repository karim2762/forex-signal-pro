"""
trend_engine.py
----------------
Python port of the Multi-Timeframe Trend Dashboard logic:
- EMA Crossover
- Supertrend
- ADX + EMA filter
- VWAP bias
Combines multiple timeframes with majority-vote consensus, same spirit as
the Pine Script v6 "Multi-Timeframe Trend Dashboard Pro" indicator.
"""

import numpy as np
import pandas as pd
import yfinance as yf
from dataclasses import dataclass, field
from typing import Dict, List

# yfinance tickers for major FX pairs (Yahoo uses =X suffix)
PAIR_TICKERS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "USDCHF": "USDCHF=X",
    "AUDUSD": "AUDUSD=X",
    "USDCAD": "USDCAD=X",
    "NZDUSD": "NZDUSD=X",
    "XAUUSD": "GC=F",  # Gold futures as proxy
}

# Timeframes evaluated for consensus (interval, lookback period)
TIMEFRAMES = [
    ("15m", "5d"),
    ("30m", "5d"),
    ("1h", "1mo"),
    ("4h", "3mo"),
    ("1d", "1y"),
]


@dataclass
class TrendResult:
    pair: str
    timeframe_votes: Dict[str, str] = field(default_factory=dict)  # tf -> "bull"/"bear"/"neutral"
    bull_count: int = 0
    bear_count: int = 0
    neutral_count: int = 0
    consensus: str = "neutral"
    strength_pct: float = 0.0


def _ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def _atr(df: pd.DataFrame, length: int = 10) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / length, adjust=False).mean()


def _supertrend(df: pd.DataFrame, period: int = 10, mult: float = 3.0) -> pd.Series:
    atr = _atr(df, period)
    hl2 = (df["High"] + df["Low"]) / 2
    upper = hl2 + mult * atr
    lower = hl2 - mult * atr

    trend = pd.Series(index=df.index, dtype="object")
    direction = 1
    final_upper = upper.copy()
    final_lower = lower.copy()

    for i in range(1, len(df)):
        if df["Close"].iloc[i - 1] > final_upper.iloc[i - 1]:
            direction = 1
        elif df["Close"].iloc[i - 1] < final_lower.iloc[i - 1]:
            direction = -1

        if direction == 1 and lower.iloc[i] < final_lower.iloc[i - 1]:
            final_lower.iloc[i] = final_lower.iloc[i - 1]
        if direction == -1 and upper.iloc[i] > final_upper.iloc[i - 1]:
            final_upper.iloc[i] = final_upper.iloc[i - 1]

        trend.iloc[i] = "bull" if direction == 1 else "bear"

    trend.iloc[0] = "neutral"
    return trend


def _adx(df: pd.DataFrame, length: int = 14) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    atr = _atr(df, length)
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / length, adjust=False).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / length, adjust=False).mean() / atr
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)) * 100
    adx = dx.ewm(alpha=1 / length, adjust=False).mean()
    return adx.fillna(0)


def _vwap(df: pd.DataFrame) -> pd.Series:
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    vol = df["Volume"].replace(0, np.nan).fillna(1)
    cum_vol = vol.cumsum()
    cum_tp_vol = (typical * vol).cumsum()
    return cum_tp_vol / cum_vol


def evaluate_timeframe(df: pd.DataFrame) -> str:
    """Returns 'bull', 'bear', or 'neutral' using a 4-engine vote for one timeframe."""
    if df is None or len(df) < 30:
        return "neutral"

    votes = []

    # 1) EMA crossover (fast 9 / slow 21)
    ema_fast = _ema(df["Close"], 9)
    ema_slow = _ema(df["Close"], 21)
    votes.append("bull" if ema_fast.iloc[-1] > ema_slow.iloc[-1] else "bear")

    # 2) Supertrend
    st = _supertrend(df)
    last_st = st.dropna().iloc[-1] if not st.dropna().empty else "neutral"
    votes.append(last_st)

    # 3) ADX + EMA (trend strength filter)
    adx = _adx(df)
    ema_50 = _ema(df["Close"], 50) if len(df) >= 50 else _ema(df["Close"], len(df) // 2 or 1)
    if adx.iloc[-1] > 20:
        votes.append("bull" if df["Close"].iloc[-1] > ema_50.iloc[-1] else "bear")
    else:
        votes.append("neutral")

    # 4) VWAP bias
    vwap = _vwap(df)
    votes.append("bull" if df["Close"].iloc[-1] > vwap.iloc[-1] else "bear")

    bulls = votes.count("bull")
    bears = votes.count("bear")
    if bulls > bears:
        return "bull"
    elif bears > bulls:
        return "bear"
    return "neutral"


def get_trend_consensus(pair: str) -> TrendResult:
    ticker = PAIR_TICKERS.get(pair.upper())
    result = TrendResult(pair=pair.upper())
    if not ticker:
        return result

    for interval, period in TIMEFRAMES:
        try:
            data = yf.Ticker(ticker).history(period=period, interval=interval)
            vote = evaluate_timeframe(data)
        except Exception:
            vote = "neutral"
        result.timeframe_votes[interval] = vote

    result.bull_count = list(result.timeframe_votes.values()).count("bull")
    result.bear_count = list(result.timeframe_votes.values()).count("bear")
    result.neutral_count = list(result.timeframe_votes.values()).count("neutral")

    total = len(TIMEFRAMES)
    if result.bull_count > result.bear_count:
        result.consensus = "bull"
        result.strength_pct = round(result.bull_count / total * 100, 1)
    elif result.bear_count > result.bull_count:
        result.consensus = "bear"
        result.strength_pct = round(result.bear_count / total * 100, 1)
    else:
        result.consensus = "neutral"
        result.strength_pct = round(result.neutral_count / total * 100, 1)

    return result
