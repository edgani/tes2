"""regime_policy.py — ChatGPT flaws #1 & #2: HARD regime override + dynamic weighting.

Market is non-linear: one variable can override everything. Static weights are dangerous because
importance changes by regime. This module:
  1. classifies the dominant regime from the shock engine + quad,
  2. returns the regime-appropriate weight profile (replaces static _W),
  3. applies a HARD override: in a systemic-credit regime, long signals are disabled.
"""
from __future__ import annotations

# weight profiles per regime (priors). keys map to engine signals used in conviction/surge.
_PROFILES = {
    "SYSTEMIC_RISK":   {"credit": 0.34, "liquidity": 0.30, "volatility": 0.18, "positioning": 0.10, "momentum": 0.04, "gamma": 0.04},
    "LIQUIDITY_MELTUP":{"liquidity": 0.30, "gamma": 0.24, "momentum": 0.22, "reflexivity": 0.14, "credit": 0.06, "breadth": 0.04},
    "COMMODITY_SHOCK": {"inventory": 0.30, "curve": 0.22, "bottleneck": 0.22, "momentum": 0.14, "credit": 0.06, "liquidity": 0.06},
    "CYCLICAL_SLOWDOWN":{"breadth": 0.28, "credit": 0.24, "leadership": 0.20, "momentum": 0.16, "liquidity": 0.12},
    "NEUTRAL":         {"liquidity": 0.20, "positioning": 0.16, "credit": 0.16, "momentum": 0.16, "breadth": 0.16, "gamma": 0.16},
}


def classify_regime(shock: dict, quad: dict | None = None) -> dict:
    """Pick the dominant regime from shock components + quad. Returns {regime, why, hard_override}."""
    comp = (shock or {}).get("components", {})
    prov = (shock or {}).get("provenance", {})
    ctype = (shock or {}).get("crash_type", "LOW")
    credit = comp.get("credit_stress", 0.5); liq = comp.get("liquidity_contract", 0.5)
    credit_real = prov.get("credit_stress") == "REAL"
    q = (quad or {}).get("structural_quad")

    # HARD OVERRIDE: real systemic credit stress disables longs (flaw #1)
    systemic = ctype == "SYSTEMIC" and credit_real and credit > 0.85
    if systemic or (credit_real and credit > 0.85):
        return {"regime": "SYSTEMIC_RISK", "hard_override": "LONGS_DISABLED",
                "why": f"systemic credit stress {credit:.2f} (REAL) — risk assets penalized, longs gated"}
    if liq > 0.62 and credit < 0.5 and q in ("Q1", "Q2"):
        return {"regime": "LIQUIDITY_MELTUP", "hard_override": None,
                "why": "liquidity expanding, credit calm, growth-up quad — momentum/gamma dominate"}
    if q == "Q3":
        return {"regime": "COMMODITY_SHOCK", "hard_override": None,
                "why": "stagflation quad — inventory/curve/bottleneck dominate"}
    if comp.get("breadth_weak", 0.5) > 0.6 and credit < 0.62:
        return {"regime": "CYCLICAL_SLOWDOWN", "hard_override": None,
                "why": "breadth deteriorating without credit blow-out — growth scare"}
    return {"regime": "NEUTRAL", "hard_override": None, "why": "no single dominant driver"}


def regime_weights(regime: str) -> dict:
    return _PROFILES.get(regime, _PROFILES["NEUTRAL"])


def apply_hard_override(picks: list, regime_info: dict) -> tuple[list, str | None]:
    """If longs disabled, drop long picks and return them filtered + a banner note."""
    ov = (regime_info or {}).get("hard_override")
    if ov == "LONGS_DISABLED":
        kept = [p for p in picks if p.get("side") != "long"]
        return kept, ("🛑 HARD OVERRIDE: " + regime_info.get("why", "systemic risk") +
                      f" — {len(picks) - len(kept)} long signal(s) suppressed")
    return picks, None
