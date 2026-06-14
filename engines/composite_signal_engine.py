"""engines/composite_signal_engine.py — Multi-Signal Direction Engine (Sprint 6)

ROOT CAUSE FIXED: existing logic in app.py _build_consolidated_row never flips
direction even when COT/OI/Greeks contradict mean-reversion composite.

NEW METHODOLOGY:
  - Score each signal source independently (-1 to +1)
  - Weighted aggregate with regime conditioning
  - Direction can FLIP if 3+ strong contradicting signals
  - Outputs confidence + override flag + rationale

SIGNAL SOURCES (with weights):
  1. Mean reversion composite (price vs Trade range)        weight 0.20
  2. Trend signal (price vs Trend MA50)                     weight 0.20
  3. COT bias (commercial vs noncommercial positioning)     weight 0.15
  4. OI position (concentration High/Mid/Low)               weight 0.10
  5. Greeks composite (delta + vanna bias)                  weight 0.10
  6. Gamma regime (dealer positioning)                      weight 0.10
  7. News sentiment + front-run signal                      weight 0.10
  8. Quad alignment (regime-appropriate?)                   weight 0.05

OUTPUT:
  {
    "direction": "LONG" | "SHORT" | "NEUTRAL" | "AVOID",
    "confidence": 0.0-1.0,
    "score": -1.0 to +1.0,
    "flipped_from_composite": bool,  # did final direction differ from naive composite?
    "rationale": str,
    "contributing_signals": dict (signal name → score)
  }
"""
from __future__ import annotations

import math
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────
# Signal scoring helpers
# ────────────────────────────────────────────────────────────────────────

def _score_mean_reversion(price: float, trade_l: float, trade_r: float) -> float:
    """+1 = oversold (below Trade low), -1 = overbought (above Trade high)."""
    if not all(x and math.isfinite(x) for x in [price, trade_l, trade_r]):
        return 0.0
    if trade_r <= trade_l:
        return 0.0
    spread = trade_r - trade_l
    if price < trade_l:
        # Below range = oversold → bullish reversal signal
        distance = (trade_l - price) / spread
        return min(1.0, 0.5 + distance)
    elif price > trade_r:
        # Above range = overbought → bearish reversal signal
        distance = (price - trade_r) / spread
        return max(-1.0, -0.5 - distance)
    else:
        # Inside range: neutral with slight bias
        pos = (price - trade_l) / spread
        return 0.4 - pos * 0.8  # +0.4 near low, -0.4 near high


def _score_trend(price: float, sma50: Optional[float], sma200: Optional[float]) -> float:
    """+1 = strong uptrend (price above both MAs), -1 = strong downtrend."""
    if not price or not math.isfinite(price):
        return 0.0
    score = 0.0
    if sma50 and math.isfinite(sma50):
        if price > sma50:
            score += 0.5 * min(1.0, (price - sma50) / sma50 / 0.05)  # cap at +5% above
        else:
            score -= 0.5 * min(1.0, (sma50 - price) / sma50 / 0.05)
    if sma200 and math.isfinite(sma200):
        if price > sma200:
            score += 0.5 * min(1.0, (price - sma200) / sma200 / 0.10)
        else:
            score -= 0.5 * min(1.0, (sma200 - price) / sma200 / 0.10)
    return max(-1.0, min(1.0, score))


def _score_cot(cot: Dict) -> float:
    """+1 = commercials net long (smart money bullish), -1 = net short."""
    if not cot or not cot.get("ok"):
        return 0.0
    bias = (cot.get("bias", "") or "").lower()
    if "bullish" in bias:
        return 0.7
    if "bearish" in bias:
        return -0.7
    if "neutral" in bias:
        return 0.0
    return 0.0


def _score_oi(oi: Dict, position_in_range: Optional[float] = None) -> float:
    """+1 = OI at lows (accumulation), -1 = OI at highs (distribution)."""
    if not oi or not oi.get("ok"):
        return 0.0
    conc = (oi.get("concentration", "") or "").lower()
    if "high at lows" in conc or "accumulat" in conc:
        return 0.5
    if "high at highs" in conc or "distribut" in conc:
        return -0.5
    pos = position_in_range if position_in_range is not None else oi.get("position_in_range", 0.5)
    try:
        pos = float(pos)
    except Exception:
        return 0.0
    # Position in range: 0.0 = at lows (bullish reversal), 1.0 = at highs (bearish reversal)
    return (0.5 - pos) * 0.6  # ±0.3 max from position


def _score_greeks(greek: Dict, gamma: Dict) -> float:
    """+1 = bullish greeks (positive vanna + dealer long gamma), -1 = bearish."""
    score = 0.0
    if greek and greek.get("ok"):
        comp = (greek.get("composite", "") or "").upper()
        if "BULLISH" in comp:
            score += 0.4
        elif "BEARISH" in comp:
            score -= 0.4
        delta = (greek.get("delta", "") or "").lower()
        if "long" in delta or "positive" in delta:
            score += 0.2
        elif "short" in delta or "negative" in delta:
            score -= 0.2
    if gamma and gamma.get("ok"):
        regime = (gamma.get("regime", "") or "").upper()
        if regime in ("DEEP_POSITIVE", "POSITIVE"):
            score += 0.2
        elif regime in ("DEEP_NEGATIVE", "NEGATIVE"):
            score -= 0.2
    return max(-1.0, min(1.0, score))


def _score_news(news: Dict) -> float:
    """+1 = strong bullish news, -1 = strong bearish news."""
    if not news:
        return 0.0
    signal = (news.get("front_run_signal", "") or "").upper()
    sentiment = news.get("sentiment_score", 0) or 0
    score = 0.0
    if "STRONG_BULLISH" in signal or "BULLISH_CLUSTER" in signal or "MOMENTUM_BUILDING" in signal:
        score += 0.6
    if "STRONG_BEARISH" in signal or "NEGATIVE_HEADLINE" in signal:
        score -= 0.6
    if "RUMOR_BULLISH" in signal or "RUMOR" in signal and sentiment > 0:
        score += 0.3
    if "RUMOR_BEARISH" in signal or "RUMOR" in signal and sentiment < 0:
        score -= 0.3
    if sentiment:
        try:
            sentiment = float(sentiment)
            score += sentiment * 0.3
        except Exception:
            pass
    return max(-1.0, min(1.0, score))


def _score_quad_alignment(direction_hypothesis: str, ticker: str, quad: str,
                          market_type: str = "us_equity") -> float:
    """
    Score whether direction aligns with Quad regime playbook.
    +1 = aligned, -1 = fighting the regime.
    """
    # Regime playbook (Hedgeye)
    q1_longs = {"QQQ", "SPY", "XLK", "XLC", "XLY", "ARKK", "MAGS", "NVDA", "AAPL", "MSFT",
                "GOOGL", "META", "AMZN", "AMD", "AVGO", "BTC-USD", "ETH-USD"}
    q1_shorts = {"XLU", "XLP", "TLT", "GLD"}
    q2_longs = {"XLF", "XLE", "XLI", "XLB", "KRE", "IWM", "XOM", "CVX", "OXY", "FCX"}
    q2_shorts = {"TLT", "IEF"}
    q3_longs = {"GLD", "SLV", "GDX", "GDXJ", "USO", "XLE", "XLP", "XLU", "XOM"}
    q3_shorts = {"QQQ", "XLK", "XLY", "IWM", "ARKK", "MAGS"}
    q4_longs = {"TLT", "IEF", "GLD", "XLU", "XLP", "XLV"}
    q4_shorts = {"QQQ", "XLK", "IWM", "XLY", "XLF", "XLE", "BTC-USD", "ARKK"}

    playbook = {
        "Q1": (q1_longs, q1_shorts),
        "Q2": (q2_longs, q2_shorts),
        "Q3": (q3_longs, q3_shorts),
        "Q4": (q4_longs, q4_shorts),
    }
    longs, shorts = playbook.get(quad, (set(), set()))

    if direction_hypothesis == "LONG":
        if ticker in longs:
            return 0.8
        if ticker in shorts:
            return -0.6  # fighting regime
        return 0.0
    elif direction_hypothesis == "SHORT":
        if ticker in shorts:
            return 0.8
        if ticker in longs:
            return -0.6
        return 0.0
    return 0.0


# ────────────────────────────────────────────────────────────────────────
# MAIN: Composite signal engine
# ────────────────────────────────────────────────────────────────────────

WEIGHTS = {
    "mean_reversion": 0.20,
    "trend": 0.20,
    "cot": 0.15,
    "oi": 0.10,
    "greeks": 0.10,
    "gamma": 0.05,
    "news": 0.10,
    "quad_align": 0.10,
}

# Confidence thresholds for final direction
THRESHOLD_STRONG = 0.45        # |score| > this = STRONG signal
THRESHOLD_MODERATE = 0.20      # |score| > this = MODERATE
THRESHOLD_NEUTRAL = 0.10       # |score| < this = NEUTRAL


def compute_composite_signal(
    ticker: str,
    price: float,
    trade_l: float,
    trade_r: float,
    sma50: Optional[float] = None,
    sma200: Optional[float] = None,
    cot: Optional[Dict] = None,
    oi: Optional[Dict] = None,
    greek: Optional[Dict] = None,
    gamma: Optional[Dict] = None,
    news: Optional[Dict] = None,
    quad: str = "Q3",
    market_type: str = "us_equity",
) -> Dict:
    """
    Returns:
      {
        "direction": "LONG"|"SHORT"|"NEUTRAL"|"AVOID",
        "confidence": 0..1,
        "score": -1..+1 (negative = bearish, positive = bullish),
        "flipped_from_composite": bool,
        "naive_composite": "bullish"|"bearish"|"neutral",
        "rationale": str,
        "contributing_signals": dict,
      }
    """
    # Score each signal
    scores = {
        "mean_reversion": _score_mean_reversion(price, trade_l, trade_r),
        "trend": _score_trend(price, sma50, sma200),
        "cot": _score_cot(cot or {}),
        "oi": _score_oi(oi or {}),
        "greeks": _score_greeks(greek or {}, gamma or {}),
        "gamma": 0.0,  # Already inside greeks
        "news": _score_news(news or {}),
    }

    # Determine naive direction first (just from mean reversion)
    naive_score = scores["mean_reversion"]
    if naive_score > 0.1:
        naive_dir = "bullish"
    elif naive_score < -0.1:
        naive_dir = "bearish"
    else:
        naive_dir = "neutral"

    # Compute quad alignment based on naive direction hypothesis
    naive_hypothesis = "LONG" if naive_score > 0 else ("SHORT" if naive_score < 0 else "NEUTRAL")
    scores["quad_align"] = _score_quad_alignment(naive_hypothesis, ticker, quad, market_type)

    # Weighted aggregate
    total_score = sum(scores[k] * WEIGHTS[k] for k in WEIGHTS)
    total_score = max(-1.0, min(1.0, total_score))

    # Final direction
    if abs(total_score) < THRESHOLD_NEUTRAL:
        direction = "NEUTRAL"
        confidence = 1.0 - abs(total_score) / THRESHOLD_NEUTRAL
    elif total_score > 0:
        direction = "LONG"
        confidence = min(1.0, total_score / THRESHOLD_STRONG)
    else:
        direction = "SHORT"
        confidence = min(1.0, abs(total_score) / THRESHOLD_STRONG)

    # Check if direction FLIPPED from naive composite
    flipped = False
    if naive_dir == "bullish" and direction == "SHORT":
        flipped = True
    elif naive_dir == "bearish" and direction == "LONG":
        flipped = True

    # Count strong contradictions
    contradictions = []
    if direction == "LONG":
        for k, v in scores.items():
            if v < -0.3:
                contradictions.append(k)
    elif direction == "SHORT":
        for k, v in scores.items():
            if v > 0.3:
                contradictions.append(k)

    # AVOID if too many contradictions
    if len(contradictions) >= 3:
        direction = "AVOID"
        confidence *= 0.5

    # Rationale
    top_signals = sorted(scores.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
    top_str = ", ".join([f"{k}={v:+.2f}" for k, v in top_signals if abs(v) > 0.1])
    rationale = f"Score {total_score:+.2f} (conf {confidence:.0%}). Top: {top_str}."
    if flipped:
        rationale = f"⚠️ FLIPPED from {naive_dir}: " + rationale
    if contradictions:
        rationale += f" Contradictions: {', '.join(contradictions)}."

    return {
        "direction": direction,
        "confidence": round(confidence, 3),
        "score": round(total_score, 3),
        "flipped_from_composite": flipped,
        "naive_composite": naive_dir,
        "rationale": rationale,
        "contributing_signals": {k: round(v, 3) for k, v in scores.items()},
        "contradictions": contradictions,
        "is_strong": abs(total_score) >= THRESHOLD_STRONG,
    }


# ────────────────────────────────────────────────────────────────────────
# Convenience batch wrapper
# ────────────────────────────────────────────────────────────────────────

def analyze_multi(
    tickers: List[str],
    risk_ranges: Dict,
    prices: Dict,
    cot_data: Optional[Dict] = None,
    oi_data: Optional[Dict] = None,
    greeks_data: Optional[Dict] = None,
    gamma_data: Optional[Dict] = None,
    news_data: Optional[Dict] = None,
    quad: str = "Q3",
) -> Dict[str, Dict]:
    """Batch compute composite signals for multiple tickers."""
    ar = risk_ranges.get("asset_ranges", {})
    results = {}

    for ticker in tickers:
        rr = ar.get(ticker, {})
        if not rr:
            continue
        price = rr.get("px") or rr.get("price")
        trade = rr.get("trade", {})
        trade_l = trade.get("lrr")
        trade_r = trade.get("trr")

        # Get MAs from price series for trend signal
        sma50 = sma200 = None
        s = prices.get(ticker)
        if s is not None:
            try:
                ser = pd.to_numeric(s, errors="coerce").dropna()
                if len(ser) >= 50:
                    sma50 = float(ser.tail(50).mean())
                if len(ser) >= 200:
                    sma200 = float(ser.tail(200).mean())
                elif len(ser) >= 100:
                    sma200 = float(ser.tail(100).mean())
            except Exception:
                pass

        market_type = rr.get("market", "us_equity")
        cot = (cot_data or {}).get(ticker, {}) if cot_data else {}
        oi = (oi_data or {}).get(ticker, {}) if oi_data else {}
        greek = (greeks_data or {}).get(ticker, {}) if greeks_data else {}
        gamma = (gamma_data or {}).get(ticker, {}) if gamma_data else {}
        news = (news_data or {}).get(ticker, {}) if news_data else {}

        results[ticker] = compute_composite_signal(
            ticker, price, trade_l, trade_r,
            sma50=sma50, sma200=sma200,
            cot=cot, oi=oi, greek=greek, gamma=gamma, news=news,
            quad=quad, market_type=market_type,
        )

    return results
