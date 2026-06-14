"""final_desk.py — THE answer, not an inventory. ≤10 cross-market picks (long/short),
every pick must carry a VALID reason block: ≥2 evidence lines + invalidation + valid entry + EV.
If only N<10 clear the bar, output N — no padding with garbage to hit a quota.
desk_score = 0.45·tanh(EV/10) + 0.30·conviction + 0.15·surge + 0.10·response-quality (priors)."""
from __future__ import annotations
import numpy as np

_BUCKETS = ("master_long", "master_short")
_MAX, _MAX_PER_MARKET, _MAX_PER_THEME = 10, 3, 2

def _valid(r: dict, a: dict) -> tuple[bool, str]:
    if r.get("action") not in ("BUILD_LONG", "BUILD_SHORT", "START_SCALING"):
        return False, "not actionable"
    if not r.get("entry_valid"):
        return False, "entry invalid (WAIT)"
    if r.get("ev") is None:
        return False, "no EV (entry/stop/target incomplete)"
    why = [w for w in (r.get("why_now") or []) if w and "no single dominant" not in str(w)]
    if len(why) < 2:
        return False, "insufficient evidence (<2 reasons)"
    inv = r.get("invalidation") or {}
    if not (inv.get("price") or inv.get("conditions") or inv.get("cond")):
        return False, "no invalidation"
    if r.get("direction") == "short" and a.get("_short_conflict"):
        return False, "short vs bullish tape (conflict guard)"
    return True, "ok"

def _score(r: dict) -> float:
    ev = float(r.get("ev") or 0.0)
    conv = float(r.get("conviction") or 0.0) / 100.0
    surge = float(r.get("surge") or 50.0) / 100.0
    rq = float(((r.get("response") or {}).get("quality", 50)) or 50) / 100.0
    return float(0.45 * np.tanh(ev / 10.0) + 0.30 * conv + 0.15 * surge + 0.10 * rq)

def build_final_desk(ranking: dict, per_ticker: dict, posterior: dict | None = None) -> dict:
    risk_on = float((posterior or {}).get("risk_on", 0) or 0)
    cands, rejected = [], []
    seen = set()
    for b in _BUCKETS:
        for r in ranking.get(b, []) or []:
            t = r.get("ticker")
            if t in seen:
                continue
            seen.add(t)
            ok, why = _valid(r, per_ticker.get(t, {}) or {})
            (cands if ok else rejected).append((r, why))
    ranked = sorted((r for r, _ in cands), key=_score, reverse=True)
    picks, mkt_n, thm_n = [], {}, {}
    for r in ranked:
        m, th = r.get("market", "?"), r.get("theme") or "_"
        if mkt_n.get(m, 0) >= _MAX_PER_MARKET or thm_n.get(th, 0) >= _MAX_PER_THEME:
            continue
        mkt_n[m] = mkt_n.get(m, 0) + 1
        thm_n[th] = thm_n.get(th, 0) + 1
        picks.append({"rank": len(picks) + 1, "ticker": r["ticker"], "side": r.get("direction", ""),
                      "action": r.get("action"), "conviction": r.get("conviction"), "ev": r.get("ev"),
                      "surge": r.get("surge"), "market": m, "theme": r.get("theme") or "—",
                      "entry": r.get("entry"), "stop": r.get("stop"),
                      "targets": r.get("targets") or [x for x in (r.get("target"),) if x],
                      "size_x": r.get("size_x", r.get("size")), "hold": r.get("hold"),
                      "reasons": [str(w) for w in (r.get("why_now") or [])][:3],
                      "trapped": r.get("whos_trapped"),
                      "invalidation": r.get("invalidation") or {},
                      "mode": r.get("market_mode"), "flow": (r.get("flow") or {}).get("type"),
                      "primary_target": ((r.get("targets") or [None, None])[1]
                                         if (risk_on > 0.5 and r.get("direction") == "long"
                                             and len(r.get("targets") or []) >= 2)
                                         else (r.get("targets") or [r.get("target")])[0]),
                      "desk_score": round(_score(r), 3)})
        if len(picks) >= _MAX:
            break
    note = (f"only {len(picks)} meet the bar today — no fabricated fills" if len(picks) < _MAX
            else "top 10 of the cross-market book")
    return {"picks": picks, "note": note,
            "rejected_summary": {w: sum(1 for _, x in rejected if x == w)
                                 for w in {x for _, x in rejected}}}
