"""
lpm.py - Liquidity Pressure Model (BandarMetrics-compatible), FIXED + windowed option.

Reverse-engineered from 6 BandarMetrics reference tickers + the repo's
BANDARMETRICS_REVERSE_ENGINEERING.md (which independently derived CLV*Vol*C = value-based):
  1. STRUCTURE: signed money-flow (Chaikin A/D family), smoothed. Confirmed by BBCA
     price-down / LPM-up accumulation divergence.
  2. SCALING FIX: value-based  CLV * Volume * Price  (NOT volume-only). The EURO.JK reference
     (216k vol, |LPM| 1.24B) is impossible volume-based, natural value-based.
  3. OPEN QUESTION (now testable): cumulative-since-inception vs WINDOWED net-flow (rolling sum).
     The doc argues LPM (~4.6% of daily turnover) is too small for all-time cumulative -> likely
     windowed/net. calibrate_lpm.py tests BOTH and picks the fit.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def close_location_value(h, l, c):
    rng = (h - l).replace(0, np.nan)
    return (((c - l) - (h - c)) / rng).clip(-1, 1).fillna(0.0)


def money_flow(df, scaling="value_typical"):
    h = pd.to_numeric(df["High"], errors="coerce")
    l = pd.to_numeric(df["Low"], errors="coerce")
    c = pd.to_numeric(df["Close"], errors="coerce")
    v = pd.to_numeric(df["Volume"], errors="coerce").fillna(0.0)
    clv = close_location_value(h, l, c)
    px = 1.0 if scaling == "volume" else (c if scaling == "value_close" else (h + l + c) / 3.0)
    return (clv * v * px).fillna(0.0)


def lpm(df, scaling="value_typical", span=20, mode="cumulative", window=40):
    """mode='cumulative' -> cumsum; mode='windowed' -> rolling(window).sum. Then EMA(span)."""
    mf = money_flow(df, scaling=scaling)
    base = mf.rolling(window, min_periods=1).sum() if mode == "windowed" else mf.cumsum()
    return base.ewm(span=span, adjust=False).mean()


def lpm_last(df, **kw):
    s = lpm(df, **kw).dropna()
    return float(s.iloc[-1]) if len(s) else float("nan")


def lpm_features(df, slope_n=20, **kw):
    s = lpm(df, **kw).dropna()
    if len(s) <= slope_n:
        return {"lpm": float("nan"), "slope": 0.0, "state": "n/a"}
    last, prev = float(s.iloc[-1]), float(s.iloc[-1 - slope_n])
    slope = (last - prev) / (abs(prev) + 1e-9)
    state = "accumulation" if slope > 0.02 else "distribution" if slope < -0.02 else "neutral"
    return {"lpm": round(last, 2), "slope": round(slope, 4), "state": state}
