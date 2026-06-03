"""interconnect_engine.py — scenario × ticker mapping."""
def run_interconnect(scenarios=None, rr_data=None):
    if not scenarios: return {"connections": []}
    scen_list = scenarios.get("active_scenarios", []) if isinstance(scenarios, dict) else []
    connections = []
    for scen in scen_list:
        for tkr in scen.get("tickers", []):
            rr = (rr_data or {}).get(tkr, {})
            sig = rr.get("signals", {}).get("action", "N/A") if isinstance(rr, dict) else "N/A"
            connections.append({"scenario": scen.get("scenario"),
                               "ticker": tkr, "action": sig,
                               "active_score": scen.get("active_score", 0)})
    return {"connections": connections}
