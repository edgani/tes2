"""engines/vanna_proxy_engine.py — Vanna Flow Proxy (FIXED Sprint 1)

Vanna = ∂Δ/∂σ. Proxy from skew + VIX sensitivity.

FIXES vs prior:
  • All variables pre-initialized BEFORE conditional logic
  • Whole-body try-except wrapper catches UnboundLocalError gracefully
  • No silent fallback to undefined locals
  • Returns deterministic shape regardless of input quality
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _empty_result(ticker: str, reason: str = "") -> Dict:
    """Deterministic empty shape — same keys whether OK or fail."""
    return {
        "ok": False,
        "ticker": ticker,
        "error": reason or "no_data",
        "signal": "NEUTRAL",
        "regime": "UNKNOWN",
        "color": "#8B949E",
        "futures_per_1pct_vix": 0.0,
        "skew_spread": 0.0,
        "vix_regime": "UNKNOWN",
        "note": "Vanna unavailable",
        "source": "PROXY",
    }


def analyze_vanna(ticker: str, prices: Dict, vix: float = 20.0,
                  dxy_ret: float = 0.0) -> Dict:
    """Calculate Vanna exposure proxy for a ticker. Defensive."""
    # Pre-initialize ALL variables that any branch might reference
    spot = 0.0
    sma20 = 0.0
    std20 = 0.0
    vol_30 = 0.0
    vol_60 = 0.0
    skew_spread = 0.0
    signal = "NEUTRAL"
    regime = "NORMAL"
    color = "#8B949E"
    futures_per_1pct = 0.0
    note = "Vanna mixed"
    vix_regime = "NORMAL"

    try:
        s = prices.get(ticker) if isinstance(prices, dict) else None
        if s is None or (hasattr(s, "__len__") and len(s) < 30):
            return _empty_result(ticker, "insufficient_data")

        s_clean = pd.to_numeric(s, errors="coerce").dropna()
        if len(s_clean) < 30:
            return _empty_result(ticker, "insufficient_clean_data")

        # Spot & rolling stats
        spot = float(s_clean.iloc[-1])
        sma20 = float(s_clean.tail(20).mean())
        std20 = float(s_clean.tail(20).std())

        # Skew proxy (S2-c): realized downside-vs-upside semideviation asymmetry.
        # +ve = downside vol dominates = put-skew / crash-prone (vanna tailwind on a
        #  vol-down tick); -ve = upside-skewed. The OLD code used a 30d/60d realized-
        #  vol term-structure spread, which is NOT skew. This is computable from price.
        vol_30 = float(s_clean.tail(30).std())
        vol_60 = float(s_clean.tail(min(60, len(s_clean))).std()) if len(s_clean) >= 60 else vol_30
        _rets = s_clean.pct_change().dropna().tail(60)
        if len(_rets) >= 20:
            _dsd = float(_rets[_rets < 0].std()) if int((_rets < 0).sum()) > 1 else 0.0
            _usd = float(_rets[_rets > 0].std()) if int((_rets > 0).sum()) > 1 else 0.0
            _den = _dsd + _usd
            skew_spread = ((_dsd - _usd) / _den) if _den > 1e-9 else 0.0
        else:
            skew_spread = 0.0

        # Safety: clamp non-finite
        if not math.isfinite(skew_spread):
            skew_spread = 0.0
        if not math.isfinite(std20) or std20 <= 0:
            std20 = max(abs(spot) * 0.01, 0.01)

        # VIX regime
        vix_elevated = vix > 25
        vix_normal = 18 <= vix <= 25
        vix_low = vix < 18
        vix_regime = "ELEVATED" if vix_elevated else ("NORMAL" if vix_normal else "LOW")

        # Vanna signal logic
        if vix_elevated and skew_spread > 0.10:
            signal = "NEVER_SHORT"
            regime = "DOMINANT"
            color = "#3FB950"
            futures_per_1pct = round(std20 * 2.0, 2)
            note = f"Vanna dominant — if VIX drops 1%, dealers buy {futures_per_1pct} futures"
        elif vix_elevated and skew_spread < -0.10:
            signal = "AVOID_LONG"
            regime = "DOMINANT"
            color = "#F85149"
            futures_per_1pct = round(std20 * 2.0, 2)
            note = f"Vanna headwind — if VIX rises 1%, dealers sell {futures_per_1pct} futures"
        elif vix_normal and abs(skew_spread) < 0.10:
            signal = "NEUTRAL"
            regime = "NORMAL"
            color = "#8B949E"
            futures_per_1pct = round(std20 * 1.0, 2)
            note = "Vanna balanced — vol moves have neutral impact"
        else:
            # DXY correlation fallback for precious metals
            is_pm = ticker in ("GLD", "SLV", "GC=F", "SI=F", "GDX", "GDXJ", "SIL", "SILJ")
            if dxy_ret > 0.01:
                signal = "AVOID_LONG" if is_pm else "NEUTRAL"
            elif dxy_ret < -0.01:
                signal = "NEVER_SHORT" if is_pm else "NEUTRAL"
            else:
                signal = "NEUTRAL"
            regime = "NORMAL"
            color = "#8B949E"
            futures_per_1pct = round(std20 * 1.0, 2)
            note = "Vanna mixed — no clear vol-driven bias"

        return {
            "ok": True,
            "ticker": ticker,
            "spot": spot,
            "signal": signal,
            "regime": regime,
            "color": color,
            "futures_per_1pct_vix": futures_per_1pct,
            "skew_spread": round(skew_spread, 4),
            "vix_regime": vix_regime,
            "note": note,
            "source": "PROXY",
        }

    except Exception as e:
        # Top-level guard — any unexpected error
        logger.debug(f"Vanna analyze failed for {ticker}: {e}")
        return _empty_result(ticker, f"exception:{type(e).__name__}")


def analyze_multi(tickers: List[str], prices: Dict,
                  vix: float = 20.0, dxy_ret: float = 0.0) -> Dict[str, Dict]:
    """Batch wrapper. Always returns a dict for every ticker (never raises)."""
    results = {}
    for t in tickers:
        try:
            results[t] = analyze_vanna(t, prices, vix, dxy_ret)
        except Exception as e:
            logger.warning(f"Vanna multi failed for {t}: {e}")
            results[t] = _empty_result(t, f"multi_exception:{type(e).__name__}")
    return results
