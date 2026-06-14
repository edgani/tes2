"""surge.py — doc-20 8-layer surge pre-conditioning score (0-100).
HONEST: built ONLY from fields the system already computes (OHLCV proxies + systemic).
Missing institutional feeds (dark pool, CTA, social velocity) are NOT faked — layers fall
back to neutral 0.5 and the components dict shows exactly what fed the score.
Weights are PRIORS pending walk-forward validation."""
from __future__ import annotations
import numpy as np

_W = {"liquidity": 0.20, "positioning": 0.15, "bottleneck": 0.12, "accumulation": 0.20,
      "narrative": 0.10, "reflexivity": 0.08, "rs": 0.08, "compression": 0.07}

def run_surge(a: dict, systemic: dict, internals: dict | None = None) -> dict:
    f = a.get("flow") or {}
    crowd = float(a.get("crowding", 50) or 50)
    vel = float(a.get("adoption_velocity", 0) or 0)
    comp = {}
    comp["liquidity"] = float(np.clip(float(systemic.get("liquidity", 50) or 50) / 100.0, 0, 1))
    comp["positioning"] = float(np.clip((100.0 - crowd) / 100.0, 0, 1))            # underpositioned = fuel
    comp["bottleneck"] = 1.0 if a.get("bottleneck_node") else 0.4                  # presence-based (graph feed = seam)
    f01 = float(a.get("flow01") if a.get("flow01") is not None else 0.5)
    absn = float(f.get("absorption", 50) or 50) / 100.0
    pers = float(np.clip(float(f.get("persistence", 0) or 0), 0, 1))
    comp["accumulation"] = float(np.clip(0.5 * f01 + 0.3 * absn + 0.2 * pers, 0, 1))
    early_stage = str(a.get("stage", "")) in ("SMART_MONEY", "INSTITUTIONAL")
    comp["narrative"] = float(np.clip((0.5 if a.get("theme") else 0.3)
                                      + (0.3 if early_stage and vel > 0 else 0.0)
                                      + (0.2 if crowd < 55 else 0.0), 0, 1))
    refl = float(a.get("reflexivity", a.get("reflex", 0)) or 0)
    comp["reflexivity"] = float(np.clip(min(refl, 80.0) / 100.0, 0, 1))            # capped: parabolic = EXIT elsewhere
    acc = float(a.get("acceleration", 0) or 0)
    comp["rs"] = float(np.clip(0.5 + 0.5 * np.tanh(acc), 0, 1))
    mode = (a.get("market_mode") or {}).get("mode")
    comp["compression"] = 1.0 if mode in ("SQUEEZE", "PINNING") else 0.3
    score = 100.0 * sum(_W[k] * comp[k] for k in _W)
    return {"score": round(float(score), 1), "components": {k: round(v, 2) for k, v in comp.items()}}
