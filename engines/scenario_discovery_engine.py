"""scenario_discovery_engine.py — narrative scenario discovery."""
SCENARIOS = {
    "REFLATION_BOOM": {"quad": "Q2", "thesis": "Growth+Inflation re-accel → Energy, Financials, Cyclicals",
                       "tickers": ["XLE", "XLF", "XLI", "FCX", "CAT"]},
    "STAGFLATION": {"quad": "Q3", "thesis": "Growth↓ Inflation↑ → Energy, Gold, Defensive",
                    "tickers": ["XLE", "GLD", "GDX", "CL=F"]},
    "LIQUIDITY_CRUNCH": {"quad": "Q4", "thesis": "Growth↓ Inflation↓ → USD, Treasuries, Utilities",
                         "tickers": ["UUP", "TLT", "XLU", "XLP"]},
    "AI_CAPEX_PHASE2": {"quad": "Q1", "thesis": "AI buildout — Power, Cooling, Custom Silicon",
                        "tickers": ["VRT", "ETN", "AVGO", "MRVL", "MU"]},
    "ATOMS_OVER_BITS": {"quad": "Q2", "thesis": "Citrini — physical bottlenecks > software",
                        "tickers": ["STX", "WDC", "SNDK", "MTRN", "ATI"]},
    "GOLD_DEBASEMENT": {"quad": "Q3", "thesis": "Fiscal dominance → gold flows",
                        "tickers": ["GLD", "GDX", "NEM", "FNV"]},
    "ENERGY_GEOPOLITICS": {"quad": "Q2", "thesis": "Iran/Houthi escalation → oil tankers, defense",
                           "tickers": ["FRO", "STNG", "INSW", "LMT", "RTX"]},
}

def run_scenario_discovery(gip_result=None, current_quad="Q3"):
    # Accept GIPResult object OR dict
    if gip_result is None:
        quad = current_quad
    elif isinstance(gip_result, dict):
        quad = gip_result.get("current_quad") or gip_result.get("monthly_quad") or gip_result.get("structural_quad") or current_quad
    else:
        # GIPResult dataclass / object
        quad = getattr(gip_result, "monthly_quad", None) or getattr(gip_result, "current_quad", None) or getattr(gip_result, "structural_quad", None) or current_quad
    if not isinstance(quad, str) or not quad.startswith("Q"):
        quad = current_quad
    active = []
    for name, data in SCENARIOS.items():
        score = 0.85 if data["quad"] == quad else 0.40
        active.append({"scenario": name, "thesis": data["thesis"],
                      "tickers": data["tickers"], "active_score": score,
                      "quad_match": data["quad"] == quad})
    active.sort(key=lambda x: -x["active_score"])
    return {"active_scenarios": active[:5], "all_scenarios": active,
            "current_quad": quad}
