"""engines/gex_engine.py — Net Gamma Exposure (GEX) Engine
Calculates Gamma Exposure per strike, finds Gamma Flip, Call/Put Walls, Speed.
Uses yfinance options chain as proxy for true dealer positioning.
"""
import math
import numpy as np
import pandas as pd

try:
    import yfinance as yf
    _HAS_YF = True
except Exception:
    _HAS_YF = False


def _black_scholes_gamma(S, K, T, r, sigma):
    """Calculate Black-Scholes gamma."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    gamma = np.exp(-0.5 * d1 ** 2) / (S * sigma * math.sqrt(2 * math.pi * T))
    return float(gamma)


def _get_options_chain(ticker, expiry_days=0):
    """Fetch options chain from yfinance. Returns calls/puts DataFrames."""
    if not _HAS_YF:
        return None, None, None
    try:
        t = yf.Ticker(ticker)
        exps = t.options
        if not exps:
            return None, None, None
        # Pick nearest expiry
        expiry = exps[min(expiry_days, len(exps) - 1)]
        chain = t.option_chain(expiry)
        return chain.calls, chain.puts, expiry
    except Exception:
        return None, None, None


def analyze_gex(ticker, prices, vix=20.0, risk_free=0.045):
    """
    Calculate GEX (Gamma Exposure) metrics for a ticker.
    Returns dict with flip level, walls, regime, speed.
    """
    s = prices.get(ticker)
    if s is None or len(s) < 20:
        return {"ok": False, "error": "No price data"}

    try:
        s_clean = pd.to_numeric(s, errors="coerce").dropna()
        spot = float(s_clean.iloc[-1])
    except Exception:
        return {"ok": False, "error": "Price parse failed"}

    calls, puts, expiry = _get_options_chain(ticker, expiry_days=0)
    if calls is None or puts is None:
        # Fallback: proxy from price action
        return _gex_proxy(ticker, spot, s_clean, vix)

    try:
        # Calculate days to expiry
        from datetime import datetime
        exp_date = datetime.strptime(expiry, "%Y-%m-%d")
        T = max((exp_date - datetime.now()).days / 365.0, 0.0027)
    except Exception:
        T = 0.02  # ~1 week

    sigma = vix / 100.0
    # S0-b: align dealer-sign convention with spotgamma_gex_engine
    _idx_set = {"SPY", "QQQ", "IWM", "DIA", "^GSPC", "^NDX", "^RUT", "^DJI"}
    is_idx = ticker.upper() in _idx_set or ticker.startswith("^")

    # Build strike → GEX map
    gex_by_strike = {}

    for _, opt in calls.iterrows():
        strike = float(opt.get("strike", 0))
        oi = float(opt.get("openInterest", 0) or 0)
        if strike <= 0 or oi <= 0:
            continue
        iv = float(opt.get("impliedVolatility", 0) or 0)
        vol = iv if iv > 0 else sigma  # S1-c: per-strike IV (skew); VIX fallback
        gamma = _black_scholes_gamma(spot, strike, T, risk_free, vol)
        # S0-b: SpotGamma convention + per-1%-notional scaling (spot²·0.01).
        # Index: dealers long calls (+); single-stock equity: dealers short calls (−).
        gex = gamma * oi * 100 * (spot ** 2) * 0.01
        gex *= (1.0 if is_idx else -1.0)
        gex_by_strike[strike] = gex_by_strike.get(strike, 0) + gex

    for _, opt in puts.iterrows():
        strike = float(opt.get("strike", 0))
        oi = float(opt.get("openInterest", 0) or 0)
        if strike <= 0 or oi <= 0:
            continue
        iv = float(opt.get("impliedVolatility", 0) or 0)
        vol = iv if iv > 0 else sigma  # S1-c: per-strike IV (skew); VIX fallback
        gamma = _black_scholes_gamma(spot, strike, T, risk_free, vol)
        # S0-b: dealers short puts → −GEX (both index & equity)
        gex = gamma * oi * 100 * (spot ** 2) * 0.01
        gex_by_strike[strike] = gex_by_strike.get(strike, 0) - gex

    if not gex_by_strike:
        return _gex_proxy(ticker, spot, s_clean, vix)

    # Sort strikes
    strikes = sorted(gex_by_strike.keys())
    gex_values = [gex_by_strike[k] for k in strikes]

    # Net GEX
    net_gex = sum(gex_values)

    # Gamma Flip: where cumulative GEX crosses zero
    cumulative = 0
    flip_level = None
    for strike, gex in zip(strikes, gex_values):
        cumulative += gex
        if cumulative > 0 and flip_level is None:
            flip_level = strike

    if flip_level is None:
        # No sign change (single-regime book, common for negative-gamma equities):
        # default the flip to the strike nearest spot rather than an arbitrary middle.
        flip_level = min(strikes, key=lambda k: abs(k - spot)) if strikes else spot

    # Walls — position-anchored so they stay meaningful even for single-stock
    # all-negative (negative-gamma) books: call wall = the dominant-GEX strike ABOVE
    # spot, put wall = the most-negative-GEX strike BELOW spot.
    above = {k: v for k, v in gex_by_strike.items() if k >= spot}
    below = {k: v for k, v in gex_by_strike.items() if k <= spot}
    call_wall = max(above.items(), key=lambda x: x[1])[0] if above else spot * 1.05
    put_wall = min(below.items(), key=lambda x: x[1])[0] if below else spot * 0.95

    # Speed: rate of gamma change near spot
    near_strikes = [k for k in strikes if abs(k - spot) / spot < 0.05]
    if len(near_strikes) >= 2:
        near_gex = [gex_by_strike[k] for k in near_strikes]
        speed = abs(near_gex[-1] - near_gex[0]) / (near_strikes[-1] - near_strikes[0]) if near_strikes[-1] != near_strikes[0] else 0
    else:
        speed = 0

    # Regime — S0-b: ratio-based (net/gross) so it's scale-invariant and not
    # tied to an absolute magnitude that changes with the spot² scaling.
    # (Also fixes the old inverted bug: small positive was labelled DEEP_POSITIVE.)
    gross_gex = sum(abs(g) for g in gex_values) or 1.0
    ratio = net_gex / gross_gex
    if ratio > 0.15:
        regime, label, color = "DEEP_POSITIVE", "Deep Positive", "#3FB950"
    elif ratio > 0:
        regime, label, color = "POSITIVE", "Positive", "#3FB950"
    elif ratio > -0.15:
        regime, label, color = "NEGATIVE", "Negative", "#D29922"
    else:
        regime, label, color = "DEEP_NEGATIVE", "Deep Negative", "#F85149"

    return {
        "ok": True,
        "spot": round(spot, 2),
        "net_gex": round(net_gex, 0),
        "flip_level": round(flip_level, 2),
        "call_wall": round(call_wall, 2),
        "put_wall": round(put_wall, 2),
        "speed": round(speed, 2),
        "regime": regime,
        "label": label,
        "color": color,
        "expiry": expiry,
        "strikes": [round(float(k), 2) for k in strikes],
        "gex_by_strike": [round(float(v), 0) for v in gex_values],
        "source": "YF_OPTIONS"
    }


def _gex_proxy(ticker, spot, s_clean, vix):
    """Proxy GEX from price action when options unavailable."""
    sma20 = float(s_clean.tail(20).mean())
    std20 = float(s_clean.tail(20).std())

    flip_level = round(sma20, 2)
    call_wall = round(sma20 + std20 * 2.0, 2)
    put_wall = round(sma20 - std20 * 2.0, 2)

    # Proxy net GEX from momentum
    r5d = float(s_clean.iloc[-1] / s_clean.iloc[-6] - 1) if len(s_clean) >= 6 else 0
    net_gex_proxy = r5d * 1e6  # arbitrary scale

    if r5d > 0.03:
        regime = "POSITIVE"; label = "Positive"; color = "#3FB950"
    elif r5d < -0.03:
        regime = "NEGATIVE"; label = "Negative"; color = "#D29922"
    else:
        regime = "TRANSITION"; label = "Transition"; color = "#8B949E"

    return {
        "ok": True,
        "spot": round(spot, 2),
        "net_gex": round(net_gex_proxy, 0),
        "flip_level": flip_level,
        "call_wall": call_wall,
        "put_wall": put_wall,
        "speed": 0.5,
        "regime": regime,
        "label": label,
        "color": color,
        "expiry": "PROXY",
        "source": "PROXY"
    }


def analyze_multi(tickers, prices, vix=20.0):
    """Run GEX analysis on multiple tickers."""
    results = {}
    for t in tickers:
        results[t] = analyze_gex(t, prices, vix)
    return results
