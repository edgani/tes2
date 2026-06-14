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


# doc 5: each market ranks by ITS OWN dominant drivers — weighted geometric mean, not one universal model
_MKT_W = {
    "idx":       {"flow": 1.4, "accumulation": 1.3, "adoption": 1.0, "theme": 0.8, "bottleneck": 0.6, "reflexivity": 0.8},
    "us":        {"theme": 1.2, "bottleneck": 1.3, "accumulation": 1.0, "adoption": 1.0, "reflexivity": 1.0, "flow": 1.0},
    "crypto":    {"reflexivity": 1.3, "flow": 1.2, "adoption": 1.2, "accumulation": 1.1, "theme": 0.8, "bottleneck": 0.5},
    "fx":        {"flow": 1.2, "accumulation": 1.0, "reflexivity": 0.8, "theme": 0.7, "bottleneck": 0.3, "adoption": 0.8},
    "commodity": {"bottleneck": 1.3, "flow": 1.1, "accumulation": 1.0, "theme": 0.9, "reflexivity": 0.8, "adoption": 0.9},
}

def _conv_blend(a: dict, meta_dir: float, offensive: float, crowd: float, direction: str) -> float:
    """HYBRID conviction (doc-13/19): regime gate stays in meta; conviction = additive blend of
    ORTHOGONAL evidence so tickers DISCRIMINATE (pure product/floor collapsed everything to one number).
    Weights are priors pending walk-forward."""
    f01 = float(a.get("flow01") if a.get("flow01") is not None else 0.5)
    hz = float(((a.get("horizon") or {}).get("alignment", 50)) or 50) / 100.0
    rq = float(((a.get("response") or {}).get("quality", 50)) or 50) / 100.0
    cr = float(crowd or 50) / 100.0
    if direction == "short":
        f01, hz, rq, cr = 1.0 - f01, 1.0 - hz, 1.0 - rq, cr   # shorts like bearish flow, broken TFs, weak response, crowded longs
    else:
        cr = 1.0 - cr                                          # longs like UNcrowded
    raw = (0.30 * (meta_dir / 100.0) + 0.25 * float(offensive) + 0.15 * f01
           + 0.10 * hz + 0.10 * rq + 0.10 * cr)
    return float(np.clip(raw * 100.0, 0, 100))


def _wgeo(subs: dict, market: str, stress: bool = False) -> float:
    """Weighted geometric mean: exp(Σ w·ln s / Σ w). Absent layers excluded (no penalty).
    stress=True (deleveraging / risk-off) → adaptive tilt: flow & accumulation matter MORE,
    theme & reflexivity matter LESS (doc-6 adaptive-weight layer; multipliers are priors)."""
    W = dict(_MKT_W.get(market, {}))
    if stress:
        W["flow"] = W.get("flow", 1.0) * 1.25
        W["accumulation"] = W.get("accumulation", 1.0) * 1.10
        W["theme"] = W.get("theme", 1.0) * 0.85
        W["reflexivity"] = W.get("reflexivity", 1.0) * 0.80
    num = den = 0.0
    for k, v in subs.items():
        w = float(W.get(k, 1.0)); v = float(np.clip(v, 1e-3, 1.0))
        num += w * np.log(v); den += w
    return float(np.exp(num / den)) if den else 0.0

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
        if a.get("flow01") is not None:
            f01 = float(a["flow01"])
            if a.get("broker_sign", 0) > 0: f01 = min(1.0, f01 + 0.10)     # IDX: broker accumulation reinforces flow
            elif a.get("broker_sign", 0) < 0: f01 = max(0.0, f01 - 0.10)
            subs["flow"] = float(np.clip(f01, 0, 1))
        market = a.get("market", "us")
        cross = (systemic or {}).get("cross_asset", {}) or {}
        stress_mode = bool(cross.get("defer_longs")) or float((regime_posterior or {}).get("risk_off", 0) or 0) > 0.5
        offensive = _wgeo(subs, market, stress=stress_mode)                # doc 5 + adaptive stress tilt
        bull = offensive * 100.0

        # --- DISTRIBUTION (short side) ---
        crowded_rolling_over = (crowd > 85 and vel < 0)
        bsign = a.get("broker_sign", 0)
        dist = 0.0
        if a.get("exit_signal"): dist += 0.40
        if crowded_rolling_over: dist += 0.40
        if bsign < 0: dist += 0.30
        if a.get("cot_extreme_long"): dist += 0.20
        _ftd = (a.get("flow") or {}).get("type"); _rzd = (a.get("response") or {}).get("response")
        if _ftd == "DISTRIBUTION": dist += 0.30                       # doc-1/2 microstructure feeds the short side
        if _ftd == "PANIC_LIQUIDATION": dist += 0.15
        if (a.get("market_mode") or {}).get("mode") == "DISTRIBUTION": dist += 0.20
        if _rzd in ("REJECTION", "NO_BID_CONTINUATION"): dist += 0.15
        dist = min(dist, 1.0); bear = dist * 100.0

        meta_long = bull * W["long"] * (1 - W["drag"] * stress)
        if crowd > 90 and vel < 0:
            meta_long *= 0.30                                   # positioning override: crowded & rolling over beats macro
        # stress AMPLIFIES per-ticker bear evidence — it never manufactures a short by itself
        # (the old ticker-independent floor 100·stress·W_short collapsed every conviction to one constant)
        meta_short = bear * W["short"] * (1.0 + 0.6 * stress)
        _ft = (a.get("flow") or {}).get("type"); _rz = (a.get("response") or {}).get("response")
        a["_short_conflict"] = False
        if _ft == "ACCUMULATION" or _rz == "FAILED_BREAKDOWN_RECLAIM":
            meta_short *= 0.45                                # contradiction guard: bullish tape caps the short
            a["_short_conflict"] = True
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
            action, conv, direction = "BUILD_LONG", _conv_blend(a, meta_long, offensive, crowd, "long"), "long"
        elif meta_short >= confluence_min and bear >= 35:     # short needs REAL per-ticker distribution evidence
            action, conv, direction = "BUILD_SHORT", _conv_blend(a, meta_short, offensive, crowd, "short"), "short"
        elif max(meta_long, meta_short) >= 50:
            direction = "long" if meta_long >= meta_short else "short"
            action = "START_SCALING"
            conv = _conv_blend(a, max(meta_long, meta_short), offensive, crowd, direction)
        else:
            action, conv, direction = "STAND_ASIDE", max(meta_long, meta_short), "none"
        if not reason:
            conf_str = " · ".join(f"{k[:4]}={v:.2f}" for k, v in subs.items())
            reason = f"{a.get('stage','?')} | {a.get('market','us')} | crowd {crowd} | confluence[{conf_str}]→{offensive:.2f} | tiltL {W['long']:.2f}"

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
