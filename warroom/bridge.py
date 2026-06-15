"""bridge.py — pure compute that WIRES everything together (no Streamlit here).

Computable signals (price/volume) → TickerCandidate pillars → competitive ranking → tiers.
Plus regime read, breadth, leadership, and the propagation chains for the Bottleneck Map.
Feed-gated enrichments (gamma/on-chain/COT) are absent and flagged — never faked.
Not financial advice.
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import numpy as np
import pandas as pd

from gcfis.engines.risk_range_hedgeye import compute_risk_range
from gcfis.engines.competitive_ranking_engine import TickerCandidate, rank, causal_summary
from gcfis.data.moonshot_universe import all_candidates

UNIVERSE = {
    "us":        ["SPY", "QQQ", "NVDA", "PLTR", "AAPL", "MSFT", "AMD", "META", "AVGO", "MU", "VRT", "CEG"],
    "crypto":    ["BTC-USD", "ETH-USD", "SOL-USD"],
    "fx":        ["EURUSD=X", "USDJPY=X", "GBPUSD=X"],
    "commodity": ["GC=F", "CL=F", "SI=F", "HG=F"],
    "idx":       ["BBCA.JK", "BBRI.JK", "BMRI.JK", "ASII.JK", "TLKM.JK"],
}
LONG_ONLY = {"idx"}
MKT_LABEL = {"us": "US equity", "crypto": "Crypto", "fx": "FX", "commodity": "Commodity", "idx": "IHSG"}
BENCH = "SPY"

# ── propagation chains (Bottleneck Map): event → ordered nodes, each with type + role ──
# role: "src" trigger · "ben" beneficiary · "fragile" hurt · "infl" macro
PROPAGATION = {
    "Oil / Hormuz shock": [("Hormuz tension", "src"), ("Crude oil", "ben"), ("Tankers", "ben"),
                           ("LNG", "ben"), ("Coal", "ben"), ("Inflation", "infl"), ("Yields", "infl"),
                           ("Airlines", "fragile"), ("EM FX", "fragile")],
    "AI capex → power": [("AI capex", "src"), ("Power demand", "ben"), ("Grid / transformers", "ben"),
                         ("Utilities", "ben"), ("Cooling", "ben"), ("Uranium", "ben"), ("Copper", "ben")],
    "Liquidity": [("Fed NetLiq Δ", "src"), ("Risk appetite", "ben"), ("Tech / Crypto", "ben"), ("Small caps", "ben")],
    "IDX flow": [("DXY / Fed", "src"), ("USDIDR", "infl"), ("Foreign flow", "ben"), ("Banks (>51%)", "ben"), ("IHSG", "ben")],
}

# bottleneck centrality lookup from the moonshot universe
_BNECK = {}
for _m in all_candidates():
    cen = {1: 0.45, 2: 0.62, 3: 0.80, 4: 0.74, 5: 0.70}.get(_m["tier"], 0.55)
    cen += {"emergence": 0.12, "acceleration": 0.04, "consensus": -0.10}.get(_m["stage"], 0)
    _BNECK[_m["ticker"]] = float(max(0.2, min(1.0, cen)))


def _ret(c, n):
    return float(c.iloc[-1] / c.iloc[-1 - n] - 1.0) if len(c) > n else np.nan


def _pctrank_last(s, win=252):
    a = s.dropna().to_numpy()
    if len(a) < 20:
        return 0.5
    a = a[-win:]
    return float((a[-1] >= a).mean())


def _clip01(x):
    return float(max(0.0, min(1.0, x)))


def analyze_ticker(df, ticker, market, bench_ret63, regime_growth, liq_z=None):
    """Risk Range + computable signals → a TickerCandidate (pillars) + a display row."""
    try:
        rr = compute_risk_range(df, ticker=ticker)
    except Exception:
        return None
    d = df.rename(columns=str.lower)
    c = d["close"].astype(float)
    v = d["volume"].astype(float) if "volume" in d.columns else pd.Series(np.nan, index=c.index)

    ret63 = _ret(c, 63)
    rs63 = (ret63 - bench_ret63) if (bench_ret63 is not None and not np.isnan(ret63)) else 0.0
    sma200 = c.rolling(200, min_periods=60).mean().iloc[-1]
    dist200 = (c.iloc[-1] / sma200 - 1.0) if pd.notna(sma200) else 0.0
    crowding = _pctrank_last(c / c.rolling(200, min_periods=60).mean() - 1.0, 252)   # 0..1, high=extended
    mom = _pctrank_last(c.pct_change(63), 252)                                       # 0..1
    # accumulation proxy: volume-weighted close-location-value over 20d (silent accumulation)
    clv = (((c - d["low"]) - (d["high"] - c)) / (d["high"] - d["low"]).replace(0, np.nan)).fillna(0.0)
    acc = _clip01(0.5 + float((clv * (v / v.rolling(20).mean())).tail(20).mean()) * 0.5) if v.notna().any() else 0.5
    vz = 0.0
    if v.notna().any() and v.rolling(20).std().iloc[-1] and v.rolling(20).std().iloc[-1] > 0:
        vz = float((v.iloc[-1] - v.rolling(20).mean().iloc[-1]) / v.rolling(20).std().iloc[-1])
    atr_pct = (rr.get("atr14", 0.0) / rr["close"] * 100.0) if rr["close"] else 1.0
    dollar = float((c * v).tail(20).median()) if v.notna().any() else 0.0
    bull = rr["formation"] == "BULLISH"

    # ── map signals → TickerCandidate pillars (computable proxies; honest) ──
    bottleneck = _BNECK.get(ticker, 0.35)
    cand = TickerCandidate(
        ticker=ticker, market=market,
        regime_alignment=_clip01(0.5 + np.sign(regime_growth) * (0.5 if bull else -0.5) * 0.7 + (rs63 * 1.5)),
        bottleneck_pressure=bottleneck,
        accumulation_persistence=acc,
        positioning_asymmetry=_clip01(1.0 - crowding),                 # uncrowded = asymmetric
        reflexivity_potential=_clip01(0.4 + (mom - 0.5) * 0.6 + vz * 0.06),
        liquidity_score=_clip01((np.log10(dollar + 1) - 5) / 4) if dollar > 0 else 0.5,  # ~$1e5..$1e9
        confidence_score=_clip01(0.5 + (0.2 if len(c) > 400 else 0) + (0.15 if (bull and rs63 > 0) else 0)),
        catalyst_score=_clip01(0.35 + max(0, vz) * 0.12 + max(0, mom - 0.6) * 0.6),
        crowding_risk=crowding,
        fragility_risk=_clip01(max(0, dist200) * 1.2 + max(0, atr_pct - 4) * 0.05),
        narrative_exhaustion=_clip01((crowding - 0.6) * 1.5 + max(0, mom - 0.85) * 2) if crowding > 0.6 else 0.0,
        propagation_strength=_clip01(0.5 + bottleneck * 0.4),
        narrative_strength=_clip01(mom),
        volatility_quality=_clip01(1.0 - abs(atr_pct - 2.5) / 5),
    )
    row = {
        "ticker": ticker, "market": market, "close": rr["close"], "formation": rr["formation"],
        "rta": rr["rta"], "response": rr["response"], "lrr": rr["trade"]["lrr"], "trr": rr["trade"]["trr"],
        "rs63": round(rs63 * 100, 2), "crowding": round(crowding * 100), "momentum": round(mom * 100),
        "accumulation": round(acc * 100), "reflexivity": round(cand.reflexivity_potential * 100),
        "atr_pct": round(atr_pct, 2), "bottleneck": round(bottleneck * 100), "series": rr["series"],
        "candidate": cand,
    }
    return row


def regime_read(rows, netliq_chg=None):
    b = breadth(rows)
    rs = [r["rs63"] for r in rows if r["rs63"] is not None]
    med_rs = float(np.median(rs)) if rs else 0.0
    growth = max(-1.0, min(1.0, (b["pct_above_200"] - 50) / 50 * 0.6 + np.tanh(med_rs / 12.0) * 0.4))
    liq = 0.0 if netliq_chg is None else float(max(-1.0, min(1.0, np.tanh(netliq_chg / 50.0))))
    crash = max(0, min(100, b["bearish"] / max(b["n"], 1) * 100 * 0.5 + max(0, 50 - b["pct_above_50"]) * 0.6))
    liq_stress = 0 if netliq_chg is None else max(0, min(100, 50 - liq * 50))
    fragility = max(0, min(100, 100 - b["health"]))
    crowd = max(0, min(100, float(np.median([r["crowding"] for r in rows])) if rows else 50))
    contagion = max(0, min(100, fragility * 0.5 + crowd * 0.5))
    # coarse regime label for the ranking engine's override (internals-derived; gamma/cmdty need feeds)
    if liq < -0.3 and b["health"] < 45:
        label = "liquidity_contraction"
    elif crash > 65:
        label = "macro_panic"
    else:
        label = "normal"
    return {"growth": round(growth, 2), "liquidity": round(liq, 2), "label": label,
            "crash": round(crash), "liq_stress": round(liq_stress), "fragility": round(fragility),
            "crowding": round(crowd), "contagion": round(contagion), "health": b["health"]}


def build(data_by_market, netliq_chg=None):
    """Top-level: analyze universe → regime → competitive ranking. Returns everything wired."""
    bench_ret63 = None
    for dd in data_by_market.values():
        if BENCH in dd:
            bench_ret63 = _ret(dd[BENCH].rename(columns=str.lower)["close"].astype(float), 63)
            break
    # first pass for a provisional regime growth sign
    prelim = []
    for market, dd in data_by_market.items():
        for t, df in dd.items():
            r = analyze_ticker(df, t, market, bench_ret63, regime_growth=0.0)
            if r:
                prelim.append(r)
    reg = regime_read(prelim, netliq_chg)
    # second pass with the real regime growth, then rank
    rows = []
    for market, dd in data_by_market.items():
        for t, df in dd.items():
            r = analyze_ticker(df, t, market, bench_ret63, regime_growth=reg["growth"])
            if r:
                rows.append(r)
    ranking = rank([r["candidate"] for r in rows], regime=reg["label"])
    tier_of = {}
    for tier, lst in ranking["tiers"].items():
        for cand in lst:
            tier_of[id(cand)] = tier
    for r in rows:
        r["tier"] = tier_of.get(id(r["candidate"]), "eliminated" if r["candidate"].eliminated else "hidden")
        r["score"] = r["candidate"].score
    return {"rows": rows, "regime": reg, "ranking": ranking}


def breadth(rows):
    valid = [r for r in rows if "close" in r]
    n = len(valid) or 1
    a50, a200, bull, bear = 0, 0, 0, 0
    for r in valid:
        s = r.get("series", {})
        cl = [x for x in s.get("close", []) if x is not None]
        if len(cl) >= 200:
            import numpy as _np
            a50 += r["close"] > _np.mean(cl[-50:])
            a200 += r["close"] > _np.mean(cl[-200:])
        if r["formation"] == "BULLISH":
            bull += 1
        elif r["formation"] == "BEARISH":
            bear += 1
    health = round(0.4 * (a50 / n * 100) + 0.4 * (a200 / n * 100) + 0.2 * (bull / n * 100), 1)
    return {"pct_above_50": round(a50 / n * 100, 1), "pct_above_200": round(a200 / n * 100, 1),
            "bullish": bull, "bearish": bear, "n": len(valid), "health": health}


def breadth_by_market(rows):
    return {m: breadth([r for r in rows if r["market"] == m]) for m in UNIVERSE if any(r["market"] == m for r in rows)}


def leadership(rows, top=10):
    rk = sorted(rows, key=lambda r: (-(r["rs63"] or -999), r["crowding"]))
    return rk[:top]
