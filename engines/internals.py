"""internals.py — doc-6/12 layers feasible from OHLCV (honest: internals/correlation, NOT causal):
multi-horizon alignment · relative-pair engine · divergence engine · dispersion-lite."""
from __future__ import annotations
import numpy as np, pandas as pd

def run_horizon(price) -> dict:
    """Multi-timeframe trend agreement (daily/weekly/monthly z) → alignment 0-100."""
    px = pd.to_numeric(pd.Series(price), errors="coerce").dropna()
    if len(px) < 130:
        return {"ok": False, "alignment": 50}
    r = np.log(px).diff()
    sd = float(r.tail(120).std() or 1e-9)
    signs, zs = {}, {}
    for name, n in (("daily", 20), ("weekly", 60), ("monthly", 120)):
        z = float(r.tail(n).sum() / (np.sqrt(n) * sd))
        zs[name + "_z"] = round(z, 2)
        signs[name] = 1 if z > 0.3 else -1 if z < -0.3 else 0
    align = 0.3 * signs["daily"] + 0.4 * signs["weekly"] + 0.3 * signs["monthly"]
    return {"ok": True, "signs": signs, **zs, "alignment": int(round(50 + 50 * align))}

_PAIRS = [
    ("gold/silver", ["XAUUSD", "GC=F", "GOLD"], ["XAGUSD", "SI=F", "SILVER"], "ratio UP = growth-fear / defensive tell"),
    ("gold/miners", ["XAUUSD", "GC=F", "GOLD"], ["GDX"], "metal up w/o miners = weak conviction"),
    ("semis/utilities", ["SOXX", "SMH"], ["XLU"], "AI risk appetite vs defensive rotation"),
    ("btc/dxy", ["BTCUSD", "BTC-USD", "BTCUSDT"], ["DXY", "DX=F"], "liquidity dependence (inverse)"),
    ("oil/energy-eq", ["USOIL", "WTI", "CL=F", "XTIUSD"], ["XLE"], "physical vs equity confirmation"),
    ("copper/gold", ["HG=F", "COPPER", "XCUUSD", "CPER"], ["XAUUSD", "GC=F", "GOLD"], "growth vs fear (doc-18)"),
    ("btc/eth", ["BTCUSD", "BTC-USD", "BTCUSDT"], ["ETHUSD", "ETH-USD", "ETHUSDT"], "quality vs alt-risk preference"),
]

_SINGLES = [("audjpy", ["AUDJPY", "AUDJPY=X"], "global risk appetite (carry barometer, doc-18)")]

def _close(v):
    if hasattr(v, "columns") and "Close" in getattr(v, "columns", []):
        v = v["Close"]
    return pd.to_numeric(pd.Series(v), errors="coerce").dropna()

def _find(prices: dict, aliases):
    up = {str(k).upper(): k for k in prices}
    for a in aliases:
        if a.upper() in up:
            return _close(prices[up[a.upper()]])
    return None

def run_internals(prices: dict, bench=None) -> dict:
    """Relative pairs (z of 20d ratio change) + divergences + breadth/concentration."""
    out = {"ok": True, "pairs": [], "divergences": [], "breadth": None, "top5_share": None}
    rets, above, tot = {}, 0, 0
    for k, v in prices.items():
        s = _close(v)
        if len(s) < 70:
            continue
        rets[k] = float(s.iloc[-1] / s.iloc[-21] - 1)
        tot += 1
        if float(s.iloc[-1]) > float(s.tail(50).mean()):
            above += 1
    if tot >= 5:
        out["breadth"] = round(above / tot, 2)
        pos = sorted((v for v in rets.values() if v > 0), reverse=True)
        if pos:
            out["top5_share"] = round(sum(pos[:5]) / (sum(pos) or 1e-9), 2)
    if bench is not None and out["breadth"] is not None:
        b = _close(bench)
        if len(b) > 30:
            bz = float(b.iloc[-1] / b.iloc[-21] - 1)
            if bz > 0.01 and out["breadth"] < 0.45:
                out["divergences"].append(f"index +{bz:.1%} on weak breadth {out['breadth']:.0%} — narrow fragility")
            if out["top5_share"] and out["top5_share"] > 0.75 and tot >= 8:
                out["divergences"].append(f"top-5 names = {out['top5_share']:.0%} of positive 20d returns — concentration risk")
    for name, aliases, note in _SINGLES:
        s = _find(prices, aliases)
        if s is None or len(s) < 150:
            continue
        ch = s.pct_change(20)
        z = float((ch.iloc[-1] - ch.tail(120).mean()) / (ch.tail(120).std() or 1e-9))
        out["pairs"].append({"pair": name, "z20": round(z, 2), "note": note})
    for name, aal, bal, note in _PAIRS:
        A, B = _find(prices, aal), _find(prices, bal)
        if A is None or B is None:
            continue
        ix = A.index.intersection(B.index)
        if len(ix) < 80:
            continue
        ch = (A.loc[ix] / B.loc[ix]).pct_change(20)
        z = float((ch.iloc[-1] - ch.tail(120).mean()) / (ch.tail(120).std() or 1e-9))
        out["pairs"].append({"pair": name, "z20": round(z, 2), "note": note})
        if name == "gold/silver" and z > 1.5:
            out["divergences"].append("gold/silver ratio spiking — defensive bid, growth fear")
        if name == "btc/dxy" and z < -1.5:
            out["divergences"].append("BTC underperforming a squeezing dollar — liquidity headwind")
    return out
