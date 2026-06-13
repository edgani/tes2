"""ai_capex.py — AI-Capex regime (Leopold/Aschenbrenner 'situational awareness'). ChatGPT flaw #8.

Quad isn't built for the AI era: NVDA/SMR/VST/CEG/VRT outperform on the AI build-out, not macro.
This composites the AI-infrastructure complex (compute, power, cooling/grid) from price RS to a
0-100 AI-cycle score + phase. Drives US-market DNA and the theme regime. Prices-only (no paid feed).
"""
from __future__ import annotations
import numpy as np
import pandas as pd

# engine_ticker -> role in the AI build-out (uses whatever the universe provides)
_COMPUTE = ("NVDA", "SMH", "AVGO", "AMD")
_POWER = ("SMR", "VST", "CEG", "NRG", "XLU")        # nuclear/IPP/utility (datacenter power)
_INFRA = ("VRT", "ETN", "PWR", "GEV")               # cooling/grid/electrical


def _rs_score(close: pd.Series, bench: pd.Series, n: int = 63) -> float | None:
    a = pd.to_numeric(close, errors="coerce").dropna()
    b = pd.to_numeric(bench, errors="coerce").dropna()
    idx = a.index.intersection(b.index)
    if len(idx) < n + 1:
        return None
    a, b = a.reindex(idx), b.reindex(idx)
    rs = (a.iloc[-1] / a.iloc[-n - 1]) / (b.iloc[-1] / b.iloc[-n - 1]) - 1.0   # excess return vs bench
    return float(np.tanh(rs * 4))                                              # -1..1


def run_ai_capex(prices: dict, bench_ticker: str = "XLU") -> dict:
    """0-100 AI-cycle score from compute/power/infra relative strength + phase classification."""
    bench = None
    for b in (bench_ticker, "SPY", "TLT"):
        if b in prices and "Close" in prices[b]:
            bench = pd.to_numeric(prices[b]["Close"], errors="coerce").dropna(); break
    if bench is None:
        # fall back to equal-weight of the universe as the benchmark
        closes = [pd.to_numeric(d["Close"], errors="coerce") for d in prices.values() if "Close" in d]
        bench = pd.concat(closes, axis=1).mean(axis=1).dropna() if closes else None
    if bench is None:
        return {"ok": False, "reason": "no benchmark"}

    legs = {}
    for name, group in (("compute", _COMPUTE), ("power", _POWER), ("infra", _INFRA)):
        vals = []
        for t in group:
            if t in prices and "Close" in prices[t]:
                s = _rs_score(prices[t]["Close"], bench)
                if s is not None:
                    vals.append(s)
        legs[name] = round(float(np.mean(vals)), 3) if vals else None

    present = {k: v for k, v in legs.items() if v is not None}
    if not present:
        return {"ok": False, "reason": "no AI-complex names in universe", "legs": legs}
    score = float(np.clip(50 + 50 * np.mean(list(present.values())), 0, 100))
    breadth = sum(1 for v in present.values() if v > 0) / len(present)   # how broad the leadership is

    if score >= 70 and breadth >= 0.66:
        phase = "ACCELERATION (broad AI leadership)"
    elif score >= 60:
        phase = "EARLY/COMPUTE-LED (narrow — compute ahead of power/grid)"
    elif score >= 45:
        phase = "CONSOLIDATION"
    else:
        phase = "DERATING (AI complex underperforming)"
    return {"ok": True, "ai_cycle_score": round(score, 1), "phase": phase,
            "legs": legs, "leadership_breadth": round(breadth, 2),
            "note": "AI build-out RS composite (compute/power/infra) — prices-only proxy"}
