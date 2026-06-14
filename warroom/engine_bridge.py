"""engine_bridge.py — pure compute for the war room (no Streamlit here).

Everything is derived from price/volume (yfinance) + the verified Risk Range engine.
Feed-gated enrichments (GEX, on-chain, COT, fundamentals) are NOT faked — they are
simply absent and flagged in the UI. Nothing here is financial advice.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from gcfis.engines.risk_range_hedgeye import compute_risk_range

UNIVERSE = {
    "us":        ["SPY", "QQQ", "NVDA", "PLTR", "AAPL", "MSFT", "AMD", "META", "AVGO", "MU"],
    "crypto":    ["BTC-USD", "ETH-USD", "SOL-USD"],
    "fx":        ["EURUSD=X", "USDJPY=X", "GBPUSD=X"],
    "commodity": ["GC=F", "CL=F", "SI=F", "HG=F"],
    "idx":       ["BBCA.JK", "BBRI.JK", "BMRI.JK", "ASII.JK", "TLKM.JK"],
}
LONG_ONLY = {"idx"}
MKT_LABEL = {"us": "US equity", "crypto": "Crypto", "fx": "FX", "commodity": "Commodity", "idx": "IHSG"}
BENCH = "SPY"


def _pctrank_last(s, win=252):
    a = s.dropna().to_numpy()
    if len(a) < 20:
        return 50.0
    a = a[-win:]
    return float((a[-1] >= a).mean() * 100.0)


def _ret(c, n):
    if len(c) <= n:
        return np.nan
    return float(c.iloc[-1] / c.iloc[-1 - n] - 1.0) * 100.0


def _trade_plan(rr, market):
    """Entry/stop/target from the Risk Range bands, formation-gated. Long-only markets
    never get a short plan."""
    t = rr["trade"]
    lrr, trr, close = t["lrr"], t["trr"], rr["close"]
    half = max((trr - lrr) / 2.0, 1e-9)
    form = rr["formation"]
    rta = rr["rta"]
    side = "—"
    plan = {"side": "—", "entry": None, "stop": None, "t1": None, "t2": None, "rr": None, "note": ""}
    if form == "BULLISH" and rta in ("BUY", "ADD", "TRIM", "TRIM_RIP"):
        side = "TRIM" if rta in ("TRIM", "TRIM_RIP") else "LONG"
        entry = lrr if close > lrr else close
        stop = lrr - 0.5 * half
        t1 = trr
        t2 = rr["trend"]["trr"] if rr["trend"]["trr"] > trr else None
        rrr = round((t1 - entry) / (entry - stop), 2) if (entry - stop) > 0 else None
        plan = {"side": side, "entry": round(entry, 4), "stop": round(stop, 4),
                "t1": round(t1, 4), "t2": (round(t2, 4) if t2 else None), "rr": rrr,
                "note": "trim into strength near TRR" if side == "TRIM" else "buy/add the low end (LRR) in bull formation"}
    elif form == "BEARISH" and rta in ("SHORT", "COVER") and market not in LONG_ONLY:
        side = "SHORT"
        entry = trr if close < trr else close
        stop = trr + 0.5 * half
        t1 = lrr
        t2 = rr["trend"]["lrr"] if rr["trend"]["lrr"] < lrr else None
        rrr = round((entry - t1) / (stop - entry), 2) if (stop - entry) > 0 else None
        plan = {"side": side, "entry": round(entry, 4), "stop": round(stop, 4),
                "t1": round(t1, 4), "t2": (round(t2, 4) if t2 else None), "rr": rrr,
                "note": "short the high end (TRR) in bear formation"}
    return plan


def analyze_ticker(df, ticker, market, bench_ret63=None):
    """Risk Range + computable signals + trade plan for one ticker."""
    try:
        rr = compute_risk_range(df, ticker=ticker)
    except Exception:
        return None
    c = df.rename(columns=str.lower)["close"].astype(float)
    v = df.rename(columns=str.lower)["volume"].astype(float) if "volume" in df.rename(columns=str.lower) else None
    sma50 = c.rolling(50, min_periods=20).mean().iloc[-1]
    sma200 = c.rolling(200, min_periods=60).mean().iloc[-1]
    ret63 = _ret(c, 63)
    rs63 = (ret63 - bench_ret63) if (bench_ret63 is not None and not np.isnan(ret63)) else np.nan
    dist200 = (c.iloc[-1] / sma200 - 1.0) * 100.0 if pd.notna(sma200) else np.nan
    crowding = _pctrank_last((c / c.rolling(200, min_periods=60).mean() - 1.0), 252)
    mom = _pctrank_last(c.pct_change(63), 252)
    vz = 0.0
    if v is not None and v.rolling(20).std().iloc[-1] and v.rolling(20).std().iloc[-1] > 0:
        vz = float((v.iloc[-1] - v.rolling(20).mean().iloc[-1]) / v.rolling(20).std().iloc[-1])
    atr_pct = (rr.get("atr14", 0.0) / rr["close"] * 100.0) if rr["close"] else 0.0
    reflexivity = max(0.0, min(100.0, 50.0 + (mom - 50.0) * 0.5 + vz * 8.0))

    signaling = _trade_plan(rr, market)["side"] != "—"
    plan = _trade_plan(rr, market)
    return {
        "ticker": ticker, "market": market, "close": rr["close"],
        "formation": rr["formation"], "rta": rr["rta"], "response": rr["response"],
        "lrr": rr["trade"]["lrr"], "trr": rr["trade"]["trr"], "trend_phase": rr["trend"]["phase"],
        "er": rr.get("efficiency_ratio", 0.0), "vol_state": rr.get("vol_state", 1.0),
        "ret5": round(_ret(c, 5), 2), "ret21": round(_ret(c, 21), 2), "ret63": round(ret63, 2) if not np.isnan(ret63) else None,
        "rs63": round(rs63, 2) if (rs63 is not None and not np.isnan(rs63)) else None,
        "dist200": round(dist200, 2) if not np.isnan(dist200) else None,
        "crowding": round(crowding, 1), "momentum": round(mom, 1), "atr_pct": round(atr_pct, 2),
        "reflexivity": round(reflexivity, 1), "above_50": bool(c.iloc[-1] > sma50) if pd.notna(sma50) else None,
        "above_200": bool(c.iloc[-1] > sma200) if pd.notna(sma200) else None,
        "signaling": signaling, "side": plan["side"], "plan": plan,
        "series": rr["series"],
    }


def build_rows(data_by_market):
    """Analyze the whole universe. data_by_market: {market: {ticker: df}}."""
    bench_ret63 = None
    for m, dd in data_by_market.items():
        if BENCH in dd:
            bc = dd[BENCH].rename(columns=str.lower)["close"].astype(float)
            bench_ret63 = _ret(bc, 63)
            break
    rows = []
    for market, dd in data_by_market.items():
        for tkr, df in dd.items():
            r = analyze_ticker(df, tkr, market, bench_ret63)
            if r:
                rows.append(r)
    return rows


def breadth(rows):
    """Universe breadth from computable signals."""
    valid = [r for r in rows if r["above_50"] is not None and r["above_200"] is not None]
    n = len(valid) or 1
    a50 = sum(1 for r in valid if r["above_50"]) / n * 100.0
    a200 = sum(1 for r in valid if r["above_200"]) / n * 100.0
    bull = sum(1 for r in valid if r["formation"] == "BULLISH")
    bear = sum(1 for r in valid if r["formation"] == "BEARISH")
    health = round(0.4 * a50 + 0.4 * a200 + 0.2 * (bull / n * 100.0), 1)
    return {"pct_above_50": round(a50, 1), "pct_above_200": round(a200, 1),
            "bullish": bull, "bearish": bear, "n": len(valid), "health": health}


def breadth_by_market(rows):
    out = {}
    for m in UNIVERSE:
        mr = [r for r in rows if r["market"] == m]
        if mr:
            out[m] = breadth(mr)
    return out


def leadership(rows, top=8):
    """RS leaders (uncrowded leaders first: high RS, lower crowding)."""
    rk = [r for r in rows if r["rs63"] is not None]
    rk.sort(key=lambda r: (-(r["rs63"]), r["crowding"]))
    return rk[:top]


def rr_backtest(data_by_market, fwd=10):
    """Honest quick diagnostic of the Risk Range dip-buy signal:
    bars where close <= TRADE LRR AND bullish formation → forward `fwd`-day return.
    NOT a true OOS harness (overlapping, no costs, in-sample params) — directional only."""
    rets, by_market = [], {}
    for market, dd in data_by_market.items():
        mret = []
        for tkr, df in dd.items():
            try:
                rr = compute_risk_range(df, ticker=tkr)
            except Exception:
                continue
            s = rr["series"]
            close = s.get("close", [])
            lrr = s.get("trade_lrr", [])
            bull = s.get("bull", [])
            L = len(close)
            for t in range(L - fwd):
                ct, lt, bt = close[t], lrr[t], bull[t]
                if ct is None or lt is None or not bt:
                    continue
                if ct <= lt:
                    fwd_px = close[t + fwd]
                    if fwd_px:
                        mret.append((fwd_px / ct - 1.0) * 100.0)
        if mret:
            by_market[market] = {"n": len(mret), "mean": round(float(np.mean(mret)), 2),
                                 "hit": round(float(np.mean([x > 0 for x in mret])) * 100.0, 1)}
            rets += mret
    if not rets:
        return {"n": 0}
    arr = np.array(rets)
    return {"n": int(len(arr)), "mean": round(float(arr.mean()), 2), "median": round(float(np.median(arr)), 2),
            "hit": round(float((arr > 0).mean() * 100.0), 1), "std": round(float(arr.std()), 2),
            "fwd": fwd, "by_market": by_market}


def regime_read(rows, netliq_chg=None):
    """Honest regime/risk read from MARKET INTERNALS + NetLiq (the full GIP quad is
    feed-gated). Axes: risk-appetite (breadth/RS) × liquidity (NetLiq Δ). Thermometers 0-100."""
    b = breadth(rows)
    rs = [r["rs63"] for r in rows if r["rs63"] is not None]
    med_rs = float(np.median(rs)) if rs else 0.0
    growth = max(-1.0, min(1.0, (b["pct_above_200"] - 50) / 50 * 0.6 + np.tanh(med_rs / 15.0) * 0.4))
    liq = 0.0 if netliq_chg is None else float(max(-1.0, min(1.0, np.tanh(netliq_chg / 50.0))))
    vol = [r["vol_state"] for r in rows if r.get("vol_state")]
    med_vol = float(np.median(vol)) if vol else 1.0
    bear_pct = b["bearish"] / max(b["n"], 1) * 100
    crash = max(0, min(100, bear_pct * 0.5 + max(0, 50 - b["pct_above_50"]) * 0.6 + max(0, (med_vol - 1.0)) * 120))
    liq_stress = 0 if netliq_chg is None else max(0, min(100, 50 - float(np.tanh(netliq_chg / 50.0)) * 50))
    longs = sum(1 for r in rows if r["side"] == "LONG")
    shorts = sum(1 for r in rows if r["side"] == "SHORT")
    positioning = max(0, min(100, 50 + (shorts - longs) * 8))
    return {"growth": round(growth, 2), "liquidity": round(liq, 2), "crash": round(crash),
            "liq_stress": round(liq_stress), "positioning": round(positioning),
            "breadth_det": round(max(0, min(100, 100 - b["health"]))), "health": b["health"], "med_vol": round(med_vol, 2)}


def hot_now(rows):
    """Notable names right now (computable) — leader/laggard/most-stretched/best-dip."""
    def pos(r):
        rng = max(r["trr"] - r["lrr"], 1e-9)
        return (r["close"] - r["lrr"]) / rng
    out = {}
    rsv = [r for r in rows if r["rs63"] is not None]
    if rsv:
        out["leader"] = max(rsv, key=lambda r: r["rs63"])
        out["laggard"] = min(rsv, key=lambda r: r["rs63"])
    if rows:
        out["stretched"] = max(rows, key=pos)
    dips = [r for r in rows if r["formation"] == "BULLISH"]
    if dips:
        out["dip"] = min(dips, key=pos)
    return out
