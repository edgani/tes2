"""change_detection.py — the Druckenmiller philosophy fix: classify the REGIME OF CHANGE
per metric (level vs RoC vs acceleration). Validated premise: acceleration is predictive."""
from __future__ import annotations
import pandas as pd
from ..core.change_core import robust_z, delta_z, acceleration, last

def classify_series(x: pd.Series, window: int = 252) -> dict:
    lvl = last(robust_z(x, window)); roc = last(delta_z(x, window=window)); acc = last(acceleration(x, window=window))
    if   roc > 0 and acc > 0: state = "ACCELERATING_UP"
    elif roc > 0 and acc < 0: state = "DECELERATING"        # momentum fading (early warning)
    elif roc < 0 and acc < 0: state = "ACCELERATING_DOWN"
    elif roc < 0 and acc > 0: state = "RECOVERING"          # early turn
    else:                     state = "STABLE"
    return {"level_z": round(lvl, 2), "roc_z": round(roc, 2), "accel_z": round(acc, 2),
            "state": state, "strength": round(abs(roc) + abs(acc), 2)}

def run_change_detection(metrics: dict[str, pd.Series], window: int = 252) -> dict:
    out = {k: classify_series(v, window) for k, v in (metrics or {}).items() if v is not None and len(v) > 20}
    accel_up = [k for k, v in out.items() if v["state"] == "ACCELERATING_UP"]
    accel_dn = [k for k, v in out.items() if v["state"] == "ACCELERATING_DOWN"]
    return {"ok": bool(out), "per_metric": out, "accelerating_up": accel_up, "accelerating_down": accel_dn}
