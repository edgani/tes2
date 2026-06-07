"""sizing.py — position sizing / risk layer (C4). Fractional-Kelly x vol-target x VIX-bucket x
drawdown-guard, ALL gated on significance: edge not significant => size 0. No edge, no bet."""
from __future__ import annotations
import numpy as np, pandas as pd

def kelly_fraction(win_rate: float, payoff: float, frac: float = 0.5) -> float:
    """f* = (b*p - q)/b ; payoff b = avg_win/avg_loss. Returns fractional Kelly, clipped >=0."""
    if payoff <= 0:
        return 0.0
    p = float(np.clip(win_rate, 0, 1)); q = 1 - p
    f = (payoff * p - q) / payoff
    return float(max(0.0, f) * frac)

def vol_target_weight(returns: pd.Series, target_vol: float = 0.20, cap: float = 1.0) -> float:
    rv = pd.Series(returns).dropna().std() * np.sqrt(252)
    return float(min(cap, target_vol / rv)) if rv > 1e-9 else 0.0

def vix_bucket_mult(vix: float) -> float:
    if vix < 19: return 1.0          # investable
    if vix < 29: return 0.5          # chop
    return 0.1                        # extreme — risk off (Hedgeye 'fuck bucket')

def drawdown_guard(equity_curve: pd.Series, max_dd: float = 0.20) -> float:
    eq = pd.Series(equity_curve).dropna()
    if len(eq) < 2:
        return 1.0
    dd = 1 - eq.iloc[-1] / eq.cummax().iloc[-1]
    return float(np.clip(1 - dd / max_dd, 0.0, 1.0))      # scale toward 0 as DD -> max

def atr_stop(high, low, close, mult: float = 2.0, period: int = 14) -> float:
    h, l, c = map(lambda x: pd.Series(x).astype(float), (high, low, close))
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(period).mean().iloc[-1]
    return float(c.iloc[-1] - mult * atr)

def size_position(conviction: float, returns: pd.Series, edge_significant: bool,
                  vix: float = 16.0, equity_curve: pd.Series | None = None,
                  max_pct: float = 0.06, win_rate: float = 0.55, payoff: float = 1.8) -> dict:
    """Final allocation %. GATED: edge not significant -> 0 (no edge, no bet)."""
    if not edge_significant:
        return {"alloc_pct": 0.0, "gated": True, "reason": "edge not significant (perm_p>=0.05 or DSR<0.95)"}
    kelly = kelly_fraction(win_rate, payoff)
    voltgt = vol_target_weight(returns)
    vixm = vix_bucket_mult(vix)
    ddg = drawdown_guard(equity_curve) if equity_curve is not None else 1.0
    conv = float(np.clip(conviction / 100.0, 0, 1))
    alloc = max_pct * kelly * 2 * voltgt * vixm * ddg * conv     # kelly*2 so half-Kelly maps ~1.0 at base
    return {"alloc_pct": round(float(np.clip(alloc, 0, max_pct)), 4), "gated": False,
            "kelly": round(kelly, 3), "vol_target_w": round(voltgt, 3), "vix_mult": vixm,
            "dd_guard": round(ddg, 3), "conviction": round(conv, 2)}
