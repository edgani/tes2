"""engines/bottleneck_engine.py — Bottleneck Scanner (Clean)
Simplified version that imports reliably and produces Alpha Center data.
"""
from __future__ import annotations
import math
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

try:
    from config.settings import BOTTLENECK_PROFILES, TICKER_SECTOR, QUAD_ASSET_PERFORMANCE
except Exception:
    BOTTLENECK_PROFILES = {"generic": {"constraint": 0.5, "Q1": 0.5, "Q2": 0.5, "Q3": 0.5, "Q4": 0.5}}
    TICKER_SECTOR = {}
    QUAD_ASSET_PERFORMANCE = {}

def _ret(s, n):
    if s is None: return None
    s = pd.to_numeric(s, errors="coerce").dropna()
    if len(s) < n + 1: return None
    try:
        return float(s.iloc[-1] / s.iloc[-n-1] - 1)
    except:
        return None

def _rs(close, bench, n):
    if close is None or bench is None: return None
    c = pd.to_numeric(close, errors="coerce").dropna()
    b = pd.to_numeric(bench, errors="coerce").dropna()
    if len(c) < n + 1 or len(b) < n + 1: return None
    try:
        cr = float(c.iloc[-1] / c.iloc[-n-1] - 1)
        br = float(b.iloc[-1] / b.iloc[-n-1] - 1)
        return cr - br if abs(br) > 1e-10 else None
    except:
        return None

def _trend(close, n=63):
    c = pd.to_numeric(close, errors="coerce").dropna().tail(n).values
    if len(c) < 20: return False, False, "insufficient"
    half = max(len(c) // 3, 5)
    hh = float(np.max(c[-half:])) > float(np.max(c[:half])) * 1.003
    hl = float(np.min(c[-half:])) > float(np.min(c[:half])) * 1.003
    lh = float(np.max(c[-half:])) < float(np.max(c[:half])) * 0.997
    ll = float(np.min(c[-half:])) < float(np.min(c[:half])) * 0.997
    if hh and hl: return True, True, "uptrend"
    if lh and ll: return False, False, "downtrend"
    return hh, hl, "range"

def _acc(close, n):
    c = pd.to_numeric(close, errors="coerce").dropna().tail(n)
    if len(c) < 15: return 0.5
    try:
        ret = c.pct_change().dropna()
        up = ret > 0
        vv = np.abs(ret.values)
        if len(vv) < 2: return 0.5
        dn = ret < 0
        uv = float(np.mean(vv[up])) if up.any() else float(np.mean(vv))
        dv = float(np.mean(vv[dn])) if dn.any() else float(np.mean(vv))
        return float(np.clip(0.5 * (uv / (dv + 1e-10)), 0., 1.))
    except:
        return 0.5

class BottleneckEngine:
    def run(self, prices, volumes=None, quad_str="Q3", quad_mon="Q2",
            benchmark="SPY", asset_ranges=None, min_rs=-0.10, top_n=25):
        volumes = volumes or {}
        bench = prices.get(benchmark)
        qk = quad_str.upper()
        qk_mon = quad_mon.upper()
        regime_allows = {
            "Q1": {"structural": True, "squeeze": True, "commodity": False, "ihsg": True, "crypto": True},
            "Q2": {"structural": True, "squeeze": True, "commodity": True, "ihsg": True, "crypto": True},
            "Q3": {"structural": True, "squeeze": False, "commodity": True, "ihsg": True, "crypto": False},
            "Q4": {"structural": False, "squeeze": False, "commodity": False, "ihsg": False, "crypto": False}
        }.get(qk, {"structural": True})
        playbook = QUAD_ASSET_PERFORMANCE.get(quad_str, {})
        scored = []

        for ticker, close in prices.items():
            if ticker == benchmark:
                continue
            close = pd.to_numeric(close, errors="coerce").dropna()
            if len(close) < 30:
                continue
            sector = TICKER_SECTOR.get(ticker, "generic")
            prof = BOTTLENECK_PROFILES.get(sector, BOTTLENECK_PROFILES.get("generic", {"constraint": 0.5, "Q1": 0.5, "Q2": 0.5, "Q3": 0.5, "Q4": 0.5}))
            constraint = float(prof.get("constraint", 0.5))
            rf_str = float(prof.get(qk, 0.5))
            rf_mon = float(prof.get(qk_mon, 0.5))
            regime_fit = 0.65 * rf_str + 0.35 * rf_mon
            btn_type = "structural"
            rs3 = _rs(close, bench, 63) if bench is not None else None
            rs21 = _rs(close, bench, 21) if bench is not None else None
            if rs3 is not None and rs3 < min_rs:
                continue
            trd, acc_s, hh, hl = _trend(close, 63)[2], _acc(close, 63), _trend(close, 63)[0], _trend(close, 63)[1]
            px = float(close.iloc[-1])
            hi52 = float(close.tail(252).max()) if len(close) >= 252 else float(close.max())
            lo52 = float(close.tail(252).min()) if len(close) >= 252 else float(close.min())
            pct_from_hi = (px - hi52) / max(hi52, 1e-9)
            pct_from_lo = (px - lo52) / max(lo52, 1e-9)
            if trd == "uptrend":
                level = "level_2"
            elif trd == "range" and acc_s >= 0.60:
                level = "level_1"
            elif trd == "downtrend":
                level = "avoid"
            else:
                level = "watch"
            regime_trap = (qk in ("Q3", "Q4") and btn_type == "squeeze")
            score = (0.30 * constraint + 0.25 * regime_fit + 0.20 * (0.5 if trd == "uptrend" else 0.3) + 0.15 * (0.5 if rs3 and rs3 > 0 else 0.3) + 0.10 * acc_s)
            if level == "avoid":
                score *= 0.30
            if regime_trap:
                score *= 0.40
            score = float(np.clip(score, 0.0, 1.0))
            scored.append(dict(
                ticker=ticker, sector=sector, btn_type=btn_type, level=level,
                score=round(score, 3), constraint=round(constraint, 2),
                regime_fit=round(regime_fit, 2), trend=trd,
                acc=round(acc_s, 2), rs_3m=round(rs3, 4) if rs3 else None,
                px=round(px, 4), pct_from_hi=round(pct_from_hi, 3),
                pct_from_lo=round(pct_from_lo, 3), regime_trap=regime_trap,
                rationale=f"{sector}|{trd}|RS {rs3:.1%}" if rs3 else sector,
            ))

        scored.sort(key=lambda x: x["score"], reverse=True)

        return dict(
            all_candidates=scored[:top_n],
            level_1=[s for s in scored if s["level"] == "level_1" and not s["regime_trap"]][:top_n],
            level_2=[s for s in scored if s["level"] == "level_2" and not s["regime_trap"]][:top_n],
            watch=[s for s in scored if s["level"] == "watch"][:top_n],
            avoid=[s for s in scored if s["level"] == "avoid"][:8],
            regime_traps=[s for s in scored if s["regime_trap"]][:8],
            playbook=dict(structural=quad_str, monthly=quad_mon,
                         best=playbook.get("best", []), worst=playbook.get("worst", []),
                         sectors_overweight=playbook.get("sectors_overweight", []),
                         sectors_underweight=playbook.get("sectors_underweight", []),
                         style=playbook.get("style", ""), fx=playbook.get("fx", ""), bonds=playbook.get("bonds", "")),
            regime_filter=regime_allows,
            meta=dict(universe=len(prices) - 1, scored=len(scored)),
        )
