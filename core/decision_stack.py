"""meta/decision_stack.py — doc 6: every ticker answers 'SO WHAT DO I DO NOW?'
Composes per signal: CATEGORY (opportunity type) / WHY-NOW / WHO'S TRAPPED / MARKET MODE /
INVALIDATION (thesis conditions + price) / EXECUTION (mode, aggression, size, holding, target map)."""
from __future__ import annotations

HOLDING = {"STRUCTURAL_LONG": "weeks–months", "TACTICAL_MOMENTUM": "days–weeks",
           "SQUEEZE": "days (tactical)", "MEAN_REVERSION": "hours–days",
           "DISTRIBUTION_SHORT": "days–weeks", "REDUCE_AVOID": "—", "WATCH": "—"}

def _category(sig, a, mode):
    ftype = (a.get("flow") or {}).get("type", "NEUTRAL")
    stage = a.get("stage", "")
    if sig.direction == "short" or sig.action == "BUILD_SHORT":
        return "DISTRIBUTION_SHORT"
    if sig.action in ("AVOID",) or mode == "DISTRIBUTION":
        return "REDUCE_AVOID"
    if sig.direction == "long":
        if mode == "SQUEEZE" or ftype == "SHORT_COVERING":
            return "SQUEEZE"
        if ftype == "PANIC_LIQUIDATION" or sig.entry_type in ("MEAN_REVERSION", "PULLBACK") and mode == "PINNING":
            return "MEAN_REVERSION"
        if sig.entry_type in ("BREAKOUT", "CONTINUATION") and mode == "EXPANSION":
            return "TACTICAL_MOMENTUM"
        if ftype == "ACCUMULATION" or a.get("sweet_spot") or stage in ("SMART_MONEY", "INSTITUTIONAL"):
            return "STRUCTURAL_LONG"
        return "TACTICAL_MOMENTUM" if mode == "EXPANSION" else "STRUCTURAL_LONG"
    return "WATCH"

def _why_now(sig, a):
    w = []
    f = a.get("flow") or {}; rz = a.get("response") or {}; bm = a.get("bm") or {}
    bearish = sig.direction == "short" or sig.category in ("DISTRIBUTION_SHORT", "REDUCE_AVOID")
    if bearish:                                        # ONLY bearish evidence may justify a short/avoid
        if f.get("type") == "DISTRIBUTION": w.append(f"volume climax with NO price progress (eff {f.get('efficiency')}) — inventory unloading")
        if f.get("type") == "PANIC_LIQUIDATION": w.append("panic tape — forced selling in control")
        if rz.get("response") == "REJECTION": w.append("rejection at upper band — breakout buyers trapped above")
        if rz.get("response") == "NO_BID_CONTINUATION": w.append("no bid at the band — lower band is a waypoint, not support")
        crowd = float(a.get("crowding", 50) or 50); vel = float(a.get("adoption_velocity", 0) or 0)
        if crowd > 80 and vel < 0: w.append(f"late-stage crowding ({crowd:.0f}) with fading velocity — unwind fuel")
        if a.get("exit_signal"): w.append("stage rollover / exit signal fired")
        if (a.get("market_mode") or {}).get("mode") == "DISTRIBUTION": w.append("market mode DISTRIBUTION — upside reactions weak")
        if bm.get("regime") == "FOREIGN_LED" and bm.get("flow_score", 0) < -20: w.append("foreign-led distribution — do not fade the foreign tape")
        if a.get("_short_conflict"): w.append("⚠ conflicting tape (accumulation/reclaim present) — short is regime-driven, conviction haircut applied")
        return w[:4] or ["regime tilt short + per-ticker distribution evidence"]
    if f.get("type") == "ACCUMULATION": w.append(f"persistent accumulation (absorption {f.get('absorption')}, persistence {f.get('persistence')})")
    if f.get("type") == "SHORT_COVERING": w.append("violent short-covering tape — squeeze propagating")
    if f.get("type") == "PANIC_LIQUIDATION": w.append("panic climax, low is in (sellers exhausted)")
    if a.get("rotation"): w.append(f"rotation-primed by {a['rotation'].get('leader')} (~{a['rotation'].get('window')}d window)")
    if a.get("runaway"): w.append("reflexive runaway loop (price×flow accelerating)")
    if a.get("sweet_spot"): w.append("uncrowded sweet-spot (Stage 2→3 adoption)")
    if a.get("bottleneck_node"): w.append(f"supply-chain bottleneck: {a['bottleneck_node']}")
    if a.get("broker_verdict") == "NET_ACCUMULATION": w.append("smart-money net buying (broker flow)")
    if bm.get("regime") == "DOMESTIC_LED" and bm.get("flow_score", 0) > 20:
        w.append("domestic-led markup vs foreign selling (counter-consensus — the 2025-IHSG pattern)")
    if bm.get("regime") == "FOREIGN_LED" and bm.get("flow_score", 0) > 20:
        w.append(f"foreign-led bid (EFD {bm.get('efd')}) — follow the foreign tape")
    if rz.get("response") == "FAILED_BREAKDOWN_RECLAIM": w.append("failed breakdown + reclaim at lower band (trapped shorts)")
    if rz.get("response") == "ACCEPTANCE_ABOVE": w.append("acceptance above range (valid expansion, not a wick)")
    return w[:4] or ["confluence of layers (no single dominant trigger)"]

def _whos_trapped(sig, a, mode):
    crowd = float(a.get("crowding", 50) or 50); vel = float(a.get("adoption_velocity", 0) or 0)
    f = (a.get("flow") or {}).get("type"); rz = (a.get("response") or {}).get("response"); bm = a.get("bm") or {}
    bearish = sig.direction == "short" or sig.category in ("DISTRIBUTION_SHORT", "REDUCE_AVOID")
    if bearish:
        if rz == "REJECTION": return "breakout buyers trapped above the band"
        if crowd > 80 and vel < 0: return "late euphoric longs — unwind risk"
        if bm.get("regime") == "FOREIGN_LED" and bm.get("flow_score", 0) < -20: return "longs holding against a foreign exit"
        if f == "DISTRIBUTION": return "late buyers absorbing the unload"
        return "late longs above — supply overhead"
    if f == "SHORT_COVERING" or mode == "SQUEEZE": return "shorts trapped — forced buying fuel"
    if rz == "FAILED_BREAKDOWN_RECLAIM": return "breakdown sellers trapped below the reclaim"
    if rz == "REJECTION": return "breakout buyers trapped above the band"
    if crowd > 85 and vel < 0: return "late euphoric longs — unwind risk"
    if f == "PANIC_LIQUIDATION": return "weak hands just flushed — supply reduced"
    if crowd < 25 and sig.direction == "long": return "underexposed institutions — chase risk is UP"
    return "no acute trap — flow-driven setup"

def _invalidation(sig, a, category):
    conds = {
        "STRUCTURAL_LONG": ["absorption disappears (flow flips to distribution)",
                             f"acceptance below stop {sig.stop} (failed reclaim)", "crowding turns euphoric (>85) with fading velocity"],
        "TACTICAL_MOMENTUM": [f"close back inside the range (below {sig.stop})", "participation contracts (volume/breadth fade on push)"],
        "SQUEEZE": ["squeeze fails to propagate (no follow-through within 3 bars)", f"loss of {sig.stop}"],
        "MEAN_REVERSION": ["no reclaim of the band within a few bars (waypoint, not support)", f"new low through {sig.stop}"],
        "DISTRIBUTION_SHORT": [f"acceptance back above {sig.stop}", "absorption of supply (buyer steps in)"],
        "REDUCE_AVOID": ["reclaim + acceptance above the range turns this back on"],
        "WATCH": ["—"],
    }[category]
    return {"price": sig.stop, "conditions": conds}

def _execution(sig, a, category, mode_info):
    if category == "REDUCE_AVOID":
        em, aggr = "REDUCE/AVOID", "—"
    elif category == "STRUCTURAL_LONG":
        em, aggr = "BUILD (scale in during compression)", "low → add on acceptance"
    elif category == "TACTICAL_MOMENTUM":
        em, aggr = "ADD on accepted continuation", "medium"
    elif category == "SQUEEZE":
        em, aggr = "EARLY BUILD, add as it propagates", "medium-high, tactical"
    elif category == "MEAN_REVERSION":
        em, aggr = "SCALP the reclaim only", "low, tight leash"
    elif category == "DISTRIBUTION_SHORT":
        em, aggr = "SHORT failed continuation", "medium"
    else:
        em, aggr = "WAIT", "—"
    size = round(min(1.0, (sig.conviction / 100.0)) * float(a.get("_alloc_mult", 1.0)), 2)
    opp = sig.opportunity or {}
    targets = {"near": sig.target or opp.get("base"), "expansion": opp.get("bull"), "convex": opp.get("supercycle")}
    if (sig.options or {}).get("call_wall"):
        targets["expansion"] = sig.options["call_wall"]
    return {"mode": em, "aggression": aggr, "size_x": size, "holding": HOLDING[category],
            "style": mode_info.get("style", "—"), "targets": targets}

def build_decision_stack(sig, a) -> None:
    """Mutates the TickerSignal with the full doc-6 decision stack."""
    mm = a.get("market_mode") or {}
    category = _category(sig, a, mm.get("mode", "MIXED"))
    sig.category = category
    sig.market_mode = mm.get("mode", "MIXED")
    sig.flow = {k: (a.get("flow") or {}).get(k) for k in ("type", "absorption", "efficiency", "persistence", "resilience", "proxy")}
    sig.why_now = _why_now(sig, a)
    sig.whos_trapped = _whos_trapped(sig, a, mm.get("mode"))
    sig.invalidation = _invalidation(sig, a, category)
    sig.execution = _execution(sig, a, category, mm)
