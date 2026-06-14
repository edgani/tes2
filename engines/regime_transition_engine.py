"""engines/regime_transition_engine.py — Regime Inflection / Ripeness Engine

Answers the trader's real question (not "what quad are we in" but): HAS the regime change
happened yet, or not — and is it RIPE or not? The goal is to catch the turn BEFORE it
completes, by reading the leading (fast) horizon against the structural (slow) one.

Method — entirely from signals GIP already computes (no new data, no guessing):
  • Dual horizon: monthly_quad (fast/leading) vs structural_quad (slow/confirming). When the
    fast horizon has already turned but the slow one hasn't, the change is in motion but not
    yet confirmed — the actionable window.
  • Direction of travel: (monthly_g - structural_g, monthly_i - structural_i) shows where the
    fast horizon is pulling growth & inflation (the 2nd-derivative direction).
  • flip_hazard + probability margin: how fragile the current quad is.
  • Driver indicators: the leading indicators (features ROC) doing the pulling.

Stages: DORMANT (no change) -> BUILDING (early, fast horizon starting to diverge) ->
RIPE (fast horizon turned, slow not yet — act here) -> CONFIRMED (both flipped, you're late).
"""
from __future__ import annotations
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_QUAD = {"Q1": ("up", "down"), "Q2": ("up", "up"), "Q3": ("down", "up"), "Q4": ("down", "down")}
_QUAD_NAME = {"Q1": "Goldilocks", "Q2": "Reflation", "Q3": "Stagflation", "Q4": "Deflation"}


def _g(obj, key, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _num(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _implied_from_travel(quad, dg, di):
    g_dir = "up" if dg > 0.04 else "down" if dg < -0.04 else None
    i_dir = "up" if di > 0.04 else "down" if di < -0.04 else None
    if g_dir is None and i_dir is None:
        return quad
    cur_g, cur_i = _QUAD.get(quad, ("down", "up"))
    new_g = g_dir or cur_g
    new_i = i_dir or cur_i
    for q, (qg, qi) in _QUAD.items():
        if qg == new_g and qi == new_i:
            return q
    return quad


def _top_drivers(features, dg, di, n=3):
    if not isinstance(features, dict) or not features:
        return []
    ranked = sorted(((k, v) for k, v in features.items()
                     if isinstance(v, (int, float)) and abs(v) > 1e-6),
                    key=lambda kv: -abs(kv[1]))
    return [{"indicator": k, "roc": round(float(v), 4),
             "direction": "accelerating" if v > 0 else "decelerating"} for k, v in ranked[:n]]


def _summary(struct_q, month_q, implied, stage, flip, drivers):
    qn = _QUAD_NAME.get(implied, implied)
    drv = ", ".join(d["indicator"] for d in drivers[:2]) if drivers else "broad data"
    if stage == "DORMANT":
        return f"Stable in {struct_q} ({_QUAD_NAME.get(struct_q,'')}). No regime change brewing (flip hazard {flip:.0%})."
    if stage == "BUILDING":
        return (f"Early signs of a {struct_q}->{implied} ({qn}) shift — momentum turning ({drv}), "
                f"but the leading horizon hasn't confirmed. Not ready yet; watch.")
    if stage == "RIPE":
        return (f"RIPE: leading horizon already in {month_q} while structural still reads {struct_q}. "
                f"The {struct_q}->{implied} ({qn}) turn is in motion but not yet confirmed — "
                f"the window to position ahead of it. Drivers: {drv}.")
    return f"{struct_q} / {month_q}."


def _action_hint(stage, struct_q, implied):
    if stage == "RIPE":
        return f"Position for {implied} leadership now (front-run the structural confirmation)."
    if stage == "BUILDING":
        return f"Build a watchlist for {implied}; size only on confirmation of the turn."
    return "No transition edge — trade the prevailing quad."


def run_regime_transition(gip, prices: Optional[Dict] = None, fred: Optional[Dict] = None) -> Dict:
    """gip: GIPResult (dataclass) or dict. Returns ripeness-staged transition read."""
    if gip is None:
        return {"stage": "UNKNOWN", "transitioning": False, "summary": "No GIP input."}

    struct_q = _g(gip, "structural_quad", "Q3")
    month_q = _g(gip, "monthly_quad", struct_q)
    struct_g = _num(_g(gip, "structural_g")); struct_i = _num(_g(gip, "structural_i"))
    month_g = _num(_g(gip, "monthly_g")); month_i = _num(_g(gip, "monthly_i"))
    s_probs = _g(gip, "structural_probs", {}) or {}
    features = _g(gip, "features", {}) or {}

    flip = _g(gip, "flip_hazard")
    if flip is None and isinstance(s_probs, dict) and len(s_probs) >= 2:
        top = max(s_probs.values()); runner = sorted(s_probs.values(), reverse=True)[1]
        flip = max(0.0, min(1.0, 0.5 - 0.8 * (top - runner)))
    flip = _num(flip, 0.5)

    dg = month_g - struct_g
    di = month_i - struct_i
    travel_mag = abs(dg) + abs(di)

    diverging = month_q != struct_q
    implied_next = month_q if diverging else _implied_from_travel(struct_q, dg, di)

    if diverging:
        stage = "RIPE" if (flip > 0.45 or travel_mag > 0.15) else "BUILDING"
    elif implied_next != struct_q and travel_mag > 0.08:
        stage = "BUILDING"
    elif flip > 0.6:
        stage = "BUILDING"
    else:
        stage = "DORMANT"

    drivers = _top_drivers(features, dg, di)
    return {
        "stage": stage,
        "transitioning": stage in ("BUILDING", "RIPE"),
        "from_quad": struct_q, "leading_quad": month_q, "implied_next": implied_next,
        "diverging": diverging, "flip_hazard": round(flip, 3),
        "growth_accel": round(dg, 4), "inflation_accel": round(di, 4),
        "travel_magnitude": round(travel_mag, 4), "drivers": drivers,
        "label": (f"{struct_q}->{implied_next} [{stage}]" if implied_next != struct_q else f"{struct_q} [{stage}]"),
        "summary": _summary(struct_q, month_q, implied_next, stage, flip, drivers),
        "action_hint": _action_hint(stage, struct_q, implied_next),
    }
