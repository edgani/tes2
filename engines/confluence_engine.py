"""
confluence_engine.py — reusable multi-timeframe + cross-signal confluence for ANY market tab.

Edward's requirement: distinguish a 1–2% scalp from a "naik & panjang" position move. A durable trend
needs the duration bands (TRADE/TREND/TAIL from Risk Range) to AGREE *and* at least one independent
driver (macro/FX driver, bandar accumulation, or on-chain) to confirm — not a single-timeframe blip.

Inputs are all sign-coded {-1 bearish, 0 neutral, +1 bullish}; defensive (neutral on missing).
Pure-logic, unit-tested in __main__.
"""
from __future__ import annotations
from typing import Optional


def _sign(x) -> int:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0
    if v != v:
        return 0
    return 1 if v > 0 else -1 if v < 0 else 0


def multi_tf_confluence(trade_phase=0, trend_phase=0, tail_phase=0, *,
                        driver_bias=0, bandar_bias=0, onchain_bias=0, momentum=None) -> dict:
    """Unified confluence verdict.
      - TRADE/TREND/TAIL: duration-band phases from Risk Range
      - driver_bias: macro/FX/commodity driver (gold/oil/GSR/DXY) sign
      - bandar_bias: IHSG accumulation/distribution sign (signal_adjustment > 0 → +1)
      - onchain_bias: crypto on-chain composite verdict sign
      - momentum: optional recent ROC (for tie-break / scalp gating)
    Returns {conviction, side, alignment_pct, tf_aligned, cross_confirm, hold, reason, layers}."""
    tfs = {"TRADE": _sign(trade_phase), "TREND": _sign(trend_phase), "TAIL": _sign(tail_phase)}
    cross = {"driver": _sign(driver_bias), "bandar": _sign(bandar_bias), "onchain": _sign(onchain_bias)}

    tf_vals = [v for v in tfs.values() if v != 0]
    tf_net = sum(tfs.values())
    all_tf_bull = all(v > 0 for v in tfs.values())
    all_tf_bear = all(v < 0 for v in tfs.values())
    tf_aligned = all_tf_bull or all_tf_bear

    side_sign = 1 if tf_net > 0 else -1 if tf_net < 0 else 0
    cross_present = [v for v in cross.values() if v != 0]
    cross_confirm = sum(1 for v in cross_present if v == side_sign) if side_sign else 0
    cross_oppose = sum(1 for v in cross_present if v == -side_sign) if side_sign else 0

    present = tf_vals + cross_present
    alignment_pct = round(100.0 * abs(sum(tfs.values()) + sum(cross.values())) / max(1, len(present)), 0) if present else 0.0

    side = "LONG" if side_sign > 0 else "SHORT" if side_sign < 0 else "FLAT"

    # ── conviction ladder ──
    if tf_aligned and cross_confirm >= 1 and cross_oppose == 0:
        conviction, hold = "FULL", "position trade — target trend/tail (puluhan–ratusan %)"
        reason = f"3 TF ({side}) align + {cross_confirm} driver konfirmasi, 0 lawan"
    elif tf_aligned and cross_oppose == 0:
        conviction, hold = "STRONG", "swing — ride TREND, trail stop di TAIL band"
        reason = f"3 TF ({side}) align, driver netral"
    elif tf_aligned and cross_oppose >= 1:
        conviction, hold = "PARTIAL", "hati-hati — TF align tapi driver lawan; scalp/kecilin size"
        reason = f"3 TF ({side}) align TAPI {cross_oppose} driver lawan arah"
    else:
        bull = sum(1 for v in tfs.values() if v > 0)
        bear = sum(1 for v in tfs.values() if v < 0)
        if max(bull, bear) >= 2:
            sd = "LONG" if bull > bear else "SHORT"
            conviction, side, hold = "PARTIAL", sd, "scalp/swing 1–3% — TF belum align penuh"
            reason = f"{max(bull,bear)}/3 TF {sd.lower()} (TAIL/TREND/TRADE campur)"
        else:
            conviction, side, hold = "NONE", "FLAT", "tunggu — gak ada alignment"
            reason = "TF & driver gak searah"

    # momentum sanity for FULL/STRONG longs/shorts
    m = _sign(momentum) if momentum is not None else 0
    if conviction in ("FULL", "STRONG") and m != 0 and side_sign != 0 and m != side_sign:
        reason += f" · ⚠️ momentum jangka pendek lawan ({'+' if m>0 else '−'}) — entry sabar"

    return {"conviction": conviction, "side": side, "alignment_pct": alignment_pct,
            "tf_aligned": tf_aligned, "cross_confirm": cross_confirm, "cross_oppose": cross_oppose,
            "hold": hold, "reason": reason, "layers": {"tf": tfs, "cross": cross}}


if __name__ == "__main__":
    print("=== SELF-TEST confluence_engine ===")
    # FULL: all TF bull + driver + bandar confirm
    f = multi_tf_confluence(1, 1, 1, driver_bias=1, bandar_bias=1)
    assert f["conviction"] == "FULL" and f["side"] == "LONG", f
    print("✓ FULL →", f["alignment_pct"], "%", "|", f["hold"])
    # STRONG: all TF bull, no cross
    s = multi_tf_confluence(1, 1, 1)
    assert s["conviction"] == "STRONG", s
    print("✓ STRONG")
    # PARTIAL w/ opposition: TF bull but driver bear
    p = multi_tf_confluence(1, 1, 1, driver_bias=-1)
    assert p["conviction"] == "PARTIAL" and p["cross_oppose"] == 1, p
    print("✓ PARTIAL (driver opposes)")
    # PARTIAL: 2/3 TF
    p2 = multi_tf_confluence(1, 1, -1)
    assert p2["conviction"] == "PARTIAL", p2
    print("✓ PARTIAL (2/3 TF)")
    # NONE
    n = multi_tf_confluence(1, -1, 0)
    assert n["conviction"] == "NONE", n
    print("✓ NONE")
    # short FULL
    sf = multi_tf_confluence(-1, -1, -1, onchain_bias=-1)
    assert sf["conviction"] == "FULL" and sf["side"] == "SHORT", sf
    print("✓ FULL SHORT")
    # momentum warning
    mw = multi_tf_confluence(1, 1, 1, driver_bias=1, momentum=-0.02)
    assert "momentum" in mw["reason"], mw
    print("✓ momentum warn")
    # defensive
    assert multi_tf_confluence()["conviction"] == "NONE"
    print("ALL TESTS PASSED ✅")
