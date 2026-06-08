"""meta/regime_meta.py — L12 Asset Selection: regime-conditional CONFLUENCE + master ranking + FILTER.
Meta = regime-weighted confluence of accumulation + theme + smart-money(broker). Counter-regime
flow-dominance: bullish regime but distribution -> short/stand-aside. Capacity filter drops illiquid."""
from __future__ import annotations
import numpy as np
from ..core.change_core import to_100
from ..core.contracts import TickerSignal

_W = {"risk_on": {"long": 1.00, "short": 0.20, "drag": 0.20},
      "transition_up": {"long": 0.90, "short": 0.30, "drag": 0.30},
      "chop": {"long": 0.50, "short": 0.50, "drag": 0.50},
      "transition_down": {"long": 0.30, "short": 0.90, "drag": 0.80},
      "risk_off": {"long": 0.20, "short": 1.00, "drag": 1.00}}

def _blend(post):
    tot = sum(post.get(s, 0) for s in _W) or 1.0
    w = {"long": 0, "short": 0, "drag": 0}
    for s, c in _W.items():
        p = post.get(s, 0) / tot
        for k in w: w[k] += p * c[k]
    return w

def run_regime_meta(per_ticker: dict, systemic: dict, regime_posterior: dict,
                    min_adv: float = 0.0, confluence_min: float = 55.0) -> dict:
    W = _blend(regime_posterior or {"chop": 1})
    stress = (systemic.get("fragility", 0) + systemic.get("shock_prob", 0)) / 200.0
    sigs = []
    for tkr, a in per_ticker.items():
        acc = a.get("accumulation", 0.0); theme = a.get("theme_score", 0.0); bsign = a.get("broker_sign", 0)
        # CONFLUENCE (offensive): accumulation + theme + smart-money flow
        off = 0.45 * acc + 0.35 * theme + 0.20 * bsign
        bull = to_100(off); bear = to_100(-off)
        if a.get("sweet_spot"): bull = min(100, bull + 12)
        if a.get("exit_signal"): bear = min(100, bear + 15)
        if a.get("cot_extreme_long"): bear = min(100, bear + 8)
        distribution = a.get("exit_signal") or bsign < 0 or a.get("cot_extreme_long")

        meta_long = bull * W["long"] * (1 - W["drag"] * stress)
        meta_short = max(bear * W["short"], 100 * stress * W["short"])
        reason = ""
        if W["long"] > 0.6 and distribution:                    # counter-regime / flow-dominance
            meta_long *= 0.4; meta_short = min(100, meta_short + 20)
            reason = "distribution into strength (flow-dominance) — front-run the unwind"
        meta_long, meta_short = float(np.clip(meta_long, 0, 100)), float(np.clip(meta_short, 0, 100))

        # capacity filter
        adv = a.get("adv"); cap_ok = (adv is None) or (adv >= min_adv)
        if not cap_ok:
            reason = (reason + "; " if reason else "") + "below capacity (illiquid)"

        if not cap_ok:
            action, conv, direction = "STAND_ASIDE", 0.0, "none"
        elif meta_long >= confluence_min and not a.get("exit_signal"):
            action, conv, direction = "BUILD_LONG", meta_long, "long"
        elif meta_short >= confluence_min:
            action, conv, direction = "BUILD_SHORT", meta_short, "short"
        elif max(meta_long, meta_short) >= 50:
            direction = "long" if meta_long >= meta_short else "short"
            action, conv = "START_SCALING", max(meta_long, meta_short)
        else:
            action, conv, direction = "STAND_ASIDE", max(meta_long, meta_short), "none"
        if not reason:
            reason = f"{a.get('stage','?')} | crowd {a.get('crowding','?')} | conf off={off:.2f} | tilt L={W['long']:.2f}"
        sigs.append(TickerSignal(ticker=tkr, theme=a.get("theme", ""), meta_score=round(max(meta_long, meta_short), 1),
                                 action=action, direction=direction, conviction=round(conv, 1),
                                 scores={"meta_long": round(meta_long, 1), "meta_short": round(meta_short, 1),
                                         "accumulation": round(acc, 2), "theme": round(theme, 2),
                                         "confluence": round(off, 2)},
                                 adoption_stage=a.get("stage", "UNKNOWN"), crowding=a.get("crowding", 0.0),
                                 broker_verdict=a.get("broker_verdict", ""), capacity_ok=cap_ok, reason=reason))
    return {"ok": True, "regime_weights": {k: round(v, 2) for k, v in W.items()},
            "systemic_stress": round(stress, 2), "signals": sigs}
