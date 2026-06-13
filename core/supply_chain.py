"""supply_chain.py — Citrini-style bottleneck NETWORK (not boolean). ChatGPT flaw #3.

Ships a default researched AI supply-chain dependency graph (demand → compute → HBM → foundry →
power → cooling/grid → uranium) and scores each node's bottleneck tightness AND its propagation
centrality (how many downstream nodes depend on it). The hidden second-order winner is the node
with high tightness + high centrality that retail isn't looking at. Factor priors are editable.
"""
from __future__ import annotations
from engines.bottleneck_engine import bottleneck_score

# node: factor priors (0..1) + downstream dependents + representative tickers (Citrini-style)
_AI_CHAIN = {
    "AI_demand":   {"f": (0.30, 0.95, 0.20, 0.30, 0.40), "down": ["GPU_compute"], "tickers": ["MSFT", "GOOGL", "META"]},
    "GPU_compute": {"f": (0.70, 0.92, 0.65, 0.85, 0.80), "down": ["HBM", "foundry", "cooling", "power"], "tickers": ["NVDA", "AVGO", "AMD"]},
    "HBM":         {"f": (0.85, 0.88, 0.78, 0.80, 0.75), "down": ["foundry"], "tickers": ["MU", "SK_Hynix"]},
    "foundry":     {"f": (0.80, 0.80, 0.90, 0.95, 0.70), "down": [], "tickers": ["TSM"]},
    "power":       {"f": (0.75, 0.85, 0.88, 0.70, 0.65), "down": ["grid", "uranium"], "tickers": ["VST", "CEG", "NRG", "SMR"]},
    "cooling":     {"f": (0.68, 0.82, 0.60, 0.55, 0.60), "down": [], "tickers": ["VRT"]},
    "grid":        {"f": (0.72, 0.78, 0.85, 0.75, 0.62), "down": [], "tickers": ["ETN", "PWR", "GEV"]},
    "uranium":     {"f": (0.65, 0.70, 0.92, 0.80, 0.55), "down": [], "tickers": ["CCJ", "UEC"]},
}
_FK = ("scarcity", "demand_growth", "lead_time", "replace_diff", "pricing_power")


def _centrality(chain: dict) -> dict:
    """Count of all downstream nodes that (transitively) depend on each node = propagation reach."""
    def reach(n, seen):
        for d in chain.get(n, {}).get("down", []):
            if d not in seen:
                seen.add(d); reach(d, seen)
        return seen
    return {n: len(reach(n, set())) for n in chain}


def run_supply_chain(chain: dict | None = None) -> dict:
    chain = chain or _AI_CHAIN
    cent = _centrality(chain)
    cmax = max(cent.values()) or 1
    out = {}
    for n, v in chain.items():
        tight = bottleneck_score(**dict(zip(_FK, v["f"])))
        c = cent[n] / cmax
        # pressure = tightness AND centrality (both matter; geometric so neither alone dominates)
        pressure = round((tight * (0.4 + 0.6 * c)) ** 0.5 if tight > 0 else 0.0, 3)
        out[n] = {"tightness": round(tight, 3), "centrality": round(c, 2),
                  "pressure": pressure, "tickers": v.get("tickers", []),
                  "color": ("red" if tight > 0.7 else "cyan" if tight > 0.5 else "yellow")}
    rank = sorted(out.items(), key=lambda kv: kv[1]["pressure"], reverse=True)
    # hidden winner: high pressure but NOT the obvious demand/compute node
    hidden = next((n for n, _ in rank if n not in ("AI_demand", "GPU_compute")), None)
    return {"ok": True, "nodes": out, "ranked": [n for n, _ in rank],
            "tightest": rank[0][0] if rank else None, "hidden_winner": hidden,
            "ticker_node": {t: n for n, v in chain.items() for t in v.get("tickers", [])}}
