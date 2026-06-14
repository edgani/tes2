"""engines/afternoon_signal.py — "Strongest Afternoon" Signal Proxy (FIXED Sprint 1)

FIXES vs prior:
  • All variables pre-initialized
  • Whole-body try-except guards UnboundLocalError
  • Returns deterministic shape always
  • Safer handling of optional charm/vanna/structure dicts
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def _empty_result(ticker: str, reason: str = "") -> Dict:
    return {
        "ok": False,
        "ticker": ticker,
        "error": reason or "no_data",
        "signal": "WEAK",
        "direction": "NEUTRAL",
        "confidence": "LOW",
        "color": "#8B949E",
        "score": 0,
        "max_score": 6,
        "in_window": False,
        "window_note": "Unavailable",
        "reasons": [],
        "recommended_structure": "—",
        "source": "PROXY",
    }


def _safe_get(d: Optional[Dict], key: str, default=None):
    if not isinstance(d, dict):
        return default
    return d.get(key, default)


def analyze_afternoon(ticker: str, prices: Dict,
                     charm_data: Optional[Dict] = None,
                     vanna_data: Optional[Dict] = None,
                     vix: float = 20.0,
                     gex_data: Optional[Dict] = None,
                     structure_data: Optional[Dict] = None) -> Dict:
    """Generate afternoon bias signal. Defensive."""
    # Pre-initialize EVERYTHING
    vol_20 = 0.0
    mean_20 = 0.0
    vol_ratio = 0.0
    score = 0
    reasons: List[str] = []
    signal = "WEAK"
    confidence = "LOW"
    color = "#8B949E"
    direction = "NEUTRAL"
    in_window = False
    window_note = ""

    try:
        import pandas as pd

        s = prices.get(ticker) if isinstance(prices, dict) else None
        if s is None or (hasattr(s, "__len__") and len(s) < 20):
            return _empty_result(ticker, "insufficient_data")

        s_clean = pd.to_numeric(s, errors="coerce").dropna()
        if len(s_clean) < 20:
            return _empty_result(ticker, "insufficient_clean_data")

        vol_20 = float(s_clean.tail(20).std())
        mean_20 = float(s_clean.tail(20).mean())
        vol_ratio = (vol_20 / mean_20) if mean_20 > 0 else 0.0

        # Conditions (each guarded)
        vix_ok = 12 <= float(vix) <= 22

        charm_regime = _safe_get(charm_data, "regime", "")
        charm_ok = bool(_safe_get(charm_data, "ok", False)) and charm_regime in ("BUILDING", "FADING")
        net_charm = _safe_get(charm_data, "net_charm", 0) or 0
        try:
            charm_strength = abs(float(net_charm)) > 1e5 if _safe_get(charm_data, "ok") else False
        except (TypeError, ValueError):
            charm_strength = False

        structure_ok = bool(_safe_get(structure_data, "ok", False)) and \
                       _safe_get(structure_data, "quality") == "CLEAN"

        volume_ok = vol_ratio < 0.03

        # Time window
        now = datetime.now()
        hour_frac = now.hour + now.minute / 60.0
        in_window = 13.5 <= hour_frac <= 15.0
        window_note = "13:30-15:00 ET" if in_window else f"Now {now.strftime('%H:%M')} — wait for 13:30"

        # Scoring
        if vix_ok:
            score += 1
            reasons.append("VIX calm")
        if charm_ok and charm_strength:
            score += 2
            reasons.append("Charm strong")
        if structure_ok:
            score += 1
            reasons.append("Clean structure")
        if volume_ok:
            score += 1
            reasons.append("Low vol env")
        if in_window:
            score += 1
            reasons.append("In window")

        if score >= 4:
            signal = "STRONG"
            confidence = "HIGH"
            color = "#3FB950"
        elif score >= 2:
            signal = "MODERATE"
            confidence = "MEDIUM"
            color = "#D29922"
        else:
            signal = "WEAK"
            confidence = "LOW"
            color = "#8B949E"

        # Direction from charm
        if charm_regime == "BUILDING":
            direction = "LONG"
        elif charm_regime == "FADING":
            direction = "SHORT"
        else:
            direction = "NEUTRAL"

        rec_struct = (
            "Fly above test level" if direction == "LONG"
            else "Put spread below test" if direction == "SHORT"
            else "Iron condor"
        )

        return {
            "ok": True,
            "ticker": ticker,
            "signal": signal,
            "direction": direction,
            "confidence": confidence,
            "color": color,
            "score": score,
            "max_score": 6,
            "in_window": in_window,
            "window_note": window_note,
            "reasons": reasons,
            "recommended_structure": rec_struct,
            "source": "PROXY",
        }

    except Exception as e:
        logger.debug(f"Afternoon signal failed for {ticker}: {e}")
        return _empty_result(ticker, f"exception:{type(e).__name__}")


def analyze_multi(tickers: List[str], prices: Dict,
                  charm_map: Optional[Dict] = None,
                  vanna_map: Optional[Dict] = None,
                  vix: float = 20.0,
                  gex_map: Optional[Dict] = None,
                  structure_map: Optional[Dict] = None) -> Dict[str, Dict]:
    """Batch wrapper. Always returns dict (never raises)."""
    charm_map = charm_map or {}
    vanna_map = vanna_map or {}
    gex_map = gex_map or {}
    structure_map = structure_map or {}

    results = {}
    for t in tickers:
        try:
            results[t] = analyze_afternoon(
                t, prices,
                charm_map.get(t, {}) if isinstance(charm_map, dict) else {},
                vanna_map.get(t, {}) if isinstance(vanna_map, dict) else {},
                vix,
                gex_map.get(t, {}) if isinstance(gex_map, dict) else {},
                structure_map.get(t, {}) if isinstance(structure_map, dict) else {},
            )
        except Exception as e:
            logger.warning(f"Afternoon multi failed for {t}: {e}")
            results[t] = _empty_result(t, f"multi_exception:{type(e).__name__}")
    return results
