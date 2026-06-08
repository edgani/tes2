"""flow.py — L4 Flow Engine. Capital rotation: which asset/sector is GAINING relative strength
(money rotating IN) vs losing (rotating OUT). Uses ETF flow if provided, else RS-rotation proxy."""
from __future__ import annotations
import numpy as np, pandas as pd
from ..core.change_core import robust_z, delta_z, last

def run_flow(prices: dict, bench: pd.Series, etf_flows: dict | None = None, lookback: int = 21) -> dict:
    rot = {}
    b = np.log(pd.Series(bench)).diff()
    for name, px in prices.items():
        r = np.log(pd.Series(px)).diff()
        rs = (r.rolling(lookback).mean() - b.rolling(lookback).mean())
        rs_accel = last(delta_z(rs))                              # is RS accelerating? (rotation IN)
        flow_z = last(robust_z(pd.Series(etf_flows[name]))) if etf_flows and name in etf_flows else 0.0
        rot[name] = round(0.6 * last(robust_z(rs)) + 0.4 * rs_accel + 0.3 * flow_z, 2)
    rank = sorted(rot.items(), key=lambda kv: kv[1], reverse=True)
    return {"ok": True, "rotation_score": rot,
            "rotating_in": [k for k, v in rank[:3] if v > 0],
            "rotating_out": [k for k, v in rank[-3:] if v < 0]}
