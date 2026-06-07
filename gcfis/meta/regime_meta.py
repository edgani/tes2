"""meta/regime_meta.py — C1 keystone: regime-conditional weighting + MASTER RANKING (Gap #8).
Weights blend by HMM posterior. Counter-regime flow-dominance: bullish regime but distribution
into strength -> flip to short/stand-aside (the 'data good but price falls' case)."""
from __future__ import annotations
import numpy as np
from ..core.change_core import to_100
from ..core.contracts import TickerSignal

# per-state tilt: how much to favour longs vs shorts, and how hard systemic stress drags
_W = {
    "risk_on":        {"long": 1.00, "short": 0.20, "drag": 0.20},
    "transition_up":  {"long": 0.90, "short": 0.30, "drag": 0.30},
    "chop":           {"long": 0.50, "short": 0.50, "drag": 0.50},
    "transition_down":{"long": 0.30, "short": 0.90, "drag": 0.80},
    "risk_off":       {"long": 0.20, "short": 1.00, "drag": 1.00},
}

def _blend(posterior: dict) -> dict:
    tot = sum(posterior.get(s, 0) for s in _W) or 1.0
    w = {k: 0.0 for k in ("long", "short", "drag")}
    for s, cfg in _W.items():
        p = posterior.get(s, 0) / tot
        for k in w:
            w[k] += p * cfg[k]
    return w

def run_regime_meta(per_ticker: dict, systemic: dict, regime_posterior: dict) -> dict:
    W = _blend(regime_posterior or {"chop": 1})
    systemic_stress = (systemic.get("fragility", 0) + systemic.get("shock_prob", 0)) / 200.0  # 0..1
    longs, shorts, spots, sigs = [], [], [], []
    for tkr, a in per_ticker.items():
        acc = a.get("accumulation", 0.0)
        bull = to_100(acc); bear = to_100(-acc)
        if a.get("sweet_spot"): bull = min(100, bull + 12)
        if a.get("exit_signal"): bear = min(100, bear + 15)
        bsign = a.get("broker_sign", 0)
        bull += 6 * max(bsign, 0); bear += 6 * max(-bsign, 0)
        distribution = a.get("exit_signal") or bsign < 0

        meta_long = bull * W["long"] * (1 - W["drag"] * systemic_stress)
        meta_short = max(bear * W["short"], 100 * systemic_stress * W["short"])
        reason = ""
        # counter-regime / flow-dominance: distribution into a bullish regime
        if W["long"] > 0.6 and distribution:
            meta_long *= 0.4; meta_short = min(100, meta_short + 20)
            reason = "distribution into strength (flow-dominance) — front-run the unwind"

        meta_long = float(np.clip(meta_long, 0, 100)); meta_short = float(np.clip(meta_short, 0, 100))
        if meta_long >= 65 and not a.get("exit_signal"):
            action, conv, side = "BUILD_LONG", meta_long, "long"
        elif meta_short >= 65:
            action, conv, side = "BUILD_SHORT", meta_short, "short"
        elif max(meta_long, meta_short) >= 50:
            side = "long" if meta_long >= meta_short else "short"
            action, conv = "START_SCALING", max(meta_long, meta_short)
        else:
            action, conv, side = "STAND_ASIDE", max(meta_long, meta_short), "none"
        if not reason:
            reason = f"{a.get('stage','?')} | crowding {a.get('crowding','?')} | regime-tilt long={W['long']:.2f}"

        sig = TickerSignal(ticker=tkr, meta_score=round(max(meta_long, meta_short), 1),
                           scores={"meta_long": round(meta_long, 1), "meta_short": round(meta_short, 1),
                                   "accumulation": round(acc, 2)},
                           adoption_stage=a.get("stage", "UNKNOWN"), crowding=a.get("crowding", 0.0),
                           broker_verdict=a.get("broker_verdict", ""), action=action,
                           conviction=round(conv, 1), reason=reason)
        sigs.append(sig)
        row = {"ticker": tkr, "action": action, "conviction": round(conv, 1),
               "meta_long": round(meta_long, 1), "meta_short": round(meta_short, 1),
               "stage": a.get("stage", "?"), "reason": reason}
        if action == "BUILD_LONG" or (action == "START_SCALING" and side == "long"):
            longs.append(row)
        elif action == "BUILD_SHORT" or (action == "START_SCALING" and side == "short"):
            shorts.append(row)
        if a.get("sweet_spot") and meta_long >= 50:
            spots.append(row)
    longs.sort(key=lambda r: r["meta_long"], reverse=True)
    shorts.sort(key=lambda r: r["meta_short"], reverse=True)
    spots.sort(key=lambda r: r["meta_long"], reverse=True)
    return {"ok": True, "regime_weights": {k: round(v, 2) for k, v in W.items()},
            "systemic_stress": round(systemic_stress, 2),
            "master_long": longs, "master_short": shorts, "master_spot": spots,
            "signals": [s.as_dict() for s in sigs]}
