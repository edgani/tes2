"""shock_engine.py — front-run engine built on REAL feeds (ChatGPT flaws #2/#3/#5/#7).

Crashes are detectable as pressure build-up, not predictable as events. This composes the
signals that historically lead equity stress:
  credit_stress     — HY OAS level + ROC (VERY HIGH; frontruns equity by weeks)  [REAL via FRED]
  liquidity_contract— NetLiq ROC + real-yield rise                               [REAL via FRED]
  vix_term          — backwardation = panic transition (matters > spike)         [REAL via yfinance]
  breadth_weak      — % below 50dma                                              [SEAM/proxy until constituents]

crash_type (ChatGPT part-2): FLUSH (positioning, recoverable) / CYCLICAL (growth+breadth) /
SYSTEMIC (credit+funding+liquidity collapse). Weights are PRIORS pending walk-forward.

Every output carries which inputs were REAL vs PROXY so a hot reading on proxy-only data is
never mistaken for a confirmed credit-driven signal.
"""
from __future__ import annotations
import numpy as np


def _z(series, win=126):
    s = series.dropna()
    if len(s) < 30:
        return None
    tail = s.tail(win)
    sd = float(tail.std() or 1e-9)
    return float((s.iloc[-1] - tail.mean()) / sd)


def _roc(series, n=21):
    s = series.dropna()
    if len(s) <= n:
        return None
    return float(s.iloc[-1] / s.iloc[-n - 1] - 1.0)


def run_shock_engine(macro: dict, vix_term: dict, breadth: float | None = None) -> dict:
    macro = macro or {}
    comp, prov = {}, {}

    # 1) credit stress — HY OAS rich-z + widening ROC (the frontrunner)
    hy = macro.get("hy_oas", {})
    if hy.get("series") is not None:
        z = _z(hy["series"]); roc = _roc(hy["series"]) or 0.0
        comp["credit_stress"] = float(np.clip(0.5 * np.tanh((z or 0) / 1.5) + 0.5 * np.tanh(roc * 8) + 0.5, 0, 1))
        prov["credit_stress"] = "REAL"
    else:
        comp["credit_stress"] = 0.5; prov["credit_stress"] = "SEAM (no credit feed)"

    # 2) liquidity contraction — NetLiq draining + real-yield rising
    nl = macro.get("net_liquidity", {}); ry = macro.get("real_yield_10y", {})
    parts, ok = [], False
    if nl.get("series") is not None:
        roc = _roc(nl["series"], 21) or 0.0; parts.append(np.tanh(-roc * 6)); ok = True
    if ry.get("series") is not None:
        zr = _z(ry["series"]) or 0.0; parts.append(np.tanh(zr / 2)); ok = True
    comp["liquidity_contract"] = float(np.clip(0.5 + 0.5 * (np.mean(parts) if parts else 0), 0, 1))
    prov["liquidity_contract"] = "REAL" if ok else "SEAM"

    # 3) VIX term backwardation
    r = vix_term.get("ratio") if vix_term else None
    if r is not None:
        comp["vix_term"] = float(np.clip(0.5 + (r - 1.0) * 4.0, 0, 1))      # >1 = panic
        prov["vix_term"] = vix_term.get("provenance", "REAL")
    else:
        comp["vix_term"] = 0.4; prov["vix_term"] = "SEAM (no VIX term)"

    # 4) breadth deterioration (proxy until constituents wired)
    if breadth is not None:
        comp["breadth_weak"] = float(np.clip(1.0 - breadth, 0, 1)); prov["breadth_weak"] = "PROXY"
    else:
        comp["breadth_weak"] = 0.5; prov["breadth_weak"] = "SEAM (needs constituents)"

    w = {"credit_stress": 0.34, "liquidity_contract": 0.30, "vix_term": 0.20, "breadth_weak": 0.16}
    shock = 100.0 * sum(w[k] * comp[k] for k in w)

    # crash-type lean (ChatGPT part-2)
    credit_hot = comp["credit_stress"] > 0.62 and prov["credit_stress"] == "REAL"
    liq_hot = comp["liquidity_contract"] > 0.62
    breadth_hot = comp["breadth_weak"] > 0.58
    vix_hot = comp["vix_term"] > 0.6
    if credit_hot and liq_hot:
        ctype, basis = "SYSTEMIC", "credit + liquidity stress (real) — correlations break, hedge hard"
    elif breadth_hot and not credit_hot:
        ctype, basis = "CYCLICAL", "breadth deterioration without credit blow-out — growth scare"
    elif vix_hot and not credit_hot and not liq_hot:
        ctype, basis = "FLUSH", "vol/positioning spike, credit calm — recoverable (V-shape profile)"
    else:
        ctype, basis = "LOW", "no dominant crash driver"

    real_n = sum(1 for v in prov.values() if v == "REAL")
    confidence = "high" if real_n >= 3 else "medium" if real_n == 2 else "low (mostly proxy/seam)"
    return {"shock_prob": round(shock, 1), "components": {k: round(v, 2) for k, v in comp.items()},
            "provenance": prov, "crash_type": ctype, "basis": basis, "confidence": confidence}
