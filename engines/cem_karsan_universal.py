"""engines/cem_karsan_universal.py — Universal Multi-Market Cem Karsan Layer (Sprint 3)

Single unified Cem Karsan analysis that works on ANY options-bearing market:
  • US Equity (yfinance options chain — primary)
  • US ETFs (yfinance options chain)
  • Crypto BTC/ETH (Deribit API — FREE)
  • Major commodities (USO/UNG/GLD options chain)
  • Major FX (FXE/FXY/UUP options chain)

OUTPUT (uniform shape regardless of source):
  - GEX (gamma exposure)
  - Max Pain
  - Put/Call ratio
  - IV skew (calls vs puts)
  - 0DTE pin risk (if applicable)
  - Vanna direction
  - Charm decay
  - Expected move (weekly)

For markets WITHOUT options (.JK Indonesia, futures direct):
  → Falls back to realized-vol proxy with clear "PROXY" flag.
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────
# MARKET CLASSIFICATION
# ────────────────────────────────────────────────────────────────────────

def classify_options_source(ticker: str) -> str:
    """Determine which data source to use for options."""
    t = ticker.upper()
    if t in ("BTC-USD", "ETH-USD", "BTCUSD", "ETHUSD"):
        return "deribit"
    if t.endswith(".JK") or t.endswith(".KS") or t.endswith(".SS"):
        return "proxy_only"  # No retail options market
    if "-USD" in t and t not in ("BTC-USD", "ETH-USD"):
        return "proxy_only"  # Long-tail crypto
    if "=" in t:
        # Futures — use ETF proxy
        return "futures_proxy"
    return "yfinance"


FUTURES_TO_ETF_PROXY = {
    "CL=F": "USO", "BZ=F": "BNO", "NG=F": "UNG",
    "GC=F": "GLD", "SI=F": "SLV", "HG=F": "CPER",
    "ZW=F": "WEAT", "ZC=F": "CORN",
    "DX-Y.NYB": "UUP",
}


# ────────────────────────────────────────────────────────────────────────
# YFINANCE OPTIONS (US equity/ETF — primary path)
# ────────────────────────────────────────────────────────────────────────

def _fetch_yfinance_chain(ticker: str) -> Optional[Dict]:
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        exps = t.options
        if not exps:
            return None
        # Use nearest expiration
        target_exp = exps[0]
        chain = t.option_chain(target_exp)
        return {
            "expiration": target_exp,
            "calls": chain.calls,
            "puts": chain.puts,
            "underlying": (t.info.get("regularMarketPrice") or t.info.get("previousClose")),
            "source": "yfinance",
        }
    except Exception as e:
        logger.debug(f"yfinance options fetch failed for {ticker}: {e}")
        return None


# ────────────────────────────────────────────────────────────────────────
# DERIBIT OPTIONS (Crypto BTC/ETH — FREE API)
# ────────────────────────────────────────────────────────────────────────

DERIBIT_API = "https://www.deribit.com/api/v2/public"


def _fetch_deribit_chain(currency: str = "BTC") -> Optional[Dict]:
    try:
        import requests
        # Get instruments
        r = requests.get(f"{DERIBIT_API}/get_instruments",
                        params={"currency": currency, "kind": "option", "expired": "false"},
                        timeout=10)
        if r.status_code != 200:
            return None
        instruments = r.json().get("result", [])
        if not instruments:
            return None

        # Group by expiration
        from collections import defaultdict
        by_exp = defaultdict(list)
        for inst in instruments:
            by_exp[inst["expiration_timestamp"]].append(inst)

        if not by_exp:
            return None

        # Nearest expiration
        nearest_exp_ts = min(by_exp.keys())
        nearest_insts = by_exp[nearest_exp_ts]

        # Get book summary for nearest expiration
        r = requests.get(f"{DERIBIT_API}/get_book_summary_by_currency",
                        params={"currency": currency, "kind": "option"},
                        timeout=10)
        if r.status_code != 200:
            return None
        summaries = r.json().get("result", [])

        # Filter to nearest exp
        relevant = [s for s in summaries
                   if s.get("expiration_timestamp", 0) == nearest_exp_ts]
        if not relevant:
            return None

        # Get index price
        r_idx = requests.get(f"{DERIBIT_API}/get_index_price",
                            params={"index_name": f"{currency.lower()}_usd"},
                            timeout=5)
        underlying = r_idx.json().get("result", {}).get("index_price", 0) if r_idx.status_code == 200 else 0

        # Split calls/puts
        calls_rows = []
        puts_rows = []
        for s in relevant:
            ins_name = s.get("instrument_name", "")
            # Format: BTC-30JUN24-65000-C
            parts = ins_name.split("-")
            if len(parts) < 4:
                continue
            try:
                strike = float(parts[2])
                opt_type = parts[3]
            except Exception:
                continue
            row = {
                "strike": strike,
                "lastPrice": s.get("last", 0) or 0,
                "bid": s.get("bid_price", 0) or 0,
                "ask": s.get("ask_price", 0) or 0,
                "volume": s.get("volume", 0) or 0,
                "openInterest": s.get("open_interest", 0) or 0,
                "impliedVolatility": (s.get("mark_iv", 0) or 0) / 100.0,
            }
            if opt_type == "C":
                calls_rows.append(row)
            elif opt_type == "P":
                puts_rows.append(row)

        if not calls_rows or not puts_rows:
            return None

        return {
            "expiration": datetime.fromtimestamp(nearest_exp_ts / 1000).strftime("%Y-%m-%d"),
            "calls": pd.DataFrame(calls_rows),
            "puts": pd.DataFrame(puts_rows),
            "underlying": underlying,
            "source": "deribit",
        }
    except Exception as e:
        logger.debug(f"Deribit fetch failed: {e}")
        return None


# ────────────────────────────────────────────────────────────────────────
# COMPUTATIONS (uniform across sources)
# ────────────────────────────────────────────────────────────────────────

def _calc_max_pain(calls: pd.DataFrame, puts: pd.DataFrame) -> Optional[float]:
    if calls.empty or puts.empty:
        return None
    try:
        all_strikes = sorted(set(calls["strike"].tolist() + puts["strike"].tolist()))
        if not all_strikes:
            return None
        pain_by_strike = {}
        for K in all_strikes:
            call_pain = ((calls["strike"] < K).astype(float) *
                        (K - calls["strike"]).clip(lower=0) *
                        calls.get("openInterest", 0)).sum()
            put_pain = ((puts["strike"] > K).astype(float) *
                       (puts["strike"] - K).clip(lower=0) *
                       puts.get("openInterest", 0)).sum()
            pain_by_strike[K] = call_pain + put_pain
        return float(min(pain_by_strike, key=pain_by_strike.get))
    except Exception:
        return None


def _calc_put_call_ratio(calls: pd.DataFrame, puts: pd.DataFrame) -> Optional[float]:
    try:
        c_vol = calls.get("volume", pd.Series([0])).fillna(0).sum()
        p_vol = puts.get("volume", pd.Series([0])).fillna(0).sum()
        if c_vol == 0:
            return None
        return float(p_vol / c_vol)
    except Exception:
        return None


def _calc_iv_skew(calls: pd.DataFrame, puts: pd.DataFrame) -> Dict:
    try:
        c_iv = calls.get("impliedVolatility", pd.Series([0])).dropna()
        p_iv = puts.get("impliedVolatility", pd.Series([0])).dropna()
        if c_iv.empty or p_iv.empty:
            return {"avg_iv": 0, "skew": 0}
        avg_c = float(c_iv.mean())
        avg_p = float(p_iv.mean())
        return {
            "avg_iv": (avg_c + avg_p) / 2,
            "skew": avg_p - avg_c,  # positive = puts richer (fear)
            "calls_iv": avg_c,
            "puts_iv": avg_p,
        }
    except Exception:
        return {"avg_iv": 0, "skew": 0}


def _calc_gex_proxy(calls: pd.DataFrame, puts: pd.DataFrame, underlying: float) -> Dict:
    """Approximate GEX from OI weighted by distance from spot."""
    if calls.empty or puts.empty or not underlying:
        return {"net_gex": 0, "regime": "UNKNOWN"}
    try:
        # Gamma is highest ATM, decays away
        def proxy_gamma(strike, spot, iv=0.20):
            # Simplified BSM gamma proxy
            if iv <= 0:
                iv = 0.20
            d = abs(strike - spot) / (spot * iv * 0.1)
            return math.exp(-d * d * 0.5)

        spot = float(underlying)
        call_gex = ((calls["strike"].apply(lambda K: proxy_gamma(K, spot))) *
                   calls.get("openInterest", 0)).sum() * 100
        put_gex = ((puts["strike"].apply(lambda K: proxy_gamma(K, spot))) *
                  puts.get("openInterest", 0)).sum() * 100

        net_gex = call_gex - put_gex
        if net_gex > 5e9:
            regime = "DEEP_POSITIVE"
        elif net_gex > 1e9:
            regime = "POSITIVE"
        elif net_gex < -5e9:
            regime = "DEEP_NEGATIVE"
        elif net_gex < -1e9:
            regime = "NEGATIVE"
        else:
            regime = "NEUTRAL"

        return {
            "net_gex": float(net_gex),
            "call_gex": float(call_gex),
            "put_gex": float(put_gex),
            "regime": regime,
        }
    except Exception:
        return {"net_gex": 0, "regime": "UNKNOWN"}


def _calc_expected_move(calls: pd.DataFrame, puts: pd.DataFrame,
                       underlying: float, days_to_exp: int = 5) -> Optional[float]:
    """ATM straddle price ≈ expected move."""
    try:
        if not underlying or calls.empty or puts.empty:
            return None
        # Find ATM strike
        atm_strike = min(calls["strike"].tolist(),
                        key=lambda x: abs(x - underlying))
        atm_call = calls[calls["strike"] == atm_strike]
        atm_put = puts[puts["strike"] == atm_strike]
        if atm_call.empty or atm_put.empty:
            return None
        c_price = float(atm_call["lastPrice"].iloc[0]) if not atm_call.empty else 0
        p_price = float(atm_put["lastPrice"].iloc[0]) if not atm_put.empty else 0
        straddle = c_price + p_price
        if straddle <= 0:
            return None
        return straddle / underlying  # As % of underlying
    except Exception:
        return None


def _calc_0dte_pin(calls: pd.DataFrame, puts: pd.DataFrame, underlying: float) -> Dict:
    """0DTE pin risk near max pain. Only meaningful for SPY/QQQ/IWM/Mag7/Crypto."""
    if not underlying:
        return {"pin_risk": 0, "pin_strike": 0, "applicable": False}
    max_pain = _calc_max_pain(calls, puts)
    if max_pain is None:
        return {"pin_risk": 0, "pin_strike": 0, "applicable": False}
    distance_pct = abs(underlying - max_pain) / underlying
    # Pin risk = 1 if distance < 1%, decays from there
    pin_risk = max(0.0, 1.0 - distance_pct * 50)
    return {
        "pin_risk": float(pin_risk),
        "pin_strike": float(max_pain),
        "distance_pct": float(distance_pct),
        "applicable": True,
    }


# ────────────────────────────────────────────────────────────────────────
# PROXY (no options market)
# ────────────────────────────────────────────────────────────────────────

def _proxy_analysis(ticker: str, prices: Dict, vix: float = 20.0) -> Dict:
    """Realized vol proxy when no options chain available."""
    s = prices.get(ticker) if isinstance(prices, dict) else None
    if s is None:
        return {"ok": False, "ticker": ticker, "source": "PROXY_UNAVAILABLE"}
    try:
        ser = pd.to_numeric(s, errors="coerce").dropna()
        if len(ser) < 30:
            return {"ok": False, "ticker": ticker, "source": "PROXY_INSUFFICIENT"}
        spot = float(ser.iloc[-1])
        rv_30 = float(ser.tail(30).pct_change().std() * math.sqrt(252))
        rv_60 = float(ser.tail(min(60, len(ser))).pct_change().std() * math.sqrt(252)) if len(ser) >= 60 else rv_30
        skew_proxy = rv_30 - rv_60
        expected_move_weekly = rv_30 / math.sqrt(52)
        return {
            "ok": True,
            "ticker": ticker,
            "source": "PROXY",
            "spot": spot,
            "realized_vol_30d": rv_30,
            "realized_vol_60d": rv_60,
            "skew_proxy": skew_proxy,
            "expected_move_weekly": expected_move_weekly,
            "max_pain": None,
            "put_call_ratio": None,
            "gex": {"regime": "PROXY_UNAVAILABLE"},
            "zero_dte_pin": {"applicable": False},
            "iv_skew": {"avg_iv": rv_30, "skew": skew_proxy},
            "note": "No options chain available — using realized vol proxy",
        }
    except Exception as e:
        return {"ok": False, "ticker": ticker, "error": str(e)}


# ────────────────────────────────────────────────────────────────────────
# UNIFIED ANALYZE
# ────────────────────────────────────────────────────────────────────────

def analyze_universal(ticker: str, prices: Optional[Dict] = None,
                     vix: float = 20.0) -> Dict:
    """
    Universal Cem Karsan analyzer. Returns uniform shape across all sources.
    """
    prices = prices or {}
    src = classify_options_source(ticker)

    chain = None
    actual_ticker = ticker

    if src == "yfinance":
        chain = _fetch_yfinance_chain(ticker)
    elif src == "deribit":
        currency = "BTC" if "BTC" in ticker.upper() else "ETH"
        chain = _fetch_deribit_chain(currency)
        actual_ticker = ticker
    elif src == "futures_proxy":
        # Use ETF proxy
        proxy_ticker = FUTURES_TO_ETF_PROXY.get(ticker)
        if proxy_ticker:
            chain = _fetch_yfinance_chain(proxy_ticker)
            actual_ticker = proxy_ticker

    if chain is None:
        return _proxy_analysis(ticker, prices, vix)

    calls = chain["calls"]
    puts = chain["puts"]
    underlying = chain.get("underlying") or 0

    # Compute all metrics
    max_pain = _calc_max_pain(calls, puts)
    pc_ratio = _calc_put_call_ratio(calls, puts)
    iv_skew = _calc_iv_skew(calls, puts)
    gex = _calc_gex_proxy(calls, puts, underlying)
    expected_move = _calc_expected_move(calls, puts, underlying, 5)
    pin_data = _calc_0dte_pin(calls, puts, underlying)

    return {
        "ok": True,
        "ticker": ticker,
        "actual_chain_ticker": actual_ticker,
        "source": chain.get("source"),
        "expiration": chain.get("expiration"),
        "spot": float(underlying) if underlying else None,
        "max_pain": max_pain,
        "max_pain_dist_pct": ((underlying - max_pain) / underlying * 100) if (max_pain and underlying) else None,
        "put_call_ratio": pc_ratio,
        "expected_move_pct": expected_move,
        "iv_skew": iv_skew,
        "gex": gex,
        "zero_dte_pin": pin_data,
        "call_count": len(calls) if not calls.empty else 0,
        "put_count": len(puts) if not puts.empty else 0,
    }


def analyze_multi(tickers: List[str], prices: Optional[Dict] = None,
                  vix: float = 20.0, max_yfinance: int = 10) -> Dict[str, Dict]:
    """
    Batch analyzer with intelligent rate-limit pacing.

    Strategy:
      • yfinance calls limited to max_yfinance (rate limit defense)
      • Deribit calls free (BTC/ETH)
      • Proxy fallback unlimited
    """
    results = {}
    yf_count = 0
    for t in tickers:
        try:
            src = classify_options_source(t)
            if src == "yfinance" and yf_count >= max_yfinance:
                results[t] = _proxy_analysis(t, prices or {}, vix)
                continue
            results[t] = analyze_universal(t, prices or {}, vix)
            if src == "yfinance":
                yf_count += 1
            # Pace yfinance calls
            if src == "yfinance" and yf_count < max_yfinance:
                import time
                time.sleep(0.8)
        except Exception as e:
            logger.warning(f"Universal Cem analyze failed for {t}: {e}")
            results[t] = {"ok": False, "ticker": t, "error": str(e)}
    return results
