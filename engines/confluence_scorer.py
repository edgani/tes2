"""engines/confluence_scorer.py — Regime-Aware Multi-Engine Confluence Scorer (ELEVATION v1)

WHY THIS EXISTS
---------------
Every engine in this system emits in ISOLATION: gip → quad, risk_range → bands,
gex → gamma regime, vanna/charm → flow bias, sizing → bps. Nothing fused them.
The market pages ("tickers per market") and Alpha Center ranked tickers on a single
dimension (mostly risk-range quality), so a name could rank high while the MACRO
regime said AVOID, or while dealer gamma said "crash-prone — don't be long."

This module is the connective tissue. It scores any ticker by stacking the 5 layers
from the methodology research as a CONFLUENCE with HARD VETOES — multiplicative
gating, NOT a weighted sum. The distinction is the whole point:

    weighted-sum:  a strong GEX signal can OUTVOTE a quad AVOID  → bad
    gating/veto:   quad AVOID = 0, full stop, regardless of everything else → correct

LAYERS (each gates the next)
  1. REGIME  (macro, slow)   — quad-fit of the ticker (structural anchor + monthly tilt)
  2. STRUCTURE (flow, medium)— GEX regime: positive=mean-revert-supportive,
                               deep-negative+high-VIX = crash gate (veto longs)
  3. TIMING  (fast)          — risk-range action/quality (BUY_DIP@LRR best, TRR=trim)
  4. OVERLAYS (veto/tilt)    — Keith TRADE bearish = veto; vanna AVOID_LONG = haircut;
                               charm = directional tilt
  5. SIZE                    — hedgeye_position_sizing (VIX bucket × fit × conviction,
                               6% envelope)

Consumers: market_page_base (rank a market's universe) and alpha_center_curator
(rank the curated bottleneck universe). Both call rank_universe().
"""
from __future__ import annotations
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from engines.hedgeye_position_sizing import get_quad_fit, calculate_position_size
except Exception:  # pragma: no cover - defensive import
    def get_quad_fit(ticker, quad):  # type: ignore
        return "NEUTRAL"

    def calculate_position_size(*a, **k):  # type: ignore
        return {"bps": 0, "blocked": False, "tier": "❌ NONE"}

# ── layer scoring tables ────────────────────────────────────────────────────
_FIT_SCORE = {"GREAT": 1.00, "GOOD": 0.70, "NEUTRAL": 0.40, "BAD": 0.15, "AVOID": 0.0}
_GEX_MULT = {"DEEP_POSITIVE": 1.00, "POSITIVE": 0.90, "NEGATIVE": 0.60,
             "DEEP_NEGATIVE": 0.30, "TRANSITION": 0.75, "UNKNOWN": 0.80}
# risk-range action → timing score (for a LONG thesis)
_ACTION_LONG = {"BUY_DIP": 1.00, "ADD": 0.85, "HOLD": 0.45, "WATCH": 0.35,
                "COVER": 0.30, "TRIM": 0.20, "TRIM_RIP": 0.05, "SHORT_RIP": 0.0}
# for a SHORT thesis, mirror
_ACTION_SHORT = {"SHORT_RIP": 1.00, "TRIM_RIP": 0.85, "TRIM": 0.55, "WATCH": 0.35,
                 "HOLD": 0.35, "ADD": 0.15, "BUY_DIP": 0.0, "COVER": 0.25}
_QUALITY_BONUS = {"A+": 0.12, "A": 0.08, "B": 0.03, "short_A+": 0.12, "short_A": 0.08,
                  "short_B": 0.03, "C": 0.0}


def _safe(d: Optional[Dict], *keys, default=None):
    cur = d or {}
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, default if k == keys[-1] else {})
    return cur if cur is not None else default


def score_ticker(
    ticker: str,
    quad_struct: str,
    quad_monthly: str,
    vix: float,
    rr: Optional[Dict] = None,
    gex: Optional[Dict] = None,
    vanna: Optional[Dict] = None,
    charm: Optional[Dict] = None,
    keith: Optional[Dict] = None,
    conviction: int = 5,
    current_position_bps: int = 0,
) -> Dict:
    """Score one ticker across the 5 confluence layers. Returns a dict with the
    final 0-100 score, direction, per-layer breakdown, vetoes, and recommended size.
    Any layer with no data degrades gracefully (neutral) and is flagged.
    """
    gates: List[str] = []
    vetoes: List[str] = []

    # ── 1. REGIME GATE ──────────────────────────────────────────────────────
    fit_s = get_quad_fit(ticker, quad_struct)
    fit_m = get_quad_fit(ticker, quad_monthly)
    regime = 0.70 * _FIT_SCORE.get(fit_s, 0.4) + 0.30 * _FIT_SCORE.get(fit_m, 0.4)
    gates.append(f"regime {fit_s}/{fit_m}→{regime:.2f}")

    # direction bias from the macro regime
    if fit_s in ("GREAT", "GOOD") or regime >= 0.55:
        direction = "LONG"
    elif fit_s in ("BAD", "AVOID"):
        direction = "SHORT"
    else:
        direction = "NEUTRAL"

    # hard veto: structurally AVOID → excluded entirely
    if fit_s == "AVOID":
        vetoes.append(f"quad AVOID in structural {quad_struct}")
        return _result(ticker, 0.0, "AVOID", regime, 0.0, 0.0, 1.0,
                       gates, vetoes, direction, size=None)

    # ── 2. STRUCTURE GATE (dealer gamma) ─────────────────────────────────────
    gex_regime = _safe(gex, "regime", default="UNKNOWN")
    structure = _GEX_MULT.get(gex_regime, 0.80)
    if gex is None:
        gates.append("structure UNKNOWN (no GEX)→0.80")
    else:
        gates.append(f"structure {gex_regime}→{structure:.2f}")
    # crash gate: deep-negative gamma + f-bucket VIX → don't be long into a cascade
    if direction == "LONG" and gex_regime == "DEEP_NEGATIVE" and vix >= 29:
        vetoes.append("crash gate: deep-negative gamma + VIX≥29")
        return _result(ticker, 0.0, "AVOID", regime, structure, 0.0, 1.0,
                       gates, vetoes, direction, size=None)

    # ── 3. TIMING (risk-range entry quality) ─────────────────────────────────
    action = _safe(rr, "signals", "action", default=None) or _safe(rr, "action", default="HOLD")
    quality = _safe(rr, "signals", "quality", default=None) or _safe(rr, "quality", default="C")
    table = _ACTION_LONG if direction != "SHORT" else _ACTION_SHORT
    timing = table.get(action, 0.40)
    timing = min(1.0, timing + _QUALITY_BONUS.get(quality, 0.0))
    if rr is None:
        gates.append("timing HOLD (no RR)→0.40")
    else:
        gates.append(f"timing {action}/{quality}→{timing:.2f}")

    # ── 4. OVERLAYS (veto / tilt) ────────────────────────────────────────────
    overlay = 1.0
    keith_trade = _safe(keith, "TRADE", default=None) or _safe(keith, "trade", default=None)
    if isinstance(keith_trade, str):
        if keith_trade.upper() == "BEARISH" and direction == "LONG":
            vetoes.append("Keith TRADE BEARISH blocks long")
            return _result(ticker, 0.0, "AVOID", regime, structure, timing, overlay,
                           gates, vetoes, direction, size=None)
        if keith_trade.upper() == "BULLISH" and direction == "LONG":
            overlay *= 1.10
            gates.append("Keith TRADE BULLISH +10%")
    vanna_sig = _safe(vanna, "signal", default="NEUTRAL")
    if vanna_sig == "AVOID_LONG" and direction == "LONG":
        overlay *= 0.70
        gates.append("vanna AVOID_LONG −30%")
    elif vanna_sig == "NEVER_SHORT" and direction == "LONG":
        overlay *= 1.08
        gates.append("vanna NEVER_SHORT +8%")
    charm_sig = _safe(charm, "signal", default="NEUTRAL")
    if charm_sig in ("BULLISH_BIAS", "NEVER_SHORT") and direction == "LONG":
        overlay *= 1.05
    elif charm_sig in ("BEARISH_BIAS", "AVOID_LONG") and direction == "LONG":
        overlay *= 0.92

    # ── composite (multiplicative gating) ────────────────────────────────────
    score = round(regime * structure * timing * overlay * 100.0, 1)

    # ── 5. SIZE ──────────────────────────────────────────────────────────────
    try:
        size = calculate_position_size(ticker, quad_struct, vix, conviction=conviction,
                                        rr_data=rr, keith_signal=keith,
                                        is_breakout=(action == "ADD" and quality in ("A+", "A")),
                                        current_position_bps=current_position_bps)
    except Exception as e:  # pragma: no cover
        logger.debug(f"sizing failed for {ticker}: {e}")
        size = None

    return _result(ticker, score, direction, regime, structure, timing, overlay,
                   gates, vetoes, direction, size=size)


def _result(ticker, score, verdict, regime, structure, timing, overlay,
            gates, vetoes, direction, size):
    grade = ("A+" if score >= 70 else "A" if score >= 55 else "B" if score >= 40
             else "C" if score >= 25 else "D")
    return {
        "ticker": ticker,
        "score": score,
        "grade": grade,
        "verdict": verdict,          # LONG / SHORT / NEUTRAL / AVOID
        "direction": direction,
        "vetoed": bool(vetoes),
        "layers": {"regime": round(regime, 3), "structure": round(structure, 3),
                   "timing": round(timing, 3), "overlay": round(overlay, 3)},
        "gates": gates,
        "vetoes": vetoes,
        "size": size,
    }


def rank_universe(
    tickers: List[str],
    quad_struct: str,
    quad_monthly: str,
    vix: float,
    rr_map: Optional[Dict[str, Dict]] = None,
    gex_map: Optional[Dict[str, Dict]] = None,
    vanna_map: Optional[Dict[str, Dict]] = None,
    charm_map: Optional[Dict[str, Dict]] = None,
    keith_map: Optional[Dict[str, Dict]] = None,
    convictions: Optional[Dict[str, int]] = None,
    positions: Optional[Dict[str, int]] = None,
    include_vetoed: bool = False,
    top_n: Optional[int] = None,
) -> List[Dict]:
    """Score + rank a universe. Used by market pages (per-market universe) and by
    Alpha Center (curated bottleneck universe). Vetoed names are excluded by default.
    """
    rr_map = rr_map or {}; gex_map = gex_map or {}
    vanna_map = vanna_map or {}; charm_map = charm_map or {}
    keith_map = keith_map or {}; convictions = convictions or {}; positions = positions or {}

    scored = []
    for t in (tickers or []):
        try:
            r = score_ticker(
                t, quad_struct, quad_monthly, vix,
                rr=rr_map.get(t), gex=gex_map.get(t), vanna=vanna_map.get(t),
                charm=charm_map.get(t), keith=keith_map.get(t),
                conviction=convictions.get(t, 5), current_position_bps=positions.get(t, 0),
            )
            scored.append(r)
        except Exception as e:  # pragma: no cover
            logger.debug(f"confluence score failed for {t}: {e}")

    if not include_vetoed:
        scored = [s for s in scored if not s["vetoed"]]
    scored.sort(key=lambda x: x["score"], reverse=True)
    if top_n:
        scored = scored[:top_n]
    return scored
