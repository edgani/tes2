"""engines/odte_enhanced.py — Enhanced 0DTE Monitor
Pin probability, anchor levels, test levels, straddle range.
"""
import math
import numpy as np
import pandas as pd


def analyze_0dte(ticker, prices, vix=20.0):
    """Analyze 0DTE (or nearest expiry) options structure."""
    s = prices.get(ticker)
    if s is None or len(s) < 20:
        return {"ok": False, "error": "No price data"}

    try:
        s_clean = pd.to_numeric(s, errors="coerce").dropna()
        spot = float(s_clean.iloc[-1])
        sma20 = float(s_clean.tail(20).mean())
        std20 = float(s_clean.tail(20).std())
    except Exception:
        return {"ok": False, "error": "Price parse failed"}

    # Max Pain = SMA20
    max_pain = round(sma20, 2)
    max_pain_dist = round((spot - sma20) / sma20, 4) if sma20 != 0 else 0

    # Pin probability: higher when price near max pain and low vol
    dist_to_max_pain = abs(spot - sma20) / sma20 if sma20 != 0 else 1
    vol_env = vix / 100.0
    pin_prob = max(0, min(1, 0.7 - dist_to_max_pain * 5 - vol_env * 2))

    # Anchor: where price likely gravitates (charm magnetic effect)
    # Proxy: nearest round strike to max pain
    strike_step = 1.0 if spot > 100 else 0.5 if spot > 50 else 0.25
    anchor = round(max_pain / strike_step) * strike_step

    # Test levels: support/resistance from gamma concentration
    call_wall = round(sma20 + std20 * 2.0, 2)
    put_wall = round(sma20 - std20 * 2.0, 2)

    # Straddle range: expected move
    daily_vol = std20 / sma20 if sma20 > 0 else 0.02
    straddle = round(sma20 * daily_vol * math.sqrt(1), 2)

    # Pin risk flag
    pin_risk = pin_prob > 0.6

    return {
        "ok": True,
        "spot": round(spot, 2),
        "max_pain": max_pain,
        "max_pain_dist": max_pain_dist,
        "pin_probability": round(pin_prob, 2),
        "pin_risk": pin_risk,
        "anchor": round(anchor, 2),
        "call_wall": call_wall,
        "put_wall": put_wall,
        "straddle": straddle,
        "upper_test": round(anchor + straddle, 2),
        "lower_test": round(anchor - straddle, 2),
        "expiry": "0DTE/Weekly",
        "source": "PROXY",
    }


def analyze_multi(tickers, prices, vix=20.0):
    results = {}
    for t in tickers:
        results[t] = analyze_0dte(t, prices, vix)
    return results
