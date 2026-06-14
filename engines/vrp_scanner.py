"""engines/vrp_scanner.py — Volatility Risk Premium Scanner (Sprint 7)

Identifies vol mispricing by comparing implied vol proxy vs realized vol.
HIGH VRP = options expensive relative to actual movement = sell vol (sell premium)
LOW VRP  = options cheap relative to actual movement = buy vol (buy premium)

Without paid IV data, uses VIX-correlated proxy + realized vol regime.
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_realized_vol(s, window: int = 21) -> Optional[float]:
    """Annualized realized vol over rolling window."""
    if s is None:
        return None
    try:
        ser = pd.to_numeric(s, errors="coerce").dropna()
        if len(ser) < window:
            return None
        returns = ser.pct_change().dropna()
        if len(returns) < window:
            return None
        return float(returns.tail(window).std() * math.sqrt(252))
    except Exception:
        return None


def estimate_iv_proxy(ticker: str, ticker_rv: Optional[float], vix: float, market_type: str = "us_equity") -> Optional[float]:
    """
    Estimate implied vol proxy when actual options chain unavailable.
    
    Logic: IV typically trades at premium to RV (vol risk premium).
    Premium varies by:
      - Asset type (single stock > index)
      - VIX regime (higher VIX = wider IV/RV spread)
      - Liquidity
    """
    if ticker_rv is None or ticker_rv <= 0:
        return None
    
    # Beta to VIX (single stocks have higher IV than RV in calm markets)
    if ticker in ("SPY", "QQQ", "IWM", "DIA"):
        base_premium = 1.10  # 10% premium for index ETFs
    elif market_type == "crypto":
        base_premium = 1.20  # Crypto has wider IV/RV
    elif market_type == "commodity":
        base_premium = 1.15
    else:
        base_premium = 1.18  # Single stock typical
    
    # VIX-regime adjustment
    if vix >= 30:
        regime_adj = 1.10  # Stress widens premium
    elif vix <= 14:
        regime_adj = 0.95  # Complacency compresses premium
    else:
        regime_adj = 1.0
    
    iv_proxy = ticker_rv * base_premium * regime_adj
    return iv_proxy


def compute_iv_rank(current_iv: float, lookback_iv_history: List[float]) -> Optional[float]:
    """IV Rank: percentile of current IV vs history (0-100)."""
    if current_iv is None or not lookback_iv_history:
        return None
    h = [x for x in lookback_iv_history if x is not None and math.isfinite(x)]
    if not h:
        return None
    below = sum(1 for x in h if x < current_iv)
    return round(below / len(h) * 100, 1)


def scan_vrp(tickers: List[str], prices: Dict, vix: float = 20.0) -> Dict:
    """
    Scan tickers for VRP opportunities.
    
    Returns:
      - high_vrp_sell_premium: tickers where IV >> RV (sell options/spreads)
      - low_vrp_buy_premium:   tickers where IV ~= RV (buy options cheap)
      - per_ticker_breakdown
    """
    out = {
        "ok": True,
        "vix_regime": vix,
        "per_ticker": {},
        "high_vrp_sell_premium": [],
        "low_vrp_buy_premium": [],
        "calls_to_action": [],
    }
    
    for ticker in tickers:
        s = prices.get(ticker)
        if s is None:
            continue
        
        rv_21d = compute_realized_vol(s, 21)
        rv_60d = compute_realized_vol(s, 60)
        if rv_21d is None or rv_60d is None:
            continue
        
        iv_proxy = estimate_iv_proxy(ticker, rv_21d, vix)
        if iv_proxy is None:
            continue
        
        # VRP = IV / RV - 1 (positive = expensive options)
        vrp_pct = (iv_proxy / max(rv_21d, 0.01) - 1) * 100
        
        # RV trend (rising RV = vol expansion regime)
        rv_trend = "RISING" if rv_21d > rv_60d * 1.15 else "FALLING" if rv_21d < rv_60d * 0.85 else "STABLE"
        
        # Build IV history (60d rolling) for IV rank
        try:
            ser = pd.to_numeric(s, errors="coerce").dropna()
            rv_history = []
            for i in range(min(60, len(ser) - 21)):
                window = ser.iloc[-(i + 21):-i] if i > 0 else ser.tail(21)
                hr = window.pct_change().dropna()
                if len(hr) >= 10:
                    rv_history.append(float(hr.std() * math.sqrt(252)))
            iv_proxy_history = [r * 1.15 for r in rv_history]  # apply same multiplier
            iv_rank = compute_iv_rank(iv_proxy, iv_proxy_history)
        except Exception:
            iv_rank = None
        
        per_ticker = {
            "rv_21d_pct": round(rv_21d * 100, 2),
            "rv_60d_pct": round(rv_60d * 100, 2),
            "iv_proxy_pct": round(iv_proxy * 100, 2),
            "vrp_pct": round(vrp_pct, 1),
            "iv_rank": iv_rank,
            "rv_trend": rv_trend,
            "signal": None,
            "action": None,
        }
        
        # Signal generation
        if vrp_pct > 30 and (iv_rank or 50) > 70:
            per_ticker["signal"] = "🔴 IV EXPENSIVE — sell premium"
            per_ticker["action"] = "Sell iron condor / strangle / covered call"
            out["high_vrp_sell_premium"].append({
                "ticker": ticker,
                "vrp_pct": round(vrp_pct, 1),
                "iv_rank": iv_rank,
                "rv_21d_pct": round(rv_21d * 100, 2),
            })
        elif vrp_pct < 5 and (iv_rank or 50) < 30:
            per_ticker["signal"] = "🟢 IV CHEAP — buy premium"
            per_ticker["action"] = "Buy straddle / call / put depending on direction"
            out["low_vrp_buy_premium"].append({
                "ticker": ticker,
                "vrp_pct": round(vrp_pct, 1),
                "iv_rank": iv_rank,
                "rv_21d_pct": round(rv_21d * 100, 2),
            })
        elif vrp_pct > 10:
            per_ticker["signal"] = "🟡 IV slightly elevated"
            per_ticker["action"] = "Consider covered call / put credit spread"
        else:
            per_ticker["signal"] = "⚪ Fair pricing"
            per_ticker["action"] = "Trade direction not vol"
        
        out["per_ticker"][ticker] = per_ticker
    
    # Sort lists
    out["high_vrp_sell_premium"].sort(key=lambda x: x["vrp_pct"], reverse=True)
    out["low_vrp_buy_premium"].sort(key=lambda x: x["vrp_pct"])
    
    # Top calls-to-action
    for item in out["high_vrp_sell_premium"][:3]:
        out["calls_to_action"].append(
            f"🔴 SELL PREMIUM {item['ticker']}: VRP +{item['vrp_pct']:.0f}%, IV rank {item['iv_rank']}"
        )
    for item in out["low_vrp_buy_premium"][:3]:
        out["calls_to_action"].append(
            f"🟢 BUY PREMIUM {item['ticker']}: VRP {item['vrp_pct']:.0f}%, IV rank {item['iv_rank']}"
        )
    
    return out
