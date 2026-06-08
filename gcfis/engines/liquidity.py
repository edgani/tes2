"""liquidity.py — L3 Liquidity Engine. NetLiq = FedBS - TGA - RRP (correct signs: TGA/RRP DRAIN).
Flow (Δ) matters more than level. Dominance gate flags when liquidity is the driver."""
from __future__ import annotations
import pandas as pd
from ..core.change_core import robust_z, to_100, last

def run_liquidity(inputs: dict) -> dict:
    fed, tga, rrp = inputs.get("fed_bs"), inputs.get("tga"), inputs.get("rrp")
    if fed is None:
        return {"ok": False, "reason": "no Fed balance-sheet data"}
    fed = pd.Series(fed).astype(float)
    netliq = fed.copy()
    if tga is not None: netliq = netliq.sub(pd.Series(tga).astype(float), fill_value=0)
    if rrp is not None: netliq = netliq.sub(pd.Series(rrp).astype(float), fill_value=0)
    flow20 = netliq.diff(20)
    expanding = bool(last(flow20) > 0)                            # direction vs ZERO baseline (robust)
    flow_z = last(robust_z(flow20))                              # pace: is the change unusually fast?
    level_z = last(robust_z(netliq))                             # ampleness vs own history (well-behaved on trends)
    credit = inputs.get("credit_creation")
    cc = last(robust_z(pd.Series(credit).diff(20))) if credit is not None else 0.0
    score = float(to_100(0.6 * level_z + 0.4 * (1.0 if expanding else -1.0) + 0.2 * cc))
    return {"ok": True, "liquidity_regime": round(score, 1), "liq_flow_z": round(flow_z, 2),
            "expanding": expanding, "dominant": abs(flow_z) > 1.5}
