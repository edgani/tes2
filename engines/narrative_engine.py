"""engines/narrative_engine.py — Autonomous Narrative + Scenario + Bottleneck Generator (Sprint 10)

THE engine that synthesizes ALL state into actionable narratives.
Generates:
  1. Macro Narratives (e.g., "Fiscal dominance + AI capex compression = 6mo squeeze in dollar")
  2. Scenarios (3 paths: bull/base/bear with prob + ticker exposure)
  3. Bottleneck Detection (where demand river meets capacity constraint)
  4. Behavioral Divergences (crowd vs flow mismatches)
  5. Cross-Asset Causal Chains (e.g., yields ↑ → DXY ↑ → EM weak → commodities under pressure)

The output is the TOP-LEVEL narrative card on the Dashboard.
It pulls from EVERY other engine and produces synthesized prose.
"""
from __future__ import annotations
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════
# Cross-asset causal chains (rule-based + market-state aware)
# ════════════════════════════════════════════════════════════════════════

CAUSAL_CHAINS = {
    "fiscal_dominance_chain": {
        "trigger": {"fiscal_dominance_score": ">= 50"},
        "chain": [
            "Treasury must finance $1T+/yr interest cost",
            "→ More duration issuance → term premium ↑",
            "→ Long bonds underperform (TLT short)",
            "→ Real yields elevated → gold under pressure short-term",
            "→ BUT debasement narrative → gold + BTC bid medium-term",
            "→ Foreign central banks rotate USD reserves → gold",
        ],
        "long_exposure": ["GLD", "SLV", "BTC-USD", "GDX"],
        "short_exposure": ["TLT", "IEF"],
        "duration_months": 12,
    },
    "ai_capex_rotation_chain": {
        "trigger": {"capital_rotation_label": "ROTATION VALIDATED"},
        "chain": [
            "Hyperscaler capex $680B → silicon FCF $525B",
            "→ Sellers of shortage rip (NVDA/AVGO/TSM)",
            "→ Power gen → on-site fuel cells + nuclear (BE/VST/CEG)",
            "→ Stranded power (BTC miners → AI hosting: CORZ/IREN)",
            "→ Optics + memory bottleneck (LITE/COHR/MU)",
            "→ Buyers (GOOGL/AMZN) eventually rerate when AI revenue scales",
        ],
        "long_exposure": ["NVDA", "AVGO", "TSM", "BE", "VST", "CEG", "LITE", "COHR",
                          "CORZ", "IREN", "APLD", "MU", "GOOGL", "AMZN"],
        "short_exposure": ["META"],  # defensive capex, no enterprise AI rev
        "duration_months": 24,
    },
    "agentic_cpu_rotation_chain": {
        "trigger": {"markov_regime": ["Q1_GOLDILOCKS", "Q2_REFLATION"]},
        "chain": [
            "Agentic Big Bang post-Claude Code release",
            "→ Tokens 12x/yr growth (35T → 400T+ within 2yr)",
            "→ CPU-intensive workloads (search, file ops, agent loops)",
            "→ AMD takes server share from Intel (6+ quarters straight)",
            "→ HBM memory becomes new bottleneck (context windows)",
            "→ MU/SK Hynix HBM3E capture rotation",
        ],
        "long_exposure": ["AMD", "MU", "ANET"],
        "short_exposure": [],
        "duration_months": 12,
    },
    "stagflation_real_asset_chain": {
        "trigger": {"markov_regime": "Q3_STAGFLATION"},
        "chain": [
            "Growth ↓ + Inflation ↑ → traditional 60/40 fails",
            "→ Tech multiples compress (long duration vulnerable)",
            "→ Commodities + gold + miners catch real-asset bid",
            "→ Energy + materials lead",
            "→ XLP/XLU defensive earnings hold up",
        ],
        "long_exposure": ["GLD", "SLV", "GDX", "GDXJ", "USO", "XLE", "XLP", "XLU", "DBA"],
        "short_exposure": ["QQQ", "XLK", "XLY", "IWM", "ARKK", "BTC-USD"],
        "duration_months": 9,
    },
    "deflation_crash_chain": {
        "trigger": {"markov_regime": ["Q4_DEFLATION", "Q5_CRASH"]},
        "chain": [
            "Growth ↓ + Inflation ↓ → recession risk",
            "→ Long bonds bid (TLT rally on rate cuts)",
            "→ Defensives (XLU/XLP/XLV) outperform",
            "→ Gold bid on Fed pivot",
            "→ Cyclicals + small caps + crypto MAULED",
        ],
        "long_exposure": ["TLT", "IEF", "GLD", "XLU", "XLP", "XLV", "XLY"],
        "short_exposure": ["QQQ", "XLK", "IWM", "XLE", "XLF", "BTC-USD", "ARKK"],
        "duration_months": 6,
    },
    "credit_stress_chain": {
        "trigger": {"bonds_xau_flags": "CREDIT_STRESS"},
        "chain": [
            "HYG underperforming LQD → high yield spreads widening",
            "→ Risk-off cascade — credit leads equity",
            "→ Defensive rotation accelerates",
            "→ Bonds bid + gold bid",
            "→ Watch banks (KRE) + cyclicals (IWM)",
        ],
        "long_exposure": ["TLT", "LQD", "GLD"],
        "short_exposure": ["HYG", "KRE", "IWM", "XLF"],
        "duration_months": 3,
    },
    "behavioral_squeeze_chain": {
        "trigger": {"karsan_squeeze_setups": "> 0"},
        "chain": [
            "Two-sided skew detected (call > put IV)",
            "+ Negative dealer gamma = trend amplification",
            "+ High short interest + bull momentum",
            "→ Squeeze setup — Karsan + SpotGamma + behavioral aligned",
        ],
        "long_exposure": [],  # dynamic — pulled from squeeze scanner
        "short_exposure": [],
        "duration_months": 1,
    },
}


# ════════════════════════════════════════════════════════════════════════
# BOTTLENECK SCANNER (Citrini-style autonomous)
# ════════════════════════════════════════════════════════════════════════

BOTTLENECK_PATTERNS = {
    "power_grid_5yr_waitlist": {
        "demand": "AI datacenter buildout 100x compute by 2027",
        "supply_constraint": "Grid interconnection waitlist 5+ years",
        "bottleneck_layer": "physical_infrastructure",
        "beneficiaries": ["BE", "VST", "CEG", "TLN", "GEV"],
        "duration_yr": 5,
        "confidence": "HIGH",
    },
    "hbm_memory_supply": {
        "demand": "AI training + agentic context windows = HBM3E demand explosion",
        "supply_constraint": "Only SK Hynix + Samsung + Micron produce HBM, capacity-constrained",
        "bottleneck_layer": "memory",
        "beneficiaries": ["MU", "000660.KS", "005930.KS"],
        "duration_yr": 2,
        "confidence": "HIGH",
    },
    "advanced_packaging_cowos": {
        "demand": "Nvidia Blackwell + H100 production",
        "supply_constraint": "TSMC CoWoS packaging = single point of failure",
        "bottleneck_layer": "advanced_packaging",
        "beneficiaries": ["TSM", "AMAT", "LRCX"],
        "duration_yr": 3,
        "confidence": "HIGH",
    },
    "optical_photonics_datacenter": {
        "demand": "Datacenter scale-out networking (>1.6Tbps)",
        "supply_constraint": "Photonic components — only ~3 major suppliers",
        "bottleneck_layer": "optical",
        "beneficiaries": ["LITE", "COHR", "MRVL"],
        "duration_yr": 3,
        "confidence": "MEDIUM",
    },
    "uranium_nuclear_renaissance": {
        "demand": "AI power offtake + reactor restarts (Constellation, etc.)",
        "supply_constraint": "Uranium supply gap, NRC permitting 10yr+",
        "bottleneck_layer": "fuel_supply",
        "beneficiaries": ["CCJ", "URA", "BWXT"],
        "duration_yr": 7,
        "confidence": "MEDIUM",
    },
    "fiscal_dominance_real_asset": {
        "demand": "Debasement hedge as US debt $40T, interest $1T/yr",
        "supply_constraint": "Gold supply growth ~1.5%/yr, BTC fixed",
        "bottleneck_layer": "store_of_value",
        "beneficiaries": ["GLD", "SLV", "BTC-USD", "GDX"],
        "duration_yr": 5,
        "confidence": "HIGH",
    },
    "defense_rearmament_post_ukraine": {
        "demand": "NATO 3% GDP target + Asia-Pacific build",
        "supply_constraint": "Defense industrial base ground out, 5yr+ to rebuild",
        "bottleneck_layer": "defense_industrial",
        "beneficiaries": ["LMT", "NOC", "RTX", "GD", "HII"],
        "duration_yr": 7,
        "confidence": "MEDIUM",
    },
}


def detect_active_bottlenecks(snap: Dict) -> List[Dict]:
    """Return list of bottlenecks that match current market state."""
    active = []
    
    # Check macro state to filter
    markov_regime = (snap.get("markov_v3", {}) or {}).get("current_regime", "")
    fiscal_score = (snap.get("ust_auction", {}) or {}).get("fiscal_dominance", {}).get("score", 0)
    capital_rotation = (snap.get("capital_rotation", {}) or {}).get("regime_label", "")
    
    for name, btn in BOTTLENECK_PATTERNS.items():
        applies = True
        # Filter by regime
        if "fiscal_dominance" in name and fiscal_score < 30:
            applies = False
        if "rotation" in name.lower() and "ROTATION" not in capital_rotation.upper():
            applies = False
        if applies:
            active.append({
                "name": name,
                "demand": btn["demand"],
                "supply_constraint": btn["supply_constraint"],
                "layer": btn["bottleneck_layer"],
                "beneficiaries": btn["beneficiaries"],
                "duration_yr": btn["duration_yr"],
                "confidence": btn["confidence"],
            })
    
    return active


# ════════════════════════════════════════════════════════════════════════
# MACRO NARRATIVE GENERATOR (the headline)
# ════════════════════════════════════════════════════════════════════════

def generate_macro_narrative(snap: Dict) -> Dict:
    """Generate THE single dominant macro narrative right now."""
    # Pull state from all engines
    markov = snap.get("markov_v3", {}) or {}
    bxau = snap.get("bonds_xau_regime", {}) or {}
    ust = snap.get("ust_auction", {}) or {}
    caprot = snap.get("capital_rotation", {}) or {}
    boom_bust = snap.get("boom_bust", {}) or {}
    yves_v2 = snap.get("yves_v2", {}) or {}
    
    regime = markov.get("current_regime", "UNKNOWN")
    conf = markov.get("confidence", 0)
    cp_alert = markov.get("change_point_alert", False)
    fiscal_score = ust.get("fiscal_dominance", {}).get("score", 0)
    rotation_label = caprot.get("regime_label", "")
    stage = boom_bust.get("stage", "UNKNOWN")
    
    # Compose narrative based on dominant signals
    headline = ""
    sub_narrative = ""
    
    # Priority 1: Change-point alert (regime shift forming)
    if cp_alert:
        headline = f"🚨 REGIME TRANSITION FORMING — {markov.get('change_point_probability', 0):.0%} CP probability"
        sub_narrative = (
            f"Markov V3 + Schadner vol surface signal regime change. Current: {regime}. "
            f"Tighten stops, reduce leverage, watch for Quad shift."
        )
    # Priority 2: Severe fiscal dominance
    elif fiscal_score >= 70:
        headline = f"💀 SEVERE FISCAL DOMINANCE — UST market stress acute (score {fiscal_score}/100)"
        sub_narrative = (
            "30Y >5% first time since pre-GFC. Primary dealer takedown elevated. "
            "China divesting (offset by Euro/UK/private). $1T annual interest > defense. "
            "Real asset bid (GLD/BTC) + bonds short (TLT). Behavioral edge: crowd labels 'bubble', "
            "smart money labels 'capital rotation' funded by $12T dry powder."
        )
    # Priority 3: Markov Q3 stagflation
    elif regime == "Q3_STAGFLATION" and conf >= 0.5:
        headline = f"🟡 STAGFLATION CONFIRMED — {conf:.0%} Markov confidence"
        sub_narrative = (
            "Growth ↓ + Inflation ↑ playbook active. Real assets bid. "
            "Trim tech/long-duration. Long XLE/XLP/GLD/SLV. Short QQQ/XLK/IWM."
        )
    # Priority 4: Q1 Goldilocks + AI rotation
    elif regime == "Q1_GOLDILOCKS" and "ROTATION" in rotation_label.upper():
        headline = f"🟢 GOLDILOCKS + AI CAPITAL ROTATION VALIDATED"
        sub_narrative = (
            "Tech leadership confirmed. Smart money rotation: hyperscaler capex $680B → "
            "silicon FCF $525B. Long NVDA/AVGO/TSM/BE/VST/CEG. Tier1Alpha: dealers long "
            "gamma → buy dips at trade low."
        )
    # Priority 5: Default Q1 (no rotation signal)
    elif regime == "Q1_GOLDILOCKS":
        headline = "🟢 GOLDILOCKS REGIME"
        sub_narrative = "Tech-led rally. Risk-on. But monitor for change-point."
    # Priority 6: Q4 deflation
    elif regime == "Q4_DEFLATION":
        headline = "🔴 DEFLATION — Most dangerous Quad"
        sub_narrative = "Long bonds/gold/defensives. Short tech/cyclicals. Cash high allocation."
    # Priority 7: Soros twilight/reversal
    elif stage in ("TWILIGHT", "REVERSAL"):
        headline = f"⚠️ SOROS {stage} — Reflexivity reaching its limit"
        sub_narrative = "Smart money exiting. Trim core. Consider reverse positioning."
    else:
        headline = f"⚪ {regime.replace('_', ' ')}"
        sub_narrative = "No dominant theme. Monitor for catalysts."
    
    return {
        "headline": headline,
        "narrative": sub_narrative,
        "regime": regime,
        "confidence": conf,
        "change_point_alert": cp_alert,
        "fiscal_score": fiscal_score,
        "rotation_label": rotation_label,
        "soros_stage": stage,
    }


# ════════════════════════════════════════════════════════════════════════
# 3-SCENARIO GENERATOR (Bull / Base / Bear)
# ════════════════════════════════════════════════════════════════════════

def generate_scenarios(snap: Dict) -> Dict:
    """Generate Bull/Base/Bear scenarios with probabilities + ticker exposure."""
    markov = snap.get("markov_v3", {}) or {}
    forecast_3m = markov.get("forecast_3m", {})
    
    # Default probabilities from Markov forecast
    bull_regimes = ["Q1_GOLDILOCKS", "Q2_REFLATION"]
    bear_regimes = ["Q4_DEFLATION", "Q5_CRASH"]
    
    p_bull = sum(forecast_3m.get(r, 0) for r in bull_regimes) if forecast_3m else 0.4
    p_bear = sum(forecast_3m.get(r, 0) for r in bear_regimes) if forecast_3m else 0.2
    p_base = max(0.0, 1.0 - p_bull - p_bear)
    
    return {
        "bull": {
            "probability": round(p_bull, 3),
            "narrative": "Growth re-acceleration + AI capex sustained. Risk-on regime.",
            "long_picks": ["QQQ", "NVDA", "AVGO", "AMD", "BE", "CRWV", "BTC-USD"],
            "short_picks": ["TLT", "VIXY"],
            "options_play": "Long QQQ calls 30-60d, sell put spreads on dips",
            "regime_path": "Q1 → Q1 → Q2",
        },
        "base": {
            "probability": round(p_base, 3),
            "narrative": "Range-bound chop. Stagflation light. Real asset bid.",
            "long_picks": ["GLD", "SLV", "VST", "CEG", "XLE", "XLP"],
            "short_picks": ["IWM", "ARKK"],
            "options_play": "Sell premium (iron condor SPY/QQQ). Long calls on GLD/SLV.",
            "regime_path": "Q3 → Q3 → Q1 (recovery)",
        },
        "bear": {
            "probability": round(p_bear, 3),
            "narrative": "Recession risk. Credit stress. Liquidity drain.",
            "long_picks": ["TLT", "GLD", "XLU", "XLP", "XLV"],
            "short_picks": ["QQQ", "XLK", "IWM", "ARKK", "BTC-USD", "KRE"],
            "options_play": "Long QQQ puts 3-6mo OTM. VIX call spreads. Long TLT calls.",
            "regime_path": "Q3 → Q4 → Q4/Q5",
        },
        "dominant_scenario": ("bull" if p_bull > max(p_base, p_bear) else
                              "bear" if p_bear > p_base else "base"),
    }


# ════════════════════════════════════════════════════════════════════════
# BEHAVIORAL DIVERGENCES (Yves-style across the universe)
# ════════════════════════════════════════════════════════════════════════

def detect_behavioral_divergences(snap: Dict) -> List[Dict]:
    """Find tickers where crowd narrative diverges from flow data."""
    divergences = []
    
    # Use Yves framework matches
    thought_process = snap.get("thought_process", {}) or {}
    for ticker, tp in thought_process.items():
        yves = tp.get("framework_breakdown", {}).get("yves", {})
        if yves.get("narrative_divergence"):
            divergences.append({
                "ticker": ticker,
                "thesis": yves.get("thesis"),
                "rationale": yves.get("rationale", []),
                "score": yves.get("score", 0),
            })
    
    # Sort by score
    divergences.sort(key=lambda x: x.get("score", 0), reverse=True)
    return divergences[:15]


# ════════════════════════════════════════════════════════════════════════
# CAUSAL CHAIN ACTIVATION
# ════════════════════════════════════════════════════════════════════════

def detect_active_causal_chains(snap: Dict) -> List[Dict]:
    """Determine which causal chains are currently active given market state."""
    active = []
    fiscal_score = (snap.get("ust_auction", {}) or {}).get("fiscal_dominance", {}).get("score", 0)
    markov_regime = (snap.get("markov_v3", {}) or {}).get("current_regime", "")
    rotation = (snap.get("capital_rotation", {}) or {}).get("regime_label", "")
    bxau_flags = (snap.get("bonds_xau_regime", {}) or {}).get("flags", [])
    karsan_squeezes = (snap.get("karsan_scanner", {}) or {}).get("squeeze_setups", [])
    
    for chain_name, chain_data in CAUSAL_CHAINS.items():
        trigger = chain_data.get("trigger", {})
        activated = False
        
        if "fiscal_dominance_score" in trigger:
            cmp_str = trigger["fiscal_dominance_score"]
            if ">=" in cmp_str:
                val = float(cmp_str.split(">=")[1].strip())
                if fiscal_score >= val:
                    activated = True
        if "markov_regime" in trigger:
            target = trigger["markov_regime"]
            if isinstance(target, str) and markov_regime == target:
                activated = True
            elif isinstance(target, list) and markov_regime in target:
                activated = True
        if "capital_rotation_label" in trigger:
            if trigger["capital_rotation_label"] in rotation.upper():
                activated = True
        if "bonds_xau_flags" in trigger:
            if trigger["bonds_xau_flags"] in bxau_flags:
                activated = True
        if "karsan_squeeze_setups" in trigger:
            if ">" in trigger["karsan_squeeze_setups"]:
                val = int(trigger["karsan_squeeze_setups"].split(">")[1].strip())
                if len(karsan_squeezes) > val:
                    activated = True
        
        if activated:
            active.append({
                "name": chain_name,
                "chain": chain_data["chain"],
                "long_exposure": chain_data["long_exposure"],
                "short_exposure": chain_data["short_exposure"],
                "duration_months": chain_data["duration_months"],
            })
    
    return active


# ════════════════════════════════════════════════════════════════════════
# MASTER NARRATIVE BUILDER
# ════════════════════════════════════════════════════════════════════════

def build_narrative(snap: Dict) -> Dict:
    """
    Master entry: build complete narrative output for Dashboard.
    """
    macro = generate_macro_narrative(snap)
    scenarios = generate_scenarios(snap)
    causal = detect_active_causal_chains(snap)
    bottlenecks = detect_active_bottlenecks(snap)
    divergences = detect_behavioral_divergences(snap)
    quad_seq = generate_quad_sequencing(snap)  # NEW: Hedgeye-style
    
    # Build action summary
    dominant = scenarios["dominant_scenario"]
    dominant_data = scenarios[dominant]
    action_summary = {
        "primary_action": f"Position for {dominant.upper()} scenario ({dominant_data['probability']:.0%})",
        "top_longs": dominant_data["long_picks"][:5],
        "top_shorts": dominant_data["short_picks"][:5],
        "options_play": dominant_data["options_play"],
        "active_themes": [c["name"].replace("_", " ").title() for c in causal[:3]],
        "active_bottlenecks": [b["name"].replace("_", " ").title() for b in bottlenecks[:3]],
    }
    
    return {
        "macro_narrative": macro,
        "scenarios": scenarios,
        "quad_sequencing": quad_seq,  # NEW
        "active_causal_chains": causal,
        "active_bottlenecks": bottlenecks,
        "behavioral_divergences": divergences,
        "action_summary": action_summary,
        "n_active_chains": len(causal),
        "n_active_bottlenecks": len(bottlenecks),
        "n_behavioral_divergences": len(divergences),
    }


# ════════════════════════════════════════════════════════════════════════
# HEDGEYE-STYLE QUAD SEQUENCING + STAG-ON-A-LAG DETECTOR
# Replicates Hedgeye's monthly Quad cadence + path-dependency narrative
# ════════════════════════════════════════════════════════════════════════

def generate_quad_sequencing(snap: Dict) -> Dict:
    """
    Hedgeye-style Quad sequencing:
    - Current Quad (from Markov + GIP consensus)
    - Last transition (from Markov regime probability history if available)
    - Next likely Quad (from forecast_3m argmax)
    - "Stag on a Lag" detection: Q2 with growth deceleration brewing → likely Q3 transition
    - Path dependency: explicit trigger conditions
    """
    markov = snap.get("markov_v3", {}) or {}
    gip_v10 = snap.get("gip_v10", {}) or {}
    bxau = snap.get("bonds_xau_regime", {}) or {}
    
    current_regime = markov.get("current_regime", "UNKNOWN")
    current_conf = markov.get("confidence", 0)
    fc_3m = markov.get("forecast_3m", {}) or {}
    
    # Map Markov regime to clean Hedgeye Quad label
    quad_map = {
        "Q1_GOLDILOCKS": "Q1 (Goldilocks)",
        "Q2_REFLATION": "Q2 (Reflation)",
        "Q3_STAGFLATION": "Q3 (Stagflation)",
        "Q4_DEFLATION": "Q4 (Deflation)",
        "Q5_CRASH": "Q5 (Crash - non-Hedgeye)",
    }
    current_quad_label = quad_map.get(current_regime, current_regime)
    
    # Next quad: argmax of 3M forecast (excluding current to find transition)
    next_quad = None
    next_p = 0
    for q, p in fc_3m.items():
        if q != current_regime and p > next_p:
            next_quad = q
            next_p = p
    next_quad_label = quad_map.get(next_quad, next_quad) if next_quad else None
    
    # ── STAG-ON-A-LAG DETECTOR (Hedgeye May 2026 framework) ──
    # Q2 + P(Q3) > 30% in 3M forecast + RV trending up + DXY/USD strong = stag forming under reflation
    stag_on_lag = False
    stag_signals = []
    
    if current_regime == "Q2_REFLATION":
        p_q3 = fc_3m.get("Q3_STAGFLATION", 0)
        if p_q3 > 0.30:
            stag_signals.append(f"P(Q3) = {p_q3:.0%} (>30% threshold)")
            stag_on_lag = True
        
        # Check oil/inflation cascade
        cascade = snap.get("cascade_analysis", {}) or {}
        oil_shocks = [k for k in cascade.get("active_shocks", {}).keys() if "CL" in k or "OIL" in k.upper()]
        if oil_shocks:
            stag_signals.append(f"Oil/energy shock active: {oil_shocks[0]}")
            stag_on_lag = True
        
        # Check Hormuz-style supply shock proxy via XLE momentum + USD strength
        bxau_metrics = bxau.get("metrics", {})
        if bxau_metrics.get("real_yield", 0) and bxau_metrics["real_yield"] > 2.5:
            stag_signals.append(f"Real yield elevated {bxau_metrics['real_yield']:.2f}% — restrictive tightness")
    
    # ── Build narrative ──
    narrative_lines = []
    if stag_on_lag:
        narrative_lines.append(
            f"🟡 **\"Flation Now, Stag-On-A-Lag\"** — Currently {current_quad_label} but Q3 dynamics "
            f"building beneath. Hedgeye Q2 → Q3 pivot risk."
        )
        for sig in stag_signals:
            narrative_lines.append(f"  • {sig}")
        narrative_lines.append(
            "  → Action: Tactical equity LONG window still open. "
            "Tighten stops. Watch for Mag 7 comp headwind. Re-add GLD/TLT defensive pair as Q3 confirms."
        )
    elif current_regime == "Q1_GOLDILOCKS":
        narrative_lines.append(f"🟢 {current_quad_label} ({current_conf:.0%} conf) — Risk-on regime")
    elif current_regime == "Q2_REFLATION":
        narrative_lines.append(f"🟠 {current_quad_label} ({current_conf:.0%} conf) — Reflation, cyclicals lead")
    elif current_regime == "Q3_STAGFLATION":
        narrative_lines.append(f"🟡 {current_quad_label} ({current_conf:.0%} conf) — Real assets bid")
    elif current_regime == "Q4_DEFLATION":
        narrative_lines.append(f"🔴 {current_quad_label} ({current_conf:.0%} conf) — Most dangerous Quad")
    
    if next_quad and next_p > 0.30:
        narrative_lines.append(
            f"📍 **Next likely**: {next_quad_label} ({next_p:.0%} prob in 3M)"
        )
    
    # Path dependencies (explicit Hedgeye-style triggers)
    path_deps = []
    if current_regime == "Q2_REFLATION":
        path_deps.append("Q2 holds if: payrolls strong + ISM>50 + crude stable")
        path_deps.append("Q2 → Q3 trigger: crude breaks $90 OR ISM<48 with sticky inflation")
        path_deps.append("Q2 → Q1 trigger: inflation rolls AND growth stays strong")
    elif current_regime == "Q1_GOLDILOCKS":
        path_deps.append("Q1 → Q3 trigger: inflation reaccelerates (oil shock, services CPI)")
        path_deps.append("Q1 → Q4 trigger: growth rolls over WITH inflation falling")
    elif current_regime == "Q3_STAGFLATION":
        path_deps.append("Q3 → Q4 trigger: growth deteriorates faster + inflation rolls")
        path_deps.append("Q3 → Q2 trigger: growth reaccelerates with sticky inflation")
    
    return {
        "current_quad": current_quad_label,
        "current_quad_raw": current_regime,
        "confidence": round(current_conf, 3),
        "next_quad": next_quad_label,
        "next_quad_prob_3m": round(next_p, 3),
        "stag_on_a_lag": stag_on_lag,
        "stag_signals": stag_signals,
        "narrative_lines": narrative_lines,
        "path_dependencies": path_deps,
        "hedgeye_aligned": True,
    }


# ═══════════════════════════════════════════════════════════════════════════
# NEXT-QUAD PLAYBOOK — position AHEAD of the transition (Keith's storm-prep)
# Synthesizes Hedgeye quad→asset rotation + Ricky-style bottleneck thesis pattern
# so we're positioned BEFORE the regime shift, not reacting after.
# ═══════════════════════════════════════════════════════════════════════════

# Hedgeye-backtested quad → asset/sector winners & losers
_QUAD_PLAYBOOK = {
    "Q1_GOLDILOCKS": {  # growth↑ inflation↓
        "label": "Q1 Goldilocks (growth↑ infl↓)",
        "into": ["Tech/Nasdaq (XLK, QQQ)", "Consumer Disc (XLY)", "growth & high-beta", "BTC/crypto", "long-duration growth"],
        "out": ["Energy (XLE)", "defensives (XLU/XLP)", "USD cash", "commodities"],
        "factor": "Momentum + Growth + High Beta",
    },
    "Q2_REFLATION": {  # growth↑ inflation↑
        "label": "Q2 Reflation (growth↑ infl↑)",
        "into": ["Energy (XLE)", "Materials (XLB)", "Industrials (XLI)", "commodities (oil/copper)", "EM equities (EEM)", "small-caps (IWM)", "Tech that's a bottleneck"],
        "out": ["long bonds (TLT)", "utilities (XLU)", "staples (XLP)", "USD"],
        "factor": "High Beta + Cyclical + Inflation-leverage",
    },
    "Q3_STAGFLATION": {  # growth↓ inflation↑
        "label": "Q3 Stagflation (growth↓ infl↑)",
        "into": ["Gold (GLD)", "Energy (XLE)", "Utilities (XLU)", "commodities", "TIPS", "Consumer Staples (XLP)", "low-vol/quality"],
        "out": ["Tech/growth (XLK)", "Consumer Disc (XLY)", "small-caps", "high-beta", "long bonds early"],
        "factor": "Low Beta + Quality + Inflation-hedge",
    },
    "Q4_DEFLATION": {  # growth↓ inflation↓
        "label": "Q4 Deflation (growth↓ infl↓)",
        "into": ["Long Treasuries (TLT)", "Utilities (XLU)", "Staples (XLP)", "USD (UUP)", "Healthcare (XLV)", "low-beta/min-vol"],
        "out": ["Energy (XLE)", "Materials", "small-caps", "high-beta", "cyclicals", "commodities"],
        "factor": "Defensive + Long-Duration Bonds + USD",
    },
}


def generate_next_quad_playbook(snap: Dict) -> Dict:
    """Position AHEAD of the next quad. Returns rotate-into / rotate-out-of lists
    plus the trigger to watch — so we set up before the transition (Keith storm-prep)."""
    seq = generate_quad_sequencing(snap)
    markov = snap.get("markov_v3", {}) or {}
    current = markov.get("current_regime", "UNKNOWN")
    fc_3m = markov.get("forecast_3m", {}) or {}

    # Next quad = highest-prob non-current in 3M forecast
    nxt, nxt_p = None, 0.0
    for q, p in fc_3m.items():
        if q != current and p > nxt_p:
            nxt, nxt_p = q, p

    cur_pb = _QUAD_PLAYBOOK.get(current, {})
    nxt_pb = _QUAD_PLAYBOOK.get(nxt, {}) if nxt else {}

    # What to ADD ahead: next-quad winners that are ALSO current-quad losers = early rotation edge
    rotate_in = nxt_pb.get("into", [])
    rotate_out = nxt_pb.get("out", [])
    # Names to start accumulating early (next-quad winners not yet bid because still current quad)
    early_edge = [x for x in nxt_pb.get("into", []) if x in cur_pb.get("out", [])]

    storm_or_opp = None
    if nxt in ("Q3_STAGFLATION", "Q4_DEFLATION"):
        storm_or_opp = "🌪️ STORM — defensive rotation; de-risk high-beta BEFORE the shift"
    elif nxt in ("Q1_GOLDILOCKS", "Q2_REFLATION"):
        storm_or_opp = "🌤️ OPPORTUNITY — risk-on rotation; accumulate cyclicals/growth early"

    return {
        "current_quad": cur_pb.get("label", current),
        "next_quad": nxt_pb.get("label", nxt) if nxt else None,
        "next_prob": nxt_p,
        "transition_eta": seq.get("transition_eta") or seq.get("eta"),
        "storm_or_opportunity": storm_or_opp,
        "rotate_into": rotate_in,
        "rotate_out_of": rotate_out,
        "early_rotation_edge": early_edge,  # next-quad winners that are current-quad laggards
        "next_quad_factor": nxt_pb.get("factor"),
        "trigger": seq.get("trigger") or seq.get("narrative_lines", []),
        "stag_on_lag": seq.get("stag_on_lag", False),
    }
