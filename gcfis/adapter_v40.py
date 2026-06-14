"""adapter_v40.py — bridge GCFIS <-> existing MacroRegime v40 (data + regime), with safe fallbacks.
Run inside the v40 package so these imports resolve. No market data is fetched here."""
from __future__ import annotations
import pandas as pd

def get_prices_from_v40(tickers=None, start="2023-01-01"):
    try:
        from orchestrator import load_prices            # type: ignore
        return load_prices(tickers, start)
    except Exception as e:
        return {"_error": f"v40 load_prices unavailable: {e}"}

def get_regime_posterior_from_v40(prices) -> dict:
    """Map v40 markov_v3 regime output -> GCFIS posterior dict. Falls back to neutral chop."""
    try:
        from orchestrator import run_markov_v3           # type: ignore
        out = run_markov_v3(prices) or {}
        st = (out.get("state") or out.get("regime") or "").lower()
        m = {"risk on": "risk_on", "bull": "risk_on", "risk off": "risk_off", "bear": "risk_off",
             "recovery": "transition_up", "topping": "transition_down", "range": "chop"}
        key = next((v for k, v in m.items() if k in st), "chop")
        return {key: 1.0}
    except Exception:
        return {"chop": 1.0}
