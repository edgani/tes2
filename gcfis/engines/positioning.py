"""positioning.py — L9 Positioning Engine. COT (Williams index), OI ROC (Δz not ratio), crowding.
Feeds the adoption-curve / asset-selection. Graceful on missing inputs."""
from __future__ import annotations
import numpy as np, pandas as pd
from ..core.change_core import robust_z, delta_z, pct_rank, last

def cot_index(net_position: pd.Series, window: int = 156) -> float:
    s = pd.Series(net_position).dropna()
    if len(s) < 10:
        return 0.5
    lo, hi = s.tail(window).min(), s.tail(window).max()
    return float((s.iloc[-1] - lo) / (hi - lo)) if hi > lo else 0.5

def run_positioning(ticker: str, cot_net=None, open_interest=None, short_interest=None,
                    inst_own=None) -> dict:
    cot = cot_index(cot_net) if cot_net is not None else None
    oi_roc = last(delta_z(pd.Series(open_interest))) if open_interest is not None else 0.0
    crowd_parts = [last(pct_rank(x)) for x in (short_interest, inst_own, open_interest)
                   if x is not None and len(pd.Series(x).dropna()) > 20]
    crowding = float(np.mean(crowd_parts)) * 100 if crowd_parts else None
    return {"ticker": ticker, "cot_index": (round(cot, 2) if cot is not None else None),
            "oi_roc_z": round(oi_roc, 2), "crowding": (round(crowding, 1) if crowding is not None else None),
            "extreme_long": (cot is not None and cot > 0.9), "extreme_short": (cot is not None and cot < 0.1)}
