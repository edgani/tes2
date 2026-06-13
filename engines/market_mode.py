"""market_mode.py — doc 7: classify the 4 market MODES and map each to an execution style.
PINNING (pos-gamma/compressed) → fade extremes, tight stop, small target
EXPANSION (neg-gamma/vol-rising trend) → momentum continuation, wide stop, big target
SQUEEZE (crowded wrong-way + acceleration) → early build, add on propagation
DISTRIBUTION (climax volume, no progress / crowded rolling over) → reduce / avoid / tactical short"""
from __future__ import annotations
import numpy as np, pandas as pd

EXEC_MAP = {
    "PINNING":      {"style": "MEAN_REVERT", "stop": "tight", "target": "opposite range", "note": "dealers dampen — fade extremes, don't chase breakouts"},
    "EXPANSION":    {"style": "MOMENTUM", "stop": "wide", "target": "next liquidity / gamma wall", "note": "dealers amplify — continuation valid, add on acceptance"},
    "SQUEEZE":      {"style": "EARLY_BUILD", "stop": "squeeze fails to propagate", "target": "where crowding turns euphoric", "note": "forced flow possible — position before the chase"},
    "DISTRIBUTION": {"style": "REDUCE", "stop": "acceptance back above zone", "target": "liquidity vacuum below", "note": "upside reactions weak — reduce/avoid; tactical short only where shortable"},
    "MIXED":        {"style": "WAIT", "stop": "-", "target": "-", "note": "no dominant mode — lower aggression"},
}

def run_market_mode(price, dealer=None, flow=None, crowding=50.0, adoption_velocity=0.0) -> dict:
    px = pd.to_numeric(pd.Series(price), errors="coerce").dropna()
    if len(px) < 70:
        return {"ok": False, "mode": "MIXED", **EXEC_MAP["MIXED"]}
    r = np.log(px).diff()
    s10, s30 = float(r.tail(10).std() or 0), float(r.tail(30).std() or 1e-9)
    vol_rising = s10 > 1.2 * s30
    rng10 = float(px.tail(10).max() - px.tail(10).min()); rng60 = float(px.tail(60).max() - px.tail(60).min() or 1e-9)
    compressed = (rng10 / rng60) < 0.30
    ret20z = float(r.tail(20).sum() / ((np.sqrt(20) * s30) + 1e-9)); trending = abs(ret20z) > 1.0
    gex_sign = int((dealer or {}).get("gex_sign", 0)); greg = (dealer or {}).get("regime", "unknown")
    ftype = (flow or {}).get("type", "NEUTRAL")
    crowd = float(crowding if crowding is not None else 50.0); vel = float(adoption_velocity or 0.0)
    if ftype == "DISTRIBUTION" or (crowd > 85 and vel < 0):
        mode = "DISTRIBUTION"
    elif ftype == "SHORT_COVERING" or (crowd < 20 and ret20z > 0.8 and (vol_rising or gex_sign < 0)):
        mode = "SQUEEZE"
    elif (gex_sign < 0 and (vol_rising or trending)) or (greg == "momentum" and trending) or (vol_rising and trending):
        mode = "EXPANSION"
    elif (gex_sign > 0 and not vol_rising) or (greg == "mean_reversion" and not trending) or (compressed and not trending):
        mode = "PINNING"
    else:
        mode = "MIXED"
    out = {"ok": True, "mode": mode, "compressed": bool(compressed), "vol_rising": bool(vol_rising),
           "trend_z": round(ret20z, 2), "gex_sign": gex_sign}
    out.update(EXEC_MAP[mode])
    return out
