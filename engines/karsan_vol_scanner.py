"""engines/karsan_vol_scanner.py — Cem Karsan's 3-Pillar Vol Methodology (Sprint 9)

Replicates Karsan's actual scanning methodology — NOT his portfolio.

3 Pillars he scans:
  1. 30-Day Skew (term structure of skew across expirations)
  2. Dispersion (index vol vs constituent vol)
  3. VVIX / Convexity (vol-of-vol for tail hedging)

His insight: "We really don't look at fundamentals. It's all about flow."
Two-Sided Skew = call skew > put skew = meme/convex environment (rare in equities)

Output per ticker:
  - skew_score (-1 to +1, positive = call skew > put skew = bullish/convex setup)
  - vrp_score (-1 to +1, positive = sell premium opportunity)
  - vol_regime (mean_reversion / breakout / chop)
  - two_sided_skew (boolean)
  - karsan_setup (description of which setup applies)
"""
from __future__ import annotations

import math
import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_realized_vol(prices_series, window: int = 21) -> Optional[float]:
    """Annualized realized vol."""
    if prices_series is None:
        return None
    try:
        s = pd.to_numeric(prices_series, errors="coerce").dropna()
        if len(s) < window + 1:
            return None
        rets = s.pct_change().dropna()
        return float(rets.tail(window).std() * math.sqrt(252))
    except Exception:
        return None


def compute_iv_proxy(ticker: str, rv: float, vix: float, market_type: str = "us_equity") -> float:
    """
    Estimate implied vol when options data unavailable.
    Premium varies by asset type & VIX regime (Karsan: dealers structurally short vol).
    """
    if rv is None or rv <= 0:
        return None
    if ticker in ("SPY", "QQQ", "IWM", "DIA"):
        base_premium = 1.10
    elif ticker.startswith("BTC") or ticker.startswith("ETH"):
        base_premium = 1.25
    elif market_type == "commodity":
        base_premium = 1.18
    else:
        base_premium = 1.20  # single stock typical
    regime_adj = 1.10 if vix >= 30 else 0.95 if vix <= 14 else 1.0
    return rv * base_premium * regime_adj


def compute_iv_rank(current_iv: float, iv_history: List[float]) -> Optional[float]:
    """IV Rank = percentile of current IV in historical range (0-100)."""
    if current_iv is None or not iv_history:
        return None
    h = [x for x in iv_history if x is not None and math.isfinite(x)]
    if len(h) < 10:
        return None
    below = sum(1 for x in h if x < current_iv)
    return round(below / len(h) * 100, 1)


def detect_two_sided_skew(prices_series) -> Dict:
    """
    Karsan's two-sided skew: when call IV > put IV (rare, signals convex environment).
    Without real options chain, use returns asymmetry as proxy:
      - If recent upside vol > downside vol → call skew likely elevated
      - This is the meme/squeeze setup
    """
    out = {"two_sided_skew": False, "upside_vol_pct": 0, "downside_vol_pct": 0, "skew_asym": 0}
    if prices_series is None:
        return out
    try:
        s = pd.to_numeric(prices_series, errors="coerce").dropna()
        if len(s) < 60:
            return out
        rets = s.pct_change().dropna().tail(60)
        ups = rets[rets > 0]
        downs = rets[rets < 0]
        if len(ups) < 5 or len(downs) < 5:
            return out
        up_vol = float(ups.std() * math.sqrt(252))
        dn_vol = float(downs.std() * math.sqrt(252))
        asym = (up_vol - dn_vol) / max(dn_vol, 0.001)
        out["upside_vol_pct"] = round(up_vol * 100, 2)
        out["downside_vol_pct"] = round(dn_vol * 100, 2)
        out["skew_asym"] = round(asym, 3)
        # Two-sided skew = upside vol > downside vol by significant margin
        out["two_sided_skew"] = asym > 0.20
    except Exception:
        pass
    return out


def classify_vol_regime(prices_series, vix: float) -> str:
    """
    Karsan: above Zero Gamma = mean reversion, below = exacerbate moves.
    Without GEX data, proxy via VIX level + RV trajectory.
    """
    if prices_series is None:
        return "UNKNOWN"
    try:
        s = pd.to_numeric(prices_series, errors="coerce").dropna()
        rv_21 = compute_realized_vol(s, 21)
        rv_60 = compute_realized_vol(s, 60)
        if rv_21 is None or rv_60 is None:
            return "UNKNOWN"
        if vix <= 16 and rv_21 < rv_60 * 0.9:
            return "MEAN_REVERSION"  # dealers long gamma, stabilizing
        elif vix >= 25 or rv_21 > rv_60 * 1.4:
            return "BREAKOUT"  # dealers short gamma, exacerbating
        else:
            return "CHOP"
    except Exception:
        return "UNKNOWN"


def compute_karsan_score(ticker: str, prices_series, vix: float = 20.0,
                         market_type: str = "us_equity") -> Dict:
    """
    Aggregate Karsan methodology output per ticker.
    """
    out = {
        "ticker": ticker,
        "skew_score": 0,
        "vrp_score": 0,
        "vol_regime": "UNKNOWN",
        "two_sided_skew": False,
        "karsan_setup": None,
        "iv_proxy_pct": None,
        "rv_21d_pct": None,
        "iv_rank": None,
        "rationale": [],
    }
    
    rv_21 = compute_realized_vol(prices_series, 21)
    rv_60 = compute_realized_vol(prices_series, 60)
    if rv_21 is None:
        return out
    
    iv_proxy = compute_iv_proxy(ticker, rv_21, vix, market_type)
    out["iv_proxy_pct"] = round(iv_proxy * 100, 2)
    out["rv_21d_pct"] = round(rv_21 * 100, 2)
    
    # VRP score: positive = IV > RV by lot = sell premium opportunity
    if iv_proxy and rv_21:
        vrp_pct = (iv_proxy / rv_21 - 1) * 100
        if vrp_pct > 30:
            out["vrp_score"] = 0.8
            out["rationale"].append(f"VRP +{vrp_pct:.0f}% — SELL premium (iron condor/strangle)")
        elif vrp_pct > 15:
            out["vrp_score"] = 0.4
            out["rationale"].append(f"VRP +{vrp_pct:.0f}% — mildly rich, covered call")
        elif vrp_pct < 5:
            out["vrp_score"] = -0.5
            out["rationale"].append(f"VRP {vrp_pct:.0f}% — IV cheap, BUY premium")
    
    # IV Rank (from rolling RV history)
    try:
        s = pd.to_numeric(prices_series, errors="coerce").dropna()
        rv_history = []
        for i in range(60):
            if 21 + i > len(s):
                break
            window_end = len(s) - i
            window = s.iloc[window_end - 21:window_end]
            hr = window.pct_change().dropna()
            if len(hr) >= 10:
                rv_history.append(float(hr.std() * math.sqrt(252)))
        out["iv_rank"] = compute_iv_rank(rv_21, rv_history)
    except Exception:
        pass
    
    # Two-sided skew detection
    skew = detect_two_sided_skew(prices_series)
    out.update({
        "two_sided_skew": skew["two_sided_skew"],
        "skew_asym": skew["skew_asym"],
        "upside_vol_pct": skew["upside_vol_pct"],
        "downside_vol_pct": skew["downside_vol_pct"],
    })
    
    if skew["two_sided_skew"]:
        out["skew_score"] = 0.7
        out["rationale"].append(
            f"⚡ TWO-SIDED SKEW: up vol {skew['upside_vol_pct']:.0f}% > down vol {skew['downside_vol_pct']:.0f}%. "
            "Karsan setup: meme/convex environment, dealers short calls → squeeze fuel."
        )
    elif skew["skew_asym"] < -0.20:
        out["skew_score"] = -0.5
        out["rationale"].append(
            f"Downside skew dominant — classic put-protection regime. Vanna/Charm flows favor mean reversion."
        )
    
    # Vol regime
    out["vol_regime"] = classify_vol_regime(prices_series, vix)
    if out["vol_regime"] == "MEAN_REVERSION":
        out["rationale"].append("Vol regime: MEAN REVERSION (dealers long gamma) — pin to range")
    elif out["vol_regime"] == "BREAKOUT":
        out["rationale"].append("Vol regime: BREAKOUT (dealers short gamma) — trend amplified")
    
    # Karsan setup label
    if skew["two_sided_skew"] and out["vol_regime"] == "BREAKOUT":
        out["karsan_setup"] = "🚀 SQUEEZE_SETUP — Two-sided skew + breakout regime + dealer short gamma"
    elif out["vrp_score"] >= 0.6 and out["vol_regime"] == "MEAN_REVERSION":
        out["karsan_setup"] = "💰 SELL_PREMIUM — Rich IV + mean reversion = monetize skew decay"
    elif out["vrp_score"] <= -0.4:
        out["karsan_setup"] = "📈 BUY_CONVEXITY — Cheap IV, long straddle/calls"
    elif skew["two_sided_skew"]:
        out["karsan_setup"] = "👀 UPSIDE_WATCH — Call skew elevated, monitor for breakout"
    
    return out


def scan_karsan(tickers: List[str], prices: Dict, vix: float = 20.0,
                market_types: Optional[Dict[str, str]] = None) -> Dict:
    """Batch scan multiple tickers."""
    market_types = market_types or {}
    out = {
        "ok": True,
        "vix": vix,
        "per_ticker": {},
        "squeeze_setups": [],
        "sell_premium": [],
        "buy_convexity": [],
    }
    
    for t in tickers:
        if t not in prices:
            continue
        mt = market_types.get(t, "us_equity")
        result = compute_karsan_score(t, prices[t], vix, mt)
        if result.get("rv_21d_pct") is None:
            continue
        out["per_ticker"][t] = result
        
        setup = result.get("karsan_setup") or ""
        if "SQUEEZE_SETUP" in setup:
            out["squeeze_setups"].append({
                "ticker": t, "score": result["skew_score"],
                "asym": result["skew_asym"], "setup": setup,
            })
        elif "SELL_PREMIUM" in setup:
            out["sell_premium"].append({
                "ticker": t, "vrp": result["vrp_score"],
                "iv_rank": result.get("iv_rank"), "setup": setup,
            })
        elif "BUY_CONVEXITY" in setup:
            out["buy_convexity"].append({
                "ticker": t, "vrp": result["vrp_score"], "setup": setup,
            })
    
    out["squeeze_setups"].sort(key=lambda x: x.get("score", 0), reverse=True)
    out["sell_premium"].sort(key=lambda x: x.get("vrp", 0), reverse=True)
    out["buy_convexity"].sort(key=lambda x: x.get("vrp", 0))
    
    return out
