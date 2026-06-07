"""fragility.py — systemic fragility with non-linear amplifiers (correlation conduit + CSD).
Linear z-sum misses phase transitions; we amplify when components co-breach and when the
system shows Critical Slowing Down. Output 0..100 + velocity (what matters is the RISE)."""
from __future__ import annotations
import numpy as np, pandas as pd
from ..core.change_core import robust_z, to_100, last, csd

_W = {"credit": 0.30, "breadth": 0.20, "vol": 0.20, "funding": 0.15, "leverage": 0.15}
# breadth is inverted inside (low breadth => high fragility)

def run_fragility(inputs: dict, returns_matrix: pd.DataFrame | None = None,
                  index_returns: pd.Series | None = None, lam_corr: float = 0.6, lam_csd: float = 0.5) -> dict:
    comps, wsum, base = {}, 0.0, 0.0
    for k, w in _W.items():
        s = inputs.get(k)
        if s is None or len(pd.Series(s).dropna()) < 10:
            continue
        z = last(robust_z(s))
        if k == "breadth":
            z = -z
        comps[k] = round(z, 2); base += w * z; wsum += w
    if wsum == 0:
        return {"ok": False, "reason": "no fragility inputs available"}
    base /= wsum
    amp_corr = 1.0
    if returns_matrix is not None and returns_matrix.shape[1] >= 3:
        rc = returns_matrix.tail(63).corr().values
        cur = np.nanmean(rc[np.triu_indices_from(rc, 1)])
        rc0 = returns_matrix.tail(252).corr().values
        base_corr = np.nanmean(rc0[np.triu_indices_from(rc0, 1)])
        amp_corr = 1.0 + lam_corr * max(0.0, cur - base_corr)
    amp_csd = 1.0
    if index_returns is not None:
        amp_csd = 1.0 + lam_csd * max(0.0, last(csd(index_returns)))
    raw = base * amp_corr * amp_csd
    frag = float(to_100(raw))
    label = ("EXTREME" if frag >= 80 else "HIGH" if frag >= 60 else "WATCH" if frag >= 30 else "NORMAL")
    return {"ok": True, "fragility": round(frag, 1), "raw_z": round(raw, 2), "label": label,
            "amp_corr": round(amp_corr, 3), "amp_csd": round(amp_csd, 3), "components": comps}
