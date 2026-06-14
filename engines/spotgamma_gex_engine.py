"""engines/spotgamma_gex_engine.py — Dealer GEX Framework (Sprint 9)

Replicates SpotGamma's methodology (Tier 1 — free data only):
  - GEX per strike (when options chain available via yfinance)
  - Zero Gamma approximation
  - Call Wall / Put Wall identification
  - Expected Move (ATM straddle approximation)
  - Compass Scanner (2D: IV Rank vs RV-based directional positioning)

Tier 2 NOT implemented (requires paid feeds):
  - HIRO real-time (OPRA tick data)
  - Synthetic OI Model (trade-level categorization)
  - Dark Pool Indicator
  - Exact Volatility Trigger formula (proprietary)

Methodology source: SpotGamma documentation + FlashAlpha backtest validation
"""
from __future__ import annotations

import math
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# SpotGamma DDOI Positioning Assumption
# Index products: dealers short puts (-1 multiplier), long calls (+1 multiplier)
# Equity products: dealers short BOTH puts and calls
INDEX_TICKERS = {"SPY", "QQQ", "IWM", "DIA", "^GSPC", "^NDX", "^RUT", "^DJI"}


def is_index_ticker(ticker: str) -> bool:
    return ticker.upper() in INDEX_TICKERS or ticker.startswith("^")


def compute_gamma_bs(spot: float, strike: float, t: float, sigma: float,
                     r: float = 0.04) -> float:
    """Black-Scholes gamma. t in years."""
    if spot <= 0 or strike <= 0 or t <= 0 or sigma <= 0:
        return 0.0
    try:
        d1 = (math.log(spot / strike) + (r + 0.5 * sigma ** 2) * t) / (sigma * math.sqrt(t))
        # Normal PDF
        pdf = math.exp(-0.5 * d1 ** 2) / math.sqrt(2 * math.pi)
        gamma = pdf / (spot * sigma * math.sqrt(t))
        return gamma
    except Exception:
        return 0.0


def compute_gex_from_chain(
    ticker: str,
    spot: float,
    chain_calls: List[Dict],  # [{strike, open_interest, iv, days_to_exp}]
    chain_puts: List[Dict],
    contract_size: int = 100,
) -> Dict:
    """
    Compute GEX per strike from options chain.
    Returns: total_gex, per_strike_gex, call_wall, put_wall, zero_gamma_approx
    """
    out = {
        "ticker": ticker, "spot": spot, "total_gex_bn": 0,
        "call_gex_bn": 0, "put_gex_bn": 0,
        "call_wall": None, "put_wall": None, "zero_gamma_approx": None,
        "regime": "UNKNOWN", "per_strike": {},
    }
    
    if not chain_calls and not chain_puts:
        return out
    
    is_idx = is_index_ticker(ticker)
    per_strike = {}
    
    # Process calls
    for opt in (chain_calls or []):
        strike = opt.get("strike")
        oi = opt.get("open_interest", 0) or 0
        iv = opt.get("iv", 0) or 0
        days = opt.get("days_to_exp", 30) or 30
        if not (strike and oi > 0 and iv > 0):
            continue
        t = max(days / 365.0, 1/365.0)
        gamma = compute_gamma_bs(spot, strike, t, iv)
        # GEX formula: gamma × OI × contract_size × spot² × 0.01
        gex = gamma * oi * contract_size * (spot ** 2) * 0.01
        # Index: dealers long calls → +gamma; Equity: dealers short calls → -gamma
        sign = 1 if is_idx else -1
        gex *= sign
        per_strike.setdefault(strike, {"call_gex": 0, "put_gex": 0})
        per_strike[strike]["call_gex"] += gex
    
    # Process puts
    for opt in (chain_puts or []):
        strike = opt.get("strike")
        oi = opt.get("open_interest", 0) or 0
        iv = opt.get("iv", 0) or 0
        days = opt.get("days_to_exp", 30) or 30
        if not (strike and oi > 0 and iv > 0):
            continue
        t = max(days / 365.0, 1/365.0)
        gamma = compute_gamma_bs(spot, strike, t, iv)
        gex = gamma * oi * contract_size * (spot ** 2) * 0.01
        # Both index and equity: dealers short puts → -gamma
        gex *= -1
        per_strike.setdefault(strike, {"call_gex": 0, "put_gex": 0})
        per_strike[strike]["put_gex"] += gex
    
    # Aggregate
    total_call_gex = sum(s.get("call_gex", 0) for s in per_strike.values())
    total_put_gex = sum(s.get("put_gex", 0) for s in per_strike.values())
    total_gex = total_call_gex + total_put_gex
    
    out["call_gex_bn"] = round(total_call_gex / 1e9, 3)
    out["put_gex_bn"] = round(total_put_gex / 1e9, 3)
    out["total_gex_bn"] = round(total_gex / 1e9, 3)
    out["per_strike"] = {str(k): v for k, v in per_strike.items()}
    
    # Regime classification
    if total_gex > 1e9:
        out["regime"] = "POSITIVE_GAMMA"  # mean-reverting, dealers stabilize
    elif total_gex < -1e9:
        out["regime"] = "NEGATIVE_GAMMA"  # amplifying, dealers exacerbate
    else:
        out["regime"] = "NEUTRAL"
    
    # Call Wall = strike with largest call_gex above spot
    call_wall_candidates = [(k, v["call_gex"]) for k, v in per_strike.items() if k > spot]
    if call_wall_candidates:
        cw = max(call_wall_candidates, key=lambda x: abs(x[1]))
        out["call_wall"] = float(cw[0])
    
    # Put Wall = strike with largest put_gex below spot (most negative)
    put_wall_candidates = [(k, v["put_gex"]) for k, v in per_strike.items() if k < spot]
    if put_wall_candidates:
        pw = min(put_wall_candidates, key=lambda x: x[1])
        out["put_wall"] = float(pw[0])
    
    # Zero Gamma approximation: linear interpolation of cumulative GEX vs price
    if len(per_strike) >= 5:
        sorted_strikes = sorted(per_strike.keys())
        cumulative_gex = []
        running = 0
        for s in sorted_strikes:
            running += per_strike[s]["call_gex"] + per_strike[s]["put_gex"]
            cumulative_gex.append((s, running))
        # Find zero crossing
        for i in range(len(cumulative_gex) - 1):
            s1, g1 = cumulative_gex[i]
            s2, g2 = cumulative_gex[i + 1]
            if (g1 <= 0 <= g2) or (g1 >= 0 >= g2):
                # Linear interpolation
                if g2 - g1 != 0:
                    zero = s1 + (s2 - s1) * (-g1 / (g2 - g1))
                    out["zero_gamma_approx"] = round(zero, 2)
                break
    
    return out


def compute_expected_move(spot: float, atm_iv: float, days: int = 21) -> Dict:
    """
    Expected move = spot × IV × sqrt(t/365)
    """
    if spot <= 0 or atm_iv <= 0:
        return {"days": days, "move_pct": None, "move_abs": None, "high": None, "low": None}
    t = days / 365.0
    move = spot * atm_iv * math.sqrt(t)
    move_pct = move / spot * 100
    return {
        "days": days,
        "move_pct": round(move_pct, 2),
        "move_abs": round(move, 2),
        "high": round(spot + move, 2),
        "low": round(spot - move, 2),
        "atm_iv_pct": round(atm_iv * 100, 2),
    }


def compute_proxy_gex(ticker: str, prices_series, vix: float = 20.0,
                      proxy_oi: int = 50000) -> Dict:
    """
    PROXY GEX when actual options chain unavailable.
    Estimate using price/vol-implied dealer positioning.
    """
    out = {
        "ticker": ticker, "spot": None, "regime": "UNKNOWN",
        "estimated_gex_bn": None, "call_wall_proxy": None, "put_wall_proxy": None,
        "expected_move_21d": None, "is_proxy": True,
    }
    
    if prices_series is None:
        return out
    try:
        s = pd.to_numeric(prices_series, errors="coerce").dropna()
        if len(s) < 60:
            return out
        spot = float(s.iloc[-1])
        out["spot"] = spot
        
        rets = s.pct_change().dropna()
        rv = float(rets.tail(21).std() * math.sqrt(252))
        atm_iv = rv * (1.10 if is_index_ticker(ticker) else 1.20)
        
        # Approximate Call Wall: spot × (1 + 1.5σ over 21d)
        sigma_21d = rv * math.sqrt(21/365.0)
        out["call_wall_proxy"] = round(spot * (1 + 1.5 * sigma_21d), 2)
        out["put_wall_proxy"] = round(spot * (1 - 1.5 * sigma_21d), 2)
        
        # Regime proxy from VIX + RV trajectory
        rv_60 = float(rets.tail(60).std() * math.sqrt(252))
        if vix <= 16 and rv < rv_60 * 0.9:
            out["regime"] = "POSITIVE_GAMMA_PROXY"
        elif vix >= 25 or rv > rv_60 * 1.4:
            out["regime"] = "NEGATIVE_GAMMA_PROXY"
        else:
            out["regime"] = "NEUTRAL_PROXY"
        
        out["expected_move_21d"] = compute_expected_move(spot, atm_iv, 21)
    except Exception as e:
        logger.debug(f"Proxy GEX failed for {ticker}: {e}")
    
    return out


def compass_scanner(tickers: List[str], prices: Dict, vix: float = 20.0) -> Dict:
    """
    SpotGamma's Compass Scanner — 2D grid: IV Rank × Directional positioning.
    Categorize each ticker into 4 quadrants.
    """
    from engines.karsan_vol_scanner import compute_karsan_score
    
    out = {
        "ok": True,
        "high_iv_bullish": [],   # rich vol, upside bias = sell vol on rallies
        "high_iv_bearish": [],   # rich vol, downside bias = sell vol on dips
        "low_iv_bullish": [],    # cheap vol, upside bias = buy calls
        "low_iv_bearish": [],    # cheap vol, downside bias = buy puts
        "two_sided_outliers": [],  # extreme skew asymmetry
    }
    
    for t in tickers:
        if t not in prices:
            continue
        k = compute_karsan_score(t, prices[t], vix)
        if k.get("iv_rank") is None:
            continue
        iv_rank = k["iv_rank"]
        skew_asym = k.get("skew_asym", 0)
        ticker_data = {
            "ticker": t,
            "iv_rank": iv_rank,
            "skew_asym": skew_asym,
            "vrp_score": k.get("vrp_score", 0),
        }
        # Categorize
        if iv_rank >= 70 and skew_asym >= 0:
            out["high_iv_bullish"].append(ticker_data)
        elif iv_rank >= 70 and skew_asym < 0:
            out["high_iv_bearish"].append(ticker_data)
        elif iv_rank <= 30 and skew_asym >= 0:
            out["low_iv_bullish"].append(ticker_data)
        elif iv_rank <= 30 and skew_asym < 0:
            out["low_iv_bearish"].append(ticker_data)
        # Two-sided outliers
        if k.get("two_sided_skew") and abs(skew_asym) > 0.3:
            out["two_sided_outliers"].append(ticker_data)
    
    # Sort by relevance
    out["high_iv_bullish"].sort(key=lambda x: x["iv_rank"], reverse=True)
    out["high_iv_bearish"].sort(key=lambda x: x["iv_rank"], reverse=True)
    out["low_iv_bullish"].sort(key=lambda x: x["iv_rank"])
    out["low_iv_bearish"].sort(key=lambda x: x["iv_rank"])
    out["two_sided_outliers"].sort(key=lambda x: x["skew_asym"], reverse=True)
    
    return out


def run_spotgamma_scanner(prices: Dict, vix: float = 20.0,
                          focus_tickers: Optional[List[str]] = None) -> Dict:
    """
    Master entry: run GEX/Compass scanner across key liquid tickers.
    For tickers without options chain data, use proxy GEX.
    """
    focus = focus_tickers or ["SPY", "QQQ", "IWM", "NVDA", "TSLA", "AAPL", "MSFT", "META",
                              "GOOGL", "AMZN", "AMD", "GLD", "TLT"]
    
    out = {
        "ok": True,
        "scanner_type": "spotgamma_proxy",
        "vix": vix,
        "per_ticker_proxy_gex": {},
        "compass": {},
        "note": "Proxy GEX only — install options chain feed (CBOE/OPRA) for actual dealer GEX.",
    }
    
    for t in focus:
        if t in prices:
            out["per_ticker_proxy_gex"][t] = compute_proxy_gex(t, prices[t], vix)
    
    # Compass scanner
    out["compass"] = compass_scanner(focus, prices, vix)
    
    return out
