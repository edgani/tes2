"""backtest.py — honest walk-forward validation. NO curve-fit, NO look-ahead, NO fake 100%.
Reports cross-sectional IC + permutation p, long-short decile Sharpe, Wilson CI (non-overlap),
and Probabilistic/Deflated Sharpe. Hard rule: perm_p>=0.05 OR DSR<0.95 => NOISE, do not trade."""
from __future__ import annotations
import numpy as np, pandas as pd
from scipy.stats import norm

def forward_return(close: pd.DataFrame, h: int) -> pd.DataFrame:
    return np.log(close.shift(-h) / close)

def cross_sectional_ic(signal: pd.DataFrame, fwd: pd.DataFrame, rebalance: int) -> tuple[float, list]:
    """Spearman IC per rebalance date (non-overlapping), averaged. Returns (mean_ic, per_date_ics)."""
    dates = signal.index[::rebalance]
    ics = []
    for d in dates:
        s = signal.loc[d].dropna(); f = fwd.loc[d].dropna()
        common = s.index.intersection(f.index)
        if len(common) < 20:
            continue
        ic = s[common].rank().corr(f[common].rank())
        if np.isfinite(ic):
            ics.append(ic)
    return (float(np.mean(ics)) if ics else 0.0), ics

def permutation_pvalue(signal: pd.DataFrame, fwd: pd.DataFrame, rebalance: int,
                       observed_ic: float, n: int = 300, seed: int = 0) -> float:
    """Shuffle signal cross-sectionally each date; fraction of shuffles with |IC|>=|observed|."""
    rng = np.random.default_rng(seed)
    dates = signal.index[::rebalance]; ge = 0
    for _ in range(n):
        ics = []
        for d in dates:
            s = signal.loc[d].dropna(); f = fwd.loc[d].dropna()
            common = s.index.intersection(f.index)
            if len(common) < 20:
                continue
            perm = rng.permutation(s[common].values)
            ic = pd.Series(perm, index=common).rank().corr(f[common].rank())
            if np.isfinite(ic):
                ics.append(ic)
        if ics and abs(np.mean(ics)) >= abs(observed_ic):
            ge += 1
    return (ge + 1) / (n + 1)

def long_short_decile(signal: pd.DataFrame, fwd: pd.DataFrame, rebalance: int) -> dict:
    """Top-decile minus bottom-decile, held `rebalance` days (non-overlapping). Honest Sharpe + DSR."""
    dates = signal.index[::rebalance]; rets = []
    for d in dates:
        s = signal.loc[d].dropna(); f = fwd.loc[d].dropna()
        common = s.index.intersection(f.index)
        if len(common) < 30:
            continue
        s = s[common]; f = f[common]
        q = s.quantile([0.1, 0.9])
        longs = f[s >= q.iloc[1]].mean(); shorts = f[s <= q.iloc[0]].mean()
        if np.isfinite(longs) and np.isfinite(shorts):
            rets.append(longs - shorts)
    r = np.array(rets)
    if len(r) < 10:
        return {"ok": False, "n": len(r)}
    freq = 252 / rebalance
    sr_obs = r.mean() / (r.std(ddof=1) or 1e-9)            # per-trade Sharpe
    sharpe_ann = sr_obs * np.sqrt(freq)
    hits = int((r > 0).sum()); n = len(r)
    return {"ok": True, "n_trades": n, "mean_ret": float(r.mean()), "sharpe_ann": float(sharpe_ann),
            "hit_rate": hits / n, "wilson_ci": wilson_ci(hits, n),
            "psr_vs0": probabilistic_sharpe(r, sr0=0.0),
            "dsr": deflated_sharpe(r, n_trials=10)}

def wilson_ci(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = hits / n; d = 1 + z**2 / n
    c = (p + z**2 / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / d
    return (round(max(0, c - h), 3), round(min(1, c + h), 3))

def probabilistic_sharpe(r: np.ndarray, sr0: float = 0.0) -> float:
    """PSR: prob that true Sharpe > sr0, adjusting for skew/kurtosis (Bailey & Lopez de Prado)."""
    r = np.asarray(r); n = len(r)
    if n < 5 or r.std(ddof=1) == 0:
        return 0.5
    sr = r.mean() / r.std(ddof=1)
    sk = float(pd.Series(r).skew()); ku = float(pd.Series(r).kurt()) + 3.0  # Pearson kurtosis
    denom = np.sqrt(1 - sk * sr + (ku - 1) / 4 * sr**2)
    return float(norm.cdf((sr - sr0) * np.sqrt(n - 1) / (denom or 1e-9)))

def deflated_sharpe(r: np.ndarray, n_trials: int = 10) -> float:
    """DSR: PSR vs the expected-max Sharpe under n_trials (haircut for selection bias)."""
    r = np.asarray(r); n = len(r)
    if n < 5 or r.std(ddof=1) == 0:
        return 0.5
    sr = r.mean() / r.std(ddof=1)
    var_sr = (1 + 0.5 * sr**2) / (n - 1)                  # sampling variance of SR estimate
    g = 0.5772156649
    e = np.e
    sr0 = np.sqrt(var_sr) * ((1 - g) * norm.ppf(1 - 1.0 / n_trials) + g * norm.ppf(1 - 1.0 / (n_trials * e)))
    return probabilistic_sharpe(r, sr0=sr0)

def no_lookahead_check(feature_fn, series: pd.Series, t: int = -50) -> bool:
    """feature at time t must be identical whether or not future data exists."""
    full = feature_fn(series); trunc = feature_fn(series.iloc[:t])
    a, b = full.iloc[t - 1], trunc.iloc[-1]
    return bool(np.isclose(a, b, equal_nan=True) or (pd.isna(a) and pd.isna(b)))

def verdict(perm_p: float, dsr: float) -> str:
    return "TRADEABLE" if (perm_p < 0.05 and dsr >= 0.95) else "NOISE — do not trade"
