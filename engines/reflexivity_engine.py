"""engines/reflexivity_engine.py — Soros Reflexivity & Super-Bubble Tracker"""
from __future__ import annotations
import math, logging
from typing import Dict, Optional
import pandas as pd
import numpy as np

logger = logging.getLogger("reflexivity")

def _price_momentum(ticker: str, prices: Dict[str, pd.Series], days: int = 63) -> Optional[float]:
    s = prices.get(ticker)
    if s is None or len(s) < days + 1:
        return None
    try:
        s_clean = pd.to_numeric(s, errors="coerce").dropna()
        if len(s_clean) < days + 1:
            return None
        return float(s_clean.iloc[-1] / s_clean.iloc[-(days + 1)] - 1)
    except Exception:
        return None

def _credit_proxy(fred: Dict[str, pd.Series]) -> Dict:
    hyoas = fred.get("HYOAS")
    dgs10 = fred.get("DGS10")
    fedfunds = fred.get("FEDFUNDS")
    out = {"tightening": 0.0, "credit_spread": 3.5, "real_rate": 2.0}
    if hyoas is not None and not hyoas.empty:
        try:
            out["credit_spread"] = float(hyoas.dropna().iloc[-1])
        except Exception:
            pass
    if dgs10 is not None and not dgs10.empty:
        try:
            out["real_rate"] = float(dgs10.dropna().iloc[-1])
        except Exception:
            pass
    if fedfunds is not None and not fedfunds.empty:
        try:
            out["tightening"] = float(fedfunds.dropna().iloc[-1])
        except Exception:
            pass
    out["tightening_score"] = max(0, min(10, out["tightening"] / 0.5))
    out["stress_score"] = max(0, min(10, (out["credit_spread"] - 2.0)))
    return out

def run_reflexivity(prices: Dict[str, pd.Series], fred: Dict[str, pd.Series],
                    quad: str = "Q3") -> Dict:
    credit = _credit_proxy(fred)
    spy_mom = _price_momentum("SPY", prices, 63) or 0.0
    qqq_mom = _price_momentum("QQQ", prices, 63) or 0.0
    iwm_mom = _price_momentum("IWM", prices, 63) or 0.0
    avg_mom = (spy_mom + qqq_mom + iwm_mom) / 3
    divergence = avg_mom * 10 - credit["stress_score"]
    bubble_score = credit["tightening_score"] + credit["stress_score"] + max(0, avg_mom * 5)
    bubble_score = min(10, bubble_score)

    if bubble_score > 7 and avg_mom > 0.15:
        stage = "MOMENT_OF_TRUTH"; stage_color = "#F85149"
    elif bubble_score > 5 and avg_mom > 0.08:
        stage = "ACCELERATION"; stage_color = "#D29922"
    elif bubble_score > 4:
        stage = "TEST"; stage_color = "#D29922"
    elif avg_mom < -0.05 and bubble_score > 3:
        stage = "REVERSAL"; stage_color = "#3FB950"
    else:
        stage = "INCEPTION" if avg_mom > 0 else "TWILIGHT"
        stage_color = "#8B949E"

    scores = {}
    for t in ["SPY", "QQQ", "IWM", "GLD", "TLT", "BTC-USD", "ETH-USD"]:
        mom = _price_momentum(t, prices, 21) or 0.0
        mom_3m = _price_momentum(t, prices, 63) or 0.0
        score = min(1.0, max(-1.0, mom * 5 - credit["stress_score"] * 0.1))
        scores[t] = {
            "momentum_1m": round(mom, 4),
            "momentum_3m": round(mom_3m, 4),
            "reflexivity_score": round(score, 2),
            "divergence": "PRICE_AHEAD" if score > 0.3 else "FUNDAMENT_AHEAD" if score < -0.3 else "ALIGNED",
        }

    return {
        "super_bubble_score": round(bubble_score, 1),
        "super_bubble_max": 10,
        "credit_conditions": credit,
        "avg_equity_momentum_3m": round(avg_mom, 4),
        "divergence_index": round(divergence, 2),
        "stage": stage,
        "stage_color": stage_color,
        "stage_desc": {
            "INCEPTION": "Trend forming, misconception small",
            "ACCELERATION": "Trend & misconception reinforcing",
            "TEST": "Negative feedback testing strength",
            "MOMENT_OF_TRUTH": "Belief vs reality gap too wide",
            "TWILIGHT": "Doubts grow, inertia sustains",
            "REVERSAL": "Trend reverses, forced liquidation",
        }.get(stage, ""),
        "ticker_scores": scores,
        "alert": f"Reflexivity stage: {stage} (score {bubble_score}/10)" if bubble_score > 6 else None,
    }
