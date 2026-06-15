"""competitive_ranking_engine.py — institutional competitive opportunity ranking.

Replaces threshold filtering ("show everything > 70" → 60 tickers) with a multi-stage
COMPETITIVE engine, per FINAL_REDESIGN_SPEC:
  Stage 1  hard elimination  (liquidity / confidence / catalyst floors)
  Stage 2  regime-weighted scoring (dynamic weights + regime OVERRIDE)
  Stage 3  hard penalties    (crowding / fragility / narrative-exhaustion collapse the score)
  Stage 4  competition       (per-market caps + global conviction tiers: 3-5 / 5-10 / hidden)

Why a geometric mean (improvement over the naive multiplicative draft): raw products of
five [0,1] pillars are tiny and unbounded by the regime weights, so scores can't be
compared across regimes and one mid pillar tanks everything pathologically. A WEIGHTED
GEOMETRIC MEAN keeps the intended AND-gate ("any weak pillar collapses the score") but
stays in [0,1]; we then gate by confidence and reduce by penalties → final in [0,100].

Causal fields are DATA-DRIVEN from each candidate's own factor values. Fields that need an
absent feed (positioning for "who is trapped", flow for "who must buy") are FLAGGED, never
fabricated. Not financial advice.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import math

EPS = 1e-6

# ── per-market visible caps (spec): compete WITHIN market, then globally ──
MARKET_CAPS = {"us": 10, "crypto": 6, "commodity": 5, "fx": 4, "idx": 8}
TIER1_MAX = 5     # highest conviction (global)
TIER2_MAX = 10    # watchlist (global)

# ── hard elimination floors (the system must be able to say NO) ──
MIN_CONFIDENCE = 0.55
MIN_LIQUIDITY = 0.40
MIN_CATALYST = 0.35


@dataclass
class TickerCandidate:
    ticker: str
    market: str
    # five pillars (each 0..1) — the asymmetry thesis
    regime_alignment: float           # fits the current regime
    bottleneck_pressure: float        # sits on a hardening choke point
    accumulation_persistence: float   # silent-accumulation signature
    positioning_asymmetry: float      # crowd offside / room to move
    reflexivity_potential: float      # price <-> flow <-> narrative feedback
    # quality / risk (0..1)
    liquidity_score: float
    confidence_score: float
    catalyst_score: float
    crowding_risk: float = 0.0
    fragility_risk: float = 0.0
    narrative_exhaustion: float = 0.0
    # context modifiers (0..1)
    propagation_strength: float = 0.5
    narrative_strength: float = 0.5
    volatility_quality: float = 0.5
    # outputs
    score: float = 0.0
    tier: str = "hidden"
    eliminated: Optional[str] = None
    breakdown: Dict = field(default_factory=dict)


def regime_weights(regime: str) -> Dict[str, float]:
    """Dynamic weights normalized to sum=1. The regime OVERRIDE: amplify the pillars that
    matter in this regime, damp the rest."""
    w = {"regime_alignment": 1.0, "bottleneck_pressure": 1.0, "accumulation_persistence": 1.0,
         "positioning_asymmetry": 1.0, "reflexivity_potential": 1.0}
    r = (regime or "").lower()
    if r == "negative_gamma":
        w["positioning_asymmetry"] *= 1.8; w["reflexivity_potential"] *= 1.6; w["bottleneck_pressure"] *= 0.7
    elif r == "liquidity_contraction":
        w["accumulation_persistence"] *= 1.5; w["regime_alignment"] *= 1.6; w["reflexivity_potential"] *= 0.6
    elif r == "commodity_shock":
        w["bottleneck_pressure"] *= 2.0; w["regime_alignment"] *= 1.3; w["reflexivity_potential"] *= 0.8
    elif r == "macro_panic":
        w["regime_alignment"] *= 2.2; w["positioning_asymmetry"] *= 1.5; w["accumulation_persistence"] *= 0.6
    s = sum(w.values())
    return {k: v / s for k, v in w.items()}


def eliminate(c: TickerCandidate) -> Optional[str]:
    """Stage 1 — hard floors. Returns reason string if eliminated, else None."""
    if c.confidence_score < MIN_CONFIDENCE:
        return f"confidence {c.confidence_score:.2f}<{MIN_CONFIDENCE}"
    if c.liquidity_score < MIN_LIQUIDITY:
        return f"liquidity {c.liquidity_score:.2f}<{MIN_LIQUIDITY}"
    if c.catalyst_score < MIN_CATALYST:
        return f"no catalyst {c.catalyst_score:.2f}<{MIN_CATALYST}"
    return None


def score(c: TickerCandidate, regime: str) -> float:
    """Stages 2-3 — regime-weighted geometric mean, confidence-gated, penalty-reduced → [0,100]."""
    w = regime_weights(regime)
    pillars = {"regime_alignment": c.regime_alignment, "bottleneck_pressure": c.bottleneck_pressure,
               "accumulation_persistence": c.accumulation_persistence,
               "positioning_asymmetry": c.positioning_asymmetry, "reflexivity_potential": c.reflexivity_potential}
    # weighted geometric mean in (0,1] — AND-gate without magnitude blow-up
    geo = math.exp(sum(w[k] * math.log(max(pillars[k], 0.0) + EPS) for k in pillars))
    # bounded context modifiers
    mod = (1 + 0.30 * c.propagation_strength) * (1 + 0.18 * c.narrative_strength) * (1 + 0.12 * c.volatility_quality)
    # hard penalties — crowded / fragile / exhausted collapse the score
    pen = max(0.0, (1 - 0.45 * c.crowding_risk) * (1 - 0.30 * c.fragility_risk) * (1 - 0.40 * c.narrative_exhaustion))
    final = round(min(100.0, geo * c.confidence_score * mod * pen * 100.0), 2)
    c.breakdown = {"geo": round(geo, 3), "conf": round(c.confidence_score, 2),
                   "modifier": round(mod, 3), "penalty": round(pen, 3),
                   "weights": {k: round(v, 2) for k, v in w.items()}}
    return final


def causal_summary(c: TickerCandidate) -> Dict[str, str]:
    """Data-driven from the candidate's OWN factors. Feed-gated fields flagged, not faked."""
    def lvl(x):
        return "high" if x >= 0.66 else "moderate" if x >= 0.4 else "low"
    why = []
    if c.accumulation_persistence >= 0.6:
        why.append("persistent silent accumulation")
    if c.bottleneck_pressure >= 0.6:
        why.append("hardening bottleneck")
    if c.positioning_asymmetry >= 0.6:
        why.append("crowd offside")
    return {
        "why_now": ", ".join(why) or "no strong edge yet",
        "what_changed": f"reflexivity {lvl(c.reflexivity_potential)} · propagation {lvl(c.propagation_strength)}",
        "who_is_trapped": "⊘ needs positioning feed (options/COT/short-interest) — not computed",
        "who_must_buy": "⊘ needs flow feed (ETF/dealer/foreign) — not computed",
        "what_is_mispriced": f"narrative {lvl(c.narrative_strength)} vs crowding {lvl(c.crowding_risk)}",
        "bottleneck": f"centrality pressure {lvl(c.bottleneck_pressure)}",
        "macro_alignment": f"regime fit {lvl(c.regime_alignment)}",
        "invalidation": f"accumulation breakdown / liquidity loss (liq {lvl(c.liquidity_score)})",
    }


def rank(candidates: List[TickerCandidate], regime: str, market_caps: Dict[str, int] = None) -> Dict:
    """Stage 4 — eliminate, score, compete per-market (caps), then global conviction tiers."""
    caps = market_caps or MARKET_CAPS
    survivors, eliminated = [], []
    for c in candidates:
        reason = eliminate(c)
        if reason:
            c.eliminated = reason
            eliminated.append(c)
            continue
        c.score = score(c, regime)
        survivors.append(c)
    survivors.sort(key=lambda x: -x.score)

    # per-market competition (visible caps)
    by_market: Dict[str, List[TickerCandidate]] = {}
    cnt: Dict[str, int] = {}
    for c in survivors:
        cap = caps.get(c.market, 6)
        cnt.setdefault(c.market, 0)
        if cnt[c.market] < cap:
            by_market.setdefault(c.market, []).append(c)
            cnt[c.market] += 1

    # global conviction tiers across the per-market survivors
    visible = sorted((c for lst in by_market.values() for c in lst), key=lambda x: -x.score)
    tier1, tier2, hidden = visible[:TIER1_MAX], visible[TIER1_MAX:TIER1_MAX + TIER2_MAX], visible[TIER1_MAX + TIER2_MAX:]
    for c in tier1:
        c.tier = "highest_conviction"
    for c in tier2:
        c.tier = "watchlist"
    for c in hidden:
        c.tier = "emerging_hidden"

    return {
        "regime": regime,
        "tiers": {"highest_conviction": tier1, "watchlist": tier2, "emerging_hidden": hidden},
        "by_market": by_market,
        "eliminated": eliminated,
        "summary": {"in": len(candidates), "eliminated": len(eliminated), "survived": len(survivors),
                    "visible": len(visible), "tier1": len(tier1), "tier2": len(tier2),
                    "say_no_ratio": round(1 - len(tier1) / max(len(candidates), 1), 2)},
    }


if __name__ == "__main__":
    import random
    random.seed(11)
    mkts = ["us", "crypto", "commodity", "fx", "idx"]
    pool = []
    # one hand-built clean bottleneck name + one strong-but-crowded mega + noise
    pool.append(TickerCandidate("CLEAN_BOTTLENECK", "us", 0.85, 0.92, 0.88, 0.80, 0.78,
                                liquidity_score=0.7, confidence_score=0.82, catalyst_score=0.7,
                                crowding_risk=0.15, fragility_risk=0.1, propagation_strength=0.8, narrative_strength=0.6))
    pool.append(TickerCandidate("CROWDED_MEGA", "us", 0.9, 0.9, 0.85, 0.8, 0.95,
                                liquidity_score=0.99, confidence_score=0.9, catalyst_score=0.9,
                                crowding_risk=0.9, fragility_risk=0.2, narrative_exhaustion=0.7,
                                propagation_strength=0.9, narrative_strength=0.95))
    for i in range(28):
        m = random.choice(mkts)
        pool.append(TickerCandidate(
            f"{m.upper()}_{i}", m,
            regime_alignment=random.random(), bottleneck_pressure=random.random(),
            accumulation_persistence=random.random(), positioning_asymmetry=random.random(),
            reflexivity_potential=random.random(), liquidity_score=random.random(),
            confidence_score=random.random(), catalyst_score=random.random(),
            crowding_risk=random.random() * 0.8, fragility_risk=random.random() * 0.6,
            narrative_exhaustion=random.random() * 0.5, propagation_strength=random.random(),
            narrative_strength=random.random(), volatility_quality=random.random()))

    out = rank(pool, regime="commodity_shock")
    s = out["summary"]
    print(f"IN {s['in']} → eliminated {s['eliminated']} → survived {s['survived']} → "
          f"visible {s['visible']} → TIER1 {s['tier1']} / TIER2 {s['tier2']} · say-no {s['say_no_ratio']}")
    print("\nTIER 1 — highest conviction (the only primary screen):")
    for c in out["tiers"]["highest_conviction"]:
        print(f"  {c.ticker:18} {c.market:9} score {c.score:6} · {causal_summary(c)['why_now']}")
    print("\nclean-vs-crowded check:")
    cb = next(c for c in pool if c.ticker == "CLEAN_BOTTLENECK")
    cm = next(c for c in pool if c.ticker == "CROWDED_MEGA")
    print(f"  CLEAN_BOTTLENECK score {cb.score} (tier {cb.tier}) vs CROWDED_MEGA score {cm.score} (tier {cm.tier})")
    assert cb.score > cm.score, "crowded/exhausted mega must rank below the clean uncrowded bottleneck"
    assert len(out['tiers']['highest_conviction']) <= TIER1_MAX
    assert s['eliminated'] > 0, "engine must be able to say NO"
    print("\nOK — competitive engine says NO and ranks asymmetry over crowded beta.")
