"""bandarmetrics.py — clean BM metrics + a CALIBRATION HARNESS to exact-match a reference app.

The metric DEFINITIONS are reverse-engineered from BandarMetrics' visible outputs (already
targeted in flow_regime.py). The remaining unknowns to hit EXACT numbers are conventions the
reference app doesn't publish:
  - Corr_F window length W (BM shows one number; we don't know its lookback)
  - smoothing spans (corr/par)
  - Par_F aggregation: mean of daily ratios vs Σ(FB+FS)/Σ(2·Value) over the window
  - whether Value = close·volume or exchange-reported turnover

Rather than guess, calibrate(): given a stock's daily series AND its reference (Corr_F, Par_F),
sweep the conventions and find the ONE parameter set that reproduces the reference numbers across
ALL provided stocks simultaneously. With ≥2 reference points (e.g. TPIA 0.711/30.93% and
BREN −0.188/50.74%) the parameter set is identifiable. This is reverse-engineering from known
outputs, not curve-fitting a single point.

Required per stock: a DataFrame with columns
  date, open, high, low, close, volume, value(optional), fb(foreign buy value), fs(foreign sell value)
IDX is blocked in this sandbox, so you export this (e.g. from your data source) and run calibrate
locally / on Cloud. The harness is unit-tested here on synthetic data: it recovers a hidden window.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

PAR_AGG = ("mean_daily", "sum_ratio")


def _ensure_value(df: pd.DataFrame) -> pd.Series:
    if "value" in df and df["value"].notna().any():
        return pd.to_numeric(df["value"], errors="coerce").clip(lower=1e-9)
    return (pd.to_numeric(df["close"], errors="coerce") *
            pd.to_numeric(df["volume"], errors="coerce")).clip(lower=1e-9)


def compute_bm(df: pd.DataFrame, window: int = 60, corr_smooth: int = 8,
               par_smooth: int = 20, par_agg: str = "mean_daily") -> dict:
    """Return the BM metric stack for the LAST bar, given conventions."""
    c = pd.to_numeric(df["close"], errors="coerce")
    h = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    vol = pd.to_numeric(df["volume"], errors="coerce").clip(lower=1e-9)
    val = _ensure_value(df)
    fb = pd.to_numeric(df["fb"], errors="coerce")
    fs = pd.to_numeric(df["fs"], errors="coerce")
    fn = fb - fs                                                   # Net Buy/Sell F (foreign net value)

    # Corr_F: price LEVEL vs CUMULATIVE foreign net, rolling window, optional EWM smoothing
    corr = c.rolling(window, min_periods=max(2, window // 2)).corr(fn.cumsum()).clip(-1, 1)
    corr_f = corr.ewm(span=corr_smooth, adjust=False).mean() if corr_smooth > 1 else corr

    # Par_F: foreign participation, two conventions
    daily_par = ((fb + fs) / (2.0 * val)).clip(0, 1)
    if par_agg == "sum_ratio":
        par_f_series = ((fb + fs).rolling(window, min_periods=2).sum()
                        / (2.0 * val.rolling(window, min_periods=2).sum())).clip(0, 1)
    else:  # mean_daily
        par_f_series = daily_par.ewm(span=par_smooth, adjust=False).mean() if par_smooth > 1 else daily_par

    # LPM: cumulative (close - vwap) * volume, smoothed
    tp = (h + low + c) / 3.0
    vwap = ((tp * vol).rolling(20, min_periods=20).sum() / vol.rolling(20, min_periods=20).sum())
    lpm = ((c - vwap) * vol).fillna(0.0).cumsum().ewm(span=20, adjust=False).mean()

    return {
        "corr_f": float(corr_f.iloc[-1]) if np.isfinite(corr_f.iloc[-1]) else None,
        "par_f": float(par_f_series.iloc[-1]) if np.isfinite(par_f_series.iloc[-1]) else None,
        "lpm": float(lpm.iloc[-1]) if np.isfinite(lpm.iloc[-1]) else None,
        "net_foreign": float(fn.sum()),
        "volume": float(vol.sum()),
        "_series": {"corr_f": corr_f, "par_f": par_f_series},
    }


def calibrate(stocks: dict, targets: dict,
              windows=range(20, 121, 5), corr_smooths=(1, 5, 8, 13),
              par_smooths=(1, 10, 20), par_aggs=PAR_AGG) -> dict:
    """Solve for the convention set reproducing reference numbers across ALL stocks at once.

    stocks:  {ticker: df}              targets: {ticker: {"corr_f": x, "par_f": y}}
    Returns the best (window, corr_smooth, par_smooth, par_agg) + achieved values + error.
    """
    best = None
    for w in windows:
        for cs in corr_smooths:
            for ps in par_smooths:
                for agg in par_aggs:
                    err, achieved, ok = 0.0, {}, True
                    for tkr, df in stocks.items():
                        if tkr not in targets:
                            continue
                        m = compute_bm(df, window=w, corr_smooth=cs, par_smooth=ps, par_agg=agg)
                        if m["corr_f"] is None or m["par_f"] is None:
                            ok = False; break
                        tg = targets[tkr]
                        e = 0.0
                        if "corr_f" in tg:
                            e += abs(m["corr_f"] - tg["corr_f"])
                        if "par_f" in tg:
                            e += abs(m["par_f"] - tg["par_f"])
                        err += e
                        achieved[tkr] = {"corr_f": round(m["corr_f"], 3), "par_f": round(m["par_f"], 4)}
                    if not ok:
                        continue
                    cand = {"window": w, "corr_smooth": cs, "par_smooth": ps, "par_agg": agg,
                            "total_abs_error": round(err, 4), "achieved": achieved}
                    if best is None or cand["total_abs_error"] < best["total_abs_error"]:
                        best = cand
    if best is None:
        return {"ok": False, "reason": "no parameter set produced finite metrics (check data columns)"}
    best["ok"] = True
    best["verdict"] = ("EXACT-MATCH" if best["total_abs_error"] < 0.02 else
                       "CLOSE — refine grid / check Value convention" if best["total_abs_error"] < 0.1 else
                       "NO MATCH — definition differs; need more reference points")
    return best
