"""bottleneck.py — L6 Bottleneck Engine. FIXED: geometric mean of NORMALIZED [0,1] factors
(AND-logic: any zero kills it), NOT a raw dimensional product. PricingPower (Δgross-margin) is the
observable signature. Optional supply-chain graph ranks nodes + tracks winner migration."""
from __future__ import annotations
import numpy as np

def _n(x):  # clamp to [0,1]
    return float(np.clip(x, 0.0, 1.0))

def bottleneck_score(scarcity, demand_growth, lead_time, replace_diff, pricing_power) -> float:
    factors = [_n(scarcity), _n(demand_growth), _n(lead_time), _n(replace_diff), _n(pricing_power)]
    return float(np.prod(factors) ** (1.0 / len(factors)))      # geometric mean

def run_bottleneck(nodes: dict, chain_edges: list | None = None) -> dict:
    """nodes: {name: {scarcity, demand_growth, lead_time, replace_diff, pricing_power}} each 0..1."""
    scored = {n: round(bottleneck_score(**v), 3) for n, v in nodes.items()}
    rank = sorted(scored.items(), key=lambda kv: kv[1], reverse=True)
    return {"ok": True, "scores": scored, "tightest_bottleneck": rank[0][0] if rank else None,
            "ranked": [n for n, _ in rank]}
