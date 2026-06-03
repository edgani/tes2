"""tier1alpha_model.py — Tier1Alpha Market Structure Report replica v40

Replicates the Tier1Alpha (presented by Hedgeye) 4-signal dashboard:
  1. SPX Gamma Exposure: Positive / Neutral / Negative
  2. Systematic Flow Risk: Bullish / Neutral / Bearish
  3. PV Band Risk/Reward: Long / Neutral / Short
  4. Strategic Allocation: Risk On / Neutral / Risk Off

Plus SPX Key Levels:
  • Last Price
  • Upper PV Band (≈ TRADE TRR)
  • Lower PV Band (≈ TRADE LRR)

PV Bands ≈ Hedgeye TRR/LRR (per Keith McCullough uses Tier1Alpha data).
Gamma exposure from options (SpotGamma-style). Systematic flow from vol-control
+ CTA trend models. Strategic allocation = composite.
"""
from __future__ import annotations
from typing import Dict, Optional
import math


def compute_tier1alpha(snap: dict, spx_ticker: str = "^GSPC") -> Dict:
    """Build the Tier1Alpha 4-signal market structure report."""
    rr_data = snap.get("risk_range", {}).get("asset_ranges", {}) if isinstance(snap.get("risk_range"), dict) else {}
    options_data = snap.get("options_data", {}) or {}
    vix = snap.get("vix", 20.0) or 20.0

    # Resolve SPX RR (try ^GSPC then SPY then ES=F)
    spx_rr = None
    for t in ("^GSPC", "SPY", "^SPX", "ES=F"):
        if t in rr_data:
            spx_rr = rr_data[t]
            spx_ticker = t
            break

    # ── Signal 1: SPX Gamma Exposure ─────────────────────────────────────
    gamma_signal = "Neutral"
    gamma_note = ""
    spx_opts = options_data.get(spx_ticker, {}) or options_data.get("SPY", {})
    net_gex = spx_opts.get("gex") or spx_opts.get("net_gex")
    if net_gex is not None:
        try:
            g = float(net_gex)
            if g > 1e8:
                gamma_signal = "Positive"
                gamma_note = ("Market makers LONG GAMMA → lower volatility expected. "
                             "Dealers buy dips / sell rips → mean-reverting, range-bound.")
            elif g < -1e8:
                gamma_signal = "Negative"
                gamma_note = ("Market makers SHORT GAMMA → higher volatility. "
                             "Dealers chase moves → trending, breakout-prone.")
            else:
                gamma_signal = "Neutral"
                gamma_note = "Gamma near flip — transitional volatility regime."
        except (TypeError, ValueError):
            pass
    else:
        # Fallback: use VIX as gamma proxy
        if vix < 16:
            gamma_signal = "Positive"
            gamma_note = "VIX low (proxy) → likely positive gamma, suppressed vol. (No live SPX GEX — using VIX proxy.)"
        elif vix > 25:
            gamma_signal = "Negative"
            gamma_note = "VIX elevated (proxy) → likely negative gamma, amplified moves. (No live SPX GEX.)"
        else:
            gamma_note = "VIX mid-range (proxy). Connect SPX options data for precise GEX."

    # ── Signal 2: Systematic Flow Risk ───────────────────────────────────
    # Proxy: vol-control + CTA trend. Use VIX trend + SPX momentum.
    flow_signal = "Neutral"
    flow_note = ""
    if spx_rr:
        phase = spx_rr.get("phase", "NEUTRAL")
        trade_pos = spx_rr.get("signals", {}).get("trade_position_pct", 50)
        if phase == "BULL" and vix < 20:
            flow_signal = "Bullish"
            flow_note = "Vol-control funds adding exposure (low VIX + uptrend). CTAs long."
        elif phase == "BEAR" or vix > 25:
            flow_signal = "Bearish"
            flow_note = "Vol-control de-risking (rising VIX). CTA trend models flipping short."
        else:
            flow_note = "Systematic flows balanced — no strong vol-control or CTA bias."

    # ── Signal 3: PV Band Risk/Reward (= TRR/LRR position) ───────────────
    pv_signal = "Neutral"
    pv_note = ""
    last_price = upper_pv = lower_pv = None
    if spx_rr:
        last_price = spx_rr.get("px")
        trade = spx_rr.get("trade", {})
        upper_pv = trade.get("trr")
        lower_pv = trade.get("lrr")
        sig = spx_rr.get("signals", {})
        trade_pos = sig.get("trade_position_pct", 50)
        if trade_pos < 30:
            pv_signal = "Long"
            pv_note = f"Price near Lower PV Band (LRR) — favorable long entry. Position {trade_pos:.0f}% of range."
        elif trade_pos > 70:
            pv_signal = "Short"
            pv_note = f"Price near Upper PV Band (TRR) — risk skewed short/trim. Position {trade_pos:.0f}%."
        else:
            pv_note = f"Price mid PV band ({trade_pos:.0f}%) — balanced R/R."

    # ── Signal 4: Strategic Allocation (composite) ───────────────────────
    score = 0
    if gamma_signal == "Positive": score += 1
    elif gamma_signal == "Negative": score -= 1
    if flow_signal == "Bullish": score += 1
    elif flow_signal == "Bearish": score -= 1
    if pv_signal == "Long": score += 1
    elif pv_signal == "Short": score -= 1
    if vix < 16: score += 1
    elif vix > 25: score -= 1

    if score >= 2:
        alloc_signal = "Risk On"
        alloc_note = "Composite favorable — add risk exposure, lean long."
    elif score <= -2:
        alloc_signal = "Risk Off"
        alloc_note = "Composite defensive — reduce exposure, raise cash/hedges."
    else:
        alloc_signal = "Neutral"
        alloc_note = "Mixed signals — maintain neutral positioning."

    return {
        "spx_ticker": spx_ticker,
        "signals": {
            "gamma_exposure": {"value": gamma_signal, "note": gamma_note,
                               "options": ["Positive", "Neutral", "Negative"]},
            "systematic_flow": {"value": flow_signal, "note": flow_note,
                                "options": ["Bullish", "Neutral", "Bearish"]},
            "pv_band_rr": {"value": pv_signal, "note": pv_note,
                          "options": ["Long", "Neutral", "Short"]},
            "strategic_allocation": {"value": alloc_signal, "note": alloc_note,
                                     "options": ["Risk On", "Neutral", "Risk Off"]},
        },
        "spx_levels": {
            "last_price": round(last_price, 2) if last_price else None,
            "upper_pv_band": round(upper_pv, 2) if upper_pv else None,
            "lower_pv_band": round(lower_pv, 2) if lower_pv else None,
        },
        "composite_score": score,
        "data_quality": "live_gex" if net_gex is not None else "vix_proxy",
    }
