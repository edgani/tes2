"""shock.py — probabilistic P(shock/regime-break) from market-based stress + CSD.
Honest target: detect a regime break 2-5 days early, NOT predict the event."""
from __future__ import annotations
import pandas as pd
from ..core.change_core import robust_z, to_100, last, csd

# higher z = more stress for each (vix_ts = VIX/VIX3M inversion already oriented stress-positive)
_W = {"vix_ts": 0.18, "move": 0.12, "vvix": 0.08, "skew": 0.08, "hy_oas": 0.18,
      "cdx": 0.10, "fra_ois": 0.10, "xccy_basis": 0.08, "xasset_corr": 0.08}

def run_shock(inputs: dict, index_returns: pd.Series | None = None, lam_csd: float = 0.8) -> dict:
    s, wsum, comps = 0.0, 0.0, {}
    for k, w in _W.items():
        x = inputs.get(k)
        if x is None or len(pd.Series(x).dropna()) < 10:
            continue
        z = last(robust_z(x)); comps[k] = round(z, 2); s += w * z; wsum += w
    if wsum == 0:
        return {"ok": False, "reason": "no shock inputs available"}
    raw = s / wsum
    if index_returns is not None:
        raw += lam_csd * max(0.0, last(csd(index_returns)))
    p = float(to_100(raw))
    return {"ok": True, "shock_prob": round(p, 1), "raw_z": round(raw, 2),
            "alert": "HIGH" if p >= 70 else "ELEVATED" if p >= 50 else "LOW", "components": comps}
