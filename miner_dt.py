#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
miner_dt.py — Robert Miner / Dynamic Trader engine (multi-asset)

Reproduces Miner's "math engine" exactly (close-based, exact ratios):
  - DTosc (StochRSI) dual-timeframe + DLB
  - Price: Internal/External Retracement, Alternate Price Projection (APP),
           End-of-Wave-C / End-of-Wave-5 target ZONES (clustered, not lines)
  - Time:  Time Retracement, Alternate Time Projection (ATP), L-L/H-H cycle,
           Time Bands, Dynamic-Time-Projection-style cluster
  - Decision: trigger / void CLOSE levels + timeframe nesting frame

WHAT IS EXACT vs NOT (be honest):
  - MATH ENGINE (projections/DTosc) is deterministic -> ~exact given the SAME
    pivots + basis. This is reproducible to the decimal.
  - DECISION ENGINE (which pivots, which pattern/degree, context/regime) is
    DISCRETIONARY. Miner himself says no software auto-detects pivots/waves
    reliably. The auto pivot/pattern below is a STARTING POINT. Override it.

ASSETS / TICKERS:
  US stocks   : AAPL, NVDA, SPY ...
  IDX (IHSG)  : HUMI, BBCA ...           -> use --market idx  (becomes HUMI.JK)
  Forex       : USDJPY, EURUSD ...       -> auto -> USDJPY=X
  Commodities : GOLD, SILVER, OIL ...    -> auto -> GC=F / SI=F / CL=F
  Crypto      : BTC, ETH ...             -> auto -> BTC-USD

USAGE (local machine with internet):
    pip install yfinance pandas numpy
    python miner_dt.py HUMI --market idx
    python miner_dt.py USDJPY
    python miner_dt.py BTC --interval 1d
    python miner_dt.py NVDA --interval 1d --dtosc-set 2 --htf W
    python miner_dt.py GOLD --basis close --swing-pct 3.0

Note: data is fetched via yfinance. In a no-network sandbox use analyze(df=...).
"""

from __future__ import annotations
import argparse
import sys
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------
# 0. MINER CONSTANTS (verbatim from High Probability Trading Strategies)
# ----------------------------------------------------------------------------
INTERNAL_RET = (0.382, 0.50, 0.618, 0.786)          # corrections
EXTERNAL_RET = (1.27, 1.62, 2.62)                   # final section
APP_CORR     = (0.618, 1.000, 1.618)                # APP corrective (focus 100%)
APP_TREND    = (0.382, 0.618, 1.000)                # APP trend
TIME_RET     = (0.382, 0.50, 0.618, 1.000, 1.618)   # ABC: 38-62%; complex max 100%
ATP_RATIOS   = (0.618, 1.000, 1.618)                # alternate time projection

# DTosc StochRSI parameter sets (a=RSI, b=Stoch, c=K smooth, d=D smooth)
DTOSC_SETS = {1: (8, 5, 3, 3), 2: (13, 8, 5, 5), 3: (21, 13, 8, 8), 4: (34, 21, 13, 13)}
DTOSC_OB, DTOSC_OS = 75.0, 25.0

# Weight for cluster scoring (Miner order: In-Ret > APP > Ex-Ret)
W_INRET, W_APP, W_EXRET, W_APP100_BONUS = 3.0, 2.0, 1.0, 1.0

# ----------------------------------------------------------------------------
# 1. TICKER NORMALIZATION (multi-asset)
# ----------------------------------------------------------------------------
CURRENCIES = {"USD", "EUR", "JPY", "GBP", "AUD", "NZD", "CAD", "CHF",
              "CNH", "CNY", "SGD", "HKD", "IDR", "INR", "MXN", "ZAR",
              "SEK", "NOK", "TRY", "BRL", "KRW", "THB"}

CRYPTO = {"BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "BNB", "AVAX", "DOT",
          "LINK", "MATIC", "LTC", "TRX", "SHIB", "ATOM", "ARB", "OP", "SUI",
          "TON", "NEAR", "APT", "INJ", "PEPE", "RNDR", "TIA"}

COMMODITY_ALIAS = {
    "GOLD": "GC=F", "XAU": "GC=F", "XAUUSD": "GC=F",
    "SILVER": "SI=F", "XAG": "SI=F", "XAGUSD": "SI=F",
    "OIL": "CL=F", "WTI": "CL=F", "CRUDE": "CL=F",
    "BRENT": "BZ=F", "NATGAS": "NG=F", "GAS": "NG=F",
    "COPPER": "HG=F", "PLATINUM": "PL=F", "PALLADIUM": "PA=F",
    "CORN": "ZC=F", "WHEAT": "ZW=F", "SOYBEAN": "ZS=F", "SOYBEANS": "ZS=F",
    "SUGAR": "SB=F", "COFFEE": "KC=F", "COCOA": "CC=F", "COTTON": "CT=F",
}

INDEX_ALIAS = {  # convenience
    "SPX": "^GSPC", "SP500": "^GSPC", "NDX": "^NDX", "NASDAQ": "^IXIC",
    "DJI": "^DJI", "DOW": "^DJI", "VIX": "^VIX", "IHSG": "^JKSE", "JKSE": "^JKSE",
    "DAX": "^GDAXI", "FTSE": "^FTSE", "N225": "^N225", "NIKKEI": "^N225",
}


def normalize_ticker(user: str, market: str = "auto") -> tuple[list[str], str, str]:
    """
    Returns (candidate_yf_tickers, asset_class, display_input).
    candidate list is tried in order until one returns data (handles IDX .JK
    ambiguity for plain symbols like HUMI in auto mode).
    """
    raw = user.strip().upper()
    disp = raw

    # explicit suffixes already present
    if raw.endswith("=X"):
        return [raw], "forex", disp
    if raw.endswith("=F"):
        return [raw], "commodity", disp
    if raw.endswith("-USD"):
        return [raw], "crypto", disp
    if raw.endswith(".JK"):
        return [raw], "idx", disp
    if raw.startswith("^"):
        return [raw], "index", disp

    # explicit market override
    if market == "idx":
        return [raw + ".JK"], "idx", disp
    if market == "forex":
        t = raw if "=" in raw else raw + "=X"
        return [t], "forex", disp
    if market == "crypto":
        t = raw if "-" in raw else raw + "-USD"
        return [t], "crypto", disp
    if market == "commodity":
        return [COMMODITY_ALIAS.get(raw, raw)], "commodity", disp
    if market == "us":
        return [raw], "us", disp

    # ---- auto detection ----
    if raw in INDEX_ALIAS:
        return [INDEX_ALIAS[raw]], "index", disp
    if raw in COMMODITY_ALIAS:
        return [COMMODITY_ALIAS[raw]], "commodity", disp
    # forex: 6 letters = two currency codes
    if len(raw) == 6 and raw[:3] in CURRENCIES and raw[3:] in CURRENCIES:
        return [raw + "=X"], "forex", disp
    # crypto: known symbol or SYM-USD pattern
    if raw in CRYPTO:
        return [raw + "-USD"], "crypto", disp
    # ambiguous plain symbol (e.g. HUMI): try US first, then IDX (.JK)
    return [raw, raw + ".JK"], "us/idx?", disp


# ----------------------------------------------------------------------------
# 2. DATA
# ----------------------------------------------------------------------------
DEFAULT_PERIOD = {"1d": "3y", "1wk": "10y", "1h": "180d", "60m": "180d",
                  "15m": "30d", "5m": "14d", "30m": "60d"}

# higher-timeframe resample rule per base interval (pandas 3.0 aliases)
HTF_RULE = {"1d": "W", "1wk": "ME", "1h": "1D", "60m": "1D",
            "30m": "1D", "15m": "h", "5m": "h"}


def fetch_data(candidates: list[str], interval: str = "1d",
               period: Optional[str] = None) -> tuple[pd.DataFrame, str]:
    """Fetch OHLC via yfinance. Returns (df, resolved_ticker)."""
    try:
        import yfinance as yf
    except ImportError:
        raise SystemExit("yfinance not installed. Run: pip install yfinance")

    period = period or DEFAULT_PERIOD.get(interval, "2y")
    last_err = None
    for tk in candidates:
        try:
            df = yf.download(tk, period=period, interval=interval,
                             auto_adjust=True, progress=False)
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue
        if df is not None and len(df) > 0:
            # flatten possible MultiIndex columns (single ticker)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df.rename(columns=str.title)
            keep = [c for c in ("Open", "High", "Low", "Close") if c in df.columns]
            df = df[keep].dropna()
            if len(df) > 0:
                return df, tk
    raise SystemExit(f"No data for {candidates} ({interval}). "
                     f"Last error: {last_err}. For IDX try --market idx.")


# ----------------------------------------------------------------------------
# 3. DTosc (StochRSI) — Layer 3
# ----------------------------------------------------------------------------
def rsi_wilder(close: pd.Series, n: int) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0.0)
    down = (-delta).clip(lower=0.0)
    roll_up = up.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    roll_dn = down.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    rs = roll_up / roll_dn.replace(0.0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    return rsi.fillna(100.0)  # all-gains window -> 100


def dtosc(close: pd.Series, a: int, b: int, c: int, d: int,
          ma: str = "sma") -> tuple[pd.Series, pd.Series]:
    """DTosc = StochRSI double-smoothed. Returns (K, D)."""
    rsi = rsi_wilder(close, a)
    lo = rsi.rolling(b).min()
    hi = rsi.rolling(b).max()
    rng = (hi - lo).replace(0.0, np.nan)
    stoch = (100.0 * (rsi - lo) / rng).fillna(50.0)
    if ma == "ema":
        K = stoch.ewm(span=c, adjust=False).mean()
        D = K.ewm(span=d, adjust=False).mean()
    else:  # sma (ProRealCode default)
        K = stoch.rolling(c).mean()
        D = K.rolling(d).mean()
    return K, D


def dtosc_status(K: pd.Series, D: pd.Series) -> dict:
    k, dd = float(K.iloc[-1]), float(D.iloc[-1])
    kp, dp = float(K.iloc[-2]), float(D.iloc[-2])
    direction = "BULL" if k > dd else "BEAR"
    zone = "OB" if (k >= DTOSC_OB and dd >= DTOSC_OB) else \
           "OS" if (k <= DTOSC_OS and dd <= DTOSC_OS) else "MID"
    cross = None
    if kp <= dp and k > dd:
        cross = "BULLISH_REVERSAL" + (" (from OS)" if dp <= DTOSC_OS else "")
    elif kp >= dp and k < dd:
        cross = "BEARISH_REVERSAL" + (" (from OB)" if dp >= DTOSC_OB else "")
    return {"K": round(k, 2), "D": round(dd, 2), "dir": direction,
            "zone": zone, "cross": cross}


def resample_close(df: pd.DataFrame, rule: str) -> pd.Series:
    return df["Close"].resample(rule).last().dropna()


# ----------------------------------------------------------------------------
# 4. PIVOTS + STRUCTURE — Layer 1 (DISCRETIONARY; auto = starting point)
# ----------------------------------------------------------------------------
@dataclass
class Pivot:
    idx: int          # positional index into the series
    date: pd.Timestamp
    price: float
    kind: str         # 'H' or 'L'


def _alternate(piv: list[Pivot]) -> list[Pivot]:
    """Force strictly alternating H/L, keeping the more extreme on collisions."""
    out: list[Pivot] = []
    for p in piv:
        if out and out[-1].kind == p.kind:
            if (p.kind == "H" and p.price >= out[-1].price) or \
               (p.kind == "L" and p.price <= out[-1].price):
                out[-1] = p
        else:
            out.append(p)
    return out


def zigzag_pivots(series: pd.Series, pct: float = 3.0) -> list[Pivot]:
    """Percentage-threshold zigzag on the (close) series. Separate up/down
    extreme trackers (single shared extreme corrupts state)."""
    s = series.values
    dates = series.index
    n = len(s)
    if n < 3:
        return []
    thr = pct / 100.0
    piv: list[Pivot] = []
    direction = 0                       # +1 up leg, -1 down leg, 0 unknown
    up_i, up_v = 0, float(s[0])         # highest since last confirmed pivot
    dn_i, dn_v = 0, float(s[0])         # lowest since last confirmed pivot
    for i in range(1, n):
        v = float(s[i])
        if v > up_v:
            up_v, up_i = v, i
        if v < dn_v:
            dn_v, dn_i = v, i
        if direction >= 0 and v <= up_v * (1 - thr):
            piv.append(Pivot(up_i, dates[up_i], up_v, "H"))
            direction = -1
            up_v, up_i = v, i
            dn_v, dn_i = v, i
        elif direction <= 0 and v >= dn_v * (1 + thr):
            piv.append(Pivot(dn_i, dates[dn_i], dn_v, "L"))
            direction = 1
            up_v, up_i = v, i
            dn_v, dn_i = v, i
    # tentative (unconfirmed) last extreme — useful current context
    if direction >= 0:
        if not piv or piv[-1].idx != up_i:
            piv.append(Pivot(up_i, dates[up_i], up_v, "H"))
    else:
        if not piv or piv[-1].idx != dn_i:
            piv.append(Pivot(dn_i, dates[dn_i], dn_v, "L"))
    return _alternate(piv)


def classify_structure(piv: list[Pivot]) -> dict:
    """
    Overlap guideline -> trend vs correction, plus a heuristic current-wave
    label. AUTO ONLY — flagged as discretionary. Uses last up to 6 pivots.
    """
    if len(piv) < 3:
        return {"pattern": "n/a", "wave": "n/a", "overlap": None,
                "bias": "n/a", "note": "not enough pivots"}
    last = piv[-6:]
    # overlap test on the most recent 3 same-direction sections
    overlap = False
    for i in range(2, len(last)):
        a, b = last[i - 2], last[i]
        if a.kind == b.kind:  # two highs or two lows = a 'section' comparison
            prev = last[i - 1]
            if a.kind == "H":  # downward sections (H->L), overlap if new H back into prior range
                if b.price <= a.price and prev.price < a.price:
                    pass
            # generic overlap: latest extreme retraces into the section two-back
            lo = min(a.price, prev.price)
            hi = max(a.price, prev.price)
            if lo <= b.price <= hi:
                overlap = True
    pattern = "CORRECTION (overlap)" if overlap else "TREND (impulsive, no overlap)"
    # crude wave guess from count of legs since a major pivot
    legs = len(piv)
    cur = piv[-1]
    if overlap:
        wave = "Wave-B / C of a correction (verify)"
    else:
        wave = "late-wave of an impulse — possible W3/W5 (verify)"
    bias = "expecting DOWN reversal" if cur.kind == "H" else "expecting UP reversal"
    return {"pattern": pattern, "wave": wave, "overlap": overlap,
            "bias": bias, "legs": legs,
            "note": "AUTO read — override pivots/pattern for Miner-grade accuracy"}


# ----------------------------------------------------------------------------
# 5. PRICE PROJECTIONS — Layer 2 (EXACT)
# ----------------------------------------------------------------------------
def internal_ret(start: float, end: float) -> dict:
    rng = end - start
    return {f"{r:.3f} Ret": end - rng * r for r in INTERNAL_RET}


def external_ret(start: float, end: float) -> dict:
    rng = end - start
    return {f"{r:.2f} ExtRet": end - rng * r for r in EXTERNAL_RET}


def app(base_start: float, base_end: float, pivot: float,
        structure: str = "corr") -> dict:
    rng = base_end - base_start
    ratios = APP_CORR if structure == "corr" else APP_TREND
    return {f"{r:.3f} App": pivot + rng * r for r in ratios}


def eow_c_targets(prior_start, prior_end, A, B) -> dict[str, dict]:
    """End-of-Wave-C zone components. prior trend = prior_start->prior_end."""
    return {
        "InRet(prior)": internal_ret(prior_start, prior_end),
        "App(WaveA)": app(prior_start, A, B, "corr"),
        "ExtRet(WaveB)": external_ret(A, B),
    }


def eow_5_targets(W0, W1, W3, W4) -> dict[str, dict]:
    """End-of-Wave-5 zone components."""
    return {
        "App(W1-3 fromW4)": {f"{r:.3f} App": W4 + (W3 - W0) * r
                             for r in (0.382, 0.618, 1.000)},
        "App(W1 fromW4)": {"1.000 App": W4 + (W1 - W0) * 1.0},
        "ExtRet(W4)": external_ret(W3, W4),
    }


def _weight(label: str) -> float:
    low = label.lower()
    if "extret" in low:                 # external retracement
        return W_EXRET
    if "app" in low:                    # alternate price projection
        return W_APP + (W_APP100_BONUS if "1.000" in label else 0.0)
    if "ret" in low:                    # internal retracement
        return W_INRET
    return 1.0


def cluster_zones(components: dict[str, dict], price_ref: float,
                  tol_pct: float = 0.6, top: int = 3) -> list[dict]:
    """
    Collapse all projections into clustered ZONES. Each zone scored by summed
    weights (In-Ret>App>ExtRet, +bonus for 100% App). Returns top zones.
    """
    pts = []  # (price, label, weight)
    for grp, d in components.items():
        for lbl, price in d.items():
            if price is None or not np.isfinite(price):
                continue
            pts.append((float(price), f"{grp}:{lbl}", _weight(lbl)))
    if not pts:
        return []
    pts.sort(key=lambda x: x[0])
    tol = price_ref * tol_pct / 100.0
    zones = []
    used = [False] * len(pts)
    for i in range(len(pts)):
        if used[i]:
            continue
        members = [pts[i]]
        used[i] = True
        for j in range(i + 1, len(pts)):
            if used[j]:
                continue
            if pts[j][0] - members[0][0] <= tol:
                members.append(pts[j])
                used[j] = True
        prices = [m[0] for m in members]
        # require members from >=2 distinct groups to count as a real cluster
        groups = {m[1].split(":")[0] for m in members}
        score = sum(m[2] for m in members) + (1.0 if len(groups) >= 2 else 0.0)
        zones.append({
            "low": min(prices), "high": max(prices), "mid": float(np.mean(prices)),
            "score": round(score, 1), "n": len(members), "groups": len(groups),
            "members": [m[1] for m in members],
        })
    zones.sort(key=lambda z: (z["groups"] >= 2, z["score"]), reverse=True)
    return zones[:top]


# ----------------------------------------------------------------------------
# 6. TIME PROJECTIONS — Layer 2 (EXACT)
# ----------------------------------------------------------------------------
def time_ret(start_idx: int, end_idx: int) -> dict:
    dur = end_idx - start_idx
    return {f"{r:.3f} TimeRet": end_idx + int(round(dur * r)) for r in TIME_RET}


def atp_time(base_start_idx: int, base_end_idx: int, pivot_idx: int) -> dict:
    dur = base_end_idx - base_start_idx
    return {f"{r:.3f} ATP": pivot_idx + int(round(dur * r)) for r in ATP_RATIOS}


def _drop_outliers(vals: list[int]) -> list[int]:
    if len(vals) <= 4:
        return vals
    s = sorted(vals)
    return s[1:-1]  # drop extreme short & long


def time_band(highs: list[Pivot], lows: list[Pivot]) -> Optional[tuple[int, int]]:
    """H-H counts range  INTERSECT  L-H counts range, projected from last pivots."""
    if len(highs) < 3 or len(lows) < 2:
        return None
    hh = [highs[i].idx - highs[i - 1].idx for i in range(1, len(highs))]
    # L-H using the high pivots and the low immediately preceding each high
    lh = []
    for h in highs:
        prev_lows = [l for l in lows if l.idx < h.idx]
        if prev_lows:
            lh.append(h.idx - prev_lows[-1].idx)
    if not hh or not lh:
        return None
    hh = _drop_outliers(hh)
    lh = _drop_outliers(lh)
    last_high = highs[-1].idx
    last_low = lows[-1].idx
    band_hh = (last_high + min(hh), last_high + max(hh))
    band_lh = (last_low + min(lh), last_low + max(lh))
    lo = max(band_hh[0], band_lh[0])
    hi = min(band_hh[1], band_lh[1])
    if lo <= hi:
        return (lo, hi)
    # no overlap -> return the H-H band as fallback
    return band_hh


def time_cluster(components: dict, win: int = 1) -> list[tuple[int, int]]:
    """DTP-style: bin all projected indices, score by hit count in +/- win."""
    idxs = []
    for d in components.values():
        idxs.extend(int(v) for v in d.values())
    if not idxs:
        return []
    counts = {}
    for x in idxs:
        for y in idxs:
            if abs(x - y) <= win:
                counts[x] = counts.get(x, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    return ranked[:5]


def idx_to_date(series_index: pd.DatetimeIndex, target_idx: int) -> pd.Timestamp:
    """Map a (possibly future) positional index to an approx calendar date."""
    n = len(series_index)
    if target_idx < n:
        return series_index[target_idx]
    # extrapolate using median bar gap
    diffs = pd.Series(series_index).diff().dropna()
    gap = diffs.median() if len(diffs) else pd.Timedelta(days=1)
    return series_index[-1] + gap * (target_idx - (n - 1))


# ----------------------------------------------------------------------------
# 7. DECISION LAYER — trigger / void CLOSE levels  (Layer 4)
# ----------------------------------------------------------------------------
def decision_levels(piv: list[Pivot], struct: dict, close: pd.Series) -> dict:
    """
    Best-effort Miner-style trigger/void close levels derived from swings.
    Bearish scenario (expecting decline): trigger = close below last swing low;
    void = close above the recent corrective high. Mirror for bullish.
    """
    if len(piv) < 3:
        return {}
    last_high = max((p for p in piv if p.kind == "H"), key=lambda p: p.idx, default=None)
    last_low = min((p for p in piv if p.kind == "L"), key=lambda p: p.idx, default=None)
    # most recent swing low / high prices
    lows = [p for p in piv if p.kind == "L"]
    highs = [p for p in piv if p.kind == "H"]
    res = {}
    if struct.get("bias", "").startswith("expecting DOWN"):
        if lows:
            res["trigger"] = (f"BEAR confirmed on CLOSE < {lows[-1].price:.4g}",
                              lows[-1].date)
        if highs:
            res["void"] = (f"voided on CLOSE > {highs[-1].price:.4g}",
                           highs[-1].date)
    else:
        if highs:
            res["trigger"] = (f"BULL confirmed on CLOSE > {highs[-1].price:.4g}",
                              highs[-1].date)
        if lows:
            res["void"] = (f"voided on CLOSE < {lows[-1].price:.4g}",
                           lows[-1].date)
    return res


# ----------------------------------------------------------------------------
# 8. ORCHESTRATION + REPORT
# ----------------------------------------------------------------------------
@dataclass
class Result:
    ticker: str
    asset: str
    interval: str
    basis: str
    last_close: float
    last_date: pd.Timestamp
    htf_label: str
    htf_status: dict
    dtosc_status: dict
    dtosc_dlb: dict
    structure: dict
    pivots: list[Pivot]
    price_zones: list[dict] = field(default_factory=list)
    time_band_dates: Optional[tuple] = None
    time_cluster_dates: list = field(default_factory=list)
    decision: dict = field(default_factory=dict)
    eow_kind: str = ""


def analyze(ticker: str = None, market: str = "auto", interval: str = "1d",
            basis: str = "close", swing_pct: float = 3.0, dtosc_set: int = 2,
            ma: str = "sma", htf: Optional[str] = None,
            df: Optional[pd.DataFrame] = None,
            resolved: Optional[str] = None) -> Result:
    # --- data ---
    asset = "custom"
    if df is None:
        cands, asset, _ = normalize_ticker(ticker, market)
        df, resolved = fetch_data(cands, interval)
    resolved = resolved or (ticker or "DATA")

    # --- series (close-based by default = Miner) ---
    series = df["Close"].copy()
    series.index = pd.DatetimeIndex(series.index)

    # --- DTosc current TF + DLB (second param set) ---
    a, b, c, d = DTOSC_SETS[dtosc_set]
    K, D = dtosc(series, a, b, c, d, ma)
    st = dtosc_status(K, D)
    dlb_set = 3 if dtosc_set <= 2 else 4
    a2, b2, c2, d2 = DTOSC_SETS[dlb_set]
    K2, D2 = dtosc(series, a2, b2, c2, d2, ma)
    st2 = dtosc_status(K2, D2)
    dlb = {"set": dlb_set, "params": (a2, b2, c2, d2),
           "agree": st["dir"] == st2["dir"], **st2}

    # --- higher timeframe frame ---
    rule = htf or HTF_RULE.get(interval, "W")
    htf_close = series.resample(rule).last().dropna()
    if len(htf_close) > (a2 + b2 + c2 + d2):
        hK, hD = dtosc(htf_close, a, b, c, d, ma)
        htf_status = dtosc_status(hK, hD)
    else:
        htf_status = {"K": None, "D": None, "dir": "n/a", "zone": "n/a", "cross": None}

    # --- pivots + structure ---
    piv = zigzag_pivots(series, swing_pct)
    struct = classify_structure(piv)
    highs = [p for p in piv if p.kind == "H"]
    lows = [p for p in piv if p.kind == "L"]

    # --- price target zones (pick EOW-C or EOW-5 from auto structure) ---
    price_zones, eow_kind = [], ""
    ref = float(series.iloc[-1])
    if len(piv) >= 4:
        if struct.get("overlap"):  # treat as correction -> EOW-C
            # last 3 legs as O(prior_start)->prior_end, A, B
            p = piv[-4:]
            prior_start, prior_end, A, B = p[0].price, p[1].price, p[2].price, p[3].price
            comp = eow_c_targets(prior_start, prior_end, A, B)
            eow_kind = "EOW-C (correction)"
        else:                       # impulse -> EOW-5
            p = piv[-5:] if len(piv) >= 5 else piv[-4:]
            if len(p) >= 4:
                W0, W1, W3, W4 = p[-4].price, p[-3].price, p[-2].price, p[-1].price
                comp = eow_5_targets(W0, W1, W3, W4)
                eow_kind = "EOW-5 (impulse)"
            else:
                comp = {}
        if comp:
            price_zones = cluster_zones(comp, ref, tol_pct=0.6, top=3)

    # --- time band + cluster ---
    tband = time_band(highs, lows)
    tband_dates = None
    if tband:
        tband_dates = (idx_to_date(series.index, tband[0]),
                       idx_to_date(series.index, tband[1]))
    tcluster_dates = []
    if len(piv) >= 4:
        last = piv[-4:]
        tcomp = {
            "TimeRet": time_ret(last[0].idx, last[1].idx),
            "ATP": atp_time(last[0].idx, last[1].idx, last[2].idx),
        }
        for bar_idx, hits in time_cluster(tcomp, win=1):
            tcluster_dates.append((idx_to_date(series.index, bar_idx), hits))

    # --- decision ---
    dec = decision_levels(piv, struct, series)

    return Result(
        ticker=resolved, asset=asset, interval=interval, basis=basis,
        last_close=ref, last_date=series.index[-1],
        htf_label=rule, htf_status=htf_status,
        dtosc_status=st, dtosc_dlb=dlb, structure=struct, pivots=piv,
        price_zones=price_zones, time_band_dates=tband_dates,
        time_cluster_dates=tcluster_dates, decision=dec, eow_kind=eow_kind,
    )


def fmt_date(d) -> str:
    try:
        return pd.Timestamp(d).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return str(d)


def print_report(r: Result) -> None:
    bar = "=" * 74
    print(bar)
    print(f" DYNAMIC TRADER ANALYSIS  —  {r.ticker}   [{r.asset}]")
    print(f" Interval: {r.interval}  |  Basis: {r.basis.upper()}  |  "
          f"Last close: {r.last_close:.6g}  ({fmt_date(r.last_date)})")
    print(bar)

    # FRAME (higher TF)
    h = r.htf_status
    print(f"\n[FRAME] Higher TF ({r.htf_label}) DTosc: "
          f"{h['dir']} / {h['zone']}"
          + (f"  K={h['K']} D={h['D']}" if h['K'] is not None else ""))
    print("  -> only take trades in this direction (Miner: trade with larger TF).")

    # MOMENTUM
    s, dlb = r.dtosc_status, r.dtosc_dlb
    print(f"\n[MOMENTUM] DTosc {r.interval}  K={s['K']} D={s['D']}  "
          f"-> {s['dir']} / {s['zone']}"
          + (f"  | {s['cross']}" if s['cross'] else ""))
    print(f"  DLB set{dlb['set']} {dlb['params']}: {dlb['dir']} / {dlb['zone']}"
          f"  -> {'AGREE' if dlb['agree'] else 'DISAGREE'} with primary")

    # STRUCTURE
    st = r.structure
    print(f"\n[STRUCTURE] (auto — VERIFY)  {st.get('pattern')}")
    print(f"  Current: {st.get('wave')}   |   bias: {st.get('bias')}")
    if r.pivots:
        tail = r.pivots[-5:]
        legs = "  ".join(f"{p.kind}:{p.price:.4g}@{fmt_date(p.date)}" for p in tail)
        print(f"  Pivots(last5): {legs}")

    # PRICE
    print(f"\n[PRICE]  {r.eow_kind or 'EOW target zones'}  (zones, not lines)")
    if r.price_zones:
        conv = [z for z in r.price_zones if z["groups"] >= 2]
        if not conv:
            print("  No multi-set convergence yet -> top single projections "
                  "(Miner trades the ZONE where >=2 sets cluster):")
        for i, z in enumerate(r.price_zones, 1):
            star = " *CONVERGENCE*" if z["groups"] >= 2 else ""
            rng = (f"{z['low']:.6g}" if abs(z['high'] - z['low']) < 1e-9
                   else f"{z['low']:.6g} - {z['high']:.6g}")
            print(f"  Zone {i}: {rng}{star}   score={z['score']} "
                  f"({z['groups']} set/s, {z['n']} hit/s)")
            print(f"           {', '.join(z['members'])}")
    else:
        print("  (need >=4 clean pivots; widen --swing-pct or set pivots manually)")

    # TIME
    print("\n[TIME]  turning-period")
    if r.time_band_dates:
        print(f"  Time Band: {fmt_date(r.time_band_dates[0])} -> "
              f"{fmt_date(r.time_band_dates[1])}")
    else:
        print("  Time Band: (need >=3 highs & >=2 lows)")
    if r.time_cluster_dates:
        cl = ", ".join(f"{fmt_date(dt)}(x{h})" for dt, h in r.time_cluster_dates[:3])
        print(f"  Cluster dates: {cl}")

    # DECISION
    print("\n[DECISION]  trigger / void  (CLOSE basis)")
    if r.decision:
        if "trigger" in r.decision:
            t, dt = r.decision["trigger"]
            print(f"  Trigger: {t}   (ref {fmt_date(dt)})")
        if "void" in r.decision:
            v, dt = r.decision["void"]
            print(f"  Void   : {v}   (ref {fmt_date(dt)})")
    else:
        print("  (insufficient swings)")

    print("\n" + "-" * 74)
    print(" Learn to trade, not forecast. Zones, not lines. The auto pivot/")
    print(" pattern/wave read is a STARTING POINT — Miner's edge is discretionary")
    print(" pivot & pattern selection. Override for Miner-grade exactness.")
    print(bar + "\n")


def zone_from_pivots(prices: list[float], kind: str = "5",
                     price_ref: Optional[float] = None,
                     tol_pct: float = 0.6) -> tuple[dict, list[dict]]:
    """
    EXACT Miner reproduction from MANUAL pivots (punch in the prices Miner
    labels on his chart -> get his exact EOW zone).
      kind='c' : prices = [prior_start, prior_end, WaveA, WaveB]  (EOW-C)
      kind='5' : prices = [W0, W1, W3, W4]                        (EOW-5)
    Returns (components, clustered_zones).
    """
    if len(prices) != 4:
        raise ValueError("need exactly 4 pivot prices "
                         "(EOW-C: prior_start,prior_end,A,B | EOW-5: W0,W1,W3,W4)")
    p0, p1, p2, p3 = (float(x) for x in prices)
    if kind == "c":
        comp = eow_c_targets(p0, p1, p2, p3)
    else:
        comp = eow_5_targets(p0, p1, p2, p3)
    ref = price_ref if price_ref is not None else p3
    zones = cluster_zones(comp, ref, tol_pct=tol_pct, top=5)
    return comp, zones


def print_zone_from_pivots(prices, kind, ref=None, tol_pct=0.6):
    comp, zones = zone_from_pivots(prices, kind, ref, tol_pct)
    name = "EOW-C" if kind == "c" else "EOW-5"
    print("=" * 64)
    print(f" {name} EXACT PROJECTION  (manual pivots {prices})")
    print("=" * 64)
    print("\nAll projections:")
    for grp, d in comp.items():
        for lbl, price in d.items():
            print(f"  {grp:18s} {lbl:14s} = {price:.6g}")
    print("\nClustered zones (>=2 sets = high-probability EOW zone):")
    for i, z in enumerate(zones, 1):
        star = " *CONVERGENCE*" if z["groups"] >= 2 else ""
        rng = (f"{z['low']:.6g}" if abs(z['high'] - z['low']) < 1e-9
               else f"{z['low']:.6g} - {z['high']:.6g}")
        print(f"  Zone {i}: {rng}{star}  score={z['score']} "
              f"({z['groups']} set/s) :: {', '.join(z['members'])}")
    print("=" * 64 + "\n")


# ----------------------------------------------------------------------------
# 9. CLI
# ----------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Robert Miner / Dynamic Trader multi-asset analyzer")
    ap.add_argument("ticker", nargs="?", default=None,
                    help="e.g. HUMI, USDJPY, BTC, GOLD, NVDA, ^GSPC "
                         "(optional if using --eow/--pivots)")
    ap.add_argument("--market", default="auto",
                    choices=["auto", "us", "idx", "forex", "commodity", "crypto"])
    ap.add_argument("--interval", default="1d",
                    help="1d,1wk,1h,60m,30m,15m,5m (default 1d)")
    ap.add_argument("--basis", default="close", choices=["close", "range"],
                    help="Miner default = close")
    ap.add_argument("--swing-pct", type=float, default=3.0,
                    help="zigzag pivot threshold %% (try 2-5)")
    ap.add_argument("--dtosc-set", type=int, default=2, choices=[1, 2, 3, 4])
    ap.add_argument("--ma", default="sma", choices=["sma", "ema"],
                    help="DTosc smoothing (calibrate to Miner's chart)")
    ap.add_argument("--htf", default=None,
                    help="override higher-TF rule (W, ME, 1D, h)")
    ap.add_argument("--period", default=None, help="yfinance period override")
    ap.add_argument("--eow", choices=["c", "5"], default=None,
                    help="manual EOW projection mode (use with --pivots)")
    ap.add_argument("--pivots", default=None,
                    help="4 prices for --eow. C: prior_start,prior_end,A,B | "
                         "5: W0,W1,W3,W4  (e.g. 7000,7050,7150,7100)")
    ap.add_argument("--ref", type=float, default=None,
                    help="reference price for cluster tolerance (default last pivot)")
    args = ap.parse_args(argv)

    # ---- standalone exact-projection mode (no data fetch) ----
    if args.eow and args.pivots:
        prices = [float(x) for x in args.pivots.split(",")]
        print_zone_from_pivots(prices, args.eow, args.ref)
        return

    if not args.ticker:
        ap.error("ticker is required (or use --eow with --pivots)")

    r = analyze(ticker=args.ticker, market=args.market, interval=args.interval,
                basis=args.basis, swing_pct=args.swing_pct,
                dtosc_set=args.dtosc_set, ma=args.ma, htf=args.htf)
    print_report(r)


if __name__ == "__main__":
    main()
