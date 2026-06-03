"""engines/gamma_engine.py — Gamma Regime & Levels Engine
Generates gamma regime, max pain, gamma flip levels, put/call walls.
Uses price + vol + DXY + VIX as proxy (no real options chain needed).
"""
from __future__ import annotations
import logging, math
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

class GammaEngine:
    """
    Proxy gamma engine using price action, realized vol, and macro context.
    Generates:
    - Gamma regime (DEEP_POSITIVE / POSITIVE / TRANSITION / NEGATIVE / DEEP_NEGATIVE)
    - Max pain / gamma flip levels
    - Put wall / call wall
    - Gamma exposure direction
    """

    def __init__(self):
        pass

    def analyze(self, ticker: str, prices: dict, vix: float = 20.0, dxy_ret: float = 0.0) -> dict:
        s = prices.get(ticker)
        if s is None or s.empty:
            return {"ok": False, "reason": f"No price data for {ticker}"}

        s = pd.to_numeric(s, errors="coerce").dropna()
        if len(s) < 60:
            return {"ok": False, "reason": "Insufficient price history"}

        px = float(s.iloc[-1])

        # Realized vol (20-day annualized)
        ret = s.pct_change().dropna()
        rvol_20 = ret.tail(20).std() * math.sqrt(252) * 100 if len(ret) >= 20 else 15.0
        rvol_10 = ret.tail(10).std() * math.sqrt(252) * 100 if len(ret) >= 10 else rvol_20

        # Vol premium = implied (VIX proxy) - realized
        vol_premium = vix - rvol_20

        # Trend metrics
        sma20 = float(s.tail(20).mean())
        sma50 = float(s.tail(50).mean()) if len(s) >= 50 else sma20
        sma200 = float(s.tail(200).mean()) if len(s) >= 200 else sma50

        # Position in range (0=low, 1=high)
        recent_high = float(s.tail(60).max())
        recent_low = float(s.tail(60).min())
        pos = (px - recent_low) / (recent_high - recent_low) if recent_high > recent_low else 0.5

        # Momentum
        r5d = float(s.iloc[-1] / s.iloc[-6] - 1) if len(s) >= 6 else 0
        r1m = float(s.iloc[-1] / s.iloc[-22] - 1) if len(s) >= 22 else 0
        r3m = float(s.iloc[-1] / s.iloc[-64] - 1) if len(s) >= 64 else 0

        # ── Gamma Regime Logic ─────────────────────────────────────────────
        # Throttle = how much gamma is suppressing moves (0=none, 1=extreme)
        # High pos + low vol = high gamma (pin risk)
        # Low pos + high vol = low gamma (trending)

        vol_score = max(0, min(1, (25 - vix) / 20))  # 1.0 when VIX=5, 0.0 when VIX=25
        pos_score = 1.0 - abs(pos - 0.5) * 2  # 1.0 at 0.5, 0.0 at 0 or 1
        trend_score = min(1.0, abs(r5d) * 20)  # high trend = low gamma pin

        throttle = (vol_score * 0.4 + pos_score * 0.4 - trend_score * 0.2)
        throttle = max(0, min(1, throttle))

        # Regime classification
        if throttle > 0.75 and vol_premium < -5:
            regime = "DEEP_POSITIVE"; label = "Deep Positive"; color = "#3FB950"
            action = "Buy dips aggressively — gamma pin very strong"
        elif throttle > 0.55 and vol_premium < -2:
            regime = "POSITIVE"; label = "Positive"; color = "#3FB950"
            action = "Buy dips, normal sizing — gamma supportive"
        elif throttle > 0.35 or abs(vol_premium) < 3:
            regime = "TRANSITION"; label = "Transition"; color = "#D29922"
            action = "Reduce size — gamma shifting, choppy"
        elif throttle > 0.15:
            regime = "NEGATIVE"; label = "Negative"; color = "#F85149"
            action = "Sell rallies, tight stops — gamma accelerating moves"
        else:
            regime = "DEEP_NEGATIVE"; label = "Deep Negative"; color = "#F85149"
            action = "Stay disciplined — gamma expansion, wide stops needed"

        # ── Gamma Levels (Max Pain, Flip, Walls) ──────────────────────────
        # Max pain = where most gamma sits = typically near SMA20 (high OI strike proxy)
        max_pain = round(sma20, 2)

        # Gamma flip = level where gamma exposure flips from long to short
        # Proxy: 1 std dev move from max pain
        std_20 = float(s.tail(20).std())
        gamma_flip_up = round(max_pain + std_20 * 1.5, 2)
        gamma_flip_down = round(max_pain - std_20 * 1.5, 2)

        # Put wall = support where put gamma accumulates
        put_wall = round(max_pain - std_20 * 2.0, 2)

        # Call wall = resistance where call gamma accumulates  
        call_wall = round(max_pain + std_20 * 2.0, 2)

        # Distance to levels
        dist_max_pain = round((px - max_pain) / max_pain * 100, 2) if max_pain != 0 else 0
        dist_flip = round((px - gamma_flip_up) / gamma_flip_up * 100, 2) if gamma_flip_up != 0 else 0

        # Gamma exposure direction
        if px > gamma_flip_up:
            gamma_exposure = "NEGATIVE 🔴"  # Above flip = dealers short gamma = sell into strength
            gamma_note = "Price above gamma flip — dealers short gamma, rallies get sold"
        elif px < gamma_flip_down:
            gamma_exposure = "POSITIVE 🟢"  # Below flip = dealers long gamma = buy dips
            gamma_note = "Price below gamma flip — dealers long gamma, dips get bought"
        else:
            gamma_exposure = "NEUTRAL 🟡"
            gamma_note = "Price inside gamma flip zone — chop, pin to max pain likely"

        # ── Put/Call Skew Proxy ───────────────────────────────────────────
        # Proxy from trend: strong uptrend = call skew, strong downtrend = put skew
        if r1m > 0.08:
            skew = "CALL SKEW 📈"; skew_note = "Strong uptrend — calls in demand"
        elif r1m < -0.08:
            skew = "PUT SKEW 📉"; skew_note = "Strong downtrend — puts in demand"
        else:
            skew = "FLAT SKEW ↔"; skew_note = "Range bound — balanced demand"

        return {
            "ok": True,
            "ticker": ticker,
            "price": round(px, 2),
            "regime": regime,
            "label": label,
            "color": color,
            "throttle": round(throttle, 2),
            "rvol_20d": round(rvol_20, 1),
            "rvol_10d": round(rvol_10, 1),
            "vol_premium": round(vol_premium, 1),
            "action": action,
            "max_pain": max_pain,
            "gamma_flip_up": gamma_flip_up,
            "gamma_flip_down": gamma_flip_down,
            "put_wall": put_wall,
            "call_wall": call_wall,
            "dist_max_pain_pct": dist_max_pain,
            "dist_flip_pct": dist_flip,
            "gamma_exposure": gamma_exposure,
            "gamma_note": gamma_note,
            "skew": skew,
            "skew_note": skew_note,
            "sma20": round(sma20, 2),
            "sma50": round(sma50, 2),
            "sma200": round(sma200, 2),
            "pos_in_range": round(pos, 2),
            "r5d": round(r5d, 4),
            "r1m": round(r1m, 4),
            "vix": vix,
        }

    def analyze_multi(self, tickers: List[str], prices: dict, vix: float = 20.0, dxy_ret: float = 0.0) -> Dict[str, dict]:
        results = {}
        for t in tickers:
            try:
                r = self.analyze(t, prices, vix, dxy_ret)
                if r.get("ok"):
                    results[t] = r
            except Exception as e:
                logger.warning(f"Gamma analyze error for {t}: {e}")
        return results
