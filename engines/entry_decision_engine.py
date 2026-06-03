"""engines/entry_decision_engine.py — Multi-Signal Entry Decision v39

FIX v39:
 1. STOP LEVEL: Now reads risk_range["stop"] directly instead of hardcoding
    lrr*0.97. Ensures consistency with Risk Range Engine (1.5% buffer).
 2. TARGET1/TARGET2: Reads from risk_range["target1"]/["target2"] directly.
 3. Added options-based entry refinement (GEX walls, max pain, skew).
 4. Added conviction scoring from walkforward backtest metadata.
"""
from __future__ import annotations
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

def decide_entry(
    ticker: str,
    px: float,
    composite_signal: Optional[Dict] = None,
    risk_range: Optional[Dict] = None,
    gamma_data: Optional[Dict] = None,
    karsan: Optional[Dict] = None,
    thought_process: Optional[Dict] = None,
    quad: str = "Q1",
    options_data: Optional[Dict] = None,
) -> Dict:
    """Multi-signal entry decision with options-aware refinement."""
    out = {
        "ticker": ticker, "px": px, "action": "AVOID", "direction": "NEUTRAL",
        "entry_level": None, "stop_level": None, "target_1": None, "target_2": None,
        "wait_trigger": None, "conviction": 0, "rationale": [],
        "contradictions": [], "signals_aligned": 0, "signals_total": 6,
        "options_refinement": {},
    }

    if not composite_signal:
        out["rationale"].append("No composite signal")
        return out

    direction = composite_signal.get("direction", "NEUTRAL")
    conf = composite_signal.get("confidence", 0) or 0

    if direction in ("NEUTRAL", "AVOID"):
        out["rationale"].append(f"Composite says {direction} — no edge")
        return out
    if conf < 0.30:
        out["rationale"].append(f"Composite confidence {conf:.0%} too low")
        return out

    out["direction"] = direction
    out["conviction"] = int(conf * 50)
    out["rationale"].append(f"✓ Composite {direction} ({conf:.0%} confidence)")
    out["signals_aligned"] += 1

    # ── Layer 1: Risk Range (LRR/TRR) ──
    rr = risk_range or {}
    trade = rr.get("trade", {}) or {}
    lrr = trade.get("lrr")
    trr = trade.get("trr")
    # v39 FIX: Read stop/target directly from risk_range engine
    rr_stop = rr.get("stop")
    rr_target1 = rr.get("target1")
    rr_target2 = rr.get("target2")
    rr_entry = rr.get("entry")

    range_position = None
    if lrr and trr and trr > lrr:
        range_position = (px - lrr) / max(trr - lrr, 0.001)

    # ── Layer 2: Gamma walls ──
    gamma_ok = gamma_data and gamma_data.get("ok")
    call_wall = (gamma_data or {}).get("call_wall")
    put_wall = (gamma_data or {}).get("put_wall")
    max_pain = (gamma_data or {}).get("max_pain")
    gamma_regime = (gamma_data or {}).get("regime", "")

    # ── Layer 3: Options data (GEX, skew, vanna) ──
    opts = options_data or {}
    gex_regime = opts.get("gex", {}).get("regime", "")
    iv_skew = opts.get("iv_skew", {}).get("skew", 0)
    put_call_ratio = opts.get("put_call_ratio")
    expected_move_pct = opts.get("expected_move_pct")

    # ── Layer 4: Karsan setup ──
    karsan_setup = (karsan or {}).get("karsan_setup")
    karsan_vol_regime = (karsan or {}).get("vol_regime")

    # ── Layer 5: Thought process ──
    methodology_score = (thought_process or {}).get("thesis_score", 0) or 0
    n_frameworks = (thought_process or {}).get("n_matches", 0) or 0

    # ═══════════════════════════════════════════════════════════════
    # DECISION TREE for LONG
    # ═══════════════════════════════════════════════════════════════
    if direction == "LONG":
        if range_position is not None:
            if range_position <= 0.30:
                out["entry_level"] = round(rr_entry or px, 2)
                out["rationale"].append(f"✓ Price at Trade Low zone (pos {range_position:.0%})")
                out["conviction"] += 15
                out["signals_aligned"] += 1
            elif range_position >= 0.70:
                out["action"] = "WAIT"
                out["entry_level"] = round(lrr, 2)
                out["wait_trigger"] = f"Wait for pullback to Trade Low ${lrr:.2f}"
                out["rationale"].append(f"⏳ Price at Trade High (pos {range_position:.0%}) — too late")
                out["contradictions"].append(f"Range position {range_position:.0%} — chasing risk")
            else:
                out["entry_level"] = round(rr_entry or px, 2)
                out["rationale"].append(f"Price mid-range (pos {range_position:.0%}) — marginal")
        else:
            out["entry_level"] = round(rr_entry or px, 2)
            out["rationale"].append("No Risk Range data — entry at market")

        # v39 FIX: Use risk_range stop/target directly
        if rr_stop is not None:
            out["stop_level"] = round(rr_stop, 2)
        elif lrr:
            out["stop_level"] = round(lrr * 0.985, 2)
        if rr_target1 is not None:
            out["target_1"] = round(rr_target1, 2)
        elif trr:
            out["target_1"] = round(trr, 2)
        if rr_target2 is not None:
            out["target_2"] = round(rr_target2, 2)
        elif trr and lrr:
            out["target_2"] = round(px + (trr - lrr) * 1.5, 2)

        # ── Options-based stop refinement ──
        if put_wall and put_wall < px:
            gap = (px - put_wall) / px
            if gap < 0.05:
                out["rationale"].append(f"✓ Put Wall ${put_wall:.2f} below — dealer support")
                out["conviction"] += 10
                out["signals_aligned"] += 1
                # Better stop: put_wall if it's tighter than current stop
                if put_wall > (out["stop_level"] or 0):
                    out["stop_level"] = round(put_wall * 0.98, 2)
                    out["options_refinement"]["stop_adjusted_by"] = "put_wall"
        if call_wall and call_wall > px:
            gap_up = (call_wall - px) / px
            if gap_up < 0.03:
                out["contradictions"].append(f"⚠️ Call Wall ${call_wall:.2f} just above — resistance")
            else:
                out["target_1"] = round(min(out["target_1"] or call_wall, call_wall), 2)
        if max_pain and abs(max_pain - px) / px < 0.02:
            out["rationale"].append(f"📍 At Max Pain ${max_pain:.2f} — magnet level")
        if "NEGATIVE" in gamma_regime.upper() and direction == "LONG":
            out["rationale"].append("⚡ Negative gamma — trend amplification favors LONG breakout")
            out["conviction"] += 8

        # ── Skew confirmation ──
        if iv_skew and iv_skew > 0.05:
            out["rationale"].append(f"📈 Put skew rich ({iv_skew:+.2f}) — fear priced in = contrarian LONG edge")
            out["conviction"] += 5
        elif iv_skew and iv_skew < -0.05:
            out["contradictions"].append(f"📉 Call skew rich ({iv_skew:+.2f}) — euphoria = caution")

        # ── Karsan confirmation ──
        if karsan_setup:
            if "SQUEEZE_SETUP" in karsan_setup:
                out["rationale"].append("🚀 Karsan SQUEEZE — two-sided skew + dealer short gamma")
                out["conviction"] += 15
                out["signals_aligned"] += 1
            elif "BUY_CONVEXITY" in karsan_setup:
                out["rationale"].append("📈 Karsan: BUY convexity — IV cheap")
                out["conviction"] += 10
                out["signals_aligned"] += 1
            elif "SELL_PREMIUM" in karsan_setup:
                out["contradictions"].append("⚠️ Karsan: SELL premium — range-bound expected")

        # ── Methodology confirmation ──
        if methodology_score >= 70:
            out["rationale"].append(f"✓ Methodology consensus {methodology_score:.0f}/100 ({n_frameworks} frameworks)")
            out["conviction"] += 20
            out["signals_aligned"] += 1
        elif methodology_score >= 50:
            out["conviction"] += 10
        else:
            out["contradictions"].append(f"⚠️ Methodology weak {methodology_score:.0f}/100")

    # ═══════════════════════════════════════════════════════════════
    # DECISION TREE for SHORT (mirror)
    # ═══════════════════════════════════════════════════════════════
    elif direction == "SHORT":
        if range_position is not None:
            if range_position >= 0.70:
                out["entry_level"] = round(rr_entry or px, 2)
                out["rationale"].append(f"✓ Price at Trade High (pos {range_position:.0%}) — fade rally")
                out["conviction"] += 15
                out["signals_aligned"] += 1
            elif range_position <= 0.30:
                out["action"] = "WAIT"
                out["entry_level"] = round(trr, 2) if trr else None
                if trr:
                    out["wait_trigger"] = f"Wait for rally to Trade High ${trr:.2f}"
                out["rationale"].append(f"⏳ Price at Trade Low — premature short")
                out["contradictions"].append(f"Range position {range_position:.0%} — better to wait")
            else:
                out["entry_level"] = round(rr_entry or px, 2)
                out["rationale"].append(f"Price mid-range — marginal short")
        else:
            out["entry_level"] = round(rr_entry or px, 2)

        if rr_stop is not None:
            out["stop_level"] = round(rr_stop, 2)
        elif trr:
            out["stop_level"] = round(trr * 1.015, 2)
        if rr_target1 is not None:
            out["target_1"] = round(rr_target1, 2)
        elif lrr:
            out["target_1"] = round(lrr, 2)
        if rr_target2 is not None:
            out["target_2"] = round(rr_target2, 2)
        elif trr and lrr:
            out["target_2"] = round(px - (trr - lrr) * 1.5, 2)

        if gamma_ok:
            if call_wall and call_wall > px:
                gap = (call_wall - px) / px
                if gap < 0.05:
                    out["rationale"].append(f"✓ Call Wall ${call_wall:.2f} above — dealer resistance")
                    out["conviction"] += 10
                    out["signals_aligned"] += 1
                    if call_wall > (out["stop_level"] or 0):
                        out["stop_level"] = round(call_wall * 1.02, 2)
                        out["options_refinement"]["stop_adjusted_by"] = "call_wall"
            if put_wall and put_wall < px:
                gap_down = (px - put_wall) / px
                if gap_down < 0.03:
                    out["contradictions"].append(f"⚠️ Put Wall ${put_wall:.2f} below — support")
                else:
                    out["target_1"] = round(max(out["target_1"] or put_wall, put_wall), 2)
            if "NEGATIVE" in gamma_regime.upper():
                out["rationale"].append("⚡ Negative gamma — breakdown amplified")
                out["conviction"] += 8

        if methodology_score >= 70:
            out["rationale"].append(f"✓ Methodology bearish {methodology_score:.0f}/100")
            out["conviction"] += 20
            out["signals_aligned"] += 1

    # ═══════════════════════════════════════════════════════════════
    # FINAL ACTION
    # ═══════════════════════════════════════════════════════════════
    if out["action"] == "WAIT":
        pass
    elif out["signals_aligned"] >= 3 and out["conviction"] >= 60:
        out["action"] = "ENTRY_NOW"
        out["rationale"].insert(0, f"🎯 ENTRY_NOW — {out['signals_aligned']}/6 signals, conviction {out['conviction']}")
    elif out["signals_aligned"] >= 2 and out["conviction"] >= 40:
        out["action"] = "WAIT"
        if not out["wait_trigger"]:
            if direction == "LONG" and lrr:
                out["wait_trigger"] = f"Wait for stronger setup or pullback to ${lrr:.2f}"
            elif direction == "SHORT" and trr:
                out["wait_trigger"] = f"Wait for rally to ${trr:.2f}"
            else:
                out["wait_trigger"] = "Wait for more signal confirmation"
        out["rationale"].insert(0, f"⏳ WAIT — {out['signals_aligned']}/6 signals, conviction {out['conviction']}")
    else:
        out["action"] = "AVOID"
        out["rationale"].insert(0, f"🚫 AVOID — {out['signals_aligned']}/6 signals, conviction {out['conviction']}")

    # Compute R:R
    if out["entry_level"] and out["stop_level"] and out["target_1"]:
        if direction == "LONG":
            risk = abs(out["entry_level"] - out["stop_level"])
            reward = abs(out["target_1"] - out["entry_level"])
        else:
            risk = abs(out["stop_level"] - out["entry_level"])
            reward = abs(out["entry_level"] - out["target_1"])
        if risk > 0:
            out["risk_reward"] = round(reward / risk, 2)

    out["conviction"] = min(100, out["conviction"])
    return out


def batch_decide(snap: Dict, tickers: list = None) -> Dict:
    out = {
        "entry_now_longs": [], "entry_now_shorts": [],
        "wait_longs": [], "wait_shorts": [], "avoid": [],
    }
    composite_all = snap.get("composite_signals", {}) or {}
    rr_all = (snap.get("risk_ranges", {}) or {}).get("asset_ranges", {}) or {}
    gamma_all = snap.get("gamma_data", {}) or {}
    karsan_all = (snap.get("karsan_scanner", {}) or {}).get("per_ticker", {}) or {}
    thought_all = snap.get("thought_process", {}) or {}
    quad = (snap.get("gip_v10", {}) or {}).get("structural_quad", "Q1")
    options_all = snap.get("options_data", {}) or {}

    tickers_to_check = tickers or list(composite_all.keys())
    for ticker in tickers_to_check:
        rr = rr_all.get(ticker, {})
        px = rr.get("px") or 0
        if px <= 0:
            continue
        decision = decide_entry(
            ticker, px,
            composite_signal=composite_all.get(ticker, {}),
            risk_range=rr,
            gamma_data=gamma_all.get(ticker, {}),
            karsan=karsan_all.get(ticker, {}),
            thought_process=thought_all.get(ticker, {}),
            quad=quad,
            options_data=options_all.get(ticker, {}),
        )
        if decision["action"] == "ENTRY_NOW":
            if decision["direction"] == "LONG":
                out["entry_now_longs"].append(decision)
            else:
                out["entry_now_shorts"].append(decision)
        elif decision["action"] == "WAIT":
            if decision["direction"] == "LONG":
                out["wait_longs"].append(decision)
            else:
                out["wait_shorts"].append(decision)
        else:
            out["avoid"].append(decision)

    for k in out:
        out[k].sort(key=lambda x: x["conviction"], reverse=True)
    return out
