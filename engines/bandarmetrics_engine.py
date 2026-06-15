"""engines/bandarmetrics_engine.py — Bandarmology indicators from OHLCV (v2: A/D-based)

v2 takes the bandarmetrics LOGIC (silent accumulation / distribution detection) but rebuilds the
core on battle-tested accumulation/distribution indicators instead of a fragile custom VWAP-delta:

  • A/D Line (ADL)  — cumulative Money-Flow-Volume (Close Location Value × Volume). The canonical
                      "is smart money accumulating?" line. Rises when closes print near highs on
                      volume even if price is flat/down (the real silent-accumulation footprint).
  • OBV             — On-Balance Volume (signed-volume accumulator), confirmation of ADL.
  • CMF             — Chaikin Money Flow (20d), bounded −1..+1: >0 buying pressure, <0 selling.
  • Divergence      — price-slope vs ADL-slope: price DOWN + ADL UP = bullish divergence (the
                      accumulation signal); price UP + ADL DOWN = bearish divergence (distribution).
  • DTE / Real DTE  — days-to-exit from average daily $-volume (how trapped the inventory is).
  • Volume Rotation — efficiency of transfer (green clean / yellow noise / red distribution).
  • Intensity       — ADL rate-of-change z-spikes (fires before price moves).
  • LPM             — kept (cumulative VWAP-delta, EMA) as a secondary line for continuity.
  • Phase + Score   — now driven by divergence + CMF + ADL slope (robust), not the noisy LPM.

HONEST CEILING: still the OHLCV approximation. The real bandarmetrics edge (foreign Type-F flow +
broker-summary clustering / nominee detection) needs IDX broker data the user does NOT have. And the
phase/score thresholds are heuristic until validated against real forward returns — see
validate_bandarmetrics.py. Requires OHLCV+Volume; returns {} if data insufficient.
"""
from __future__ import annotations
import logging
from typing import Dict

logger = logging.getLogger(__name__)


def _ema(s, span):
    return s.ewm(span=span, adjust=False).mean()


def _slope(s, n=20):
    """Normalized slope over n bars: (last - n-ago) / |n-ago| (robust to scale)."""
    try:
        a = float(s.dropna().iloc[-1]); b = float(s.dropna().iloc[-1 - n])
        return (a - b) / (abs(b) + 1e-9)
    except (IndexError, ValueError):
        return 0.0


def compute(df, vwap_win: int = 20, lpm_smooth: int = 20, adv_win: int = 60, cmf_win: int = 20,
            foreign=None) -> Dict:
    """df: DataFrame with Open, High, Low, Close, Volume (daily). Returns indicator dict."""
    import pandas as pd
    import numpy as np
    if df is None or len(df) < max(adv_win, 60):
        return {}
    try:
        o, h, l, c, v = (pd.to_numeric(df[k], errors="coerce")
                         for k in ("Open", "High", "Low", "Close", "Volume"))
    except (KeyError, TypeError):
        return {}
    if c.dropna().empty or v.fillna(0).sum() == 0:
        return {}

    typ = (h + l + c) / 3.0
    rng = (h - l).replace(0, np.nan)

    # ── Accumulation/Distribution Line (the core accumulation signal) ──
    clv = (((c - l) - (h - c)) / rng).clip(-1, 1).fillna(0)   # close location value
    mfv = clv * v                                             # money flow volume
    adl = mfv.cumsum()
    # ── OBV ──
    obv = (np.sign(c.diff().fillna(0)) * v).cumsum()
    # ── Chaikin Money Flow (bounded -1..1) ──
    cmf = (mfv.rolling(cmf_win).sum() / v.rolling(cmf_win).sum().replace(0, np.nan))

    # ── LPM (Liquidity Pressure Model) = Chaikin Accumulation/Distribution Line, EMA-smoothed.
    #    Calibrated to bandarmetrics' 4 reference tickers: BBCA shows price↓ while LPM↑ (accumulation
    #    divergence) = textbook A/D Line. So LPM = EMA(cumsum(CLV×Vol)) — volume-based, NOT ×price.
    vwap = (typ * v).rolling(vwap_win).sum() / v.rolling(vwap_win).sum().replace(0, np.nan)
    _mfv_value = clv * v * typ  # LPM FIX: value-based (x price), not volume-only
    lpm = _ema(_mfv_value.cumsum(), lpm_smooth)

    # ── DTE / Real DTE: |ADL| over average daily $-volume ──
    adv = (v * typ).rolling(adv_win).mean()
    # use ADL magnitude as the "inventory" proxy (more meaningful than LPM here)
    inv = adl.abs()
    dte = (inv / adv.replace(0, np.nan))
    real_dte = (inv / (adv.replace(0, np.nan) * 0.35))

    # ── Volume Rotation: efficiency of price transfer (RE doc #4) ──
    #    efficiency = |C-O| / (H-L) ∈ 0..1 (clean move vs churn) · signed by C-O · scaled by volume z.
    efficiency = ((c - o).abs() / rng).clip(0, 1).fillna(0)
    direction = np.sign(c - o)
    vol_z = ((v - v.rolling(20).mean()) / v.rolling(20).std().replace(0, np.nan))
    rot_score = direction * efficiency * vol_z.clip(-3, 3) / 3.0

    # ── Intensity: effort = Volume × |return|, z-scored, gated (RE doc #3) ──
    ret = (c - c.shift(1)).abs() / c.shift(1).replace(0, np.nan)
    effort = (v * ret).fillna(0)
    z = (effort - effort.rolling(20).mean()) / effort.rolling(20).std().replace(0, np.nan)
    intensity = z.where(z > 1.5, 0.0).fillna(0.0)

    def _last(s, d=0.0):
        try:
            x = float(s.dropna().iloc[-1]); return x if np.isfinite(x) else d
        except (IndexError, ValueError):
            return d

    price_slope = _slope(c, 20)
    adl_slope = _slope(adl, 20)
    obv_slope = _slope(obv, 20)
    cmf_now = _last(cmf)
    intensity_now = _last(intensity)
    rot_now = _last(rot_score)
    dte_now = _last(dte)
    price_chg_20 = price_slope

    # ── Divergence (the real accumulation/distribution tell) ──
    divergence = _divergence(price_slope, adl_slope)

    # ── phase + score (v2: divergence + CMF + ADL slope) ──
    phase = _phase_v2(divergence, cmf_now, adl_slope, intensity_now, price_chg_20)
    score = _score_v2(divergence, cmf_now, adl_slope, obv_slope, intensity_now, dte_now, phase)

    avgcost = _last(_ema(typ, 60))
    rot_tail = rot_score.dropna().tail(20)
    green = int((rot_tail > 0.15).sum()); red = int((rot_tail < -0.15).sum())
    yellow = int(len(rot_tail) - green - red)

    ignition = detect_ignition(df)
    ff = foreign_flow_metrics(foreign, price=c.dropna().tolist()) if foreign is not None else {"available": False}
    stealth = detect_stealth_accumulation(adl_slope, cmf_now, price_slope, ignition.get("ignition_score", 0), obv_slope)
    markup = estimate_markup_readiness(df, adv_win=adv_win)

    # normalized ADL for charting (z-score so multiple tickers comparable)
    adl_n = ((adl - adl.rolling(120).mean()) / adl.rolling(120).std().replace(0, np.nan)).fillna(0)

    idx = c.dropna().index[-252:]

    def _ser(s):
        return [round(float(x), 3) for x in s.reindex(idx).fillna(0).tolist()]

    return {
        "ok": True,
        # core A/D signals
        "adl_slope_20": round(adl_slope, 4), "adl_rising": adl_slope > 0,
        "obv_slope_20": round(obv_slope, 4),
        "cmf": round(cmf_now, 4), "cmf_state": "buying" if cmf_now > 0.05 else "selling" if cmf_now < -0.05 else "neutral",
        "divergence": divergence,
        # legacy/secondary
        "lpm": round(_last(lpm), 2), "lpm_slope_20": round(_slope(lpm, 20), 4),
        "dte": round(dte_now, 1), "real_dte": round(_last(real_dte), 1),
        "intensity": round(intensity_now, 2), "intensity_firing": intensity_now > 0,
        "rotation": ("green" if rot_now > 0.15 else "red" if rot_now < -0.15 else "yellow"),
        "rotation_score": round(rot_now, 3),
        "rotation_dist": {"green": green, "yellow": yellow, "red": red},
        "price_slope_20": round(price_slope, 4),
        "phase": phase, "score": int(round(score)),
        "avgcost": round(avgcost, 2),
        "ignition": ignition, "foreign_flow": ff, "stealth_accumulation": stealth,
        "markup_readiness": markup,
        "series": {
            "index": [str(x)[:10] for x in idx],
            "price": _ser(c), "open": _ser(o), "high": _ser(h), "low": _ser(l),
            "volume": _ser(v), "rotation": _ser(rot_score),
            "adl": _ser(adl_n), "cmf": _ser(cmf),
            "obv": _ser(((obv - obv.rolling(120).mean()) / obv.rolling(120).std().replace(0, np.nan))),
            "intensity": _ser(intensity), "lpm": _ser(lpm),
        },
        "note": "OHLCV approximation (A/D-based) — foreign-flow + broker clustering need IDX data (unavailable); "
                "phase/score unvalidated until validate_bandarmetrics.py is run on real forward returns.",
    }


def _divergence(price_slope, adl_slope):
    """price vs ADL slope sign → divergence regime."""
    ps, ads = price_slope, adl_slope
    if ps < -0.005 and ads > 0.01:
        return "BULLISH_DIV"      # price down, accumulation up → silent accumulation
    if ps > 0.005 and ads < -0.01:
        return "BEARISH_DIV"      # price up, distribution → smart money exiting into strength
    if ps > 0.005 and ads > 0.005:
        return "ALIGNED_UP"       # trend confirmed up
    if ps < -0.005 and ads < -0.005:
        return "ALIGNED_DOWN"     # trend confirmed down
    return "FLAT"


def _phase_v2(divergence, cmf, adl_slope, intensity, price_chg):
    if divergence == "BULLISH_DIV" or (adl_slope > 0 and cmf > 0.05 and price_chg < 0.05):
        return "ACCUMULATION"
    if divergence == "ALIGNED_UP" and intensity > 0:
        return "MARKUP"
    if divergence == "ALIGNED_UP":
        return "MARKUP" if cmf > 0 else "NEUTRAL"
    if divergence == "BEARISH_DIV" or (adl_slope < 0 and cmf < -0.05 and price_chg > -0.05):
        return "DISTRIBUTION"
    if divergence == "ALIGNED_DOWN":
        return "MARKDOWN"
    return "NEUTRAL"


def _score_v2(divergence, cmf, adl_slope, obv_slope, intensity, dte, phase):
    """0-100, accumulation-positive. Driven by divergence + CMF + A/D + OBV confirmation."""
    s = 50.0
    s += {"BULLISH_DIV": 20, "ALIGNED_UP": 12, "FLAT": 0, "ALIGNED_DOWN": -12, "BEARISH_DIV": -20}.get(divergence, 0)
    s += max(-15, min(15, cmf * 60))                      # CMF -0.25..+0.25 → ±15
    s += 6 if adl_slope > 0 else -6
    s += 4 if (obv_slope > 0) == (adl_slope > 0) else -4  # OBV/ADL agreement
    s += min(10, intensity * 3) if intensity > 0 else 0
    s += {"ACCUMULATION": 8, "MARKUP": 6, "DISTRIBUTION": -10, "MARKDOWN": -14}.get(phase, 0)
    if dte > 30:
        s += 3 if phase in ("ACCUMULATION", "MARKUP") else -5
    return max(0, min(100, s))


def signal_adjustment(bm: Dict) -> float:
    """Score nudge (−1..+1) for the IHSG pick filter/ranking. + = accumulation/ignition, − = distribution."""
    if not bm or not bm.get("ok"):
        return 0.0
    div = bm.get("divergence", "FLAT")
    base = {"BULLISH_DIV": 0.8, "ALIGNED_UP": 0.4, "FLAT": 0.0, "ALIGNED_DOWN": -0.4, "BEARISH_DIV": -0.8}.get(div, 0.0)
    base += max(-0.3, min(0.3, (bm.get("cmf") or 0) * 1.2))
    if bm.get("intensity_firing") and base > 0:
        base += 0.1
    # ignition: abnormal activity amplifies an existing bullish read (don't fire bearish on ignition alone)
    ig = bm.get("ignition") or {}
    if ig.get("ignition") and base > -0.1:
        base += min(0.3, ig.get("ignition_score", 0) / 250.0)
    # hidden accumulation: the manipulation-aware tell — money in while price suppressed
    stl = bm.get("stealth_accumulation") or {}
    if stl.get("is_stealth"):
        base += min(0.35, stl.get("score", 0) / 200.0)
    # markup-readiness: stealth + READY (enough inventory absorbed + coiled) = highest-conviction long
    mk = bm.get("markup_readiness") or {}
    if mk.get("verdict") == "READY" and base > -0.1:
        base += 0.2
    # real foreign-flow divergence (only when Type-F data is plugged in) dominates when present
    ff = bm.get("foreign_flow") or {}
    if ff.get("available"):
        fdiv = ff.get("divergence")
        base += {"FOREIGN_ACCUM_DIV": 0.5, "FOREIGN_DISTRIB_DIV": -0.5}.get(fdiv, 0.0)
    return max(-1.0, min(1.0, base))


def detect_ignition(df, base_win: int = 90, vol_win: int = 20):
    """OHLCV regime-break / 'ignition' detector — the honest version of 'catch the EURO rip'.

    Flags ABNORMAL activity worth investigating (volume + range expansion + breakout from a base +
    momentum acceleration). It does NOT and CANNOT know WHY (acquisition, insider, news) — it only
    sees the footprint. Use it as: 'something is igniting here → go find the catalyst.'
    Returns {ignition, ignition_score 0-100, signals:[...], vol_ratio, range_expansion, breakout, accel}.
    """
    import pandas as pd
    import numpy as np
    out = {"ignition": False, "ignition_score": 0, "signals": [],
           "vol_ratio": 0.0, "range_expansion": 0.0, "breakout": False, "accel": 0.0}
    if df is None or len(df) < base_win + 10:
        return out
    try:
        h, l, c, v = (pd.to_numeric(df[k], errors="coerce") for k in ("High", "Low", "Close", "Volume"))
    except (KeyError, TypeError):
        return out

    # 1) volume expansion: recent 5d avg vs trailing base
    v5 = v.tail(5).mean(); vbase = v.iloc[-base_win:-5].mean()
    vol_ratio = float(v5 / vbase) if vbase else 0.0
    # 2) range/volatility expansion: ATR(14) now vs base
    tr = (h - l).combine((h - c.shift()).abs(), max).combine((l - c.shift()).abs(), max)
    atr = tr.rolling(14).mean()
    atr_now = float(atr.iloc[-1] or 0); atr_base = float(atr.iloc[-base_win:-14].mean() or 0)
    range_expansion = (atr_now / atr_base) if atr_base else 0.0
    # 3) breakout from base: close above prior base-window high
    base_high = float(c.iloc[-base_win:-3].max() or 0)
    cN = float(c.iloc[-1] or 0)
    breakout = bool(cN > base_high * 1.005) if base_high else False
    # 4) momentum acceleration: ROC(10) now vs ROC(10) 10d ago
    roc = c.pct_change(10)
    accel = float((roc.iloc[-1] or 0) - (roc.iloc[-11] or 0))

    score = 0.0; sig = []
    if vol_ratio > 2.0:
        score += min(30, (vol_ratio - 1) * 15); sig.append(f"volume {vol_ratio:.1f}× base")
    if range_expansion > 1.5:
        score += min(25, (range_expansion - 1) * 18); sig.append(f"range/ATR {range_expansion:.1f}× base")
    if breakout:
        score += 25; sig.append(f"breakout > {base_win}d base high")
    if accel > 0.05:
        score += min(20, accel * 120); sig.append(f"momentum accelerating (+{accel*100:.0f}pp)")
    score = max(0, min(100, score))
    out.update({"ignition": score >= 50, "ignition_score": int(round(score)), "signals": sig,
                "vol_ratio": round(vol_ratio, 2), "range_expansion": round(range_expansion, 2),
                "breakout": breakout, "accel": round(accel, 4)})
    return out


def foreign_flow_metrics(foreign, price=None):
    """Foreign-flow signal — INTERFACE for IDX Type-F data (the signal that actually caught EURO/MSIN).

    foreign: a daily series/list of foreign NET buy (+) / sell (−) value (Type-F). We do NOT have this
    from yfinance; plug in from a paid IDX API / scrape. If None/empty → returns unavailable=True so the
    rest of the engine degrades cleanly. When provided, computes cumulative FF, 20d slope, and FF↔price
    divergence (foreign accumulating into weakness = the strongest IDX tell)."""
    import pandas as pd
    import numpy as np
    if foreign is None or len(foreign) < 30:
        return {"available": False, "note": "needs IDX Type-F foreign net-flow (paid API / scrape)."}
    ff = pd.Series(list(foreign), dtype="float64")
    cum = ff.cumsum()
    ff_slope = float((cum.iloc[-1] - cum.iloc[-21]) / (abs(cum.iloc[-21]) + 1e-9)) if len(cum) > 21 else 0.0
    out = {"available": True, "ff_cum": round(float(cum.iloc[-1]), 0), "ff_slope_20": round(ff_slope, 4),
           "ff_state": "inflow" if ff_slope > 0 else "outflow"}
    if price is not None and len(price) >= len(ff) and len(ff) > 21:
        p = pd.Series(list(price[-len(ff):]), dtype="float64")
        p_slope = float((p.iloc[-1] - p.iloc[-21]) / (abs(p.iloc[-21]) + 1e-9))
        if p_slope < -0.005 and ff_slope > 0.01:
            out["divergence"] = "FOREIGN_ACCUM_DIV"   # price down, foreign buying = strongest accumulation
        elif p_slope > 0.005 and ff_slope < -0.01:
            out["divergence"] = "FOREIGN_DISTRIB_DIV"
        else:
            out["divergence"] = "ALIGNED" if (p_slope * ff_slope) > 0 else "FLAT"
    return out


def detect_stealth_accumulation(adl_slope, cmf, price_slope, ignition_score, obv_slope):
    """HIDDEN accumulation — money flowing in while price stays flat/down and hasn't ignited yet.
    This is the manipulation-aware tell: smart money absorbs supply quietly (A/D + CMF up) while
    keeping price suppressed, BEFORE the markup. Returns {is_stealth, score 0-100, reason}."""
    score = 0.0
    reasons = []
    if adl_slope > 0.005:
        score += 30; reasons.append("A/D rising")
    if obv_slope > 0:
        score += 8; reasons.append("OBV confirms")
    if cmf > 0.05:
        score += min(25, cmf * 100); reasons.append(f"CMF +{cmf:.2f}")
    if price_slope < 0.03:
        score += 17; reasons.append("price flat/down")
    if price_slope < -0.005:
        score += 10; reasons.append("price actually falling (divergence)")
    if ignition_score < 40:
        score += 10; reasons.append("not yet ignited")  # still stealth, not already running
    score = max(0, min(100, score))
    is_stealth = bool(score >= 62 and adl_slope > 0 and cmf > 0 and price_slope < 0.03)
    return {"is_stealth": is_stealth, "score": int(round(score)), "reason": " · ".join(reasons)}


def estimate_markup_readiness(df, adv_win: int = 60, accum_lookback: int = 60) -> Dict:
    """Answers Edward's question: 'has the operator absorbed ENOUGH inventory + is price coiled to mark up?'

    Detecting that accumulation is happening (stealth) is necessary but not sufficient — the markup only
    fires once the operator holds enough float AND price has compressed (spring). Estimates:
      - inventory_days: ADL gain over the window in DAYS-OF-$-VOLUME (how much float quietly absorbed)
      - coil_ratio: ATR(14) now vs base — <1 = compressing (loaded), >1.3 = maybe already moving
      - suppression_pct: how far below the window-high price still sits (room to mark up)
    Returns {readiness 0-100, verdict EARLY/BUILDING/READY, inventory_days, coil_ratio, suppression_pct, reason}.
    Honest limit: this is a footprint proxy (OHLCV), not the operator's actual book."""
    import pandas as pd
    import numpy as np
    out = {"readiness": 0, "verdict": "n/a", "inventory_days": 0.0, "coil_ratio": 0.0,
           "suppression_pct": 0.0, "reason": "insufficient data"}
    if df is None or len(df) < max(adv_win, accum_lookback) + 5:
        return out
    try:
        h, l, c, v = (pd.to_numeric(df[k], errors="coerce") for k in ("High", "Low", "Close", "Volume"))
    except (KeyError, TypeError):
        return out
    typ = (h + l + c) / 3.0
    rng = (h - l).replace(0, np.nan)
    clv = (((c - l) - (h - c)) / rng).clip(-1, 1).fillna(0)
    adl = (clv * v).cumsum()
    adv = (v * typ).rolling(adv_win).mean()
    advN = float(adv.dropna().iloc[-1] or 0)
    adl_gain = float(adl.iloc[-1] - adl.iloc[-accum_lookback])     # share-vol units
    px = float(typ.dropna().iloc[-1] or 0)
    inventory_days = (abs(adl_gain) * px / advN) if advN > 0 else 0.0
    tr = (h - l).combine((h - c.shift()).abs(), max).combine((l - c.shift()).abs(), max)
    atr = tr.rolling(14).mean()
    atr_now = float(atr.iloc[-1] or 0); atr_base = float(atr.iloc[-accum_lookback:-14].mean() or 0)
    coil_ratio = (atr_now / atr_base) if atr_base else 1.0
    win_high = float(c.iloc[-accum_lookback:].max() or 0)
    cN = float(c.iloc[-1] or 0)
    suppression_pct = ((win_high - cN) / win_high * 100.0) if win_high else 0.0

    score = 0.0; bits = []
    if inventory_days >= 5:
        score += min(40, inventory_days * 2.5); bits.append(f"{inventory_days:.0f}d-vol terserap")
    if coil_ratio < 0.85:
        score += min(30, (1 - coil_ratio) * 80); bits.append(f"coiled {coil_ratio:.2f}× (spring loaded)")
    elif coil_ratio > 1.3:
        score -= 10; bits.append(f"range melebar {coil_ratio:.2f}× (mungkin udah gerak)")
    if 3 <= suppression_pct <= 25:
        score += 20; bits.append(f"{suppression_pct:.0f}% di bawah high (ada ruang)")
    elif suppression_pct < 1:
        bits.append("di window-high (markup mungkin udah jalan)")
    adl_rising = _slope(adl, 20) > 0
    if adl_rising:
        score += 10; bits.append("inventory masih nambah")
    score = max(0, min(100, score))
    verdict = ("READY" if score >= 65 and inventory_days >= 5 and adl_rising
               else "BUILDING" if score >= 40 else "EARLY")
    out.update({"readiness": int(round(score)), "verdict": verdict,
                "inventory_days": round(inventory_days, 1), "coil_ratio": round(coil_ratio, 2),
                "suppression_pct": round(suppression_pct, 1),
                "reason": " · ".join(bits) or "sinyal kurang"})
    return out


def analyze_universe(ohlcv: Dict, **kw) -> Dict:
    """ohlcv: {ticker: DataFrame[OHLCV]} → {ticker: indicator dict}."""
    out = {}
    for t, df in (ohlcv or {}).items():
        try:
            r = compute(df, **kw)
            if r:
                out[t] = r
        except Exception as e:
            logger.debug(f"bandarmetrics failed for {t}: {e}")
    return out
