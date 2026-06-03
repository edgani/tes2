"""engines/vanna_charm_flows.py — Cem Karsan Vanna + Charm Extension
Standalone module to avoid greeks_proxy.py import conflicts.
"""
from __future__ import annotations
import math, logging
from typing import Dict
import pandas as pd
import numpy as np

logger = logging.getLogger("vanna_charm")

def _vanna_proxy(ticker: str, prices: Dict[str, pd.Series], vix: float, dxy_ret: float = 0.0) -> Dict:
    """Proxy vanna = dDelta/dIV. Key driver of vol-reset rallies."""
    s = prices.get(ticker)
    if s is None or len(s) < 22:
        return {"ok": False}
    try:
        s_clean = pd.to_numeric(s, errors="coerce").dropna()
        if len(s_clean) < 22:
            return {"ok": False}
        px = float(s_clean.iloc[-1])
        sma20 = float(s_clean.tail(20).mean())
        rets = s_clean.tail(20).pct_change().dropna()
        vol_of_rets = rets.std() if len(rets) > 1 else 0.001
        iv_proxy = vol_of_rets * math.sqrt(252) * 100
        iv_chg = iv_proxy - 15.0
        delta_shift = (px - sma20) / sma20 if sma20 != 0 else 0
        vanna_score = delta_shift * iv_chg * 10
        if vanna_score > 2.0:
            regime = "POSITIVE_VANNA"
            note = "IV drop → dealer buyback → self-fulfilling rally"
        elif vanna_score < -2.0:
            regime = "NEGATIVE_VANNA"
            note = "IV spike → dealer sell → pressure"
        else:
            regime = "NEUTRAL_VANNA"
            note = "Vanna flows balanced"
        return {
            "ok": True,
            "vanna_score": round(vanna_score, 2),
            "iv_proxy": round(iv_proxy, 2),
            "iv_change": round(iv_chg, 2),
            "delta_shift": round(delta_shift, 4),
            "regime": regime,
            "note": note,
            "color": "#3FB950" if "POSITIVE" in regime else "#F85149" if "NEGATIVE" in regime else "#8B949E",
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

def _charm_proxy(ticker: str, prices: Dict[str, pd.Series], days_to_expiry: int = 7) -> Dict:
    """Proxy charm = dDelta/dTime. Key driver of expiration drift/pin."""
    s = prices.get(ticker)
    if s is None or len(s) < 10:
        return {"ok": False}
    try:
        s_clean = pd.to_numeric(s, errors="coerce").dropna()
        if len(s_clean) < 10:
            return {"ok": False}
        time_factor = max(0.1, min(3.0, 30.0 / max(days_to_expiry, 1)))
        r5d = float(s_clean.iloc[-1] / s_clean.iloc[-6] - 1) if len(s_clean) >= 6 else 0
        r10d = float(s_clean.iloc[-1] / s_clean.iloc[-11] - 1) if len(s_clean) >= 11 else 0
        charm_flow = (r5d - r10d / 2) * time_factor * 100
        if charm_flow > 1.5:
            regime = "CHARM_BUY"
            note = "Delta decay → dealer unwind shorts → drift higher into expiry"
        elif charm_flow < -1.5:
            regime = "CHARM_SELL"
            note = "Delta decay → dealer unwind longs → drift lower into expiry"
        else:
            regime = "CHARM_NEUTRAL"
            note = "Minimal expiration drift"
        return {
            "ok": True,
            "charm_flow": round(charm_flow, 2),
            "time_factor": round(time_factor, 2),
            "days_to_expiry": days_to_expiry,
            "regime": regime,
            "note": note,
            "color": "#3FB950" if "BUY" in regime else "#F85149" if "SELL" in regime else "#8B949E",
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

def get_vanna_charm_flows(ticker: str, prices: Dict[str, pd.Series],
                          vix: float = 20.0, dxy_ret: float = 0.0,
                          days_to_expiry: int = 7) -> Dict:
    """Combined Vanna + Charm analysis for a ticker."""
    vanna = _vanna_proxy(ticker, prices, vix, dxy_ret)
    charm = _charm_proxy(ticker, prices, days_to_expiry)
    combined_score = 0
    if vanna.get("ok"):
        combined_score += vanna.get("vanna_score", 0) * 0.6
    if charm.get("ok"):
        combined_score += charm.get("charm_flow", 0) * 0.4
    if combined_score > 2.5:
        signal = "NEVER_SHORT_EXPIRATION"
        color = "#3FB950"
    elif combined_score < -2.5:
        signal = "AVOID_LONG_EXPIRATION"
        color = "#F85149"
    else:
        signal = "NEUTRAL"
        color = "#8B949E"
    return {
        "vanna": vanna,
        "charm": charm,
        "combined_score": round(combined_score, 2),
        "combined_signal": signal,
        "combined_color": color,
        "cem_quote": "Never short into options expiration." if "NEVER_SHORT" in signal else None,
    }
