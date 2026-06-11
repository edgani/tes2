"""entry.py — L13 Entry Engine. GCFIS: Entry = 0.25*Trend+0.25*Momentum+0.20*Dealer+0.15*Liquidity
+0.15*Structure. Classifies Breakout/Pullback/Continuation/Mean-Reversion, GAMMA-AWARE:
  GEX<0 (momentum regime) -> Breakout/Continuation valid (dealers amplify)
  GEX>0 (mean-reversion regime) -> Pullback/Mean-Reversion valid (dealers fade)
Risk-range (Hedgeye-style) gives stop & target -> R/R. Wrong-regime entries are flagged INVALID."""
from __future__ import annotations
import numpy as np, pandas as pd
from ..core.change_core import robust_z, last

def _rsi(px: pd.Series, n: int = 14) -> float:
    d = px.diff(); up = d.clip(lower=0).rolling(n).mean(); dn = (-d.clip(upper=0)).rolling(n).mean()
    return last(100 - 100 / (1 + up / dn.replace(0, np.nan)), 50)

def _atr(px: pd.Series, n: int = 14) -> float:
    return last(px.diff().abs().rolling(n).mean(), px.std() * 0.02)  # close-only ATR proxy

def run_entry(price: pd.Series, direction: str, dealer: dict | None = None,
              liquidity_score: float = 50.0, k_atr: float = 2.0, rr_min: float = 1.5, long_only: bool = False) -> dict:
    px = pd.to_numeric(pd.Series(price), errors="coerce").dropna()
    if len(px) < 60:
        return {"ok": False, "reason": "insufficient history"}
    if long_only and direction == "short":          # buy-only market: a bearish read is WAIT/reduce, never a short
        return {"ok": True, "entry_type": "AVOID", "valid": False,
                "gamma_regime": (dealer or {}).get("regime", "unknown"),
                "warning": "long-only market — bearish/distribution, no short (WAIT or reduce if holding)",
                "entry_px": 0.0, "stop": 0.0, "target": 0.0, "rr": 0.0, "entry_score": 0.0}
    p = float(px.iloc[-1]); sma50 = px.rolling(50).mean().iloc[-1]; sma200 = px.rolling(200).mean().iloc[-1] if len(px) >= 200 else sma50
    hi20, lo20 = px.tail(20).max(), px.tail(20).min()
    pos = (p - lo20) / (hi20 - lo20) if hi20 > lo20 else 0.5
    ref = px.tail(20).mean(); sigma = px.pct_change().tail(20).std() * ref or (px.std() * 0.02)
    atr = _atr(px); rsi = _rsi(px)

    trend = float(np.tanh((p / sma50 - 1) * 10) + np.sign(sma50 - sma200) * 0.3)
    mom = float(np.tanh((rsi - 50) / 20))
    dsign = (dealer or {}).get("gex_sign", 0); gregime = (dealer or {}).get("regime", "unknown")
    # dealer contribution is direction-aware: momentum regime helps trend entries, mean-rev helps fades
    dealer_contrib = float(dsign) * (1 if direction == "long" else -1) * -1  # GEX<0 (momentum) aids trend
    liq = (liquidity_score - 50) / 50.0
    structure = float((pos - 0.5) * 2) if direction == "long" else float((0.5 - pos) * 2)
    entry_score = 0.25 * trend + 0.25 * mom + 0.20 * dealer_contrib + 0.15 * liq + 0.15 * structure

    near_hi, near_lo = pos > 0.8, pos < 0.2
    breaking = p >= hi20 * 0.999
    if direction == "long":
        if gregime == "momentum" and breaking: etype = "BREAKOUT"
        elif gregime == "momentum" and trend > 0: etype = "CONTINUATION"
        elif gregime == "mean_reversion" and near_lo and rsi < 38: etype = "MEAN_REVERSION"
        elif gregime == "mean_reversion" and near_lo: etype = "PULLBACK"
        elif breaking: etype = "BREAKOUT"
        elif near_lo: etype = "PULLBACK"
        else: etype = "CONTINUATION"
    else:  # short
        if gregime == "momentum" and p <= lo20 * 1.001: etype = "BREAKDOWN"
        elif gregime == "momentum" and trend < 0: etype = "CONTINUATION"
        elif gregime == "mean_reversion" and near_hi and rsi > 62: etype = "MEAN_REVERSION"
        elif gregime == "mean_reversion" and near_hi: etype = "BOUNCE_SHORT"
        elif p <= lo20 * 1.001: etype = "BREAKDOWN"
        elif near_hi: etype = "BOUNCE_SHORT"
        else: etype = "CONTINUATION"

    # gamma-validity: breakout/continuation need momentum regime; pullback/mean-rev need mean-rev regime
    trend_types = {"BREAKOUT", "BREAKDOWN", "CONTINUATION"}
    valid = True; warn = ""
    if gregime == "mean_reversion" and etype in trend_types:
        valid = False; warn = "breakout in positive-gamma (dealers fade) — likely to fail"
    if gregime == "momentum" and etype in {"PULLBACK", "MEAN_REVERSION", "BOUNCE_SHORT"}:
        warn = "fading a negative-gamma (momentum) tape — risky"

    # risk-range stop/target
    if direction == "long":
        if etype in {"PULLBACK", "MEAN_REVERSION"}:
            entry_px = min(p, ref - 0.5 * sigma); stop = entry_px - k_atr * atr; target = ref + 1.0 * sigma
        else:
            entry_px = p; stop = p - k_atr * atr; target = p + 2.0 * sigma
    else:
        if etype in {"BOUNCE_SHORT", "MEAN_REVERSION"}:
            entry_px = max(p, ref + 0.5 * sigma); stop = entry_px + k_atr * atr; target = ref - 1.0 * sigma
        else:
            entry_px = p; stop = p + k_atr * atr; target = p - 2.0 * sigma
    risk = abs(entry_px - stop); reward = abs(target - entry_px)
    rr = round(reward / risk, 2) if risk > 0 else 0.0
    if rr < rr_min: valid = False; warn = (warn + "; " if warn else "") + f"R/R {rr} < {rr_min}"
    return {"ok": True, "entry_type": etype, "entry_score": round(float(np.clip(entry_score, -1, 1)), 2),
            "gamma_regime": gregime, "valid": bool(valid), "warning": warn,
            "entry_px": round(entry_px, 2), "stop": round(stop, 2), "target": round(target, 2),
            "rr": rr, "rsi": round(rsi, 1), "risk_range": [round(ref - sigma, 2), round(ref + sigma, 2)]}
