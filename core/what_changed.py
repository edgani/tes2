"""what_changed.py — ChatGPT flaw #11: 'what changed?' daily-delta engine.

Compares the current run's state to a stored prior snapshot (session_state) and surfaces only the
DELTAS that matter: regime/quad change, shock jump, gamma flip, new/dropped picks, crowding shifts,
AI-cycle phase change. The user shouldn't reread 500 metrics — just what moved.
"""
from __future__ import annotations


def snapshot_state(quad: dict, shock: dict, picks: list, ai: dict | None = None) -> dict:
    return {
        "quad": (quad or {}).get("structural_quad"),
        "shock": (shock or {}).get("shock_prob"),
        "crash_type": (shock or {}).get("crash_type"),
        "ai_phase": (ai or {}).get("phase"),
        "picks": {p["ticker"]: {"side": p["side"], "crowding": p.get("crowding")} for p in (picks or [])},
    }


def diff_state(prev: dict | None, cur: dict) -> list:
    """Return human-readable change cards. Empty list = nothing material changed."""
    if not prev:
        return [{"kind": "init", "text": "First run this session — baseline captured. Deltas show next refresh."}]
    out = []
    if prev.get("quad") != cur.get("quad"):
        out.append({"kind": "regime", "text": f"GIP quad shifted: {prev.get('quad')} → {cur.get('quad')}"})
    ps, cs = prev.get("shock"), cur.get("shock")
    if ps is not None and cs is not None and abs(cs - ps) >= 5:
        out.append({"kind": "shock", "text": f"Shock pressure {ps} → {cs} ({cs - ps:+.0f})"})
    if prev.get("crash_type") != cur.get("crash_type"):
        out.append({"kind": "crash", "text": f"Crash-type: {prev.get('crash_type')} → {cur.get('crash_type')}"})
    if prev.get("ai_phase") != cur.get("ai_phase"):
        out.append({"kind": "ai", "text": f"AI-cycle phase: {prev.get('ai_phase')} → {cur.get('ai_phase')}"})
    pp, cp = prev.get("picks", {}), cur.get("picks", {})
    for t in cp.keys() - pp.keys():
        out.append({"kind": "new_pick", "text": f"NEW setup: {t} {cp[t]['side'].upper()}"})
    for t in pp.keys() - cp.keys():
        out.append({"kind": "dropped", "text": f"Setup dropped: {t} (no longer clears the gate)"})
    for t in cp.keys() & pp.keys():
        a, b = pp[t].get("crowding"), cp[t].get("crowding")
        if a is not None and b is not None and abs(b - a) >= 15:
            out.append({"kind": "crowding", "text": f"{t} crowding {a:.0f} → {b:.0f}"})
    return out or [{"kind": "stable", "text": "No material regime/risk/positioning change since last refresh."}]
