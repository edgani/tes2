"""engines/quad_explainer.py — "Why this quad / what changes it / where it goes"

Turns the GIP reading + the regime-transition (ripeness) output into a plain-language,
data-driven macro panel, and lights up the Ricky2212 narratives relevant to the current
quad / the transition in motion. Everything is derived from data the snapshot already has.
"""
from __future__ import annotations
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_QUAD = {"Q1": ("up", "down"), "Q2": ("up", "up"), "Q3": ("down", "up"), "Q4": ("down", "down")}
_NAME = {"Q1": "Goldilocks", "Q2": "Reflation", "Q3": "Stagflation", "Q4": "Deflation"}

# Standard Hedgeye quad playbook + the honest caveat: this is a BASE RATE, not a guarantee.
_PLAYBOOK = {
    "Q1": {"strong": "growth/tech, consumer discretionary, high-beta, credit",
           "weak": "USD, long bonds, defensives, gold"},
    "Q2": {"strong": "energy, materials, financials, EM, commodities, small-cap",
           "weak": "long bonds, defensives, USD"},
    "Q3": {"strong": "energy, gold, commodities, defensives (utilities/staples)",
           "weak": "consumer discretionary, long-duration tech, bonds"},
    "Q4": {"strong": "long-duration bonds, USD, staples/defensives, gold (at times)",
           "weak": "energy, materials, cyclicals, EM, high-beta"},
}
_CAVEATS = [
    "crowded positioning can make the 'strong' bucket mean-revert (everyone already long it)",
    "negative dealer gamma (GEX) amplifies moves against the playbook",
    "horizon divergence — if the regime is mid-transition, the prevailing-quad winners fade early",
    "in IHSG, bandar accumulation/distribution (maker_framework) can override sector quad-fit",
    "a net-liquidity drain can sink all risk assets regardless of quad",
]


def _g(obj, key, default=None):
    if obj is None:
        return default
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


def _num(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _adjacent(quad):
    """Return (flip_growth_quad, flip_inflation_quad) for a given quad."""
    g, i = _QUAD.get(quad, ("down", "up"))
    flip_g = ("up" if g == "down" else "down", i)
    flip_i = (g, "up" if i == "down" else "down")
    inv = {v: k for k, v in _QUAD.items()}
    return inv.get(flip_g, quad), inv.get(flip_i, quad)


def _what_changes(quad):
    g, i = _QUAD.get(quad, ("down", "up"))
    gq, iq = _adjacent(quad)
    g_cond = ("growth naik lagi" if g == "down" else "growth mulai turun")
    i_cond = ("inflasi mulai turun" if i == "up" else "inflasi naik lagi")
    return [
        {"trigger": g_cond, "to": gq, "to_name": _NAME.get(gq, ""), "leg": "growth"},
        {"trigger": i_cond, "to": iq, "to_name": _NAME.get(iq, ""), "leg": "inflation"},
    ]


def _scenarios_for(quad, transition_label, nu, limit=6):
    """Surface Ricky narratives whose quad_bias matches the quad OR the transition."""
    if nu is None:
        return []
    NB = getattr(nu, "NARRATIVE_QUAD_BIAS", {}) or {}
    N = getattr(nu, "NARRATIVES", {}) or {}
    PRI = getattr(nu, "NARRATIVE_PRIORITY", {}) or {}

    def _norm(s):
        return str(s or "").strip().replace("→", "->").replace(" ", "")

    want = {_norm(quad)}
    if transition_label:
        # transition_label like "Q3->Q2 [RIPE]" → keep the "Q3->Q2" part
        want.add(_norm(transition_label.split("[")[0]))

    hits = []
    for nid, bias in NB.items():
        nb = _norm(bias)
        if nb in want or any(w in nb for w in want if "->" in w):
            meta = N.get(nid, {})
            hits.append({
                "id": nid, "title": meta.get("title", nid)[:80],
                "signal": meta.get("regime_signal", ""),
                "tickers": meta.get("tickers", [])[:5],
                "priority": PRI.get(nid, meta.get("priority", 5)),
            })
    hits.sort(key=lambda h: -_num(h["priority"], 5))
    return hits[:limit]


def explain_quad(gip, transition: Optional[Dict] = None, narrative_module=None) -> Dict:
    """Build the why/what-changes/where-it-goes + scenarios panel data."""
    if gip is None:
        return {"ok": False, "note": "No GIP input."}

    struct_q = _g(gip, "structural_quad", "Q3")
    month_q = _g(gip, "monthly_quad", struct_q)
    global_q = _g(gip, "global_quad", None) or struct_q
    sg, si = _num(_g(gip, "structural_g")), _num(_g(gip, "structural_i"))
    features = _g(gip, "features", {}) or {}
    transition = transition or {}

    g_dir, i_dir = _QUAD.get(struct_q, ("down", "up"))
    drivers = transition.get("drivers", [])
    drv_txt = ", ".join(d.get("indicator", "") for d in drivers[:3]) if drivers else "broad data"

    g_word = "naik (ekspansi)" if g_dir == "up" else "lemah/melambat"
    i_word = "naik" if i_dir == "up" else "turun/mereda"
    if month_q != struct_q:
        turn_txt = (f"Monthly udah di **{month_q}** ({_NAME.get(month_q,'')}) → mungkin mau belok.")
    else:
        turn_txt = f"Monthly juga **{month_q}** → regime stabil dulu."
    why = (f"Growth {g_word}, inflasi {i_word}. {turn_txt}")

    return {
        "ok": True,
        "structural_quad": struct_q, "monthly_quad": month_q, "global_quad": global_q,
        "structural_name": _NAME.get(struct_q, ""), "monthly_name": _NAME.get(month_q, ""),
        "why": why,
        "what_changes": _what_changes(struct_q),
        "where_it_goes": {
            "stage": transition.get("stage", "—"),
            "implied_next": transition.get("implied_next", struct_q),
            "label": transition.get("label", struct_q),
            "summary": transition.get("summary", ""),
            "action_hint": transition.get("action_hint", ""),
        },
        "playbook": {
            "current": _PLAYBOOK.get(struct_q, {}),
            "next": _PLAYBOOK.get(transition.get("implied_next", struct_q), {}),
            "caveats": _CAVEATS,
        },
        "scenarios": _scenarios_for(struct_q, transition.get("label", ""), narrative_module),
    }
