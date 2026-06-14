"""rotation.py — wires the discovered lead-lag graph INTO asset selection (the GCFIS 'moat',
previously decorative). When a LEADER fires (recent significant move), its FOLLOWERS are 'primed'
to move ~lag days later → conviction boost + timing window. This is the Track-B rotation use of LX.
Honest: predictive lead-lag (not mechanistic causation); fragile if the latent driver regime shifts."""
from __future__ import annotations
import numpy as np, pandas as pd
from ..core.change_core import robust_z, last

def run_rotation(edges, prices, fire_z: float = 1.0) -> dict:
    """edges: list of {leader, follower, lag, confidence}. prices: {tkr: pd.Series}.
    Returns {follower: {leader, lag, fired_z, days_since_fire, window, confidence, strength}} — primed only."""
    primed = {}
    for e in edges or []:
        L, F = e.get("leader"), e.get("follower")
        lag, conf = int(e.get("lag", 0)), float(e.get("confidence", 0))
        if L not in prices or F not in prices or lag < 1:
            continue
        s = pd.to_numeric(prices[L], errors="coerce").dropna()
        r = np.log(s[s > 0]).diff()
        if len(r) < 60:
            continue
        win = max(3, lag)
        roll_z = robust_z(r.rolling(win).sum())          # z of the leader's lag-window return
        recent = roll_z.tail(lag).values                 # did it fire within the last `lag` bars?
        if len(recent) == 0 or not np.isfinite(recent).any():
            continue
        peak_idx = int(np.nanargmax(recent)); peak_z = float(recent[peak_idx])
        if peak_z < fire_z:
            continue
        days_since = (len(recent) - 1) - peak_idx        # bars since the firing
        window = lag - days_since                         # ~bars until follower should react (<=0 = now/overdue)
        strength = float(peak_z * (conf / 100.0))
        cur = primed.get(F)
        if cur is None or strength > cur["strength"]:
            primed[F] = {"leader": L, "lag": lag, "fired_z": round(peak_z, 2),
                         "days_since_fire": int(days_since), "window": int(window),
                         "confidence": round(conf, 1), "strength": round(strength, 2)}
    return primed
