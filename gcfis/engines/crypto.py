"""crypto.py — L10 Crypto Engine. Post-ETF re-weighted: ETF flow + funding + CME basis + perp OI
dominate; on-chain (MVRV/SOPR/NUPL) is regime-gated (degraded since 2024). Graceful on missing."""
from __future__ import annotations
import numpy as np, pandas as pd
from ..core.change_core import robust_z, last

def run_crypto(inputs: dict, on_chain_regime_weight: float = 0.5) -> dict:
    def z(k):
        x = inputs.get(k)
        return last(robust_z(pd.Series(x))) if x is not None and len(pd.Series(x).dropna()) > 10 else None
    parts = {"etf_flow": (z("etf_flow"), 0.30), "funding": (z("funding"), 0.20),
             "cme_basis": (z("cme_basis"), 0.15), "perp_oi": (z("perp_oi"), 0.15),
             "stablecoin": (z("stablecoin_supply"), 0.10)}
    onchain_z = np.nanmean([v for v in (z("mvrv"), z("sopr"), z("nupl")) if v is not None]) \
        if any(z(k) is not None for k in ("mvrv", "sopr", "nupl")) else None
    score, wsum, comps = 0.0, 0.0, {}
    for k, (val, w) in parts.items():
        if val is not None:
            score += w * val; wsum += w; comps[k] = round(val, 2)
    if onchain_z is not None and not np.isnan(onchain_z):
        score += 0.10 * on_chain_regime_weight * onchain_z; wsum += 0.10 * on_chain_regime_weight
        comps["on_chain"] = round(float(onchain_z), 2)
    if wsum == 0:
        return {"ok": False, "reason": "no crypto inputs"}
    from ..core.change_core import to_100
    return {"ok": True, "crypto_score": round(float(to_100(score / wsum)), 1), "components": comps}
