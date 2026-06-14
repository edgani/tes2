"""accumulation.py — Accumulation score + Institutional Adoption Curve (Stage 1-5).
Catches the PLTR/SNDK pattern: enter on Stage2->3 (uncrowded -> crowding) transition.
RS = alpha (not return ratio); VE signed by price; crowding velocity = the timing edge."""
from __future__ import annotations
import numpy as np, pandas as pd
from ..core.change_core import robust_z, delta_z, pct_rank, last

def _alpha_rs(price: pd.Series, bench: pd.Series, win: int = 63) -> float:
    r = np.log(price).diff().dropna(); b = np.log(bench).diff().reindex(r.index).dropna(); r = r.reindex(b.index)
    if len(r) < win:
        return 0.0
    beta = np.cov(r.tail(win), b.tail(win))[0, 1] / (b.tail(win).var() or 1e-9)
    alpha = (r - beta * b)
    rs_line = alpha.rolling(win).mean()
    slope = last(rs_line.diff(10))
    return last(robust_z(alpha.cumsum())) + np.sign(slope) * min(abs(slope) * 50, 1.0)

def run_accumulation(ticker: str, price: pd.Series, bench: pd.Series, volume: pd.Series | None = None,
                     earnings_rev: pd.Series | None = None, inst_own: pd.Series | None = None,
                     options_oi: pd.Series | None = None, social: pd.Series | None = None,
                     short_int: pd.Series | None = None, lev_etf_exists: bool = False) -> dict:
    rs = _alpha_rs(price, bench)
    ve = 0.0
    if volume is not None and len(volume) > 60:
        ve_raw = last(robust_z(volume.rolling(20).mean() / volume.rolling(252).mean()))
        ptrend = np.sign(last(np.log(price).diff(20)))
        ve = ptrend * ve_raw
    er = last(delta_z(earnings_rev)) if earnings_rev is not None else 0.0
    own = last(delta_z(inst_own)) if inst_own is not None else 0.0
    opt = last(robust_z(options_oi)) if options_oi is not None else 0.0
    acc = 0.30 * rs + 0.25 * ve + 0.20 * er + 0.15 * own + 0.10 * opt

    # crowding composite (use whatever is available)
    crowd_parts = []
    for x in (inst_own, options_oi, social, short_int):
        if x is not None and len(pd.Series(x).dropna()) > 20:
            crowd_parts.append(last(pct_rank(x)))
    if lev_etf_exists:
        crowd_parts.append(0.95)
    crowding = float(np.mean(crowd_parts)) * 100 if crowd_parts else 50.0 + 10 * np.tanh(rs)
    crowd_series = social if social is not None else (options_oi if options_oi is not None else volume)
    adoption_velocity = last(delta_z(crowd_series)) if crowd_series is not None else 0.0

    # RSI for staging
    d = price.diff(); up = d.clip(lower=0).rolling(14).mean(); dn = (-d.clip(upper=0)).rolling(14).mean()
    rsi = last(100 - 100 / (1 + up / (dn.replace(0, np.nan))), 50)

    cp = crowding
    if cp < 25 and rs <= 0: stage = "UNKNOWN"
    elif cp < 45 and (rs > 0 or ve > 0): stage = "SMART_MONEY"     # BUY ZONE
    elif cp < 70: stage = "INSTITUTIONAL"
    elif cp < 85: stage = "ETF_INCLUSION"
    else: stage = "RETAIL_MANIA"
    if lev_etf_exists or rsi > 80:
        stage = "RETAIL_MANIA"

    sweet_spot = (cp < 40) and (adoption_velocity > 0)
    exit_signal = (stage == "RETAIL_MANIA") or (cp > 85 and adoption_velocity < 0)
    return {"ticker": ticker, "accumulation": round(float(acc), 2), "rs": round(rs, 2), "ve": round(ve, 2),
            "stage": stage, "crowding": round(crowding, 1), "adoption_velocity": round(adoption_velocity, 2),
            "rsi": round(rsi, 1), "sweet_spot": bool(sweet_spot), "exit_signal": bool(exit_signal)}
