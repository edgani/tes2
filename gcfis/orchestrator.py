"""orchestrator.py — runs the GCFIS stack end-to-end and produces master ranking + dashboard.
Hooks (regime_edge_fn/decision_fn/sizing_fn) let you plug the validated frontrun_engine modules
(regime_edge.py / decision.py / sizing.py) instead of duplicating them (avoids the F5 trap)."""
from __future__ import annotations
import pandas as pd
from .engines.fragility import run_fragility
from .engines.shock import run_shock
from .engines.forward_macro import run_forward_macro
from .engines.accumulation import run_accumulation
from .engines.broker_flow import run_broker_flow
from .engines.leadlag_discovery import run_leadlag_discovery
from .engines.change_detection import run_change_detection
from .meta.regime_meta import run_regime_meta

def run_gcfis(prices: dict, bench: pd.Series, regime_posterior: dict,
              systemic_inputs: dict | None = None, growth_inputs: dict | None = None,
              infl_inputs: dict | None = None, returns_matrix: pd.DataFrame | None = None,
              index_returns: pd.Series | None = None, broker_flow_by_ticker: dict | None = None,
              volumes: dict | None = None, leadlag_pairs: list | None = None) -> dict:
    systemic_inputs = systemic_inputs or {}
    frag = run_fragility(systemic_inputs, returns_matrix, index_returns)
    shock = run_shock(systemic_inputs, index_returns)
    fwd = run_forward_macro(growth_inputs or {}, infl_inputs or {})
    systemic = {"fragility": frag.get("fragility", 0), "shock_prob": shock.get("shock_prob", 0)}

    per_ticker = {}
    for tkr, px in prices.items():
        a = run_accumulation(tkr, px, bench, volume=(volumes or {}).get(tkr))
        if broker_flow_by_ticker and tkr in broker_flow_by_ticker:
            bf = run_broker_flow(broker_flow_by_ticker[tkr],
                                 price_down=(px.iloc[-1] < px.iloc[-20] if len(px) > 20 else True))
            a["broker_sign"] = 1 if bf.get("verdict") == "NET_ACCUMULATION" else -1
            a["broker_verdict"] = bf.get("verdict", "")
        per_ticker[tkr] = a

    ranking = run_regime_meta(per_ticker, systemic, regime_posterior)
    ll = run_leadlag_discovery(prices, candidate_pairs=leadlag_pairs) if len(prices) >= 2 else {"ok": False}
    return {"ok": True, "systemic": {"fragility": frag, "shock": shock, "forward_macro": fwd},
            "ranking": ranking, "leadlag": {k: v for k, v in ll.items() if k != "_engine"},
            "accumulation": per_ticker}
