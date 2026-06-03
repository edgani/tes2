"""engines/odte_monitor.py — 0DTE Gamma & Pin Risk Monitor"""
from __future__ import annotations
import math, logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pandas as pd
import numpy as np

logger = logging.getLogger("odte_monitor")

try:
    import yfinance as yf
    _HAS_YF = True
except Exception:
    _HAS_YF = False

def _get_next_expiry() -> str:
    today = datetime.now()
    days_to_fri = (4 - today.weekday()) % 7
    if days_to_fri == 0:
        return today.strftime("%Y-%m-%d")
    nxt = today + timedelta(days=days_to_fri)
    return nxt.strftime("%Y-%m-%d")

def _calc_gamma_exposure(ticker: str, expiry: str) -> Dict:
    if not _HAS_YF:
        return {"ok": False, "error": "yfinance not available"}
    try:
        t = yf.Ticker(ticker)
        chain = t.option_chain(expiry)
        calls = chain.calls.copy()
        puts = chain.puts.copy()
        if calls.empty and puts.empty:
            return {"ok": False, "error": "Empty chain"}
        hist = t.history(period="5d")
        spot = float(hist["Close"].iloc[-1]) if not hist.empty else 100.0
        calls["dist"] = abs(calls["strike"] - spot) / spot
        puts["dist"] = abs(puts["strike"] - spot) / spot
        calls["weight"] = calls["openInterest"].fillna(0) * (1 - calls["dist"])
        puts["weight"] = puts["openInterest"].fillna(0) * (1 - puts["dist"])
        call_gamma = calls["weight"].sum()
        put_gamma = puts["weight"].sum()
        net_gamma = call_gamma - put_gamma
        total_oi = calls["openInterest"].fillna(0).sum() + puts["openInterest"].fillna(0).sum()
        near_strikes = calls[(calls["strike"] > spot * 0.99) & (calls["strike"] < spot * 1.01)]
        near_oi = near_strikes["openInterest"].fillna(0).sum()
        pin_risk = near_oi / total_oi if total_oi > 0 else 0
        all_strikes = sorted(set(calls["strike"].tolist() + puts["strike"].tolist()))
        pain_scores = []
        for s in all_strikes:
            c_oi = calls[calls["strike"] == s]["openInterest"].fillna(0).sum()
            p_oi = puts[puts["strike"] == s]["openInterest"].fillna(0).sum()
            pain = c_oi * max(0, spot - s) + p_oi * max(0, s - spot)
            pain_scores.append((s, pain))
        max_pain = min(pain_scores, key=lambda x: x[1])[0] if pain_scores else spot
        return {
            "ok": True,
            "spot": round(spot, 2),
            "net_gamma": round(net_gamma, 0),
            "total_oi": int(total_oi),
            "pin_risk": round(pin_risk, 3),
            "max_pain": round(max_pain, 2),
            "max_pain_dist": round((spot - max_pain) / spot, 4),
            "call_gamma": round(call_gamma, 0),
            "put_gamma": round(put_gamma, 0),
            "expiry": expiry,
        }
    except Exception as e:
        logger.warning(f"0DTE calc failed for {ticker}: {e}")
        return {"ok": False, "error": str(e)}

def _odte_proxy(ticker: str, prices: Dict[str, pd.Series]) -> Dict:
    s = prices.get(ticker)
    if s is None or len(s) < 20:
        return {"ok": False, "error": "No price data"}
    try:
        s_clean = pd.to_numeric(s, errors="coerce").dropna()
        if len(s_clean) < 20:
            return {"ok": False}
        spot = float(s_clean.iloc[-1])
        vol = float(s_clean.tail(20).std())
        vol_chg = float(s_clean.tail(5).std()) / float(s_clean.tail(20).std()) if s_clean.tail(20).std() > 0 else 1.0
        mean_5 = float(s_clean.tail(5).mean())
        pin_risk = 1.0 - min(1.0, abs(spot - mean_5) / (vol + 0.001))
        return {
            "ok": True,
            "spot": round(spot, 2),
            "net_gamma": round(vol_chg * 1e6, 0),
            "total_oi": 0,
            "pin_risk": round(pin_risk, 3),
            "max_pain": round(mean_5, 2),
            "max_pain_dist": round((spot - mean_5) / spot, 4),
            "call_gamma": round(vol_chg * 0.5e6, 0),
            "put_gamma": round(vol_chg * 0.5e6, 0),
            "expiry": _get_next_expiry(),
            "source": "PROXY",
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

def run_odte_monitor(tickers: List[str], prices: Dict[str, pd.Series]) -> Dict:
    expiry = _get_next_expiry()
    results = {}
    pin_tickers = []
    total_gamma = 0.0
    for t in tickers[:50]:
        res = _calc_gamma_exposure(t, expiry)
        if not res.get("ok"):
            res = _odte_proxy(t, prices)
        if res.get("ok"):
            results[t] = res
            total_gamma += abs(res.get("net_gamma", 0))
            if res.get("pin_risk", 0) > 0.35:
                pin_tickers.append(t)
    cascade = len([x for x in results.values() if x.get("pin_risk", 0) > 0.4]) >= 3
    door_ratio = min(1.0, total_gamma / 5e9) if total_gamma > 0 else 0.0
    return {
        "expiry": expiry,
        "tickers": results,
        "pin_risk_tickers": pin_tickers[:10],
        "cascade_warning": cascade,
        "door_size_ratio": round(door_ratio, 2),
        "total_gamma_exposure": round(total_gamma, 0),
        "next_expiry": expiry,
        "summary": f"0DTE {expiry}: {len(pin_tickers)} pin-risk tickers. {'⚠️ CASCADE RISK' if cascade else 'Normal flow.'}",
    }
