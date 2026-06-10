"""meta/regime_meta.py — L12 Asset Selection. PRODUCT confluence (GCFIS spec):
offensive = geometric-mean of available offensive layers (theme × bottleneck × accumulation ×
adoption-sweet-spot × reflexivity) — AND-logic, a weak present layer drags, absent layers excluded
(honest: no penalty for missing data). Short = distribution score (exit / crowded-rolling-over /
broker distribution / COT extreme). Regime-conditional tilt + counter-regime + capacity filter."""
from __future__ import annotations
import numpy as np
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

def _z01(z, scale=4.0):       # z-ish (center 0) -> [0,1]
    return float(np.clip(0.5 + z / scale, 0.0, 1.0))

def run_regime_meta(per_ticker: dict, systemic: dict, regime_posterior: dict,
                    min_adv: float = 0.0, confluence_min: float = 55.0) -> dict:
    W = _blend(regime_posterior or {"chop": 1})
    stress = (systemic.get("fragility", 0) + systemic.get("shock_prob", 0)) / 200.0
    sigs = []
    for tkr, a in per_ticker.items():
        acc = a.get("accumulation", 0.0); theme = a.get("theme_score", None)
        bott = a.get("bottleneck_score", None)        # 0..1 inherited from supply-chain node
        reflex = a.get("reflexivity", None)            # 0..100
        vel = a.get("adoption_velocity", 0.0); crowd = a.get("crowding", 50.0)

        # --- OFFENSIVE = geometric mean of AVAILABLE [0,1] sub-scores (AND-logic confluence) ---
        subs = {"accumulation": _z01(acc)}
        adopt01 = float(np.clip(0.5 + 0.35 * (1 if a.get("sweet_spot") else 0) + 0.2 * np.tanh(vel), 0, 1))
        subs["adoption"] = adopt01
        if theme is not None: subs["theme"] = _z01(theme)
        if bott is not None: subs["bottleneck"] = float(np.clip(bott, 0, 1))
        if reflex is not None: subs["reflexivity"] = float(np.clip(reflex / 100.0, 0, 1))
        offensive = float(np.exp(np.mean(np.log(np.clip(list(subs.values()), 1e-3, 1.0)))))  # geomean
        bull = offensive * 100.0

        # --- DISTRIBUTION (short side) ---
        crowded_rolling_over = (crowd > 85 and vel < 0)
        bsign = a.get("broker_sign", 0)
        dist = 0.0
        if a.get("exit_signal"): dist += 0.40
        if crowded_rolling_over: dist += 0.40
        if bsign < 0: dist += 0.30
        if a.get("cot_extreme_long"): dist += 0.20
        dist = min(dist, 1.0); bear = dist * 100.0

        meta_long = bull * W["long"] * (1 - W["drag"] * stress)
        meta_short = max(bear * W["short"], 100 * stress * W["short"])
        reason = ""
        if W["long"] > 0.6 and dist >= 0.4:                  # counter-regime flow-dominance
            meta_long *= 0.4; meta_short = min(100, meta_short + 20)
            reason = "distribution into strength (flow-dominance) — front-run the unwind"
        meta_long, meta_short = float(np.clip(meta_long, 0, 100)), float(np.clip(meta_short, 0, 100))
        # lead-lag rotation: a follower primed by a freshly-fired leader gets a timing boost
        rot = a.get("rotation_strength", 0.0)
        if rot > 0 and W["long"] > 0.4:
            boost = min(rot * 6.0, 18.0)
            meta_long = float(np.clip(meta_long + boost, 0, 100))
            r_ = a.get("rotation", {})
            reason = (reason + "; " if reason else "") + f"rotation-primed by {r_.get('leader','?')} (fired {r_.get('days_since_fire','?')}d ago, ~{r_.get('window','?')}d window)"

        adv = a.get("adv"); cap_ok = (adv is None) or (adv >= min_adv)
        if not cap_ok:
            action, conv, direction = "STAND_ASIDE", 0.0, "none"
            reason = (reason + "; " if reason else "") + "below capacity (illiquid)"
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
            conf_str = " · ".join(f"{k[:4]}={v:.2f}" for k, v in subs.items())
            reason = f"{a.get('stage','?')} | crowd {crowd} | confluence[{conf_str}]→{offensive:.2f} | tiltL {W['long']:.2f}"

        sc = {"meta_long": round(meta_long, 1), "meta_short": round(meta_short, 1),
              "accumulation": round(acc, 2), "confluence": round(offensive, 2)}
        if theme is not None: sc["theme"] = round(theme, 2)
        if bott is not None: sc["bottleneck"] = round(bott, 2)
        if reflex is not None: sc["reflexivity"] = round(reflex, 1)
        sigs.append(TickerSignal(
            ticker=tkr, theme=a.get("theme", ""), subtheme=a.get("subtheme", ""),
            meta_score=round(max(meta_long, meta_short), 1), action=action, direction=direction,
            conviction=round(conv, 1), scores=sc, adoption_stage=a.get("stage", "UNKNOWN"),
            crowding=round(crowd, 1), broker_verdict=a.get("broker_verdict", ""),
            bottleneck=round(float(bott), 2) if bott is not None else 0.0,
            reflexivity=round(float(reflex), 1) if reflex is not None else 0.0,
            runaway=bool(a.get("runaway", False)), capacity_ok=cap_ok, reason=reason))
    return {"ok": True, "regime_weights": {k: round(v, 2) for k, v in W.items()},
            "systemic_stress": round(stress, 2), "signals": sigs}
