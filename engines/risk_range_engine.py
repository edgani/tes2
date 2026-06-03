"""engines/risk_range_engine.py — REAL Hedgeye Risk Range v39

v39 FIXES (P0):
 1. ENTRY LOGIC: Scale-in AT or NEAR trade_lrr (Hedgeye methodology).
    OLD: entry = max(px*1.005, trade_lrr*1.005) = stop-entry ABOVE low.
    NEW: px <= trade_lrr → entry = px*0.995 (scale in now).
 2. STOP: Unified 1.5% below trade_lrr (long) / above trade_trr (short).
 3. TARGET2: Uses Trend range (intermediate-term profit taking).
 4. Added walkforward metadata fields.
"""
from __future__ import annotations
import math, logging
from typing import Dict, Optional
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

QUAD_RANGE_MULT = {
    "Q1": (1.30, 2.20, 4.20),
    "Q2": (1.50, 2.50, 4.80),
    "Q3": (1.80, 3.00, 5.50),
    "Q4": (2.00, 3.50, 6.50),
}

def _calc_atr(s: pd.Series, period: int = 14) -> float:
    s = pd.to_numeric(s, errors="coerce").dropna()
    if len(s) < period + 1:
        return 0.0
    try:
        daily_range = s.diff().abs()
        synthetic_tr = daily_range * 1.4
        atr = float(synthetic_tr.tail(period).mean())
        return atr if math.isfinite(atr) else 0.0
    except Exception:
        return 0.0

def _calc_realized_vol(s: pd.Series, lookback: int = 20) -> float:
    try:
        ser = pd.to_numeric(s, errors="coerce").dropna()
        if len(ser) < lookback:
            return 0.0
        ret = ser.tail(lookback).pct_change().dropna()
        vol = float(ret.std() * np.sqrt(252))
        return vol if math.isfinite(vol) else 0.0
    except Exception:
        return 0.0

def _calc_volume_weight(s: pd.Series, lookback: int = 20) -> float:
    try:
        ser = pd.to_numeric(s, errors="coerce").dropna()
        if len(ser) < lookback * 2:
            return 1.0
        recent_velocity = float(ser.tail(lookback).pct_change().abs().mean())
        baseline_velocity = float(ser.tail(lookback * 3).pct_change().abs().mean())
        if baseline_velocity <= 0:
            return 1.0
        return min(2.0, max(0.5, recent_velocity / baseline_velocity))
    except Exception:
        return 1.0

def _calculate_risk_range_v39_atr(ticker: str, prices_or_series,
                         current_quad: str = "Q3",
                         vix_proxy: float = 20.0) -> Dict:
    """LEGACY v39 ATR×mult / SMA-basis engine. Kept ONLY as a fallback for when
    the calibrated v20.3b engine can't compute (insufficient data). Not primary."""
    s = prices_or_series.get(ticker) if isinstance(prices_or_series, dict) else prices_or_series
    if s is None or (hasattr(s, "__len__") and len(s) < 60):
        return {"ticker": ticker, "ok": False, "reason": "insufficient_data"}
    try:
        s_clean = pd.to_numeric(s, errors="coerce").dropna()
        if len(s_clean) < 60:
            return {"ticker": ticker, "ok": False, "reason": "insufficient_clean_data"}
        px = float(s_clean.iloc[-1])
        if not math.isfinite(px) or px <= 0:
            return {"ticker": ticker, "ok": False, "reason": "invalid_price"}

        sma_20 = float(s_clean.tail(20).mean())
        sma_50 = float(s_clean.tail(min(50, len(s_clean))).mean())
        sma_200 = float(s_clean.tail(min(200, len(s_clean))).mean()) if len(s_clean) >= 60 else sma_50

        atr_14 = _calc_atr(s_clean, 14)
        atr_30 = _calc_atr(s_clean, 30)
        atr_60 = _calc_atr(s_clean, 60) if len(s_clean) >= 60 else atr_30
        realized_vol_20 = _calc_realized_vol(s_clean, 20)
        realized_vol_60 = _calc_realized_vol(s_clean, 60) if len(s_clean) >= 60 else realized_vol_20
        vol_weight = _calc_volume_weight(s_clean, 20)

        trade_mult, trend_mult, tail_mult = QUAD_RANGE_MULT.get(current_quad, QUAD_RANGE_MULT["Q3"])
        vix_adj = 1.0
        if vix_proxy > 30: vix_adj = 1.40
        elif vix_proxy > 25: vix_adj = 1.20
        elif vix_proxy < 14: vix_adj = 0.85

        formation = "BULLISH" if px > sma_50 else "BEARISH" if px < sma_50 else "NEUTRAL"
        if formation == "BULLISH":
            up_mult, dn_mult = 1.15, 0.90
        elif formation == "BEARISH":
            up_mult, dn_mult = 0.85, 1.15
        else:
            up_mult, dn_mult = 1.0, 1.0

        trade_width = atr_14 * trade_mult * vix_adj * vol_weight
        trade_lrr = sma_20 - trade_width * dn_mult
        trade_trr = sma_20 + trade_width * up_mult

        trend_width = atr_30 * trend_mult * vix_adj * vol_weight
        trend_lrr = sma_50 - trend_width * dn_mult
        trend_trr = sma_50 + trend_width * up_mult

        tail_width = atr_60 * tail_mult * vix_adj
        tail_lrr = sma_200 - tail_width * dn_mult * 1.2
        tail_trr = sma_200 + tail_width * up_mult * 1.2

        # v39: Branch-aware distance + composite
        if px < trade_lrr:
            composite = "bullish"
            distance_to_entry_edge = abs(px - trade_lrr) / max(trade_lrr, 0.001)
        elif px > trade_trr:
            composite = "bearish"
            distance_to_entry_edge = abs(px - trade_trr) / max(trade_trr, 0.001)
        else:
            composite = "neutral"
            d_low = abs(px - trade_lrr) / max(trade_lrr, 0.001)
            d_high = abs(px - trade_trr) / max(trade_trr, 0.001)
            distance_to_entry_edge = min(d_low, d_high)

        if formation == "BULLISH" and composite == "bullish":
            quality = "A+" if distance_to_entry_edge < 0.02 else "A"
        elif formation == "BEARISH" and composite == "bearish":
            quality = "short_A+" if distance_to_entry_edge < 0.02 else "short_A"
        elif composite != "neutral":
            quality = "B" if formation == "BULLISH" else "short_B"
        else:
            quality = "C"

        # v39 FIX: Hedgeye entry logic
        if formation == "BULLISH":
            if px <= trade_lrr:
                entry = px * 0.995
            else:
                entry = min(px, trade_lrr * 1.01)
            target1 = trade_trr
            target2 = trend_trr
            stop = trade_lrr * 0.985
        elif formation == "BEARISH":
            if px >= trade_trr:
                entry = px * 1.005
            else:
                entry = max(px, trade_trr * 0.99)
            target1 = trade_lrr
            target2 = trend_lrr
            stop = trade_trr * 1.015
        else:
            entry = px
            target1 = trade_trr
            target2 = trend_trr
            stop = trade_lrr

        rr = abs(target1 - entry) / max(abs(entry - stop), 0.001)
        expected_move_weekly = realized_vol_20 / math.sqrt(52)
        daily_vol = realized_vol_20 / math.sqrt(252)

        return {
            "ticker": ticker, "ok": True, "px": round(px, 4),
            "trade": {"lrr": round(trade_lrr, 4), "trr": round(trade_trr, 4)},
            "trend": {"lrr": round(trend_lrr, 4), "trr": round(trend_trr, 4)},
            "tail": {"lrr": round(tail_lrr, 4), "trr": round(tail_trr, 4)},
            "atr_14": round(atr_14, 4), "atr_30": round(atr_30, 4),
            "realized_vol_20": round(realized_vol_20, 4),
            "realized_vol_60": round(realized_vol_60, 4),
            "vol_weight": round(vol_weight, 2),
            "composite": composite, "formation": formation, "quality": quality,
            "distance_to_entry_edge": round(distance_to_entry_edge, 4),
            "distance_to_low": round(distance_to_entry_edge, 4),
            "entry": round(entry, 4), "target1": round(target1, 4),
            "target2": round(target2, 4), "stop": round(stop, 4),
            "rr": round(rr, 2),
            "expected_move_weekly_pct": round(expected_move_weekly, 4),
            "daily_vol_pct": round(daily_vol, 4),
            "regime_mult_applied": current_quad, "vix_adj": vix_adj,
            "market": _classify_market_simple(ticker),
        }
    except Exception as e:
        logger.debug(f"Risk range calc failed for {ticker}: {e}")
        return {"ticker": ticker, "ok": False, "reason": f"exception:{type(e).__name__}"}

def calculate_risk_range(ticker: str, prices_or_series,
                         current_quad: str = "Q3",
                         vix_proxy: float = 20.0) -> Dict:
    """S0 CONSOLIDATION — single source of truth for BAND math.

    Delegates to the calibrated v20.3b engine (prev-close basis, realized-vol/IV,
    Hurst fractal, asymmetric skew — verified vs Hedgeye public prints), then
    derives the v39-shaped setup keys (entry/target/stop/composite/quality/rr) so
    every downstream consumer (orchestrator, market pages, daily_play, simulation)
    keeps working unchanged. Falls back to legacy v39 ATR only if v20 can't compute.
    """
    s = prices_or_series.get(ticker) if isinstance(prices_or_series, dict) else prices_or_series
    try:
        from engines.risk_range_v20 import calculate_trr_lrr_v20
        v = calculate_trr_lrr_v20(ticker, s, external_iv=vix_proxy, current_quad=current_quad)
    except Exception as e:
        logger.debug(f"v20 risk range failed for {ticker}: {e}; falling back to v39")
        v = None
    if not v:
        return _calculate_risk_range_v39_atr(ticker, prices_or_series, current_quad, vix_proxy)

    px = v["px"]
    t_lrr, t_trr = v["trade"]["lrr"], v["trade"]["trr"]
    tr_lrr, tr_trr = v["trend"]["lrr"], v["trend"]["trr"]
    tl_lrr, tl_trr = v["tail"]["lrr"], v["tail"]["trr"]
    sig = v.get("signals", {})
    formation = sig.get("formation", "NEUTRAL")
    quality = sig.get("quality", "C")

    # composite (v39 semantics): where price sits vs the TRADE band
    if px < t_lrr:
        composite = "bullish"; dist = abs(px - t_lrr) / max(t_lrr, 1e-6)
    elif px > t_trr:
        composite = "bearish"; dist = abs(px - t_trr) / max(t_trr, 1e-6)
    else:
        composite = "neutral"
        dist = min(abs(px - t_lrr) / max(t_lrr, 1e-6), abs(px - t_trr) / max(t_trr, 1e-6))

    # setup derivation (v39 entry/target/stop logic, now on v20 bands)
    if formation == "BULLISH":
        entry = px * 0.995 if px <= t_lrr else min(px, t_lrr * 1.01)
        target1, target2, stop = t_trr, tr_trr, t_lrr * 0.985
    elif formation == "BEARISH":
        entry = px * 1.005 if px >= t_trr else max(px, t_trr * 0.99)
        target1, target2, stop = t_lrr, tr_lrr, t_trr * 1.015
    else:
        entry, target1, target2, stop = px, t_trr, tr_trr, t_lrr
    rr = abs(target1 - entry) / max(abs(entry - stop), 1e-6)

    vd = v.get("vol", {})
    rv = vd.get("realized_vol_ann", 0.0) or 0.0
    return {
        "ticker": ticker, "ok": True, "px": round(px, 4),
        "trade": {"lrr": round(t_lrr, 4), "trr": round(t_trr, 4)},
        "trend": {"lrr": round(tr_lrr, 4), "trr": round(tr_trr, 4)},
        "tail": {"lrr": round(tl_lrr, 4), "trr": round(tl_trr, 4)},
        "atr_14": vd.get("atr", 0.0), "atr_30": vd.get("atr", 0.0),
        "realized_vol_20": round(rv, 4), "realized_vol_60": round(rv, 4),
        "vol_weight": 1.0,
        "composite": composite, "formation": formation, "quality": quality,
        "distance_to_entry_edge": round(dist, 4), "distance_to_low": round(dist, 4),
        "entry": round(entry, 4), "target1": round(target1, 4),
        "target2": round(target2, 4), "stop": round(stop, 4), "rr": round(rr, 2),
        "expected_move_weekly_pct": round(rv / math.sqrt(52), 4) if rv else 0.0,
        "daily_vol_pct": vd.get("daily_vol", 0.0),
        "regime_mult_applied": current_quad, "vix_adj": 1.0,
        "market": _classify_market_simple(ticker),
        # carry v20's richer signals through for engines that want them
        "signals": sig, "hurst": v.get("hurst"), "phase": v.get("phase"),
        "bsi": v.get("bsi"), "engine": "v20.3b_via_v39_shim",
    }


def _classify_market_simple(ticker: str) -> str:
    t = (ticker or "").upper()
    if "=" in t or t in ("DX-Y.NYB", "UUP"): return "forex"
    if t in ("GC=F", "SI=F", "CL=F", "BZ=F", "HG=F", "NG=F"): return "commodity"
    if "-USD" in t or t in ("BTC-USD", "ETH-USD", "SOL-USD"): return "crypto"
    if t.endswith(".JK"): return "ihsg"
    if t.startswith("^"): return "index"
    return "us_equity"

class RiskRangeEngine:
    def __init__(self, current_quad: str = "Q3", vix: float = 20.0):
        self.current_quad = current_quad
        self.vix = vix
    def run(self, prices: Dict, current_quad: Optional[str] = None, vix: Optional[float] = None) -> Dict:
        quad = current_quad or self.current_quad
        v = vix if vix is not None else self.vix
        asset_ranges = {}
        ok_count = fail_count = 0
        for ticker, series in (prices or {}).items():
            result = calculate_risk_range(ticker, series, quad, v)
            if result.get("ok"):
                asset_ranges[ticker] = result; ok_count += 1
            else:
                fail_count += 1
        if asset_ranges:
            qualities = [r.get("quality") for r in asset_ranges.values()]
            formations = [r.get("formation") for r in asset_ranges.values()]
            summary = {
                "total": ok_count, "failed": fail_count,
                "a_plus_grade": qualities.count("A+"), "a_grade": qualities.count("A"),
                "short_a_plus_grade": qualities.count("short_A+"),
                "short_a_grade": qualities.count("short_A"),
                "bullish_formations": formations.count("BULLISH"),
                "bearish_formations": formations.count("BEARISH"),
                "neutral_formations": formations.count("NEUTRAL"),
                "quad_applied": quad, "vix_applied": v,
            }
        else:
            summary = {"total": 0, "failed": fail_count}
        logger.info(f"RiskRangeEngine v39: {ok_count} ranges calculated, {fail_count} failed")
        return {"asset_ranges": asset_ranges, "summary": summary, "version": "v39"}

def calculate_for_universe(prices: Dict, current_quad: str = "Q3", vix: float = 20.0) -> Dict:
    return RiskRangeEngine(current_quad, vix).run(prices)

def get_ticker_risk_setup(ticker: str, prices: Dict, current_quad: str = "Q3", vix: float = 20.0) -> Dict:
    return calculate_risk_range(ticker, prices, current_quad, vix)
