"""theme.py — L5 Theme Engine. Theme = 0.4*Δ(EarningsRev) + 0.3*CohortRS + 0.2*Δ(Flow) + 0.1*Narrative.
Cohort RS = the theme basket's relative strength vs benchmark (change-centric)."""
from __future__ import annotations
import numpy as np, pandas as pd
from ..core.change_core import robust_z, delta_z, last

def run_theme(theme_baskets: dict, prices: dict, bench: pd.Series,
              earnings_rev: dict | None = None, flows: dict | None = None,
              narrative: dict | None = None) -> dict:
    b = np.log(pd.Series(bench)).diff()
    out = {}
    for theme, tickers in theme_baskets.items():
        rs_vals = []
        for t in tickers:
            if t in prices:
                r = np.log(pd.Series(prices[t])).diff()
                rs_vals.append(last(robust_z((r.rolling(63).mean() - b.rolling(63).mean()))))
        cohort_rs = float(np.mean(rs_vals)) if rs_vals else 0.0
        er = last(delta_z(pd.Series(earnings_rev[theme]))) if earnings_rev and theme in earnings_rev else 0.0
        fl = last(delta_z(pd.Series(flows[theme]))) if flows and theme in flows else 0.0
        nar = float(np.clip(narrative.get(theme, 0), -2, 2)) if narrative else 0.0
        strength = 0.4 * er + 0.3 * cohort_rs + 0.2 * fl + 0.1 * nar
        out[theme] = {"strength": round(strength, 2), "cohort_rs": round(cohort_rs, 2)}
    rank = sorted(out.items(), key=lambda kv: kv[1]["strength"], reverse=True)
    return {"ok": True, "themes": out, "leading_themes": [k for k, _ in rank[:3]]}
