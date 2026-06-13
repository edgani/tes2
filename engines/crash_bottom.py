"""crash_bottom.py — doc-21/22: crash-pressure composite, crash-type classifier
(FLUSH / CYCLICAL / SYSTEMIC), and local-vs-durable bottom state.
HONEST: credit-spread & funding feeds absent → systemic classification leans on the
cross-asset deleveraging flag + liquidity engine; this is labeled in `basis`.
Weights are PRIORS pending walk-forward validation."""
from __future__ import annotations
import numpy as np

def run_crash_bottom(systemic: dict, internals: dict | None, per_ticker: dict) -> dict:
    internals = internals or {}
    frag = float(systemic.get("fragility", 50) or 50)
    liq = float(systemic.get("liquidity", 50) or 50)
    shock = float(systemic.get("shock_prob", 50) or 50)
    breadth = internals.get("breadth")
    cross = (systemic.get("cross_asset") or {})
    delev = bool(cross.get("defer_longs")) or str(cross.get("regime", "")).upper().startswith("DELEV")
    n = max(len(per_ticker), 1)
    crowd_hi = sum(1 for a in per_ticker.values() if float(a.get("crowding", 50) or 50) > 80) / n
    gex_known = [a for a in per_ticker.values() if (a.get("dealer") or {}).get("gex_sign")]
    gex_neg = (sum(1 for a in gex_known if a["dealer"]["gex_sign"] < 0) / len(gex_known)) if gex_known else 0.5
    dist_sh = sum(1 for a in per_ticker.values()
                  if (a.get("flow") or {}).get("type") in ("DISTRIBUTION", "PANIC_LIQUIDATION")) / n
    comp = {
        "fragility": frag / 100.0,
        "liquidity_contraction": (100.0 - liq) / 100.0,
        "breadth_weak": (1.0 - float(breadth)) if breadth is not None else 0.5,
        "crowding_unwind": crowd_hi,
        "divergences": min(len(internals.get("divergences", [])) / 3.0, 1.0),
        "dealer_gamma": gex_neg,
        "distribution": dist_sh,
    }
    w = {"fragility": .22, "liquidity_contraction": .22, "breadth_weak": .16,
         "crowding_unwind": .12, "divergences": .10, "dealer_gamma": .10, "distribution": .08}
    pressure = 100.0 * sum(w[k] * comp[k] for k in w)
    if delev or (liq < 35 and frag > 70):
        ctype, basis = "SYSTEMIC", "deleveraging flag / liquidity+fragility extremes (credit feed = seam)"
    elif comp["breadth_weak"] > 0.55 and frag > 55:
        ctype, basis = "CYCLICAL", "breadth deterioration + fragility"
    elif crowd_hi > 0.5 and shock > 55:
        ctype, basis = "FLUSH", "positioning-driven (recoverable profile)"
    else:
        ctype, basis = "LOW", "no dominant crash driver"
    # ---- bottom state (doc-21 part 2): stabilization, not oversold ----
    panic_sh = sum(1 for a in per_ticker.values()
                   if (a.get("flow") or {}).get("type") == "PANIC_LIQUIDATION") / n
    reclaim_sh = sum(1 for a in per_ticker.values()
                     if (a.get("response") or {}).get("response") in ("FAILED_BREAKDOWN_RECLAIM", "ABSORPTION_HOLD")) / n
    accum_sh = sum(1 for a in per_ticker.values() if (a.get("flow") or {}).get("type") == "ACCUMULATION") / n
    accel_pos = sum(1 for a in per_ticker.values() if float(a.get("acceleration", 0) or 0) > 0) / n
    checks = {"seller_exhaustion": reclaim_sh > 0.25, "accumulation_return": accum_sh > 0.30,
              "breadth_recovery": (breadth is not None and breadth > 0.55),
              "leadership_return": accel_pos > 0.5, "vol_normalizing": shock < 50,
              "liquidity_recovering": liq > 55}
    n_true = sum(checks.values())
    if n_true >= 4:
        bstate = "DURABLE_BOTTOM_FORMING"
    elif panic_sh > 0.2 and n_true <= 2:
        bstate = "LOCAL_BOUNCE_RISK"
    else:
        bstate = "NO_BOTTOM_SIGNAL"
    return {"pressure": round(float(pressure), 1), "components": {k: round(v, 2) for k, v in comp.items()},
            "type": ctype, "basis": basis,
            "bottom": {"state": bstate, "checks": checks, "score": round(100.0 * n_true / 6.0, 1)}}
