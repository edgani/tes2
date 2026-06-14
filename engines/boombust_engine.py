"""engines/boombust_engine.py — Soros Boom-Bust Stage Classifier"""
from __future__ import annotations
import math, logging
from typing import Dict, List
import pandas as pd
import numpy as np

logger = logging.getLogger("boombust")

def classify_stage(prices: Dict[str, pd.Series], fred: Dict[str, pd.Series],
                   health: Dict, quad: str) -> Dict:
    spy_s = prices.get("SPY")
    vix_s = prices.get("^VIX")
    breadth_adv = 0
    breadth_dec = 0
    us_tickers = ["SPY", "QQQ", "IWM", "XLF", "XLE", "XLK", "XLV", "XLI", "XLU", "GLD", "TLT"]

    for t in us_tickers:
        s = prices.get(t)
        if s is not None and len(s) >= 22:
            try:
                s_clean = pd.to_numeric(s, errors="coerce").dropna()
                if len(s_clean) >= 22:
                    r = float(s_clean.iloc[-1] / s_clean.iloc[-22] - 1)
                    if r > 0.005:
                        breadth_adv += 1
                    elif r < -0.005:
                        breadth_dec += 1
            except Exception:
                pass

    total_b = breadth_adv + breadth_dec
    breadth_ratio = breadth_adv / total_b if total_b > 0 else 0.5

    spy_mom_1m = 0.0
    spy_mom_2m = 0.0
    if spy_s is not None and len(spy_s) >= 45:
        try:
            s_clean = pd.to_numeric(spy_s, errors="coerce").dropna()
            if len(s_clean) >= 45:
                spy_mom_1m = float(s_clean.iloc[-1] / s_clean.iloc[-22] - 1)
                spy_mom_2m = float(s_clean.iloc[-22] / s_clean.iloc[-45] - 1)
        except Exception:
            pass
    acceleration = spy_mom_1m - spy_mom_2m

    vol_expanding = False
    if vix_s is not None and len(vix_s) >= 22:
        try:
            v_clean = pd.to_numeric(vix_s, errors="coerce").dropna()
            if len(v_clean) >= 22:
                v1 = float(v_clean.tail(5).mean())
                v2 = float(v_clean.tail(20).mean())
                vol_expanding = v1 > v2 * 1.15
        except Exception:
            pass

    hyoas = fred.get("HYOAS")
    credit_stress = 0.0
    if hyoas is not None and not hyoas.empty:
        try:
            credit_stress = float(hyoas.dropna().iloc[-1])
        except Exception:
            pass

    score_map = {
        "INCEPTION": 0, "ACCELERATION": 0, "TEST": 0, "SURVIVAL": 0,
        "MOMENT_OF_TRUTH": 0, "TWILIGHT": 0, "TIP_POINT": 0, "CRISIS": 0,
    }

    if abs(spy_mom_1m) < 0.05 and not vol_expanding and breadth_ratio > 0.5:
        score_map["INCEPTION"] += 2
    if acceleration > 0.02 and breadth_ratio > 0.6:
        score_map["ACCELERATION"] += 3
    if spy_mom_1m < 0 and breadth_ratio > 0.5 and not vol_expanding:
        score_map["TEST"] += 2
    if spy_mom_1m > 0 and not vol_expanding and credit_stress < 4:
        score_map["SURVIVAL"] += 2
    if abs(spy_mom_1m) > 0.10 and breadth_ratio < 0.5 and vol_expanding:
        score_map["MOMENT_OF_TRUTH"] += 3
    if abs(spy_mom_1m) < 0.03 and vol_expanding and credit_stress > 4:
        score_map["TWILIGHT"] += 3
    if acceleration < -0.03 and vol_expanding:
        score_map["TIP_POINT"] += 3
    if spy_mom_1m < -0.10 and vol_expanding and credit_stress > 6:
        score_map["CRISIS"] += 4

    stage = max(score_map, key=score_map.get)
    conf = score_map[stage] / max(1, sum(score_map.values()))

    descriptions = {
        "INCEPTION": "Trend forming, misconception small, supply/demand balanced",
        "ACCELERATION": "Trend & misconception reinforcing, positive feedback loop",
        "TEST": "Negative feedback tests trend strength, shakeout",
        "SURVIVAL": "Trend survives test, reinforced further, vol compresses",
        "MOMENT_OF_TRUTH": "Belief vs reality gap too wide, divergence peaks",
        "TWILIGHT": "Doubts grow, more people lose faith, inertia sustains price",
        "TIP_POINT": "Trend reverses, becomes self-reinforcing downward",
        "CRISIS": "Forced liquidation of unsound positions, bust is short & steep",
    }

    return {
        "stage": stage,
        "stage_confidence": round(conf, 2),
        "descriptions": descriptions,
        "current_description": descriptions.get(stage, ""),
        "indicators": {
            "spy_momentum_1m": round(spy_mom_1m, 4),
            "acceleration": round(acceleration, 4),
            "breadth_ratio": round(breadth_ratio, 2),
            "vol_expanding": vol_expanding,
            "credit_stress": round(credit_stress, 2),
        },
        "next_likely": _next_stage(stage),
        "time_in_stage_estimate": "1-3 months" if stage in ["INCEPTION", "TEST"] else "3-6 months",
        "asymmetric_shape": "Boom long & slow, bust short & steep" if stage in ["TWILIGHT", "TIP_POINT", "CRISIS"] else "Accumulation phase",
    }

def _next_stage(stage: str) -> str:
    flow = {
        "INCEPTION": "ACCELERATION", "ACCELERATION": "TEST", "TEST": "SURVIVAL",
        "SURVIVAL": "MOMENT_OF_TRUTH", "MOMENT_OF_TRUTH": "TWILIGHT",
        "TWILIGHT": "TIP_POINT", "TIP_POINT": "CRISIS", "CRISIS": "INCEPTION",
    }
    return flow.get(stage, "UNKNOWN")
