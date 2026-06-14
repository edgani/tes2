"""response_zone.py — doc 8/9: TRR/LRR as RESPONSE zones, not S/R. What matters is how price
BEHAVES at the band, not that it touched it. Zone = 20d ref ± 1σ (same base the entry engine uses)."""
from __future__ import annotations
import numpy as np, pandas as pd

def run_response_zone(price) -> dict:
    px = pd.to_numeric(pd.Series(price), errors="coerce").dropna()
    if len(px) < 70:
        return {"ok": False, "response": "UNKNOWN", "quality": 0}
    r = np.log(px).diff()
    ref = float(px.tail(20).mean()); sigma = float(px.pct_change().tail(20).std() * ref or px.std() * 0.02)
    lo, hi = ref - sigma, ref + sigma
    p = float(px.iloc[-1]); pos = (p - lo) / ((hi - lo) or 1e-9)
    w = px.tail(7)
    dipped_below = bool((w < lo).any()); now_above_lo = p > lo
    closes_above_hi = int((w > hi).sum()); broke_hi = bool((w > hi).any())
    made_new_low = bool(p <= float(w.min()) * 1.001)
    tight = float(w.max() - w.min()) < 0.8 * sigma
    if dipped_below and now_above_lo:
        resp, q = "FAILED_BREAKDOWN_RECLAIM", 85          # trapped shorts — one of the best responses
    elif pos < 0.25 and made_new_low:
        resp, q = "NO_BID_CONTINUATION", 15               # zone is a waypoint, not support
    elif pos < 0.25 and tight:
        resp, q = "ABSORPTION_HOLD", 70                   # selling absorbed at the band
    elif pos > 0.75 and closes_above_hi >= 2:
        resp, q = "ACCEPTANCE_ABOVE", 75                  # valid expansion (not a wick)
    elif pos > 0.75 and broke_hi and p < hi:
        resp, q = "REJECTION", 25                          # breakout buyers trapped above
    else:
        resp, q = "MID_RANGE", 50
    return {"ok": True, "response": resp, "quality": q, "zone_pos": round(pos, 2),
            "zone": [round(lo, 2), round(hi, 2)]}
