"""engines/institutional_proxy.py — Institutional Flow Proxy
JPM Collar levels, CTA positioning, ETF premium/discount.
"""
import math
import numpy as np
import pandas as pd


def analyze_institutional(ticker, prices, vix=20.0):
    """Proxy institutional flow signals."""
    s = prices.get(ticker)
    if s is None or len(s) < 50:
        return {"ok": False, "error": "No price data"}

    try:
        s_clean = pd.to_numeric(s, errors="coerce").dropna()
        spot = float(s_clean.iloc[-1])
        sma50 = float(s_clean.tail(50).mean())
        sma200 = float(s_clean.tail(200).mean()) if len(s_clean) >= 200 else sma50
    except Exception:
        return {"ok": False, "error": "Parse failed"}

    # CTA proxy: trend following positioning
    r20d = float(s_clean.iloc[-1] / s_clean.iloc[-21] - 1) if len(s_clean) >= 21 else 0
    r50d = float(s_clean.iloc[-1] / s_clean.iloc[-51] - 1) if len(s_clean) >= 51 else r20d

    cta_long = r20d > 0.05 and r50d > 0.05
    cta_short = r20d < -0.05 and r50d < -0.05

    # JPM Collar proxy: 5% OTM put, 10% OTM call
    collar_put = round(spot * 0.95, 2)
    collar_call = round(spot * 1.10, 2)
    near_collar_put = abs(spot - collar_put) / spot < 0.02
    near_collar_call = abs(spot - collar_call) / spot < 0.02

    # ETF premium/discount proxy (for index tickers)
    etf_premium = 0
    if ticker in ["SPY", "QQQ", "IWM"]:
        # Proxy: deviation from SMA20
        sma20 = float(s_clean.tail(20).mean())
        etf_premium = (spot - sma20) / sma20 if sma20 > 0 else 0

    # Insurance demand proxy from VIX term structure
    vix_elevated = vix > 22

    # Flow score
    flow_score = 0
    flow_signals = []
    if cta_long:
        flow_score += 2
        flow_signals.append("CTA LONG")
    if cta_short:
        flow_score -= 2
        flow_signals.append("CTA SHORT")
    if near_collar_put:
        flow_score += 1
        flow_signals.append("Near collar put (hedge demand)")
    if near_collar_call:
        flow_score -= 1
        flow_signals.append("Near collar call (cap demand)")
    if etf_premium > 0.01:
        flow_score += 1
        flow_signals.append("ETF premium (inflow)")
    if etf_premium < -0.01:
        flow_score -= 1
        flow_signals.append("ETF discount (outflow)")
    if vix_elevated:
        flow_score += 1
        flow_signals.append("VIX elevated (insurance buying)")

    bias = "BULLISH" if flow_score > 1 else "BEARISH" if flow_score < -1 else "NEUTRAL"

    return {
        "ok": True,
        "flow_score": flow_score,
        "bias": bias,
        "cta_position": "LONG" if cta_long else "SHORT" if cta_short else "NEUTRAL",
        "collar_put": collar_put,
        "collar_call": collar_call,
        "near_collar_put": near_collar_put,
        "near_collar_call": near_collar_call,
        "etf_premium_pct": round(etf_premium * 100, 2),
        "flow_signals": flow_signals,
        "source": "PROXY",
    }


def analyze_multi(tickers, prices, vix=20.0):
    results = {}
    for t in tickers:
        results[t] = analyze_institutional(t, prices, vix)
    return results
