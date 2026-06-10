"""narrative.py — composes the LOGICAL 'why' for every ticker recommendation + the entry rationale.
No recommendation without a reason. Pulls regime + which layers fired + entry plan into plain language."""
from __future__ import annotations

def build_reason(sig, ticker_data: dict, systemic: dict, cross: dict | None = None) -> str:
    parts = []
    quad = systemic.get("forward_quad"); qn = {"Q1": "Goldilocks", "Q2": "Reflation", "Q3": "Stagflation", "Q4": "Deflation"}.get(quad, "")
    # 1) macro/regime context
    if quad:
        parts.append(f"Quad {quad} {qn}")
    if cross and cross.get("regime"):
        parts.append(f"cross-asset={cross['regime']}")
    frag = systemic.get("fragility"); shk = systemic.get("shock_prob")
    if frag and frag >= 60: parts.append(f"⚠ fragility {frag}")
    if shk and shk >= 60: parts.append(f"⚠ shock {shk}")
    # 2) which offensive layers fired (the WHY this ticker)
    why = []
    th = ticker_data.get("theme"); ts = ticker_data.get("theme_score", 0)
    if th and ts > 0.3: why.append(f"theme {th} leading (RS {ts:+.1f})")
    stg = ticker_data.get("stage")
    if stg in ("SMART_MONEY", "INSTITUTIONAL"): why.append(f"{stg.lower()} accumulation (crowd {ticker_data.get('crowding','?')})")
    if ticker_data.get("sweet_spot"): why.append("uncrowded sweet-spot (Stage 2→3)")
    if ticker_data.get("bottleneck_node"):
        why.append(f"bottleneck node {ticker_data['bottleneck_node']} ({ticker_data.get('bottleneck_score','?')})")
    if ticker_data.get("runaway"): why.append("reflexive runaway loop (price×flow accelerating)")
    if ticker_data.get("rotation"): why.append(f"rotation-primed by {ticker_data['rotation'].get('leader')} (lead-lag)")
    if ticker_data.get("broker_verdict") == "NET_ACCUMULATION": why.append("smart-money net buying")
    if ticker_data.get("broker_verdict") == "NET_DISTRIBUTION": why.append("smart-money DISTRIBUTING")
    if ticker_data.get("exit_signal"): why.append("late-stage / exit risk")
    if ticker_data.get("cot_extreme_long"): why.append("COT extreme-long (crowded)")
    # 3) compose
    head = f"{sig.action} {sig.ticker} (conv {sig.conviction})"
    ctx = " · ".join(parts) if parts else "—"
    rationale = "; ".join(why) if why else "confluence below threshold"
    out = f"{head} | {ctx} | WHY: {rationale}"
    # 4) entry plan
    if sig.entry_type:
        ev = "VALID" if sig.entry_valid else "WAIT (invalid)"
        out += (f" | ENTRY: {sig.entry_type} [{ev}], gamma={sig.gamma_regime}, "
                f"in {sig.entry_px} stop {sig.stop} tgt {sig.target} R/R {sig.rr}")
    # 5) regime gate (the 'data good but price falling' guard)
    if cross and cross.get("defer_longs") and sig.direction == "long":
        out += f" | ⛔ DEFER: {cross['regime']} — don't enter longs into liquidation; wait for exhaustion."
    return out
