"""elimination.py — doc 3 Stage-1 HARD elimination ('buang sampah dulu'): liquidity, noise,
structure. A ticker failing here never reaches scoring. From closes+volume (proxy-grade)."""
from __future__ import annotations
import numpy as np, pandas as pd

def run_elimination(price, volume=None, min_adv: float = 0.0,
                    max_gap_freq: float = 0.05, max_volofvol: float = 1.20,
                    max_false_bo: float = 0.70) -> dict:
    px = pd.to_numeric(pd.Series(price), errors="coerce").dropna()
    if len(px) < 90:
        return {"ok": True, "eliminated": True, "reasons": ["insufficient history (<90 bars)"]}
    r = np.log(px).diff().dropna()
    reasons = []
    # liquidity: ADV floor (needs volume)
    if volume is not None and min_adv > 0:
        v = pd.to_numeric(pd.Series(volume), errors="coerce").reindex(px.index)
        adv = float((px * v).tail(20).mean() or 0)
        if adv < min_adv:
            reasons.append(f"ADV {adv:,.0f} < floor {min_adv:,.0f} (edge eaten by execution cost)")
    # noise: wild gaps + unstable volatility regime — ROBUST sigma (MAD), or the gaps inflate σ and hide themselves
    med = float(r.median())
    sig = float(1.4826 * (r - med).abs().median() or 1e-9)
    gap_freq = float((r.abs() > 4 * sig).mean())
    if gap_freq > max_gap_freq:
        reasons.append(f"gap-driven ({gap_freq:.0%} of days are >4σ moves)")
    rv = r.rolling(20).std().dropna()
    volofvol = float((rv.std() / (rv.mean() or 1e-9)))
    if volofvol > max_volofvol:
        reasons.append(f"unstable volatility regime (vol-of-vol {volofvol:.2f})")
    # structure: false-breakout frequency (20d-high breaks that close back below within 3 bars)
    hi20 = px.rolling(20).max().shift(1)
    bo = px > hi20
    idxs = list(np.where(bo.fillna(False).values)[0])
    fails = total = 0; last = -10
    for i in idxs:
        if i - last < 5 or i + 3 >= len(px):
            continue
        total += 1; last = i
        if float(px.iloc[i + 1:i + 4].min()) < float(hi20.iloc[i]):
            fails += 1
    if total >= 5 and (fails / total) > max_false_bo:
        reasons.append(f"false-breakout machine ({fails}/{total} breakouts fail in 3 bars)")
    return {"ok": True, "eliminated": bool(reasons), "reasons": reasons,
            "stats": {"gap_freq": round(gap_freq, 3), "volofvol": round(volofvol, 2)}}
