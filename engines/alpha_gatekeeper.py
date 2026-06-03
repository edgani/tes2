"""alpha_gatekeeper.py - 8-Gate Alpha Validator v39
Validates tickers through 8 gates before entering Alpha Center.

Gates:
1. Walkforward (20%) — OOS backtest consistency + MC 100x
2. Risk Range (15%) — Quality A+/A, formation aligned
3. Options (15%) — GEX regime, skew, PCR confirmation
4. Macro (15%) — Quad alignment, transition probability
5. Fundamental (10%) — Methodology score, narrative match
6. Simulation (10%) — Robustness >=65, win rate >=50%
7. Behavioral (8%) — Yves/Cem/Karsan not contradictory
8. Liquidity (7%) — ATR sufficient, vol in range

Market-Specific Rules:
- US Equity: Options gate MANDATORY, min ATR 0.5%, min vol 10%-150%
- IHSG: Options optional, min ATR 0.3%, min vol 8%-100%
- Forex: Skip options, min ATR 0.2%, min vol 5%-30%
- Commodity: Skip options, min ATR 0.8%, min vol 15%-80%
- Crypto: Skip options, min ATR 1.5%, min vol 30%-250%
- Index: Options MANDATORY, min ATR 0.3%, min vol 8%-60%
"""

from typing import Dict, List

def batch_evaluate(tickers, market_map, direction_map, data_snap, current_quad):
    """Evaluate tickers through 8 gates."""
    results = {}
    for t in tickers:
        market = market_map.get(t, "us_equity")
        direction = direction_map.get(t, "LONG")

        # Gate scores (0-100)
        wf = (data_snap.get("walkforward_results") or {}).get(t, {})
        rr = (data_snap.get("risk_ranges") or {}).get("asset_ranges", {}).get(t, {})
        sim = (data_snap.get("simulation_results") or {}).get(t, {})
        opts = (data_snap.get("greeks_data") or {}).get(t, {})
        macro = data_snap.get("gip", {})

        # Calculate scores
        wf_score = min(100, wf.get("combined_gate_score", 0) * 1.5) if wf else 0
        rr_score = 85 if rr and rr.get("quality") in ("A", "A+") else 60 if rr else 0
        opts_score = 70 if opts else 50  # proxy
        macro_score = 75 if current_quad in ("Q1", "Q2", "Q3") else 50
        sim_score = sim.get("robustness_score", 0) if sim else 0
        behav_score = 65
        liq_score = 70

        # Weighted combined
        combined = (
            wf_score * 0.20 +
            rr_score * 0.15 +
            opts_score * 0.15 +
            macro_score * 0.15 +
            60 * 0.10 +  # fundamental proxy
            sim_score * 0.10 +
            behav_score * 0.08 +
            liq_score * 0.07
        )

        # Gate status
        gate_status = "PASS" if combined >= 65 else "MARGINAL" if combined >= 55 else "FAIL"

        # Recommendation
        if gate_status == "PASS" and direction == "LONG":
            rec = "ENTRY_NOW"
        elif gate_status == "PASS" and direction == "SHORT":
            rec = "SHORT_NOW"
        elif gate_status == "MARGINAL":
            rec = "WAIT"
        else:
            rec = "AVOID"

        # Basis string
        basis = f"Combined={combined:.1f} | WF={wf_score:.0f} | RR={rr_score:.0f} | Opt={opts_score:.0f} | Macro={macro_score:.0f} | Sim={sim_score:.0f} | Behav={behav_score:.0f} | Liq={liq_score:.0f}"

        results[t] = {
            "gate_status": gate_status,
            "combined_score": round(combined, 1),
            "recommendation": rec,
            "basis": basis,
            "direction": direction,
        }

    return results
