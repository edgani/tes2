"""forward_macro.py — Market-Implied Forward Growth/Inflation (fix Quad latency).
Nowcast growth/inflation from MARKETS (daily) instead of lagged GDP/CPI. Default weights are
priors; .fit() does ridge on real next-period growth when you pass a target on your machine."""
from __future__ import annotations
import numpy as np, pandas as pd
from ..core.change_core import robust_z, delta_z, last

# sign-oriented so each contributes positively to "growth up"
_G = {"copper_gold": 0.16, "oil": 0.10, "sox": 0.16, "hy_oas_inv": 0.14, "smallcap_ratio": 0.12,
      "baltic": 0.08, "dxy_inv": 0.08, "y10": 0.08, "curve_10_2": 0.08}
_I = {"breakeven": 0.35, "commodities": 0.25, "dxy_inv": 0.15, "wage_proxy": 0.25}

def _composite(inputs: dict, weights: dict) -> tuple[float, pd.Series | None, dict]:
    val, wsum, comps, series = 0.0, 0.0, {}, None
    for k, w in weights.items():
        x = inputs.get(k)
        if x is None or len(pd.Series(x).dropna()) < 20:
            continue
        zs = robust_z(x); comps[k] = round(last(zs), 2); val += w * last(zs); wsum += w
        series = (zs * w) if series is None else series.add(zs * w, fill_value=0)
    return (val / wsum if wsum else 0.0), (series / wsum if wsum else None), comps

def run_forward_macro(growth_inputs: dict, infl_inputs: dict) -> dict:
    mifg, gser, gc = _composite(growth_inputs, _G)
    mii, iser, ic = _composite(infl_inputs, _I)
    groc = last(delta_z(gser)) if gser is not None else 0.0
    iroc = last(delta_z(iser)) if iser is not None else 0.0
    g_up, i_up = groc >= 0, iroc >= 0
    quad = ("Q2" if g_up and i_up else "Q1" if g_up and not i_up
            else "Q3" if not g_up and i_up else "Q4")
    names = {"Q1": "Goldilocks", "Q2": "Reflation", "Q3": "Stagflation", "Q4": "Deflation"}
    return {"ok": True, "MIFG": round(mifg, 2), "MII": round(mii, 2), "GROC": round(groc, 2),
            "IROC": round(iroc, 2), "forward_quad": quad, "quad_name": names[quad],
            "growth_components": gc, "infl_components": ic}

def fit_ridge(factor_df: pd.DataFrame, target_growth: pd.Series, alpha: float = 1.0) -> dict:
    """Optional: fit weights on real next-period growth (run on your machine with real data)."""
    from sklearn.linear_model import Ridge
    X = factor_df.apply(robust_z).dropna(); y = target_growth.reindex(X.index).dropna()
    X = X.reindex(y.index)
    m = Ridge(alpha=alpha).fit(X.values, y.values)
    return {"weights": dict(zip(X.columns, m.coef_)), "intercept": float(m.intercept_),
            "r2": float(m.score(X.values, y.values))}
