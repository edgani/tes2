"""engines/charm_proxy_engine.py — Charm Flow Proxy
Charm = D-Delta/D-Time. Proxy from options chain theta + price momentum.
Predicts passive directional bias, especially 1:30-3pm ET.
"""
import math
import numpy as np
import pandas as pd

try:
    import yfinance as yf
    _HAS_YF = True
except Exception:
    _HAS_YF = False


def _black_scholes_theta(S, K, T, r, sigma, option_type="call"):
    """Calculate Black-Scholes theta (per day)."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    nd1 = 1 / (math.sqrt(2 * math.pi)) * math.exp(-0.5 * d1 ** 2)

    if option_type == "call":
        theta = -(S * nd1 * sigma) / (2 * math.sqrt(T)) - r * K * math.exp(-r * T) * (0.5 * (1 + math.erf(d2 / math.sqrt(2))))
    else:
        theta = -(S * nd1 * sigma) / (2 * math.sqrt(T)) + r * K * math.exp(-r * T) * (0.5 * (1 + math.erf(-d2 / math.sqrt(2))))
    return theta / 365.0  # per calendar day


def _black_scholes_charm(S, K, T, r, sigma):
    """Charm = ∂Δ/∂t (delta decay per CALENDAR day). Assumes q=0.

    FIX S1-b: the old code used theta (∂V/∂t) as a 'charm proxy' — a DIFFERENT
    Greek. Charm is the time-derivative of DELTA, which is what drives the
    delta-rehedging flow Karsan/SpotGamma describe. With q=0, ∂Δ_call/∂t ==
    ∂Δ_put/∂t, so one formula serves both legs.
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    try:
        srt = sigma * math.sqrt(T)
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / srt
        d2 = d1 - srt
        pdf = math.exp(-0.5 * d1 ** 2) / math.sqrt(2 * math.pi)
        charm_per_year = -pdf * (2 * r * T - d2 * srt) / (2 * T * srt)
        return charm_per_year / 365.0
    except Exception:
        return 0.0


def analyze_charm(ticker, prices, vix=20.0, risk_free=0.045):
    """
    Calculate Charm exposure for a ticker.
    Returns directional bias from time-decay hedging flows.
    """
    s = prices.get(ticker)
    if s is None or len(s) < 20:
        return {"ok": False, "error": "No price data"}

    try:
        s_clean = pd.to_numeric(s, errors="coerce").dropna()
        spot = float(s_clean.iloc[-1])
    except Exception:
        return {"ok": False, "error": "Price parse failed"}

    # Try to get options chain
    if _HAS_YF:
        try:
            t = yf.Ticker(ticker)
            exps = t.options
            if exps:
                expiry = exps[0]
                chain = t.option_chain(expiry)
                calls, puts = chain.calls, chain.puts

                from datetime import datetime
                exp_date = datetime.strptime(expiry, "%Y-%m-%d")
                T = max((exp_date - datetime.now()).days / 365.0, 0.0027)
                sigma = vix / 100.0

                net_charm = 0.0
                gross_charm = 0.0
                for _, opt in calls.iterrows():
                    strike = float(opt.get("strike", 0))
                    oi = float(opt.get("openInterest", 0) or 0)
                    if strike <= 0 or oi <= 0:
                        continue
                    iv = float(opt.get("impliedVolatility", 0) or 0)
                    vol = iv if iv > 0 else sigma  # per-strike IV (skew); VIX fallback
                    charm = _black_scholes_charm(spot, strike, T, risk_free, vol) * oi * 100
                    net_charm += charm            # dealers short calls
                    gross_charm += abs(charm)

                for _, opt in puts.iterrows():
                    strike = float(opt.get("strike", 0))
                    oi = float(opt.get("openInterest", 0) or 0)
                    if strike <= 0 or oi <= 0:
                        continue
                    iv = float(opt.get("impliedVolatility", 0) or 0)
                    vol = iv if iv > 0 else sigma
                    charm = _black_scholes_charm(spot, strike, T, risk_free, vol) * oi * 100
                    net_charm -= charm            # puts flip dealer sign
                    gross_charm += abs(charm)

                return _charm_from_net(net_charm, spot, s_clean, vix, "YF_OPTIONS", gross=gross_charm)
        except Exception:
            pass

    # Proxy fallback
    return _charm_proxy(ticker, spot, s_clean, vix)


def _charm_from_net(net_charm, spot, s_clean, vix, source, gross=None):
    """Interpret net charm via a SCALE-INVARIANT imbalance (−1..1).

    FIX S1-b: old code thresholded raw magnitude (±5e5/±1e5) calibrated to a
    theta-dollar scale. With the correct (tiny-magnitude) charm Greek those
    thresholds never fired → always NEUTRAL. Normalize: imbalance = net/gross.
    """
    r5d = float(s_clean.iloc[-1] / s_clean.iloc[-6] - 1) if len(s_clean) >= 6 else 0

    imb = max(-1.0, min(1.0, net_charm / gross)) if (gross and gross > 0) else 0.0
    HI, LO = 0.30, 0.10

    if imb > HI:
        regime, signal, color = "BUILDING", "NEVER_SHORT", "#3FB950"
        note = f"Charm imbalance +{imb:.2f} — dealers must BUY to hedge delta decay"
    elif imb > LO:
        regime, signal, color = "BUILDING", "BULLISH_BIAS", "#3FB950"
        note = f"Charm imbalance +{imb:.2f} — positive drift expected"
    elif imb < -HI:
        regime, signal, color = "FADING", "AVOID_LONG", "#F85149"
        note = f"Charm imbalance {imb:.2f} — dealers must SELL to hedge delta decay"
    elif imb < -LO:
        regime, signal, color = "FADING", "BEARISH_BIAS", "#F85149"
        note = f"Charm imbalance {imb:.2f} — negative drift expected"
    else:
        regime, signal, color = "STABLE", "NEUTRAL", "#8B949E"
        note = "Charm balanced — no time-decay drift"

    # Afternoon sweet spot: 1:30-3pm ET (13:30-15:00)
    from datetime import datetime
    now = datetime.now()
    hour = now.hour + now.minute / 60
    sweet_spot = 13.5 <= hour <= 15.0

    return {
        "ok": True,
        "net_charm": round(net_charm, 2),
        "charm_imbalance": round(imb, 3),
        "regime": regime,
        "signal": signal,
        "color": color,
        "note": note,
        "sweet_spot": sweet_spot,
        "sweet_spot_note": "13:30-15:00 ET charm dominates" if sweet_spot else "Wait for afternoon window",
        "r5d": round(r5d, 4),
        "source": source,
    }


def _charm_proxy(ticker, spot, s_clean, vix):
    """Proxy charm from price momentum (acceleration), normalized to a -1..1 imbalance."""
    r5d = float(s_clean.iloc[-1] / s_clean.iloc[-6] - 1) if len(s_clean) >= 6 else 0
    r10d = float(s_clean.iloc[-1] / s_clean.iloc[-11] - 1) if len(s_clean) >= 11 else 0

    accel = r5d - (r10d / 2)
    # ≈1.5% 5d-vs-10d acceleration → full-strength signal
    charm_norm = max(-1.0, min(1.0, accel / 0.015))
    return _charm_from_net(charm_norm, spot, s_clean, vix, "PROXY", gross=1.0)


def analyze_multi(tickers, prices, vix=20.0):
    results = {}
    for t in tickers:
        results[t] = analyze_charm(t, prices, vix)
    return results
