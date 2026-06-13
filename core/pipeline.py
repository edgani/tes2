"""pipeline.py — the analytical core that makes tabs have CONTENT.

Runs the OHLCV-only engines (flow_type, market_mode, internals, surge, crash) on a price
universe and produces, per ticker: market, flow, mode, multi-TF alignment, surge score,
and a quality-gated verdict (LONG/SHORT/WATCH) with reasons + price-based entry/stop/target + EV.

These engines need NO paid feed — they run on price/volume, so the tabs populate even in the
sandbox. Shock/credit/NetLiq overlay (REAL via FRED on Cloud) is layered on top separately and
labeled. Verdict logic is intentionally lean and transparent; weights are PRIORS.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from engines.flow_type import run_flow_type
from engines.market_mode import run_market_mode
from engines.internals import run_internals, run_horizon
from engines.surge import run_surge
from engines.crash_bottom import run_crash_bottom
from engines.accumulation import run_accumulation   # RS + adoption stage + crowding + velocity (dir context)
from engines.reflexivity import run_reflexivity      # melt-up / runaway detector

_CRYPTO = ("BTC", "ETH", "SOL", "USD-", "-USD", "USDT")
_FX = ("USD", "EUR", "JPY", "GBP", "AUD", "=X")


def _market_of(tkr: str) -> str:
    u = str(tkr).upper()
    if u.endswith(".JK"):
        return "idx"
    if any(k in u for k in ("XAU", "XAG", "GOLD", "SILVER", "WTI", "OIL", "CL=F", "HG", "COPPER")):
        return "commodity"
    if u.endswith("=X") or (u.startswith("USD") and len(u) <= 7) or any(u.endswith(s) for s in ("JPY", "EUR", "GBP")):
        return "fx"
    if any(k in u for k in _CRYPTO):
        return "crypto"
    return "us"


def _close_vol(df):
    if isinstance(df, pd.DataFrame):
        c = pd.to_numeric(df["Close"], errors="coerce") if "Close" in df else pd.to_numeric(df.iloc[:, 0], errors="coerce")
        v = pd.to_numeric(df["Volume"], errors="coerce") if "Volume" in df else None
        return c.dropna(), (v.dropna() if v is not None else None)
    return pd.to_numeric(pd.Series(df), errors="coerce").dropna(), None


def _levels(close: pd.Series):
    """Transparent price-based entry/stop/target from recent structure (not magic)."""
    px = float(close.iloc[-1])
    win = close.tail(20)
    lo, hi = float(win.min()), float(win.max())
    atr = float(close.diff().abs().tail(14).mean() or px * 0.01)
    return px, lo, hi, atr


def _verdict(a: dict):
    """Direction-aware gating using the RICH engines (fixes flow_type direction-blindness):
    long = positive alpha-RS + constructive flow/accumulation + aligned TFs + not parabolic;
    short = distribution/rejection + negative trend. flow_type is one input, not the sole judge."""
    flow = (a.get("flow") or {}).get("type")
    mode = (a.get("market_mode") or {}).get("mode")
    align = float((a.get("horizon") or {}).get("alignment", 50) or 50)
    surge = float((a.get("surge") or {}).get("score", 50) or 50)
    rs = float(a.get("alpha_rs") or 0.0)                 # relative strength vs bench (directional)
    crowd = float(a.get("crowding", 50) or 50)
    vel = float(a.get("adoption_velocity", 0) or 0)
    runaway = bool(a.get("runaway"))
    exit_sig = bool(a.get("exit_signal"))
    sweet = bool(a.get("sweet_spot"))
    accum = float(a.get("accum_score") or 0.0)
    px, lo, hi, atr = a["_lvl"]
    close = a["_close"]
    trend60 = (px / float(close.iloc[-61]) - 1.0) if len(close) > 61 else 0.0
    reasons, side = [], None

    # LONG: relative strength + (accumulation OR aligned uptrend) + not parabolic-exhausted
    constructive = flow in ("ACCUMULATION", "SHORT_COVERING") or accum > 0.25 or (align >= 60 and trend60 > 0.03)
    # fresh long: strong RS + constructive + NOT a late-stage exhausted top (exit_signal) + not parabolic
    bullish = rs > 0.10 and constructive and trend60 > -0.03 and not runaway and not exit_sig
    bearish = (flow in ("DISTRIBUTION", "PANIC_LIQUIDATION") or mode == "DISTRIBUTION") and trend60 < 0.0 and rs < 0.02

    if a.get("market") == "idx":
        bearish = False
    if bullish and not bearish:
        side = "long"
        reasons.append(f"relative strength vs bench (alpha-RS {rs:+.2f})")
        if flow == "ACCUMULATION": reasons.append(f"accumulation tape (abs {(a['flow'] or {}).get('absorption')})")
        elif trend60 > 0.03: reasons.append(f"aligned uptrend ({trend60:+.0%} 60d, TF {align:.0f}/100)")
        if sweet: reasons.append("uncrowded sweet-spot (Stage 2→3)")
        if a.get("stage"): reasons.append(f"adoption stage: {a['stage']}")
        if accum > 0.3: reasons.append(f"accumulation score {accum:+.2f}")
        if surge >= 62: reasons.append(f"surge pre-conditioning {surge:.0f}")
        if crowd < 45: reasons.append(f"underowned (crowding {crowd:.0f})")
        entry, stop, target = round(px, 4), round(lo - 0.5 * atr, 4), round(px + 2.0 * atr, 4)
    elif bearish:
        side = "short"
        if flow == "DISTRIBUTION": reasons.append(f"distribution — volume w/o progress (eff {(a['flow'] or {}).get('efficiency')})")
        if flow == "PANIC_LIQUIDATION": reasons.append("panic liquidation tape")
        if mode == "DISTRIBUTION": reasons.append("market mode DISTRIBUTION")
        reasons.append(f"negative RS ({rs:+.2f}) + downtrend ({trend60:+.0%} 60d)")
        if runaway: reasons.append("reflexive blow-off risk")
        entry, stop, target = round(px, 4), round(hi + 0.5 * atr, 4), round(px - 2.0 * atr, 4)
    else:
        return None

    if len(reasons) < 2:
        return None
    risk = abs(entry - stop); reward = abs(target - entry)
    if risk <= 0:
        return None
    conv = float(np.clip(45 + 0.30 * (align - 50) + 0.20 * (surge - 50) + 30 * np.tanh(rs * 3), 0, 100))
    p = conv / 100.0
    ev = round(100.0 * (p * reward - (1 - p) * risk) / entry, 2)
    return {"side": side, "conviction": round(conv, 1), "ev": ev, "entry": entry, "stop": stop,
            "target": target, "rr": round(reward / risk, 2), "reasons": reasons[:5],
            "stage": a.get("stage"), "crowding": round(crowd, 0),
            "invalidation": {"price": stop, "conditions": "close beyond stop"}}


def run_pipeline(prices: dict, bench=None, data_ctx: dict | None = None) -> dict:
    if not prices:
        return {"per_ticker": {}, "picks": [], "internals": {}, "shock": None, "note": "no prices"}
    bench = bench if bench is not None else next(iter(prices.values()))
    bclose, _ = _close_vol(bench)
    internals = run_internals(prices, bclose)

    per = {}
    for tkr, df in prices.items():
        close, vol = _close_vol(df)
        if len(close) < 130:
            continue
        a = {"ticker": tkr, "market": _market_of(tkr)}
        a["flow"] = run_flow_type(close, vol)
        acc = run_accumulation(tkr, close, bclose, volume=vol)         # RS/stage/crowding/velocity
        a["accumulation"] = acc
        a["crowding"] = float(acc.get("crowding", 50.0))
        a["adoption_velocity"] = float(acc.get("adoption_velocity", 0.0))
        a["stage"] = acc.get("stage")
        a["alpha_rs"] = float(acc.get("rs") or 0.0)
        a["accum_score"] = float(acc.get("accumulation") or 0.0)
        a["exit_signal"] = bool(acc.get("exit_signal"))
        a["sweet_spot"] = bool(acc.get("sweet_spot"))
        refl = run_reflexivity(close, volume=vol)
        a["reflexivity"] = refl.get("reflexivity")
        a["runaway"] = refl.get("runaway")
        a["acceleration"] = refl.get("price_accel")
        a["market_mode"] = run_market_mode(close, flow=a["flow"], crowding=a["crowding"],
                                           adoption_velocity=a["adoption_velocity"])
        a["horizon"] = run_horizon(close)
        a["_lvl"] = _levels(close)
        a["_close"] = close
        a["surge"] = run_surge(a, {"liquidity": 50, "fragility": 50}, internals)
        per[tkr] = a

    # crash/bottom context from the cohort (OHLCV proxy; credit overlay added separately)
    crash = run_crash_bottom({"liquidity": 50, "fragility": 50, "shock_prob": 50}, internals, per)

    # quality-gated verdicts → ranked picks (NO padding: only those that clear the gate)
    picks = []
    for tkr, a in per.items():
        v = _verdict(a)
        a["verdict"] = v
        if v:
            picks.append({"ticker": tkr, "market": a["market"], **v,
                          "flow": (a["flow"] or {}).get("type"), "mode": (a["market_mode"] or {}).get("mode"),
                          "surge": (a["surge"] or {}).get("score")})
    picks.sort(key=lambda r: (0 if r["ev"] is not None else 1,
                              -(0.5 * np.tanh((r["ev"] or 0) / 10) + 0.5 * (r["conviction"] / 100))))
    return {"per_ticker": per, "picks": picks, "internals": internals, "crash": crash,
            "note": f"{len(per)} tickers analyzed · {len(picks)} cleared the quality gate"}


# ---- demo universe so tabs show CONTENT in the sandbox (clearly labeled; replace w/ live on Cloud) ----
def demo_universe(seed: int = 11) -> dict:
    rng = np.random.default_rng(seed)
    n = 260
    ix = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    n = len(ix)

    def make(drift, vol, last_mult=1.0, vramp=False):
        c = 100 * np.exp(np.cumsum(rng.normal(drift, vol, n)))
        c[-1] *= last_mult
        v = rng.normal(1e6, 1e5, n).clip(1e5)
        if vramp:
            v[-40:] *= np.linspace(1, 3, 40)
        return pd.DataFrame({"Close": c, "Volume": v}, index=ix)

    return {
        "NVDA": make(0.0035, 0.018, vramp=True),     # strong uptrend + volume ramp → accumulation/surge
        "PLTR": make(0.004, 0.022, vramp=True),
        "SMR": make(0.0015, 0.03),
        "TLT": make(-0.0008, 0.009),
        "XLU": make(0.0012, 0.008),
        "BTCUSD": make(0.0025, 0.025, vramp=True),
        "ETHUSD": make(0.0012, 0.028),
        "XAUUSD": make(0.0008, 0.009),
        "USOIL": make(-0.001, 0.02),
        "USDJPY=X": make(0.0003, 0.006),
        "BREN.JK": make(-0.0025, 0.02),              # downtrend → distribution
        "DMAS.JK": make(0.0018, 0.013, vramp=True),
    }
