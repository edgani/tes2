"""bottleneck_engine.py — L6 Bottleneck Engine. Geometric mean of NORMALIZED [0,1] factors
(AND-logic: any zero kills it). PricingPower (Δgross-margin) = observable signature. Emits a
ticker→node map so each ticker INHERITS its supply-chain node's bottleneck score (the wiring
that was missing — bottleneck alpha now reaches asset selection)."""
from __future__ import annotations
import numpy as np

_FACTORS = ("scarcity", "demand_growth", "lead_time", "replace_diff", "pricing_power")

def _n(x): return float(np.clip(x, 0.0, 1.0))

def bottleneck_score(scarcity, demand_growth, lead_time, replace_diff, pricing_power) -> float:
    f = [_n(scarcity), _n(demand_growth), _n(lead_time), _n(replace_diff), _n(pricing_power)]
    return float(np.prod(f) ** (1.0 / len(f)))

def run_bottleneck(nodes: dict, chain_edges: list | None = None) -> dict:
    """nodes: {name: {scarcity,demand_growth,lead_time,replace_diff,pricing_power, tickers?:[...]}}."""
    scored, tmap = {}, {}
    for n, v in nodes.items():
        fv = {k: v.get(k, 0.0) for k in _FACTORS}
        scored[n] = round(bottleneck_score(**fv), 3)
        for t in v.get("tickers", []) or []:
            tmap[str(t)] = n
    rank = sorted(scored.items(), key=lambda kv: kv[1], reverse=True)
    return {"ok": True, "scores": scored, "ticker_node": tmap,
            "tightest_bottleneck": rank[0][0] if rank else None, "ranked": [n for n, _ in rank]}
