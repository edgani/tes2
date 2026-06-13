"""gcfis/core/change_core.py — change-centric foundation (P1+P2).

Both audits + real-data validation agree: markets pay for CHANGE, not level
(growth ACCELERATION was the predictive feature on real macro data, OOS).
Every engine combines metrics through these utils so nothing is level-only.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

def _s(x) -> pd.Series:
    return x if isinstance(x, pd.Series) else pd.Series(x)

def robust_z(x, window: int | None = None) -> pd.Series:
    """Median/MAD z-score (outlier-tolerant). Rolling if window given, else full-sample."""
    s = _s(x).astype(float)
    if window:
        med = s.rolling(window, min_periods=max(5, window // 3)).median()
        mad = (s - med).abs().rolling(window, min_periods=max(5, window // 3)).median()
    else:
        med = s.median(); mad = (s - med).abs().median()
    mad = mad.replace(0, np.nan) if isinstance(mad, pd.Series) else (mad or np.nan)
    z = 0.6745 * (s - med) / mad
    return z.replace([np.inf, -np.inf], np.nan)

def delta_z(x, lookback: int = 5, window: int | None = 252) -> pd.Series:
    """z-score of the CHANGE over `lookback` (1st-derivative, change-centric)."""
    return robust_z(_s(x).astype(float).diff(lookback), window=window)

def acceleration(x, lookback: int = 5, window: int | None = 252) -> pd.Series:
    """z-score of change-of-change (2nd-derivative). The validated-predictive feature."""
    d = _s(x).astype(float).diff(lookback)
    return robust_z(d.diff(lookback), window=window)

def pct_rank(x, window: int = 252) -> pd.Series:
    """Rolling percentile rank in [0,1]."""
    s = _s(x).astype(float)
    return s.rolling(window, min_periods=max(10, window // 5)).apply(
        lambda a: (a[-1] >= a).mean(), raw=True)

def logistic(x, k: float = 1.0):
    return 1.0 / (1.0 + np.exp(-k * np.asarray(x, dtype=float)))

def to_100(z, k: float = 1.0):
    """Squash a z-score to 0..100."""
    return 100.0 * logistic(z, k)

def winsorize(x, z: float = 6.0) -> pd.Series:
    s = _s(x).astype(float)
    med = s.median(); mad = (s - med).abs().median() or 1e-9
    lim = z * mad / 0.6745
    return s.clip(med - lim, med + lim)

def last(x, default: float = 0.0) -> float:
    s = _s(x).dropna()
    return float(s.iloc[-1]) if len(s) else default

def fdr_bh(pvals, q: float = 0.05) -> np.ndarray:
    """Benjamini-Hochberg FDR mask (controls false positives in multi-testing)."""
    p = np.asarray(pvals, dtype=float); m = len(p)
    if m == 0:
        return np.array([], dtype=bool)
    order = np.argsort(p); ranked = p[order]
    passed = ranked <= (np.arange(1, m + 1) / m) * q
    keep = np.zeros(m, dtype=bool)
    if passed.any():
        keep[order[:np.max(np.where(passed)[0]) + 1]] = True
    return keep

def csd(returns, window: int = 60) -> pd.Series:
    """Critical Slowing Down early-warning: rising lag-1 autocorr + rising variance
    => system losing resilience near a tipping point (from dynamical-systems theory).
    Returns a 0..1 standardized 'approaching-criticality' signal."""
    r = _s(returns).astype(float).dropna()
    if len(r) < window + 10:
        return pd.Series(0.0, index=_s(returns).index)
    ar1 = r.rolling(window).apply(lambda a: np.corrcoef(a[:-1], a[1:])[0, 1]
                                  if a[:-1].std() > 1e-12 else 0.0, raw=True)
    var = r.rolling(window).var()
    sig = robust_z(ar1.diff(5)).clip(lower=0).fillna(0) + robust_z(var.diff(5)).clip(lower=0).fillna(0)
    return (sig / 2.0).reindex(_s(returns).index).fillna(0.0)
