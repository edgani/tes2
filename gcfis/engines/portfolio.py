"""portfolio.py — portfolio-level concentration guard. Per-name sizing ignores that several longs
may be ONE bet (same factor / high correlation). Greedy-clusters the long book by return correlation,
reports effective number of independent bets, flags concentration, and emits an alloc multiplier so a
correlated cluster isn't oversized (1/cluster_size). Uses returns only — no new data."""
from __future__ import annotations
import numpy as np, pandas as pd

def run_portfolio(long_tickers, prices, rho_thresh: float = 0.6, window: int = 120) -> dict:
    ts = [t for t in long_tickers if t in prices and len(pd.Series(prices[t]).dropna()) > 30]
    if len(ts) < 2:
        return {"ok": True, "effective_bets": len(ts), "clusters": [[t] for t in ts],
                "warning": None, "alloc_mult": {t: 1.0 for t in ts}}
    rets = pd.DataFrame({t: np.log(pd.to_numeric(prices[t], errors="coerce")).diff() for t in ts}).dropna()
    if len(rets) < 30:
        return {"ok": True, "effective_bets": len(ts), "clusters": [[t] for t in ts],
                "warning": None, "alloc_mult": {t: 1.0 for t in ts}}
    C = rets.tail(window).corr()
    clusters, assigned = [], set()
    for t in ts:                                          # greedy correlation clustering
        if t in assigned:
            continue
        cl = [t]; assigned.add(t)
        for u in ts:
            if u not in assigned and float(C.loc[t, u]) >= rho_thresh:
                cl.append(u); assigned.add(u)
        clusters.append(cl)
    biggest = max(clusters, key=len)
    warning = (f"{len(biggest)} of {len(ts)} longs are ONE correlated bet "
               f"({', '.join(biggest)}, ρ≥{rho_thresh}) — size as one position"
               if len(biggest) > max(2, len(ts) // 2) else None)
    alloc_mult = {t: round(1.0 / len(cl), 3) for cl in clusters for t in cl}
    return {"ok": True, "effective_bets": len(clusters), "n_longs": len(ts),
            "clusters": clusters, "warning": warning, "alloc_mult": alloc_mult}
