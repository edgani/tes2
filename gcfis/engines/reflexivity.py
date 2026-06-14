"""reflexivity.py — B5 Reflexivity Engine. Detects self-reinforcing (runaway) loops:
price→flow→narrative→price (Soros). Runaway = price AND flow ACCELERATING together (the
PLTR/SNDK monster-move signature) with a non-contradicting cross-lag gain. Acceleration is
measured smoothly (momentum now vs momentum 20 bars ago) to avoid single-day noise."""
from __future__ import annotations
import numpy as np, pandas as pd
from ..core.change_core import to_100

def _accel(s, n: int = 20) -> float:
    """Smooth acceleration: (mean change last n) - (mean change prior n), normalized. >0 = accelerating."""
    x = pd.to_numeric(pd.Series(s), errors="coerce").dropna()
    if len(x) < 3 * n:
        return 0.0
    chg = np.log(x).diff() if bool((x > 0).all()) else x.diff()
    recent = chg.iloc[-n:].mean(); prev = chg.iloc[-2 * n:-n].mean()
    sd = chg.iloc[-3 * n:].std() or 1e-9
    return float((recent - prev) / sd)

def _flow_proxy(px_index, volume, options_oi, social):
    for cand in (volume, options_oi, social):
        if cand is not None and len(pd.Series(cand).dropna()) > 40:
            return pd.to_numeric(pd.Series(cand), errors="coerce").reindex(px_index)
    return None

def run_reflexivity(price, volume=None, options_oi=None, earnings_rev=None, social=None) -> dict:
    px = pd.to_numeric(pd.Series(price), errors="coerce").dropna()
    if len(px) < 70:
        return {"ok": False, "reason": "insufficient history", "reflexivity": 50.0, "runaway": False}
    r = np.log(px).diff()
    flow = _flow_proxy(px.index, volume, options_oi, social)
    # cross-lag gain: corr(Δprice_t, Δflow_{t+1}) * corr(Δflow_t, Δprice_{t+1})
    reflex_coef = 0.0
    if flow is not None:
        df = flow.diff()
        a = r.reindex(df.index).to_numpy(); f = df.to_numpy()
        mask = np.isfinite(a) & np.isfinite(f); a, f = a[mask], f[mask]
        if len(a) > 40 and a[:-1].std() > 1e-12 and f[:-1].std() > 1e-12:
            c1 = np.corrcoef(a[:-1], f[1:])[0, 1]; c2 = np.corrcoef(f[:-1], a[1:])[0, 1]
            if np.isfinite(c1) and np.isfinite(c2):
                reflex_coef = float(c1 * c2) if (c1 > 0 and c2 > 0) else float(-abs(c1 * c2))
    price_accel = _accel(px); flow_accel = _accel(flow) if flow is not None else 0.0
    er_accel = _accel(earnings_rev) if (earnings_rev is not None and len(pd.Series(earnings_rev).dropna()) > 60) else None
    accs = [price_accel] + ([flow_accel] if flow is not None else []) + ([er_accel] if er_accel is not None else [])
    reflex_accel = float(np.mean(accs))
    score = float(to_100(0.5 * reflex_accel + 4.0 * max(reflex_coef, 0.0) + 0.3 * min(price_accel, flow_accel)))
    runaway = bool(price_accel > 0.3 and flow_accel > 0.3 and reflex_coef >= -0.05)
    return {"ok": True, "reflexivity": round(score, 1), "reflex_coef": round(reflex_coef, 3),
            "reflex_accel": round(reflex_accel, 2), "price_accel": round(price_accel, 2),
            "flow_accel": round(flow_accel, 2), "runaway": runaway}
