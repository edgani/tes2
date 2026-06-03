"""engines/portfolio_sizing.py — Portfolio Sizing v2 (Sprint 2 + v33 fix)

Replaces conviction_sizing.py with portfolio-aware sizing:
  • % of portfolio (not absolute $)
  • Kelly cap (¼ Kelly for safety)
  • Sector concentration caps
  • Correlated-cluster caps (don't double up on AI plays)
  • Quad-conditional multiplier
  • Soros boom-bust stage damping

v33 FIX:
  • Added "short_A+" to GRADE_MULT (1.40x) — symmetric with long "A+"
  • Required because risk_range_engine v33 now emits "short_A+" for high-quality
    short setups at the entry edge. Without this entry, short_A+ would silently
    default to 1.00x and undersize.

User input: just portfolio_value (any number). Output: target_pct, target_dollar, multipliers, rationale.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional


# ────────────────────────────────────────────────────────────────────────
# CONFIG (tunable but reasonable defaults)
# ────────────────────────────────────────────────────────────────────────

# Hard caps
MAX_SINGLE_POSITION_PCT = 0.10        # 10% per name max
MAX_SECTOR_PCT = 0.30                 # 30% per sector
MAX_CORRELATED_CLUSTER_PCT = 0.40     # 40% per correlated theme (e.g., AI infra basket)

# Kelly conservative multiplier
KELLY_FRACTION = 0.25                 # Quarter Kelly

# Quad multipliers
QUAD_MULT = {
    "Q1": 1.20,    # Goldilocks — size up risk assets
    "Q2": 1.00,    # Reflation — normal
    "Q3": 0.65,    # Stagflation — size down growth
    "Q4": 0.35,    # Deflation — capital preservation
}

# Soros boom-bust stage damping
STAGE_MULT = {
    "INCEPTION": 1.00,
    "ACCELERATION": 1.25,
    "EUPHORIA": 1.00,      # Peak — neutral sizing (don't chase, don't exit)
    "TEST": 0.85,
    "SURVIVAL": 1.10,
    "MOMENT_OF_TRUTH": 0.55,
    "TWILIGHT": 0.40,
    "TIP_POINT": 0.20,
    "CRISIS": 0.10,
}

# Grade multipliers
# v33: Added short_A+ for symmetric long/short high-conviction grading.
GRADE_MULT = {
    "A+": 1.40,
    "A":  1.20,
    "B":  1.00,
    "C":  0.65,
    "D":  0.30,
    "F":  0.00,
    # Hedgeye short grades — symmetric to long side after v33 fix
    "short_A+": 1.40,    # NEW in v33 — matches long A+ multiplier
    "short_A":  1.20,
    "short_B":  1.00,
    "short_C":  0.65,
}

# Correlated theme groupings — exposure netted across these
CORRELATED_CLUSTERS = {
    "ai_compute_infra": ["NVDA", "AMD", "AVGO", "SMCI", "ALAB", "MRVL", "ANET", "MAGS"],
    "ai_power": ["VST", "CEG", "ETN", "VRT", "GEV", "EMR"],
    "ai_optics": ["COHR", "LITE", "GLW", "POET", "CIEN", "VIAV"],
    "ai_memory_substrate": ["MU", "MTRN", "TROX", "AMKR", "ASX", "TSEM"],
    "precious_metals": ["GLD", "SLV", "PPLT", "GDX", "GDXJ", "SIL", "SILJ", "AEM", "WPM", "FNV"],
    "uranium": ["URA", "CCJ", "NXE", "DNN", "UUUU", "LEU", "URG"],
    "tankers": ["FRO", "STNG", "TNK", "DHT", "INSW", "EURN", "KEX"],
    "defense": ["LMT", "RTX", "NOC", "GD", "KTOS", "HII", "LDOS", "BAH", "PLTR", "AXON", "ITA"],
    "us_growth": ["QQQ", "XLK", "MAGS", "ARKK"],
    "us_defensives": ["XLU", "XLP", "XLV", "TLT", "GLD"],
    "em_commodity": ["EIDO", "EWZ", "EWW", "NORW", "EWA"],
    "crypto": ["BTC-USD", "ETH-USD", "IBIT", "FBTC", "MSTR", "MARA", "RIOT", "COIN"],
    "tech_mag7": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"],
    "regional_bank_cre": ["KRE", "KBE", "VNO", "BXP", "SLG"],
}


def _find_cluster(ticker: str) -> Optional[str]:
    """Return cluster name if ticker belongs to any correlated cluster."""
    for cluster, members in CORRELATED_CLUSTERS.items():
        if ticker in members:
            return cluster
    return None


# ────────────────────────────────────────────────────────────────────────
# KELLY CRITERION
# ────────────────────────────────────────────────────────────────────────

def calc_kelly_pct(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """
    Kelly fraction. Returns 0-1.
    win_rate: 0-1
    avg_win, avg_loss: positive numbers (avg_loss = magnitude)
    """
    if avg_win <= 0 or avg_loss <= 0 or win_rate <= 0 or win_rate >= 1:
        return 0.02  # Sensible default 2%
    b = avg_win / avg_loss  # payoff ratio
    p = win_rate
    q = 1 - p
    kelly = (b * p - q) / b
    return max(0.0, min(0.50, kelly))  # Cap at 50%


# ────────────────────────────────────────────────────────────────────────
# MAIN SIZING FUNCTION
# ────────────────────────────────────────────────────────────────────────

def calculate_position_size(
    ticker: str,
    signal: Dict,
    portfolio_value: float = 100_000,
    quad: str = "Q3",
    stage: str = "INCEPTION",
    current_positions: Optional[Dict[str, float]] = None,  # ticker → current_pct
    gamma: Optional[Dict] = None,
    greek: Optional[Dict] = None,
    reflexivity_score: float = 0.0,
) -> Dict:
    """
    Calculate optimal position size as % of portfolio.

    Args:
        ticker: target ticker
        signal: dict with {grade, direction, rr, near_entry, hist_win_rate, avg_win_pct, avg_loss_pct}
        portfolio_value: $ value (any number — user input)
        quad: current GIP quad
        stage: Soros boom-bust stage
        current_positions: existing portfolio {ticker: pct_of_portfolio}
        gamma, greek: optional options structure data
        reflexivity_score: -1.0 to +1.0 (extreme = reduce size)

    Returns:
        {target_pct, target_dollar, kelly_pct, after_quad, after_stage, after_correlation,
         mode, rationale, max_loss_dollar, sector, cluster, capped_by}
    """
    current_positions = current_positions or {}

    # 1. KELLY base
    win_rate = signal.get("hist_win_rate", 0.55)
    avg_win = abs(signal.get("avg_win_pct", 0.08))
    avg_loss = abs(signal.get("avg_loss_pct", 0.04))
    kelly_full = calc_kelly_pct(win_rate, avg_win, avg_loss)
    kelly_capped = kelly_full * KELLY_FRACTION

    # 2. Grade multiplier
    grade = signal.get("grade", "C")
    grade_mult = GRADE_MULT.get(grade, 1.0)

    # 3. Quad multiplier (regime-aware)
    direction = signal.get("direction", "LONG")
    q_mult = QUAD_MULT.get(quad, 1.0)
    # For shorts in defensive quads, INVERT the multiplier benefit
    if direction == "SHORT" and quad in ("Q3", "Q4"):
        q_mult = 1.0 + (1.0 - q_mult)  # Q3 short = upsize

    # 4. Soros stage damping
    s_mult = STAGE_MULT.get(stage, 1.0)

    # 5. Risk:reward bonus
    rr = signal.get("rr", 2.0) or 2.0
    rr_mult = 1.2 if rr >= 3.0 else (1.0 if rr >= 2.0 else (0.5 if rr < 1.5 else 0.8))

    # 6. Near-entry bonus
    near_entry = signal.get("near_entry", False)
    entry_mult = 1.15 if near_entry else 1.0

    # 7. Gamma/Greek confirmation
    g_mult = 1.0
    if gamma and gamma.get("ok"):
        reg = gamma.get("regime", "")
        if direction == "LONG" and reg in ("DEEP_POSITIVE", "POSITIVE"):
            g_mult = 1.20
        elif direction == "SHORT" and reg in ("DEEP_NEGATIVE", "NEGATIVE"):
            g_mult = 1.20
        elif reg in ("DEEP_POSITIVE", "POSITIVE", "DEEP_NEGATIVE", "NEGATIVE"):
            g_mult = 1.10

    # 8. Reflexivity damping (extreme positioning = reduce)
    ref_mult = 1.0 - min(abs(reflexivity_score) * 0.30, 0.30)

    # 9. Compute raw target
    raw_pct = kelly_capped * grade_mult * q_mult * s_mult * rr_mult * entry_mult * g_mult * ref_mult

    # 10. Apply caps
    capped_by = None
    target_pct = raw_pct

    # 10a. Single position cap
    if target_pct > MAX_SINGLE_POSITION_PCT:
        target_pct = MAX_SINGLE_POSITION_PCT
        capped_by = "single_position_max"

    # 10b. Sector cap
    sector = signal.get("sector", "generic")
    if sector != "generic":
        sector_exposure = sum(
            pct for t, pct in current_positions.items()
            # NOTE: sector detection would need TICKER_SECTOR lookup — simplified here
            if signal.get("sector_map", {}).get(t) == sector
        )
        room_in_sector = MAX_SECTOR_PCT - sector_exposure
        if target_pct > room_in_sector:
            target_pct = max(0, room_in_sector)
            capped_by = f"sector_max_{sector}"

    # 10c. Correlated cluster cap
    cluster = _find_cluster(ticker)
    if cluster:
        cluster_members = CORRELATED_CLUSTERS[cluster]
        cluster_exposure = sum(
            pct for t, pct in current_positions.items() if t in cluster_members
        )
        room_in_cluster = MAX_CORRELATED_CLUSTER_PCT - cluster_exposure
        if target_pct > room_in_cluster:
            target_pct = max(0, room_in_cluster)
            capped_by = f"cluster_max_{cluster}"

    # 11. Mode classification
    if target_pct >= 0.08:
        mode = "🐷 PIG MODE"
    elif target_pct >= 0.05:
        mode = "🔥 SIZE UP"
    elif target_pct >= 0.02:
        mode = "✅ NORMAL"
    elif target_pct >= 0.01:
        mode = "⚠️ SMALL"
    else:
        mode = "❌ SKIP"

    target_dollar = portfolio_value * target_pct
    max_loss_dollar = portfolio_value * target_pct * avg_loss

    rationale = (
        f"Kelly({kelly_capped:.1%}) × Grade({grade_mult:.2f}) × Quad{quad}({q_mult:.2f}) "
        f"× Stage({s_mult:.2f}) × RR({rr_mult:.2f}) × Entry({entry_mult:.2f}) "
        f"× Gamma({g_mult:.2f}) × Reflex({ref_mult:.2f}) = {target_pct:.2%}"
        + (f" [CAPPED: {capped_by}]" if capped_by else "")
    )

    return {
        "ticker": ticker,
        "target_pct": round(target_pct, 4),
        "target_dollar": round(target_dollar, 0),
        "kelly_pct": round(kelly_capped, 4),
        "after_quad": round(kelly_capped * q_mult, 4),
        "after_stage": round(kelly_capped * q_mult * s_mult, 4),
        "after_correlation": round(target_pct, 4),
        "mode": mode,
        "rationale": rationale,
        "max_loss_dollar": round(max_loss_dollar, 0),
        "max_loss_pct_portfolio": round(target_pct * avg_loss, 4),
        "sector": sector,
        "cluster": cluster,
        "capped_by": capped_by,
        "multipliers": {
            "grade": round(grade_mult, 2),
            "quad": round(q_mult, 2),
            "stage": round(s_mult, 2),
            "rr": round(rr_mult, 2),
            "entry": round(entry_mult, 2),
            "gamma": round(g_mult, 2),
            "reflexivity": round(ref_mult, 2),
        },
    }


# ────────────────────────────────────────────────────────────────────────
# BATCH RUNNER (orchestrator-friendly)
# ────────────────────────────────────────────────────────────────────────

def run_portfolio_sizing(
    alpha_items: List[Dict],
    portfolio_value: float = 100_000,
    quad: str = "Q3",
    stage: str = "INCEPTION",
    gamma_data: Optional[Dict] = None,
    greeks_data: Optional[Dict] = None,
    reflexivity: Optional[Dict] = None,
    current_positions: Optional[Dict[str, float]] = None,
) -> Dict:
    """
    Batch sizing for all alpha ideas. Sorts by allocation, enforces global caps.
    """
    gamma_data = gamma_data or {}
    greeks_data = greeks_data or {}
    ref_scores = (reflexivity or {}).get("ticker_scores", {})
    current_positions = current_positions or {}

    # First pass: compute raw sizes
    sized = []
    for item in alpha_items:
        ticker = item.get("ticker", "")
        if not ticker:
            continue

        gamma = gamma_data.get(ticker, {}) if isinstance(gamma_data, dict) else {}
        greek = greeks_data.get(ticker, {}) if isinstance(greeks_data, dict) else {}
        ref_score = ref_scores.get(ticker, {}).get("reflexivity_score", 0.0) if isinstance(ref_scores, dict) else 0.0

        result = calculate_position_size(
            ticker=ticker, signal=item, portfolio_value=portfolio_value,
            quad=quad, stage=stage, current_positions=current_positions,
            gamma=gamma, greek=greek, reflexivity_score=ref_score,
        )
        sized.append(result)

    # Second pass: enforce total portfolio leverage cap (max 100% deployed)
    total_pct = sum(s["target_pct"] for s in sized)
    if total_pct > 1.0:
        scale = 1.0 / total_pct
        for s in sized:
            s["target_pct"] = round(s["target_pct"] * scale, 4)
            s["target_dollar"] = round(s["target_pct"] * portfolio_value, 0)
            s["rationale"] += f" [SCALED: total>{100:.0f}%]"

    # Sort by allocation size
    sized.sort(key=lambda x: x["target_pct"], reverse=True)

    # Summary
    total_pct_final = sum(s["target_pct"] for s in sized)
    return {
        "portfolio_value": portfolio_value,
        "quad": quad,
        "stage": stage,
        "positions": sized,
        "total_deployed_pct": round(total_pct_final, 4),
        "cash_pct": round(1.0 - total_pct_final, 4),
        "cash_dollar": round(portfolio_value * (1.0 - total_pct_final), 0),
        "n_positions": len([s for s in sized if s["target_pct"] >= 0.005]),
        "mode_counts": {
            "pig": sum(1 for s in sized if s["mode"] == "🐷 PIG MODE"),
            "size_up": sum(1 for s in sized if s["mode"] == "🔥 SIZE UP"),
            "normal": sum(1 for s in sized if s["mode"] == "✅ NORMAL"),
            "small": sum(1 for s in sized if s["mode"] == "⚠️ SMALL"),
            "skip": sum(1 for s in sized if s["mode"] == "❌ SKIP"),
        },
    }
