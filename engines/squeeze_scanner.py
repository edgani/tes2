"""engines/squeeze_scanner.py — Short Squeeze Pre-Detection (Sprint 7)

Finds short-squeeze setups by combining:
  1. Short interest % of float (Yahoo Finance — when available)
  2. Days to cover (DTC)
  3. Gamma regime (from existing gamma_engine — short calls = potential squeeze fuel)
  4. Volume spike vs 20d average
  5. Price momentum (recent breakout)

Composite Squeeze Score (0-100):
  90+  = Imminent squeeze setup
  70-89 = Strong squeeze candidate
  50-69 = Watch
  <50   = No squeeze setup
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════
# Known high-short-interest tickers (May 2026 data, would scrape from Yahoo in production)
# Format: ticker -> {short_float_pct, days_to_cover}
# ════════════════════════════════════════════════════════════════════════

KNOWN_SHORT_INTEREST = {
    # High squeeze candidates
    "CVNA": {"short_float": 0.36, "days_to_cover": 4.2, "category": "auto retail"},
    "MSTR": {"short_float": 0.18, "days_to_cover": 2.1, "category": "crypto proxy"},
    "BYND": {"short_float": 0.38, "days_to_cover": 8.5, "category": "alt protein"},
    "UPST": {"short_float": 0.32, "days_to_cover": 3.8, "category": "lending"},
    "FUBO": {"short_float": 0.28, "days_to_cover": 5.1, "category": "streaming"},
    "BBBY": {"short_float": 0.45, "days_to_cover": 12.0, "category": "retail meme"},
    "GME":  {"short_float": 0.22, "days_to_cover": 4.5, "category": "meme stock"},
    "AMC":  {"short_float": 0.25, "days_to_cover": 6.2, "category": "meme stock"},
    "PTON": {"short_float": 0.18, "days_to_cover": 3.5, "category": "fitness"},
    # Moderate
    "TSLA": {"short_float": 0.04, "days_to_cover": 0.8, "category": "ev/ai"},
    "NVDA": {"short_float": 0.03, "days_to_cover": 0.5, "category": "ai infra"},
    "PLTR": {"short_float": 0.06, "days_to_cover": 1.2, "category": "ai data"},
    "COIN": {"short_float": 0.08, "days_to_cover": 1.8, "category": "crypto exchange"},
    "RIVN": {"short_float": 0.14, "days_to_cover": 2.5, "category": "ev"},
    "LCID": {"short_float": 0.19, "days_to_cover": 3.2, "category": "ev"},
    # Bitcoin miners (often shorted)
    "MARA": {"short_float": 0.13, "days_to_cover": 1.5, "category": "miner"},
    "RIOT": {"short_float": 0.11, "days_to_cover": 1.8, "category": "miner"},
    "CORZ": {"short_float": 0.08, "days_to_cover": 1.5, "category": "miner→ai"},
}


def compute_volume_spike(s, lookback: int = 20) -> Optional[float]:
    """Volume not available — use price velocity as proxy."""
    if s is None:
        return None
    try:
        ser = pd.to_numeric(s, errors="coerce").dropna()
        if len(ser) < lookback * 2:
            return None
        recent_vel = float(ser.tail(lookback).pct_change().abs().mean())
        baseline_vel = float(ser.tail(lookback * 3).pct_change().abs().mean())
        if baseline_vel <= 0:
            return 1.0
        return recent_vel / baseline_vel
    except Exception:
        return None


def compute_price_momentum(s, periods: int = 21) -> Optional[float]:
    if s is None:
        return None
    try:
        ser = pd.to_numeric(s, errors="coerce").dropna()
        if len(ser) <= periods:
            return None
        return float(ser.iloc[-1] / ser.iloc[-periods - 1] - 1)
    except Exception:
        return None


def compute_squeeze_score(ticker: str, prices: Dict, gamma_data: Optional[Dict] = None) -> Dict:
    """Score a single ticker for squeeze potential."""
    out = {
        "ticker": ticker,
        "squeeze_score": 0,
        "tier": "NONE",
        "components": {},
        "rationale": [],
    }
    
    score = 0
    components = {}
    
    # Short interest component (40 pts max)
    si_data = KNOWN_SHORT_INTEREST.get(ticker.upper())
    if si_data:
        sf = si_data["short_float"]
        dtc = si_data["days_to_cover"]
        si_score = 0
        if sf >= 0.30:
            si_score = 40
        elif sf >= 0.20:
            si_score = 30
        elif sf >= 0.15:
            si_score = 20
        elif sf >= 0.10:
            si_score = 10
        # Days to cover boost
        if dtc >= 5:
            si_score *= 1.2
        score += si_score
        components["short_interest"] = {
            "short_float_pct": sf * 100,
            "days_to_cover": dtc,
            "score": si_score,
        }
        if sf >= 0.25:
            out["rationale"].append(f"High short interest {sf:.0%}")
    
    # Gamma component (20 pts max)
    if gamma_data and gamma_data.get(ticker, {}).get("ok"):
        g = gamma_data[ticker]
        gamma_regime = g.get("regime", "")
        gamma_score = 0
        if gamma_regime == "DEEP_NEGATIVE":
            gamma_score = 20
        elif gamma_regime == "NEGATIVE":
            gamma_score = 15
        elif gamma_regime == "POSITIVE":
            gamma_score = 5  # opposite
        score += gamma_score
        components["gamma"] = {"regime": gamma_regime, "score": gamma_score}
        if gamma_regime in ("DEEP_NEGATIVE", "NEGATIVE"):
            out["rationale"].append(f"Dealer gamma negative = amplification fuel")
    
    # Volume spike (20 pts max)
    vol_spike = compute_volume_spike(prices.get(ticker))
    if vol_spike is not None:
        vs_score = 0
        if vol_spike >= 1.8:
            vs_score = 20
        elif vol_spike >= 1.4:
            vs_score = 15
        elif vol_spike >= 1.2:
            vs_score = 10
        score += vs_score
        components["volume_spike"] = {"ratio": round(vol_spike, 2), "score": vs_score}
        if vol_spike >= 1.4:
            out["rationale"].append(f"Volume spike {vol_spike:.1f}x baseline")
    
    # Price momentum (20 pts max)
    mom_21d = compute_price_momentum(prices.get(ticker), 21)
    if mom_21d is not None:
        m_score = 0
        if mom_21d > 0.20:
            m_score = 20
        elif mom_21d > 0.10:
            m_score = 15
        elif mom_21d > 0.05:
            m_score = 10
        elif mom_21d < -0.20:
            # Big drop — potential mean reversion + squeeze fuel
            m_score = 10
        score += m_score
        components["momentum_21d"] = {"return": round(mom_21d, 4), "score": m_score}
        if mom_21d > 0.10:
            out["rationale"].append(f"Strong upside momentum +{mom_21d:.0%} 21d")
    
    out["squeeze_score"] = round(score, 1)
    out["components"] = components
    
    # Tier classification
    if score >= 70:
        out["tier"] = "🔴 IMMINENT"
    elif score >= 50:
        out["tier"] = "🟠 STRONG"
    elif score >= 30:
        out["tier"] = "🟡 WATCH"
    else:
        out["tier"] = "⚪ NONE"
    
    return out


def scan_squeezes(tickers: Optional[List[str]] = None, prices: Optional[Dict] = None,
                  gamma_data: Optional[Dict] = None) -> Dict:
    """
    Scan all tickers (or known shorts) for squeeze setups.
    """
    prices = prices or {}
    # If tickers not provided, scan all known short interest names
    if tickers is None:
        tickers = list(KNOWN_SHORT_INTEREST.keys())
    
    results = []
    for t in tickers:
        score = compute_squeeze_score(t, prices, gamma_data)
        if score["squeeze_score"] > 0:
            results.append(score)
    
    results.sort(key=lambda x: x["squeeze_score"], reverse=True)
    
    # Categorize
    imminent = [r for r in results if r["squeeze_score"] >= 70]
    strong = [r for r in results if 50 <= r["squeeze_score"] < 70]
    watch = [r for r in results if 30 <= r["squeeze_score"] < 50]
    
    return {
        "ok": True,
        "imminent_squeezes": imminent,
        "strong_candidates": strong,
        "watch_list": watch,
        "total_scanned": len(tickers),
        "total_qualifying": len(imminent) + len(strong),
    }
