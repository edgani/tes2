"""engines/perspective_engine.py — Bias Guard / Perspektif (debiasing layer)

Embeds the cognitive-debiasing playbook (Kahneman & Tversky + the "consider-an-alternative"
literature) directly into the macro call, so the system argues AGAINST its own view instead
of only confirming it. For the current regime/transition it surfaces:
  • Steelman of the opposite (consider-an-alternative)
  • Outside view / base-rate framing (model confidence is a hypothesis, not a probability —
    especially while the weights are un-validated OOS)
  • Active-bias watchlist tuned to the current setup (confirmation, overconfidence, anchoring,
    recency, herding, loss-aversion/disposition)
  • Pre-mortem: the most likely reason this call FAILS

Pure reasoning over data the snapshot already has — no new fetch, no guessing.
"""
from __future__ import annotations
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_RISK_ON = {"Q1", "Q2"}   # growth-up quads → bullish risk lean
_NAME = {"Q1": "Goldilocks", "Q2": "Reflation", "Q3": "Stagflation", "Q4": "Deflation"}


def _g(obj, key, default=None):
    if obj is None:
        return default
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


def bias_guard(quad_explainer: Optional[Dict] = None, gip=None, vix=None) -> Dict:
    qe = quad_explainer or {}
    wig = qe.get("where_it_goes", {}) if isinstance(qe, dict) else {}
    struct_q = qe.get("structural_quad", _g(gip, "structural_quad", "Q3")) if isinstance(qe, dict) else "Q3"
    implied = wig.get("implied_next", struct_q)
    stage = wig.get("stage", "—")
    lean = "bullish" if implied in _RISK_ON else "defensive"
    opp = "defensive" if lean == "bullish" else "bullish"

    # ── steelman the opposite (consider-an-alternative) ──
    if lean == "bullish":
        steelman = (f"Bear case for the {struct_q}->{implied} ({_NAME.get(implied,'')}) call: the "
                    f"leading horizon is a head-fake. Nominal strength ≠ real growth; if the energy/"
                    f"liquidity impulse fades, structural {struct_q} reasserts and the 'reflation' longs "
                    f"(energy/cyclicals/EM) give back fast. What would you see first if you're wrong? "
                    f"Breadth narrowing, credit spreads widening, the monthly quad slipping back.")
    else:
        steelman = (f"Bull case against the defensive {struct_q}/{implied} call: disinflation + policy "
                    f"easing can re-rate risk faster than the structural read implies. If growth "
                    f"surprises up, defensives/bonds underperform and you miss the turn. What would you "
                    f"see first if you're wrong? Cyclicals leading, new highs in breadth, monthly quad firming.")

    # ── active-bias watchlist (context-tuned) ──
    biases = [
        {"bias": "Confirmation", "why": f"you lean {lean} on the {implied} call — you'll over-weight data that fits it",
         "check": "actively log the 2 strongest data points AGAINST your view before adding risk"},
        {"bias": "Overconfidence", "why": "the quad probabilities come from weights not yet validated OOS",
         "check": "treat the model's confidence as a hypothesis; size to a base rate, not to the %"},
        {"bias": "Recency", "why": "the latest move/headline is shaping the read more than it should",
         "check": "would this call survive if you only saw the 6-month trend, not the last 2 weeks?"},
        {"bias": "Herding", "why": f"if {implied} is the consensus trade, the edge is already crowded",
         "check": "cross-check positioning/COT + the crowding caveat in the Quad Decoder"},
        {"bias": "Anchoring", "why": "entry levels / round numbers anchor your targets and stops",
         "check": "set stops on structure (TRR/LRR), not on your cost basis"},
        {"bias": "Loss-aversion / disposition", "why": "tendency to hold losers and cut winners early",
         "check": "rule-based exits; let the TRR/LRR + stage decide, not the P&L feeling"},
    ]
    if vix and vix > 28:
        biases.insert(0, {"bias": "Panic / capitulation", "why": f"VIX {vix:.0f} — fear distorts judgment",
                          "check": "slow down; pre-committed rules over in-the-moment reactions"})

    # ── pre-mortem ──
    if lean == "bullish":
        premortem = (f"Pre-mortem — if positioning for {implied} loses money in 3 months, the likeliest "
                     f"cause is: (1) the energy/inflation impulse reverses and growth was nominal not real, "
                     f"(2) a net-liquidity drain sinks all risk regardless of quad, or (3) the transition "
                     f"was never RIPE — structural {struct_q} held the whole time.")
    else:
        premortem = (f"Pre-mortem — if the defensive {struct_q} stance loses money in 3 months, the likeliest "
                     f"cause is: (1) disinflation + easing re-rated risk faster than expected, (2) you "
                     f"anchored on the bear case and ignored the monthly quad firming, or (3) defensives "
                     f"were already crowded.")

    return {
        "ok": True,
        "current_lean": lean, "opposite": opp, "stage": stage,
        "steelman": steelman,
        "outside_view": ("Model confidence is NOT a calibrated probability while weights are un-validated. "
                         "Anchor sizing to base rates and risk limits; let run_validation.py + the forward "
                         "log tell you how much to trust the score."),
        "active_biases": biases,
        "pre_mortem": premortem,
        "note": "Debiasing = take the outside view, steelman the opposite, watch the named biases (Kahneman/Tversky).",
    }
