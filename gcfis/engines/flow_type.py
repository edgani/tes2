"""flow_type.py — doc 1/2: 4-way flow classifier + absorption / efficiency / persistence / resilience.
HONEST: computed from OHLCV close+volume PROXIES (signed volume by return sign). True aggressor
classification needs tick/L2 — outputs are labelled proxy-grade, never presented as real orderflow.
  ACCUMULATION      : mild uptrend, persistent +delta, sell-offs absorbed (resilient), shallow retraces
  DISTRIBUTION      : stalling near highs after an uptrend, heavy volume, NO price progress (low efficiency)
  SHORT_COVERING    : prior downtrend → violent rally, volume spike, HIGH efficiency, low persistence
  PANIC_LIQUIDATION : violent down + volume climax, then price STOPS falling (absorption at lows)
  NEUTRAL           : none of the above"""
from __future__ import annotations
import numpy as np, pandas as pd
from ..core.change_core import pct_rank

def run_flow_type(price, volume=None) -> dict:
    px = pd.to_numeric(pd.Series(price), errors="coerce").dropna()
    if len(px) < 120:
        return {"ok": False, "type": "NEUTRAL", "flow01": 0.5, "reason": "insufficient history"}
    r = np.log(px).diff().fillna(0.0)
    sig20 = float(r.tail(20).std() or 1e-9)
    vol = pd.to_numeric(pd.Series(volume), errors="coerce").reindex(px.index) if volume is not None else None
    have_vol = vol is not None and vol.notna().sum() > 60
    if have_vol:
        vrel = (vol / vol.rolling(60).mean()).fillna(1.0)
        sv = np.sign(r) * vrel                              # signed volume proxy (by return sign)
        vol_z10 = float((vol.tail(10).mean() - vol.tail(120).mean()) / (vol.tail(120).std() or 1e-9))  # RAW vol climax vs 120d
        persistence = float(pd.Series(sv.tail(30)).autocorr(lag=1) or 0.0)
        net_sv10 = float(sv.tail(10).sum())
    else:
        vrel = pd.Series(1.0, index=px.index); sv = np.sign(r)
        vol_z10, persistence, net_sv10 = 0.0, float(pd.Series(sv.tail(30)).autocorr(lag=1) or 0.0), float(sv.tail(10).sum())
    # absorption (doc 2): |delta| big while |price move| small → high. pct-rank vs own history.
    win = 10
    absr = (sv.abs().rolling(win).sum()) / ((r.rolling(win).sum().abs() / (sig20 + 1e-9)) + 1.0)
    absorption = float((pct_rank(absr, window=180).iloc[-1] or 0.5) * 100) if absr.notna().sum() > 40 else 50.0
    # efficiency (doc 2): net move per unit (volume×vol) → pct-rank
    effr = (r.rolling(win).sum().abs()) / ((vrel.rolling(win).sum() * sig20) + 1e-9)
    efficiency = float((pct_rank(effr, window=180).iloc[-1] or 0.5) * 100) if effr.notna().sum() > 40 else 50.0
    # resilience: avg forward-3d return after the worst-decile down days (recovery tendency)
    dwn = r[r < r.quantile(0.1)].index
    fwd = [float(r.loc[d:].iloc[1:4].sum()) for d in dwn[-25:] if len(r.loc[d:]) > 4]
    resilience = float(np.mean(fwd) / (sig20 + 1e-9)) if fwd else 0.0
    ret10, ret20, ret60 = float(r.tail(10).sum()), float(r.tail(20).sum()), float(r.tail(60).sum())
    prior60 = float(r.iloc[-70:-10].sum())                       # trend BEFORE the recent 10-bar burst
    prior_trend = float(r.iloc[-120:-20].sum())                  # trend BEFORE the recent 20-bar stall
    pos120 = float((px.iloc[-1] - px.tail(120).min()) / ((px.tail(120).max() - px.tail(120).min()) or 1e-9))
    last_lo_idx = int(np.argmin(px.tail(10).values))
    ftype = "NEUTRAL"
    if ret10 < -2.5 * np.sqrt(10) * sig20 and vol_z10 > 0.8 and last_lo_idx <= 6:
        ftype = "PANIC_LIQUIDATION"                          # climax down, low is in, stabilizing
    elif prior60 < -0.04 and ret10 > 2.0 * np.sqrt(10) * sig20 and vol_z10 > 0.5 and efficiency > 60:
        ftype = "SHORT_COVERING"
    elif pos120 > 0.55 and prior_trend > 0.04 and abs(ret20) < 1.2 * np.sqrt(20) * sig20 and vol_z10 > 0.5 and efficiency < 65:
        ftype = "DISTRIBUTION"                                # heavy volume at highs, no progress
    elif ret60 > 0.03 and ret20 > 0 and persistence > 0.05 and resilience > 0 and absorption > 45:
        ftype = "ACCUMULATION"
    bonus = {"ACCUMULATION": 0.35, "SHORT_COVERING": 0.10, "NEUTRAL": 0.0,
             "PANIC_LIQUIDATION": -0.15, "DISTRIBUTION": -0.35}[ftype]
    flow01 = float(np.clip(0.5 + bonus + 0.12 * np.tanh(persistence * 3) + 0.10 * np.tanh(resilience)
                           + 0.08 * (absorption - 50) / 50, 0.0, 1.0))
    return {"ok": True, "type": ftype, "absorption": round(absorption, 1), "efficiency": round(efficiency, 1),
            "persistence": round(persistence, 2), "resilience": round(resilience, 2),
            "vol_z10": round(vol_z10, 2), "flow01": round(flow01, 2), "proxy": True,
            "note": "OHLCV proxy — true aggressor/L2 classification needs tick data"}
