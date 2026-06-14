"""engines/greeks_proxy.py — Greeks Proxy Engine
Generates proxy Greeks (delta, gamma, vanna, charm, volga) for any ticker.
Uses price action + VIX + DXY + macro regime as proxy.
"""
from __future__ import annotations
import logging, math
from typing import Dict, Optional
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

class GreeksProxy:
    """
    Proxy Greeks engine.
    No real options chain needed — synthesizes from price, vol, macro.
    """

    def __init__(self):
        pass

    def analyze(self, ticker: str, prices: dict, vix: float = 20.0, dxy_ret: float = 0.0, 
                regime: str = "Q3") -> dict:
        s = prices.get(ticker)
        if s is None or s.empty:
            return {"ok": False, "reason": f"No price data for {ticker}"}

        s = pd.to_numeric(s, errors="coerce").dropna()
        if len(s) < 30:
            return {"ok": False, "reason": "Insufficient price history"}

        px = float(s.iloc[-1])

        # Returns
        r5d = float(s.iloc[-1] / s.iloc[-6] - 1) if len(s) >= 6 else 0
        r10d = float(s.iloc[-1] / s.iloc[-11] - 1) if len(s) >= 11 else 0
        r1m = float(s.iloc[-1] / s.iloc[-22] - 1) if len(s) >= 22 else 0
        r3m = float(s.iloc[-1] / s.iloc[-64] - 1) if len(s) >= 64 else 0

        # Vol
        ret = s.pct_change().dropna()
        rvol_20 = ret.tail(20).std() * math.sqrt(252) * 100 if len(ret) >= 20 else 15.0
        rvol_10 = ret.tail(10).std() * math.sqrt(252) * 100 if len(ret) >= 10 else rvol_20
        vol_premium = vix - rvol_20

        # Trend
        sma20 = float(s.tail(20).mean())
        sma50 = float(s.tail(50).mean()) if len(s) >= 50 else sma20
        above_sma20 = px > sma20
        above_sma50 = px > sma50

        # ── DELTA ──────────────────────────────────────────────────────────
        # Directional bias = momentum + trend
        delta_score = r1m * 5 + (1 if above_sma20 else -1) * 0.3 + (1 if above_sma50 else -1) * 0.2
        delta_score = max(-1, min(1, delta_score))

        if delta_score > 0.5:
            delta = "Long 🟢"; delta_val = round(delta_score, 2); delta_note = "Strong upward momentum + above key MAs"
        elif delta_score > 0.1:
            delta = "Mod Long 🟡"; delta_val = round(delta_score, 2); delta_note = "Positive bias but mixed"
        elif delta_score < -0.5:
            delta = "Short 🔴"; delta_val = round(delta_score, 2); delta_note = "Strong downward momentum + below key MAs"
        elif delta_score < -0.1:
            delta = "Mod Short 🟡"; delta_val = round(delta_score, 2); delta_note = "Negative bias but mixed"
        else:
            delta = "Neutral ⚪"; delta_val = 0.0; delta_note = "No clear directional edge"

        # ── GAMMA ──────────────────────────────────────────────────────────
        # Acceleration = change in momentum
        accel = r5d - (r10d / 2)
        vol_accel = rvol_10 - rvol_20  # positive = vol expanding

        if abs(accel) > 0.03 and vol_accel > 2:
            gamma = "High 📈"; gamma_val = round(abs(accel) * 30, 2); gamma_note = "Momentum accelerating + vol expanding"
        elif abs(accel) > 0.02:
            gamma = "Elevated 🟡"; gamma_val = round(abs(accel) * 20, 2); gamma_note = "Momentum shifting — watch for breakout"
        elif abs(accel) < 0.005:
            gamma = "Low ⚪"; gamma_val = round(abs(accel) * 10, 2); gamma_note = "Momentum stable — gamma pin likely"
        else:
            gamma = "Normal 🟢"; gamma_val = round(abs(accel) * 15, 2); gamma_note = "Normal gamma environment"

        # ── VANNA ─────────────────────────────────────────────────────────
        # Vanna = delta sensitivity to vol changes
        # Proxy: how does delta change when VIX moves?
        # High vol + downtrend = negative vanna (delta drops fast as vol rises)
        # Low vol + uptrend = positive vanna (delta rises as vol drops)

        if vix > 25 and r1m < -0.05:
            vanna = "Negative ⚠️"; vanna_val = -0.6; vanna_note = "High vol + downtrend = delta collapses on vol spike"
        elif vix < 18 and r1m > 0.05:
            vanna = "Positive ✅"; vanna_val = 0.5; vanna_note = "Low vol + uptrend = delta extends on vol crush"
        elif vix > 25 and r1m > 0.03:
            vanna = "Mixed 🟡"; vanna_val = 0.1; vanna_note = "High vol but positive momentum — conflicting"
        elif vix < 18 and r1m < -0.03:
            vanna = "Mixed 🟡"; vanna_val = -0.1; vanna_note = "Low vol but negative momentum — conflicting"
        else:
            vanna = "Neutral ⚪"; vanna_val = 0.0; vanna_note = "No strong vanna signal"

        # ── CHARM ─────────────────────────────────────────────────────────
        # Charm = delta decay over time (time sensitivity)
        # Proxy: is momentum fading or building over 1M vs 3M?
        charm_diff = r1m - (r3m / 3) if r3m != 0 else r1m

        if charm_diff > 0.03:
            charm = "Building 🟢"; charm_val = round(charm_diff * 10, 2); charm_note = "1M momentum > 3M trend — acceleration building"
        elif charm_diff < -0.03:
            charm = "Fading 🔴"; charm_val = round(charm_diff * 10, 2); charm_note = "1M momentum < 3M trend — momentum fading"
        else:
            charm = "Stable 🟡"; charm_val = round(charm_diff * 10, 2); charm_note = "Momentum stable vs longer trend"

        # ── VOLGA ─────────────────────────────────────────────────────────
        # Volga = vol of vol (convexity of vol)
        # Proxy: realized vol variance
        vol_changes = ret.tail(20).diff().dropna()
        volga_val = float(vol_changes.std() * math.sqrt(252) * 100) if len(vol_changes) > 1 else 0

        if volga_val > 8:
            volga = "High 🔴"; volga_note = "Vol of vol elevated — expect vol spikes"
        elif volga_val > 4:
            volga = "Elevated 🟡"; volga_note = "Vol of vol rising — watch for regime shift"
        else:
            volga = "Low 🟢"; volga_note = "Vol of vol calm — stable environment"

        # ── VOLATILITY ────────────────────────────────────────────────────
        if vix > 30:
            vol = "Extreme 🔴"; vol_note = "VIX > 30 — crisis mode"
        elif vix > 25:
            vol = "High 🔴"; vol_note = "VIX 25-30 — elevated risk"
        elif vix > 20:
            vol = "Elevated 🟡"; vol_note = "VIX 20-25 — caution warranted"
        elif vix > 15:
            vol = "Normal 🟢"; vol_note = "VIX 15-20 — normal range"
        else:
            vol = "Low 🟢"; vol_note = "VIX < 15 — complacency zone"

        # ── MAX PAIN PROXY ────────────────────────────────────────────────
        # Max pain = where most OI sits = near SMA20
        max_pain = round(sma20, 2)
        dist_mp = round((px - max_pain) / max_pain * 100, 2) if max_pain != 0 else 0

        # ── OI CONCENTRATION PROXY ──────────────────────────────────────
        recent_high = float(s.tail(40).max())
        recent_low = float(s.tail(40).min())
        pos = (px - recent_low) / (recent_high - recent_low) if recent_high > recent_low else 0.5

        if pos > 0.8:
            oi_conc = "High at highs 🔴"; oi_note = "Price at highs — profit-taking OI likely"
        elif pos < 0.2:
            oi_conc = "High at lows 🟢"; oi_note = "Price at lows — accumulation OI likely"
        else:
            oi_conc = "Mid-range 🟡"; oi_note = "Price mid-range — OI distributed"

        # ── COMPOSITE SIGNAL ────────────────────────────────────────────
        # Combine all Greeks into directional signal
        score = 0
        if "Long" in delta: score += 0.3
        elif "Short" in delta: score -= 0.3
        if "High" in gamma and "Long" in delta: score += 0.2
        if "High" in gamma and "Short" in delta: score -= 0.2
        if "Positive" in vanna: score += 0.15
        if "Negative" in vanna: score -= 0.15
        if "Building" in charm: score += 0.1
        if "Fading" in charm: score -= 0.1
        if vol_premium < -3: score += 0.1  # vol cheap = buy
        if vol_premium > 5: score -= 0.1   # vol expensive = sell

        score = round(max(-1, min(1, score)), 2)

        if score > 0.5:
            composite = "BULLISH 🟢"; composite_note = "Greeks align long — strong directional edge"
        elif score > 0.15:
            composite = "MOD BULLISH 🟡"; composite_note = "Greeks lean long — moderate edge"
        elif score < -0.5:
            composite = "BEARISH 🔴"; composite_note = "Greeks align short — strong directional edge"
        elif score < -0.15:
            composite = "MOD BEARISH 🟡"; composite_note = "Greeks lean short — moderate edge"
        else:
            composite = "NEUTRAL ⚪"; composite_note = "Greeks mixed — no clear edge"

        return {
            "ok": True,
            "ticker": ticker,
            "price": round(px, 2),
            "delta": delta,
            "delta_val": delta_val,
            "delta_note": delta_note,
            "gamma": gamma,
            "gamma_val": gamma_val,
            "gamma_note": gamma_note,
            "vanna": vanna,
            "vanna_val": vanna_val,
            "vanna_note": vanna_note,
            "charm": charm,
            "charm_val": charm_val,
            "charm_note": charm_note,
            "volga": volga,
            "volga_val": round(volga_val, 1),
            "volga_note": volga_note,
            "vol": vol,
            "vol_note": vol_note,
            "vix": vix,
            "rvol_20d": round(rvol_20, 1),
            "vol_premium": round(vol_premium, 1),
            "max_pain": max_pain,
            "dist_max_pain_pct": dist_mp,
            "oi_concentration": oi_conc,
            "oi_note": oi_note,
            "composite": composite,
            "composite_score": score,
            "composite_note": composite_note,
            "r1m": round(r1m, 4),
            "r5d": round(r5d, 4),
            "sma20": round(sma20, 2),
            "sma50": round(sma50, 2),
        }

    def analyze_multi(self, tickers, prices, vix=20.0, dxy_ret=0.0, regime="Q3"):
        results = {}
        for t in tickers:
            try:
                r = self.analyze(t, prices, vix, dxy_ret, regime)
                if r.get("ok"):
                    results[t] = r
            except Exception as e:
                logger.warning(f"Greeks error for {t}: {e}")
        return results
