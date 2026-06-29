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
# Miner's set-to-timeframe mapping (from the book): pick by the chart interval.
INTERVAL_DTOSC_SET = {"1mo": 1, "1wk": 2, "1d": 2, "1h": 3, "60m": 3,
                      "30m": 3, "15m": 4, "5m": 4}
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
    both = pd.concat([K, D], axis=1).dropna()
    if len(both) < 2:
        return {"K": None, "D": None, "dir": "n/a", "zone": "n/a", "cross": None}
    k, dd = float(both.iloc[-1, 0]), float(both.iloc[-1, 1])
    kp, dp = float(both.iloc[-2, 0]), float(both.iloc[-2, 1])
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


def degree_pivots(series: pd.Series, base_pct: float):
    """Two-degree pivots like Miner. MAJOR = adaptive base (the primary count,
    kept stable); MINOR = finer swings for sub-wave labels."""
    major = zigzag_pivots(series, base_pct)
    minor = zigzag_pivots(series, base_pct * 0.5)
    if len(minor) <= len(major):
        minor = zigzag_pivots(series, base_pct * 0.4)
    return major, minor


def subwaves_between(minor: list, p_start: Pivot, p_end: Pivot) -> list:
    """Minor pivots strictly inside [p_start, p_end] — the sub-structure of a
    major wave (for the smaller-degree labels)."""
    return [q for q in minor if p_start.idx < q.idx < p_end.idx]
    if len(piv) < 3:
        return {"pattern": "n/a", "overlap": None}
    last = piv[-6:]
    overlap = False
    for i in range(2, len(last)):
        a, prev, b = last[i - 2], last[i - 1], last[i]
        lo, hi = min(a.price, prev.price), max(a.price, prev.price)
        if lo <= b.price <= hi:
            overlap = True
    return {"pattern": "CORRECTION" if overlap else "TREND", "overlap": overlap}


# ============================================================================
#  AUTO STRUCTURE ENGINE  (auto wave labeling — best effort, scored)
# ============================================================================
FIB_RET2 = (0.382, 0.50, 0.618, 0.786)
FIB_W3 = (1.0, 1.272, 1.618, 2.618)
FIB_W4 = (0.236, 0.382, 0.50)


@dataclass
class WaveCount:
    pattern: str                 # IMPULSE / ABC / TRIANGLE / UNKNOWN
    direction: str               # 'up' / 'down' (of the operative move)
    current_wave: str
    proj_kind: str               # 'eow5' / 'eowc' / 'thrust' / ''
    proj_pivots: list = field(default_factory=list)   # list[Pivot]
    score: float = 0.0
    guidelines_ok: bool = False
    expect: str = ""             # what we expect next
    detail: str = ""
    margin: float = 99.0         # score gap over the alternate count
    skeleton: list = field(default_factory=list)   # pivots used (for labels)

    @property
    def confidence(self) -> str:
        if self.margin < 0.4:        # too close to the alternate = ambiguous
            return "LOW"
        if self.guidelines_ok and self.score >= 3.3 and self.margin >= 0.8:
            return "HIGH"
        if self.score >= 2.0:
            return "MED"
        return "LOW"


def _nf(r: float, fibs) -> float:
    return min(abs(r - f) for f in fibs)


def atr_pct(df: pd.DataFrame, n: int = 14) -> float:
    if not {"High", "Low", "Close"}.issubset(df.columns):
        s = df["Close"].pct_change().abs().rolling(n).mean().dropna()
        return float(s.iloc[-1]) if len(s) else 0.02
    h, l, c = df["High"], df["Low"], df["Close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l).abs(), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr = tr.rolling(n).mean()
    s = (atr / c).replace([np.inf, -np.inf], np.nan).dropna()
    return float(s.iloc[-1]) if len(s) else 0.02


def auto_swing_pct(df: pd.DataFrame, series: pd.Series) -> float:
    """Adaptive zigzag threshold: ~3x ATR%, then refine to a sane pivot count."""
    if len(series) < 5:
        return 3.0
    base = max(1.0, min(8.0, atr_pct(df) * 100.0 * 3.0))
    pct = base
    for _ in range(6):
        n = len(zigzag_pivots(series, pct))
        if n < 7 and pct > 0.6:
            pct *= 0.8
        elif n > 22:
            pct *= 1.25
        else:
            break
    return round(pct, 2)


def score_impulse(q: list[Pivot]):
    """W1-4 complete + W5 in progress. q = 5-pivot skeleton (p0..p4)."""
    if len(q) < 5:
        return None
    s = q[-5:]
    p0, p1, p2, p3, p4 = (x.price for x in s)
    kinds = [x.kind for x in s]
    up = p1 > p0
    if up and kinds != ["L", "H", "L", "H", "L"]:
        return None
    if (not up) and kinds != ["H", "L", "H", "L", "H"]:
        return None
    W1, W2, W3, W4 = abs(p1 - p0), abs(p2 - p1), abs(p3 - p2), abs(p4 - p3)
    if min(W1, W3) <= 0:
        return None
    hard = 0.0
    if up and p2 <= p0:        # W2 beyond start
        hard += 3
    if (not up) and p2 >= p0:
        hard += 3
    if up and p4 < p1:         # W4 overlaps W1
        hard += 2 * (p1 - p4) / W1
    if (not up) and p4 > p1:
        hard += 2 * (p4 - p1) / W1
    if W3 < W1:                # W3 shortest tendency
        hard += 1.5 * (1 - W3 / W1)
    soft = _nf(W2 / W1, FIB_RET2) + _nf(W3 / W1, FIB_W3) + _nf(W4 / W3, FIB_W4)
    score = 5.0 - hard - soft
    wc = WaveCount(
        "IMPULSE", "up" if up else "down",
        f"Wave-5 {'up' if up else 'down'} (in progress)", "eow5",
        [s[0], s[1], s[3], s[4]], score, hard < 0.5,
        "top/reversal once W5 completes" if up else "bottom/reversal once W5 completes",
        f"W1={W1:.4g} W2={W2:.4g} W3={W3:.4g} W4={W4:.4g}", skeleton=list(s))
    return score, wc


def score_abc(q: list[Pivot]):
    """A,B complete + C in progress. q = 4 pivots [prior_start, prior_end, A, B]."""
    if len(q) < 4:
        return None
    s = q[-4:]
    r0, r1, r2, r3 = (x.price for x in s)
    kinds = [x.kind for x in s]
    down_corr = (kinds == ["L", "H", "L", "H"])   # bull trend, correcting down (C down)
    up_corr = (kinds == ["H", "L", "H", "L"])     # bear trend, correcting up (C up)
    if not (down_corr or up_corr):
        return None
    prior = abs(r1 - r0)
    A = abs(r2 - r1)
    B = abs(r3 - r2)
    if min(prior, A) <= 0:
        return None
    hard = 0.0
    if down_corr and r3 >= r1:    # B above prior high -> not a clean down-correction
        hard += 2
    if up_corr and r3 <= r1:
        hard += 2
    # B should retrace a meaningful part of A (zigzag) but not exceed it fully
    if B / A > 1.05:
        hard += 1.5 * (B / A - 1.0)
    soft = _nf(B / A, (0.382, 0.5, 0.618, 0.786, 0.886)) + _nf(A / prior, (0.382, 0.5, 0.618, 1.0, 1.618))
    score = 4.4 - hard - soft
    direction = "down" if down_corr else "up"
    wc = WaveCount(
        "ABC", direction, f"Wave-C {direction} (in progress)", "eowc",
        [s[0], s[1], s[2], s[3]], score, hard < 0.5,
        "up-reversal once Wave-C completes" if down_corr
        else "down-reversal once Wave-C completes",
        f"prior={prior:.4g} A={A:.4g} B={B:.4g} (B/A={B/A:.2f})", skeleton=list(s))
    return score, wc


def score_triangle(q: list[Pivot]):
    """Contracting ABCDE (overlapping, shrinking legs) — typically W4/Wave-B."""
    if len(q) < 6:
        return None
    s = q[-6:]
    legs = [abs(s[i + 1].price - s[i].price) for i in range(5)]
    if min(legs) <= 0:
        return None
    # require general contraction (each leg <= prior * 1.05, mostly shrinking)
    shrink = sum(1 for i in range(4) if legs[i + 1] <= legs[i] * 1.05)
    if shrink < 3:
        return None
    # overlap of successive swing ranges
    overlaps = 0
    for i in range(2, 6):
        lo, hi = sorted((s[i - 2].price, s[i - 1].price))
        if lo <= s[i].price <= hi:
            overlaps += 1
    if overlaps < 2:
        return None
    width = max(legs)
    e = s[-1]
    last_up = s[-1].price > s[-2].price
    thrust_up = not last_up
    target_mid = e.price + (width if thrust_up else -width)
    # clean contracting triangle should beat a forced ABC fit
    score = 3.2 + 0.2 * shrink + 0.2 * overlaps
    wc = WaveCount(
        "TRIANGLE", "up" if thrust_up else "down",
        "Wave-E of triangle (W4/B) — thrust pending", "thrust",
        [e], score, shrink >= 4 and overlaps >= 3,
        f"{'up' if thrust_up else 'down'} thrust ~{target_mid:.4g} after E completes",
        f"legs={[round(x,3) for x in legs]} width={width:.4g}", skeleton=list(s))
    wc._thrust = (e.price, width, thrust_up)  # type: ignore
    return score, wc


def label_structure(pivots: list[Pivot]) -> tuple[Optional[WaveCount], Optional[WaveCount]]:
    """Try all templates on recent pivots, return (primary, alternate)."""
    if len(pivots) < 4:
        return None, None
    cands = []
    for scorer, need in ((score_impulse, 5), (score_abc, 4), (score_triangle, 6)):
        if len(pivots) >= need:
            res = scorer(pivots)
            if res:
                cands.append(res)
        # also try one pivot earlier (in case last pivot is noise)
        if len(pivots) >= need + 1:
            res = scorer(pivots[:-1])
            if res:
                sc, wc = res
                cands.append((sc - 0.3, wc))   # slight penalty for older window
    if not cands:
        return None, None
    cands.sort(key=lambda x: x[0], reverse=True)
    primary = cands[0][1]
    alternate = cands[1][1] if len(cands) > 1 and cands[1][1].pattern != primary.pattern else None
    if len(cands) > 1:
        primary.margin = round(cands[0][0] - cands[1][0], 2)
    return primary, alternate


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


APP_PROJ = ((0.618, 2.0), (1.000, 3.0), (1.618, 2.0))   # ratio, weight


def swing_triples(pivots: list, kind: str) -> list:
    """Consecutive 3-pivot triples of a shape. 'LHL' (Low-High-Low → up target)
    or 'HLH' (High-Low-High → down target)."""
    want = ["L", "H", "L"] if kind == "LHL" else ["H", "L", "H"]
    return [pivots[i:i + 3] for i in range(len(pivots) - 2)
            if [p.kind for p in pivots[i:i + 3]] == want]


def _cluster_levels(levels: list, ref: float, tol_pct: float = 0.5,
                    top: int = 4) -> tuple:
    """levels: list of (price, label, weight). Returns (zones, raw_levels)."""
    raw = [{"price": p, "label": lbl} for p, lbl, _w in levels]
    if not levels:
        return [], raw
    levels = sorted(levels, key=lambda x: x[0])
    tol = ref * tol_pct / 100.0
    zones, used = [], [False] * len(levels)
    for i in range(len(levels)):
        if used[i]:
            continue
        grp = [levels[i]]
        used[i] = True
        for j in range(i + 1, len(levels)):
            if not used[j] and levels[j][0] - grp[0][0] <= tol:
                grp.append(levels[j])
                used[j] = True
        prices = [g[0] for g in grp]
        labels = {g[1] for g in grp}
        zones.append({"low": min(prices), "high": max(prices),
                      "mid": float(np.mean(prices)),
                      "score": round(sum(g[2] for g in grp), 1),
                      "n": len(grp), "groups": len(labels),
                      "members": sorted(labels)})
    zones.sort(key=lambda z: (z["n"], z["score"]), reverse=True)
    return zones[:top], raw


def price_cluster_md(major: list, minor: list, direction: str, ref: float,
                     tol_pct: float = 0.5) -> tuple:
    """Miner-style price target: APP projected from MULTIPLE swing triples at
    two degrees, then clustered. direction='up' → LHL triples (target ABOVE);
    'down' → HLH triples (target BELOW). Returns (zones, raw_levels)."""
    kind = "LHL" if direction == "up" else "HLH"
    levels = []
    for pivs, degw in ((major, 1.3), (minor, 0.8)):
        for t in swing_triples(pivs, kind)[-6:]:
            a, b, c = t[0].price, t[1].price, t[2].price
            rng = b - a
            for ratio, w in APP_PROJ:
                levels.append((c + rng * ratio, f"App {ratio:.3f}", w * degw))
    if direction == "up":
        levels = [L for L in levels if L[0] > ref * 1.001]
    else:
        levels = [L for L in levels if L[0] < ref * 0.999]
    return _cluster_levels(levels, ref, tol_pct)


def time_cluster_md(major: list, minor: list, last_idx: int, win: int = 2) -> tuple:
    """Miner-style reversal timing: project H-H and L-L cycles (two degrees) by
    Fib ratios, cluster forward projections. Returns (ranked, peak_idx,
    strength, members)."""
    proj = []
    for pivs, degw in ((major, 1.3), (minor, 0.8)):
        for knd in ("H", "L"):
            seq = [p for p in pivs if p.kind == knd]
            for i in range(len(seq) - 1):
                cyc = seq[i + 1].idx - seq[i].idx
                if cyc <= 0:
                    continue
                for ratio in (0.618, 1.0, 1.618):
                    proj.append((seq[i + 1].idx + int(round(cyc * ratio)), degw))
    proj = [(x, w) for x, w in proj if x >= last_idx - 1]
    if not proj:
        return [], None, None, None
    scored = {x: sum(w for y, w in proj if abs(y - x) <= win)
              for x, _ in proj}
    ranked = sorted(scored.items(), key=lambda kv: kv[1], reverse=True)
    peak_idx = ranked[0][0]
    members = [y for y, _w in proj if abs(y - peak_idx) <= win]
    return ranked, peak_idx, len(members), members


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
def decision_levels(wc: Optional[WaveCount], piv: list[Pivot]) -> dict:
    """Trigger/void CLOSE levels from the auto wave count's own pivots.
    eowc -> Miner go-signal = close beyond Wave-B; void = beyond prior-trend start.
    eow5 -> reversal confirmed = close beyond W4 extreme."""
    if not wc or not wc.proj_pivots:
        return {}
    pp = wc.proj_pivots
    res = {}
    if wc.proj_kind == "eowc" and len(pp) >= 4:
        prior_start, _prior_end, _A, B = pp[0], pp[1], pp[2], pp[3]
        if wc.direction == "down":          # C turun, lalu lanjut NAIK
            res["trigger"] = (f"koreksi selesai → BELI kalau CLOSE di ATAS "
                              f"{B.price:.6g} (di atas Wave-B)", B.date)
            res["void"] = (f"skenario batal kalau CLOSE di BAWAH "
                           f"{prior_start.price:.6g} (titik awal tren)", prior_start.date)
        else:                                # C naik, lalu lanjut TURUN
            res["trigger"] = (f"koreksi selesai → JUAL kalau CLOSE di BAWAH "
                              f"{B.price:.6g} (di bawah Wave-B)", B.date)
            res["void"] = (f"skenario batal kalau CLOSE di ATAS "
                           f"{prior_start.price:.6g} (titik awal tren)", prior_start.date)
    elif wc.proj_kind == "eow5" and len(pp) >= 4:
        W4 = pp[3]
        if wc.direction == "up":             # puncak → reversal TURUN
            res["trigger"] = (f"puncak Wave-5 selesai → JUAL kalau CLOSE di BAWAH "
                              f"{W4.price:.6g} (low Wave-4)", W4.date)
        else:                                # dasar → reversal NAIK
            res["trigger"] = (f"dasar Wave-5 selesai → BELI kalau CLOSE di ATAS "
                              f"{W4.price:.6g} (high Wave-4)", W4.date)
    elif wc.proj_kind == "thrust" and hasattr(wc, "_thrust"):
        e, _w, up = wc._thrust
        d0 = pp[0].date if pp else None
        if up:
            res["trigger"] = (f"dorongan NAIK kalau CLOSE di ATAS {e:.6g} "
                              f"(di atas Wave-E)", d0)
        else:
            res["trigger"] = (f"dorongan TURUN kalau CLOSE di BAWAH {e:.6g} "
                              f"(di bawah Wave-E)", d0)
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
    pivots: list[Pivot]
    minor_pivots: list = field(default_factory=list)
    swing_pct: float = 0.0
    wave_pattern: str = "UNKNOWN"
    current_wave: str = ""
    confidence: str = "LOW"
    expect: str = ""
    wave_detail: str = ""
    alternate: str = ""
    proj_kind: str = ""
    wave_dir: str = ""
    wave_labels: list = field(default_factory=list)
    proj_levels: list = field(default_factory=list)
    dtosc_k: Optional[pd.Series] = None
    dtosc_d: Optional[pd.Series] = None
    price_zones: list[dict] = field(default_factory=list)
    time_band_dates: Optional[tuple] = None
    time_cluster_dates: list = field(default_factory=list)
    reversal_date: Optional[pd.Timestamp] = None
    reversal_strength: Optional[int] = None
    reversal_window: Optional[tuple] = None
    decision: dict = field(default_factory=dict)
    eow_kind: str = ""


def analyze(ticker: str = None, market: str = "auto", interval: str = "1d",
            basis: str = "close", swing_pct: Optional[float] = None,
            dtosc_set: Optional[int] = None, ma: str = "ema",
            htf: Optional[str] = None, df: Optional[pd.DataFrame] = None,
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
    if len(series) < 20:
        raise ValueError(
            f"Data cuma {len(series)} bar — kependekan buat analisis (butuh ≥20). "
            f"Coba ticker lain, ganti Market, atau interval yang lebih besar.")

    # auto-pick DTosc set from interval (Miner's set-to-timeframe mapping)
    if dtosc_set is None:
        dtosc_set = INTERVAL_DTOSC_SET.get(interval, 2)

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

    # --- two-degree pivots (Miner nests degrees): count on MAJOR swings ---
    pct = swing_pct if swing_pct is not None else auto_swing_pct(df, series)
    major_piv, minor_piv = degree_pivots(series, pct)
    piv = major_piv                       # primary count uses the larger degree
    primary, alt = label_structure(piv)
    highs = [p for p in piv if p.kind == "H"]
    lows = [p for p in piv if p.kind == "L"]
    ref = float(series.iloc[-1])

    # --- PRICE TARGET (Miner cluster): APP from many LHL/HLH triples, 2 degrees ---
    # Direction from the wave read: up = expecting a HIGH (LHL triples → target
    # above); down = expecting a LOW (HLH triples → target below). The cluster of
    # many projections (small + large swings) IS the target — not one wave count.
    price_zones, eow_kind = [], "structure unclear"
    proj_levels = []
    target_dir = primary.direction if (primary and primary.direction in ("up", "down")) \
        else ("up" if ref >= float(series.iloc[0]) else "down")
    price_zones, proj_levels = price_cluster_md(major_piv, minor_piv, target_dir, ref)
    if primary:
        eow_kind = {"eow5": "EOW-5 (impulse W5)", "eowc": "EOW-C (Wave-C)",
                    "thrust": "Triangle thrust (post-E)"}.get(primary.proj_kind,
                                                              "APP cluster")

    # --- TIME (Miner cluster): H-H & L-L cycles at 2 degrees, projected by Fib ---
    n_bars = len(series)
    ranked, peak_idx, reversal_strength, members = time_cluster_md(
        major_piv, minor_piv, n_bars - 1,
        win=2 if interval in ("1d", "1h", "60m", "30m", "15m", "5m") else 1)
    reversal_date = reversal_window = None
    tcluster_dates = []
    if peak_idx is not None:
        reversal_date = idx_to_date(series.index, peak_idx)
        reversal_window = (idx_to_date(series.index, min(members)),
                           idx_to_date(series.index, max(members)))
        for bi, hits in ranked[:3]:
            tcluster_dates.append((idx_to_date(series.index, bi), int(round(hits))))

    # Time Band (Bressert) kept as secondary range context
    tband = time_band(highs, lows)
    tband_dates = None
    if tband:
        tband_dates = (idx_to_date(series.index, tband[0]),
                       idx_to_date(series.index, tband[1]))

    dec = decision_levels(primary, piv)

    alt_str = ""
    if alt:
        alt_str = f"{alt.pattern} / {alt.current_wave} (conf {alt.confidence})"

    # wave labels — TWO degrees (Miner style): MAJOR (1)(2)(3) + minor sub-waves
    wave_labels = []
    if primary and primary.skeleton:
        major_names = {"IMPULSE": ["(0)", "(1)", "(2)", "(3)", "(4)"],
                       "ABC": ["x", "(0)", "(A)", "(B)"],
                       "TRIANGLE": ["(A)", "(B)", "(C)", "(D)", "(E)", "x"]}.get(
            primary.pattern, [])
        for pv, nm in zip(primary.skeleton, major_names):
            wave_labels.append({"date": pv.date, "price": pv.price,
                                "label": nm, "deg": "major", "kind": pv.kind})
        cur = {"eow5": "(5)", "eowc": "(C)", "thrust": "→"}.get(primary.proj_kind, "?")
        cur_kind = "H" if primary.direction == "up" else "L"
        wave_labels.append({"date": series.index[-1], "price": float(series.iloc[-1]),
                            "label": cur + "?", "deg": "major", "kind": cur_kind})
        # minor sub-waves inside the CURRENT (last) major wave
        sk = primary.skeleton
        seg_start = sk[-1]
        cur_pivot = Pivot(len(series) - 1, series.index[-1], float(series.iloc[-1]),
                          "H" if primary.direction == "up" else "L")
        subs = subwaves_between(minor_piv, seg_start, cur_pivot)
        sub_letters = ["i", "ii", "iii", "iv", "v"]
        for k, q in enumerate(subs[:5]):
            wave_labels.append({"date": q.date, "price": q.price,
                                "label": sub_letters[k], "deg": "minor", "kind": q.kind})

    return Result(
        ticker=resolved, asset=asset, interval=interval, basis=basis,
        last_close=ref, last_date=series.index[-1],
        htf_label=rule, htf_status=htf_status,
        dtosc_status=st, dtosc_dlb=dlb, pivots=piv, swing_pct=pct,
        wave_pattern=(primary.pattern if primary else "UNKNOWN"),
        current_wave=(primary.current_wave if primary else "unclear"),
        confidence=(primary.confidence if primary else "LOW"),
        expect=(primary.expect if primary else ""),
        wave_detail=(primary.detail if primary else ""),
        alternate=alt_str,
        proj_kind=(primary.proj_kind if primary else ""),
        wave_dir=(primary.direction if primary else ""),
        wave_labels=wave_labels, dtosc_k=K, dtosc_d=D, proj_levels=proj_levels,
        minor_pivots=minor_piv,
        price_zones=price_zones, time_band_dates=tband_dates,
        time_cluster_dates=tcluster_dates, reversal_date=reversal_date,
        reversal_strength=reversal_strength, reversal_window=reversal_window,
        decision=dec, eow_kind=eow_kind,
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

    # STRUCTURE (auto wave count)
    print(f"\n[STRUCTURE] {r.wave_pattern}  |  confidence: {r.confidence}  "
          f"(auto — verify)")
    print(f"  Current: {r.current_wave}")
    if r.expect:
        print(f"  Expect : {r.expect}")
    if r.wave_detail:
        print(f"  Legs   : {r.wave_detail}")
    if r.alternate:
        print(f"  Alt    : {r.alternate}")
    print(f"  Pivot threshold (adaptive): {r.swing_pct}%")
    if r.pivots:
        tail = r.pivots[-6:]
        legs = "  ".join(f"{p.kind}:{p.price:.4g}@{fmt_date(p.date)}" for p in tail)
        print(f"  Pivots(last6): {legs}")

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
    ap.add_argument("--swing-pct", type=float, default=None,
                    help="zigzag pivot threshold %% (default: adaptive ATR-based)")
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


def _conf_color(c: str) -> str:
    return {"HIGH": "green", "MED": "orange", "LOW": "red"}.get(c, "gray")


def _target_zone(r):
    """Densest cluster zone. price_cluster_md already filtered to the target
    direction (above ref for tops, below for bottoms) and sorted densest-first."""
    if not r.price_zones:
        return None
    conv = [z for z in r.price_zones if z.get("n", 1) >= 2 or z.get("groups", 1) >= 2]
    return conv[0] if conv else r.price_zones[0]


def _eta(r):
    """Reversal window: cluster-peak window > Time Band > cluster date > None."""
    if r.reversal_window:
        return r.reversal_window
    if r.reversal_date is not None:
        return (r.reversal_date, r.reversal_date)
    if r.time_band_dates:
        return r.time_band_dates
    if r.time_cluster_dates:
        d = r.time_cluster_dates[0][0]
        return (d, d)
    return None


def trade_plan(r) -> dict:
    """Plain-language, actionable trade plan (Indonesian) — always shows concrete
    price + date numbers."""
    z = _target_zone(r)
    eta = _eta(r)
    trig = r.decision.get("trigger")
    void = r.decision.get("void")
    htf = r.htf_status.get("dir", "n/a")
    pk, wd = r.proj_kind, r.wave_dir

    # explicit numbers
    if z:
        mid = z["mid"]
        zone_txt = (f"~{mid:.6g}" if abs(z["high"] - z["low"]) < 1e-9
                    else f"~{mid:.6g}  (kisaran {z['low']:.6g} – {z['high']:.6g})")
        target_num = f"{mid:.6g}"
    else:
        zone_txt, target_num = "belum bisa dihitung", "—"
    eta_txt = f"{fmt_date(eta[0])} – {fmt_date(eta[1])}" if eta else "belum bisa dihitung"
    if r.reversal_date is not None:
        rev_date_txt = fmt_date(r.reversal_date)
        strength_txt = (f" ({r.reversal_strength} proyeksi numpuk)"
                        if r.reversal_strength and r.reversal_strength > 1 else "")
    else:
        rev_date_txt, strength_txt = (eta_txt.split(" – ")[0] if eta else "—"), ""

    expecting_top = (pk == "eow5" and wd == "up") or (pk == "eowc" and wd == "up")
    expecting_bottom = (pk == "eow5" and wd == "down") or (pk == "eowc" and wd == "down")
    is_thrust = pk == "thrust"

    wave_human = {
        ("eow5", "up"): "gelombang NAIK ke-5 (terakhir) — fase sebelum PUNCAK, lalu balik turun",
        ("eow5", "down"): "gelombang TURUN ke-5 (terakhir) — fase sebelum DASAR, lalu balik naik",
        ("eowc", "down"): "koreksi TURUN (Wave-C) — fase sebelum DASAR, lalu lanjut NAIK lagi",
        ("eowc", "up"): "koreksi NAIK (Wave-C) — fase sebelum PUNCAK, lalu lanjut TURUN lagi",
        ("thrust", "up"): "pola SEGITIGA (A-B-C-D-E) hampir selesai — habis ini dorongan NAIK",
        ("thrust", "down"): "pola SEGITIGA (A-B-C-D-E) hampir selesai — habis ini dorongan TURUN",
    }.get((pk, wd), "struktur belum jelas — tunggu setup lebih rapi")

    p = {"now": wave_human, "target_price_txt": zone_txt, "target_num": target_num,
         "eta_txt": eta_txt, "rev_date_txt": rev_date_txt, "strength_txt": strength_txt,
         "confidence": r.confidence, "trend_htf": htf,
         "expecting_top": expecting_top, "expecting_bottom": expecting_bottom,
         "is_thrust": is_thrust, "last": r.last_close}
    p["topbottom"] = ("PUNCAK (TOP)" if expecting_top else
                      "DASAR (BOTTOM)" if expecting_bottom else
                      ("DORONGAN NAIK" if (is_thrust and wd == "up") else
                       "DORONGAN TURUN" if is_thrust else "belum jelas"))

    if is_thrust:
        up = wd == "up"
        p["headline"] = (f"BREAKOUT SEGITIGA — siap dorongan {'NAIK' if up else 'TURUN'}")
        p["side"] = "LONG / BELI" if up else "SHORT / JUAL"
        p["entry_rule"] = trig[0] if trig else "tunggu harga keluar dari segitiga"
        p["entry_explain"] = (
            f"Harga lagi mampet di pola segitiga (A-B-C-D-E). Setelah selesai, biasanya "
            f"ada dorongan tajam {'NAIK' if up else 'TURUN'}. Masuk pas konfirmasi breakout: "
            f"{p['entry_rule']}. Perkiraan target dorongan: {zone_txt}.")
        p["stop_rule"] = (f"kalau balik masuk ke dalam segitiga (CLOSE {'<' if up else '>'} "
                          f"sisi segitiga)")
        p["profit"] = f"Target dorongan ~{target_num}. Pakai trailing stop."
    elif expecting_bottom:
        p["headline"] = "SIAP-SIAP BELI (LONG) — tunggu konfirmasi dasar dulu"
        p["side"] = "LONG / BELI"
        p["entry_rule"] = trig[0] if trig else "tunggu sinyal reversal naik"
        p["entry_explain"] = (
            f"Harga lagi turun nyari DASAR di sekitar {zone_txt}. Jangan beli sekarang "
            f"(itu nangkep pisau jatuh). Tunggu konfirmasi: {p['entry_rule']}. Sebelum "
            f"konfirmasi itu, harga masih bisa lanjut turun ke area {target_num} dulu.")
        p["stop_rule"] = (void[0] if void else
                          (f"kalau CLOSE jebol di bawah {z['low']:.6g}" if z else "—"))
        p["profit"] = ("Setelah masuk, target naik bertahap. Pakai trailing stop — jangan "
                       "exit di satu harga tetap (Miner: biarin market yang exit).")
    elif expecting_top:
        p["headline"] = "SIAP-SIAP JUAL / AMBIL PROFIT — tunggu konfirmasi puncak"
        p["side"] = "SHORT / JUAL (atau exit LONG)"
        p["entry_rule"] = trig[0] if trig else "tunggu sinyal reversal turun"
        p["entry_explain"] = (
            f"Harga lagi naik nyari PUNCAK di sekitar {zone_txt}. Kalau lagi pegang posisi "
            f"beli, siap-siap ambil profit di area itu. Buat SHORT: tunggu konfirmasi "
            f"{p['entry_rule']}. Sebelum itu harga masih bisa lanjut naik ke {target_num} dulu.")
        p["stop_rule"] = (void[0] if void else
                          (f"kalau CLOSE tembus di atas {z['high']:.6g}" if z else "—"))
        p["profit"] = "Setelah masuk short, target turun bertahap. Pakai trailing stop."
    else:
        p["headline"] = "BELUM ADA SETUP JELAS — tunggu"
        p["side"] = "WAIT / NUNGGU"
        p["entry_rule"] = "—"
        p["entry_explain"] = ("Struktur belum rapi / confidence rendah. Tunggu pola lebih "
                              "jelas dulu sebelum entry.")
        p["stop_rule"] = "—"
        p["profit"] = "—"

    bull_bias = expecting_bottom or (is_thrust and wd == "up")
    bear_bias = expecting_top or (is_thrust and wd == "down")
    aligned = (bull_bias and htf == "BULL") or (bear_bias and htf == "BEAR")
    if htf in ("BULL", "BEAR"):
        p["align_note"] = ("✅ Searah trend besar (timeframe atas " + htf + ") — setup lebih kuat."
                           if aligned else
                           "⚠️ LAWAN trend besar (timeframe atas " + htf +
                           ") — lebih berisiko. Kecilin ukuran posisi / tunggu konfirmasi ekstra.")
    else:
        p["align_note"] = "Trend timeframe atas belum cukup data."
    return p


_CIRCLED = {"0": "⓪", "1": "①", "2": "②", "3": "③", "4": "④", "5": "⑤",
            "5?": "⑤", "A": "Ⓐ", "B": "Ⓑ", "C": "Ⓒ", "C?": "Ⓒ",
            "D": "Ⓓ", "E": "Ⓔ", "x": "·", "→": "▲", "→?": "▲"}


def _runs_mask(values, lo=None, hi=None):
    """Contiguous index runs where lo<=v (if hi None) or v<=hi (if lo None)."""
    out, i, n = [], 0, len(values)
    def hit(v):
        if v != v:  # NaN
            return False
        if lo is not None:
            return v >= lo
        return v <= hi
    while i < n:
        if hit(values[i]):
            j = i
            while j + 1 < n and hit(values[j + 1]):
                j += 1
            out.append((i, j))
            i = j + 1
        else:
            i += 1
    return out


def _plot(df, r, plan=None):
    """Clean Miner-style chart. Projection = horizontal dashed lines with (price)
    on the right + reversal date; targets shown BOTH directions (current move +
    post-reversal); waves at two font sizes (major big / minor small); DTosc with
    green (oversold) / red (overbought) extreme boxes. No corner box."""
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except Exception:  # noqa: BLE001
        return None

    close = df["Close"]
    last_x, last_y = df.index[-1], float(close.iloc[-1])
    gaps = pd.Series(df.index).diff().dropna()
    gap = gaps.median() if len(gaps) else pd.Timedelta(days=1)
    future_x = last_x + gap * 12
    line_x0 = df.index[max(0, len(df) - 34)]          # lines on the right only

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.78, 0.22], vertical_spacing=0.03,
                        subplot_titles=("", "DTosc"))

    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"], low=df["Low"],
        close=close, name="harga", increasing_line_color="#26a69a",
        decreasing_line_color="#ef5350", showlegend=False), row=1, col=1)
    if r.pivots:
        fig.add_trace(go.Scatter(
            x=[p.date for p in r.pivots], y=[p.price for p in r.pivots],
            mode="lines", line=dict(color="#8a9aa8", width=1, dash="dot"),
            name="swing", showlegend=False), row=1, col=1)

    # --- waves: MAJOR big, minor small (font size = degree, like Miner) ---
    for i, w in enumerate(r.wave_labels):
        is_cur = w["label"].endswith("?")
        minor = w.get("deg") == "minor"
        up = w.get("kind") == "H"
        if minor:
            color, size, sh = "#9aa7b2", 9, (8 if up else -8)
        elif is_cur:
            color, size, sh = "#69f0ae", 20, (16 if up else -16)
        else:
            color, size, sh = "#ffd54f", 19, (16 if up else -16)
        fig.add_annotation(x=w["date"], y=w["price"], text=f"<b>{w['label']}</b>",
                           showarrow=False, font=dict(color=color, size=size),
                           yshift=sh, xref="x", yref="y")

    # --- PROJECTION: clean (price) lines both directions + reversal date ---
    primary_dir = r.wave_dir if r.wave_dir in ("up", "down") \
        else ("up" if last_y >= float(close.iloc[0]) else "down")
    opp_dir = "up" if primary_dir == "down" else "down"
    tgt = _target_zone(r)
    rev_txt = ""
    if r.reversal_date is not None:
        sx = f" ×{r.reversal_strength}" if (r.reversal_strength or 0) > 1 else ""
        rev_txt = f" · {pd.Timestamp(r.reversal_date).strftime('%d%b%y')}{sx}"

    def _line(price, label, color, main=False):
        if not (last_y * 0.45 < price < last_y * 1.9):
            return
        fig.add_shape(type="line", x0=line_x0, x1=future_x, y0=price, y1=price,
                      line=dict(color=color, width=2.2 if main else 1.1,
                                dash="solid" if main else "dash"),
                      opacity=0.95 if main else 0.6, xref="x", yref="y")
        fig.add_annotation(x=future_x, y=price, text=label, showarrow=False,
                           xanchor="left", xshift=4,
                           font=dict(color=color, size=13 if main else 11,
                                     family="Arial Black" if main else "Arial"),
                           bgcolor="rgba(0,0,0,0.55)" if main else None,
                           xref="x", yref="y")

    # primary-direction targets (where price is heading now)
    for z in r.price_zones[:3]:
        is_main = tgt and abs(z["mid"] - tgt["mid"]) < 1e-6
        col = "#ffd54f" if is_main else ("#ff9800" if z["mid"] < last_y else "#26c6da")
        if is_main:
            adir = "⬇" if z["mid"] < last_y else "⬆"
            _line(z["mid"], f"🎯 {adir} {z['mid']:.6g}{rev_txt}", col, main=True)
        else:
            _line(z["mid"], f"({z['mid']:.6g})", col)
    # post-reversal targets (opposite direction) — lighter
    try:
        opp_zones, _ = price_cluster_md(r.pivots, r.minor_pivots, opp_dir, last_y)
    except Exception:  # noqa: BLE001
        opp_zones = []
    for z in opp_zones[:2]:
        pre = "↗" if z["mid"] > last_y else "↘"
        _line(z["mid"], f"{pre} ({z['mid']:.6g})", "#7e9bbf")

    # reversal date vertical marker(s) + direction headline at top-center
    for dt, hits in (r.time_cluster_dates[:3] if r.time_cluster_dates else []):
        main = (r.reversal_date is not None and dt == r.reversal_date)
        col = "#42a5f5" if main else "#5b6e84"
        fig.add_shape(type="line", x0=dt, x1=dt, y0=0, y1=1, yref="paper", xref="x",
                      line=dict(color=col, width=2 if main else 1, dash="dash"),
                      opacity=0.85 if main else 0.4)
        fig.add_annotation(x=dt, y=1.0, yref="paper", xref="x",
                           text=f"📅 {pd.Timestamp(dt).strftime('%d%b%y')} ×{hits}",
                           showarrow=False, yanchor="bottom", xanchor="center",
                           font=dict(color=col, size=11,
                                     family="Arial Black" if main else "Arial"),
                           bgcolor="rgba(0,0,0,0.5)")
    # one clear direction headline (replaces the box) — in empty top area
    if tgt:
        adir, dword = ("⬇", "TURUN") if tgt["mid"] < last_y else ("⬆", "NAIK")
        dcol = "#ff7043" if tgt["mid"] < last_y else "#26c6da"
        head = (f"<b>{r.ticker} {adir} {dword}</b>  → target {tgt['mid']:.6g}"
                + (f"  ·  reversal {pd.Timestamp(r.reversal_date).strftime('%d%b%y')}"
                   if r.reversal_date is not None else ""))
        fig.add_annotation(x=0.5, y=1.10, xref="paper", yref="paper", text=head,
                           showarrow=False, xanchor="center",
                           font=dict(color=dcol, size=13),
                           bgcolor="rgba(0,0,0,0.45)")

    # --- DTosc panel with GREEN (oversold) / RED (overbought) extreme boxes ---
    if r.dtosc_k is not None:
        kv = list(r.dtosc_k.values)
        kidx = list(r.dtosc_k.index)
        for s, e in _runs_mask(kv, hi=25):            # green = oversold extreme
            fig.add_shape(type="rect", x0=kidx[s], x1=kidx[e], y0=0, y1=25,
                          fillcolor="rgba(38,200,90,0.40)", line_width=0,
                          row=2, col=1)
        for s, e in _runs_mask(kv, lo=75):            # red = overbought extreme
            fig.add_shape(type="rect", x0=kidx[s], x1=kidx[e], y0=75, y1=100,
                          fillcolor="rgba(239,83,80,0.40)", line_width=0,
                          row=2, col=1)
        for yv, cc in ((75, "#ef5350"), (25, "#26a69a")):
            fig.add_hline(y=yv, line_dash="dash", line_color=cc, line_width=1,
                          row=2, col=1)
        fig.add_trace(go.Scatter(x=r.dtosc_k.index, y=r.dtosc_k.values,
                                 line=dict(color="#d32f2f", width=1.4),
                                 name="K"), row=2, col=1)
        fig.add_trace(go.Scatter(x=r.dtosc_d.index, y=r.dtosc_d.values,
                                 line=dict(color="#2e7d32", width=1.4),
                                 name="D"), row=2, col=1)
        fig.update_yaxes(range=[0, 100], row=2, col=1)

    fig.update_xaxes(range=[df.index[0], future_x + gap * 3])
    fig.update_layout(height=680, template="plotly_dark",
                      xaxis_rangeslider_visible=False,
                      margin=dict(l=0, r=0, t=46, b=0),
                      showlegend=False, hovermode="x unified")
    return fig


def _tf_status(series, setn: int, ma: str = "ema") -> dict:
    a, b, c, d = DTOSC_SETS[setn]
    if series is None or len(series) < a + b + c + d:
        return {"dir": "n/a", "zone": "n/a", "cross": None, "K": None, "D": None}
    K, D = dtosc(series, a, b, c, d, ma)
    return dtosc_status(K, D)


def dtf_guidance(rows: list) -> tuple:
    """Miner Dual Time Frame: direction from the two BIGGER TFs (rows[0],rows[1]),
    entry timing from the smallest (rows[-1]). rows ordered largest→smallest."""
    if len(rows) < 2:
        return ("⚖️ Data timeframe kurang", "")
    b1, b2, sm = rows[0], rows[1], rows[-1]
    big = b1["dir"] if (b1["dir"] in ("BULL", "BEAR") and b1["dir"] == b2["dir"]) else None
    smtxt = (f" Sekarang {sm['tf']}: {sm.get('dir')}/{sm.get('zone')}."
             if sm.get("dir") not in (None, "n/a") else "")
    if big == "BULL":
        head = f"📈 ARAH BESAR: NAIK  ({b1['tf']} + {b2['tf']} sama-sama bull)"
        entry = (f"Cari BELI (long). Entry: tunggu {sm['tf']} balik bullish (DTosc cross "
                 "naik dari oversold) searah trend besar." + smtxt)
    elif big == "BEAR":
        head = f"📉 ARAH BESAR: TURUN  ({b1['tf']} + {b2['tf']} sama-sama bear)"
        entry = (f"Cari JUAL/SHORT. Entry: tunggu {sm['tf']} balik bearish (DTosc cross "
                 "turun dari overbought) searah trend besar." + smtxt)
    else:
        head = f"⚖️ ARAH BESAR: CAMPUR  ({b1['tf']}={b1['dir']} vs {b2['tf']}={b2['dir']})"
        entry = (f"{b1['tf']} & {b2['tf']} belum searah — paling aman TUNGGU sampai "
                 f"align, atau ikut {b2['tf']} dengan size kecil." + smtxt)
    return head, entry


# higher-TF ladder + pandas resample rule + Miner DTosc set per TF
_TF_ORDER = ["15m", "30m", "1h", "4h", "1d", "1wk", "1mo", "3mo"]
_TF_RULE = {"30m": "30min", "1h": "1h", "4h": "4h", "1d": "1D",
            "1wk": "W", "1mo": "ME", "3mo": "QE"}
_TF_NAME = {"15m": "15m", "30m": "30m", "1h": "1H", "4h": "4H", "1d": "Daily",
            "1wk": "Weekly", "1mo": "Monthly", "3mo": "Quarterly"}
_TF_SET = {"15m": 4, "30m": 4, "1h": 3, "4h": 3, "1d": 2, "1wk": 2,
           "1mo": 1, "3mo": 1}


def multi_tf_view(base_df, base_interval: str, ma: str = "ema") -> tuple:
    """DTosc on the base TF + its two HIGHER TFs, by RESAMPLING the base data
    (no extra network fetch → fast). Returns (rows largest→smallest, asset)."""
    s0 = base_df["Close"].copy()
    s0.index = pd.DatetimeIndex(s0.index)
    bi = base_interval if base_interval in _TF_ORDER else "1d"
    i = _TF_ORDER.index(bi)
    chosen = [bi] + _TF_ORDER[i + 1:i + 3]            # base + next two higher
    rows = []
    for tf in chosen:
        if tf == bi:
            s = s0
        else:
            s = s0.resample(_TF_RULE[tf]).last().dropna()
        setn = _TF_SET[tf]
        st = _tf_status(s, setn, ma)
        rows.append({"tf": _TF_NAME[tf], "set": setn, "bars": len(s), **st})
    rows.reverse()                                    # largest first
    return rows, None


def run_app():
    """Streamlit UI entry point. Run with:  streamlit run miner_dt.py"""
    import streamlit as st
    import pandas as _pd

    st.set_page_config(page_title="Dynamic Trader — Miner Engine",
                       page_icon="📊", layout="wide")
    st.title("📊 Dynamic Trader — Robert Miner Engine")
    st.caption("Auto Elliott + Fibonacci price/time projection · close-based · "
               "DTosc dual-TF + DLB · *Learn to trade, not forecast.*")

    with st.sidebar:
        st.header("Input")
        ticker = st.text_input("Ticker", value="",
                               placeholder="HUMI, USDJPY, BTC, GOLD, NVDA")
        market = st.selectbox("Market",
                              ["auto", "us", "idx", "forex", "commodity", "crypto"],
                              help="IDX stocks (HUMI, BBCA): pick 'idx' → adds .JK")
        interval = st.selectbox("Interval",
                                ["1d", "1wk", "1h", "60m", "30m", "15m", "5m"], index=0,
                                help="Timeframe analisis. Miner sering pakai Daily & "
                                     "Weekly (1wk) untuk swing/posisi. Pilih 1wk untuk "
                                     "timeframe besar.")
        c1, c2 = st.columns(2)
        set_choice = c1.selectbox("DTosc set", ["Auto", 1, 2, 3, 4], index=0,
                                  help="Auto = pilih dari interval (Miner mapping). "
                                       "Daily/Weekly→2, H1→3, M15→4.")
        dtosc_set = None if set_choice == "Auto" else int(set_choice)
        ma = c2.selectbox("DTosc MA", ["ema", "sma"], index=0,
                          help="EMA = default versi ThinkScript (match chart Miner). "
                               "Kalibrasi ke chart asli kalau perlu.")
        mode = st.radio("Pivot threshold", ["Auto (ATR)", "Custom"], horizontal=True)
        swing_pct = st.slider("Swing %", 0.5, 10.0, 3.0, 0.1) \
            if mode == "Custom" else None
        run = st.button("Analyze", type="primary", width="stretch")

        st.divider()
        with st.expander("🎯 Manual EOW (exact Miner reproduction)"):
            ekind = st.radio("Kind", ["5 (impulse W5)", "c (correction C)"])
            st.caption("EOW-5: W0, W1, W3, W4  ·  EOW-C: prior_start, prior_end, A, B")
            mp = [st.number_input(f"Pivot {i+1}", value=0.0, format="%.6f",
                                  key=f"mp{i}") for i in range(4)]
            man = st.button("Compute EOW zone", width="stretch")

    # ---------- manual EOW mode ----------
    if man and any(x != 0 for x in mp):
        kind = "5" if ekind.startswith("5") else "c"
        comp, zones = zone_from_pivots(mp, kind)
        st.subheader(f"{'EOW-5' if kind == '5' else 'EOW-C'} — exact projection")
        rows = [{"group": g, "projection": lbl, "price": round(v, 6)}
                for g, d in comp.items() for lbl, v in d.items()]
        st.dataframe(_pd.DataFrame(rows), width="stretch", hide_index=True)
        zr = [{"Zone": i, "Low": round(z["low"], 6), "High": round(z["high"], 6),
               "Converge": "★" if z["groups"] >= 2 else "", "Score": z["score"],
               "Members": ", ".join(z["members"])}
              for i, z in enumerate(zones, 1)]
        st.markdown("**Clustered zones** (★ = ≥2 sets = high-prob EOW zone)")
        st.dataframe(_pd.DataFrame(zr), width="stretch", hide_index=True)
        return

    # ---------- need a ticker ----------
    if not ticker:
        st.info("👈 Ketik ticker di sidebar lalu **Enter** — langsung jalan, nggak "
                "perlu klik apa-apa. Contoh: `HUMI` (Market=idx), `USDJPY`, `BTC`, "
                "`GOLD`, `NVDA`, `^GSPC`")
        st.markdown("""
**Ratio yang dipakai (verbatim Miner):**
`Internal Ret` 0.382 / 0.50 / 0.618 / 0.786 · `External Ret` 1.27 / 1.62 / 2.62 ·
`APP` 0.618 / 1.0 / 1.618 · `Time Ret` 0.382 / 0.50 / 0.618 / 1.0 / 1.618 ·
`DTosc` sets (8,5,3,3)(13,8,5,5)(21,13,8,8)(34,21,13,13) OB75/OS25
""")
        return

    # ---------- run analysis ----------
    try:
        cands, asset, _ = normalize_ticker(ticker, market)
        ck = (tuple(cands), interval)
        if st.session_state.get("_ck") != ck:
            with st.spinner(f"Fetching {cands} …"):
                df, resolved = fetch_data(list(cands), interval)
            st.session_state["_ck"] = ck
            st.session_state["_df"] = df
            st.session_state["_res"] = resolved
        df = st.session_state["_df"]
        resolved = st.session_state["_res"]
        r = analyze(df=df, resolved=resolved, interval=interval,
                    swing_pct=swing_pct, dtosc_set=dtosc_set, ma=ma)
        r.asset = asset
    except SystemExit as e:
        st.error(f"⚠️ {e}")
        return
    except ValueError as e:
        st.warning(f"⚠️ {e}")
        return
    except Exception as e:  # noqa: BLE001
        st.error(f"⚠️ Error: {e}")
        st.exception(e)
        return

    # ---------- header ----------
    h1, h2, h3, h4 = st.columns(4)
    h1.metric("Ticker", r.ticker)
    h2.metric("Harga terakhir", f"{r.last_close:.6g}")
    h3.metric("Per tanggal", fmt_date(r.last_date))
    h4.metric("Jenis aset", r.asset)

    p = trade_plan(r)

    # ====================  CHART FIRST (semua angka di dalam chart)  ============
    cc = _conf_color(p["confidence"])
    st.markdown(f"### 📈 Chart &nbsp;—&nbsp; :{cc}[keyakinan {p['confidence']}]")
    fig = _plot(df, r, p)
    if fig is not None:
        st.plotly_chart(fig, width="stretch")
    else:
        st.line_chart(df["Close"])
        st.caption("Install plotly untuk chart lengkap.")
    st.caption("Baca chart: **kotak pojok** = ringkasan setup · **angka kanan** = "
               "target harga + ratio Fib (🎯 = target utama) · **📅 atas** = perkiraan "
               "tanggal reversal (×N = berapa proyeksi waktu numpuk) · **wave bulet** "
               "①②③④⑤/ⒶⒷⒸⒹⒺ (merah=selesai, hijau=jalan) · **DTosc bawah** "
               "(>75 jenuh beli, <25 jenuh jual).")

    # ====================  RINGKAS: aksi + penjelasan  =========================
    if p["expecting_bottom"] or (p["is_thrust"] and r.wave_dir == "up"):
        st.success(f"### 🟢 {p['headline']}")
    elif p["expecting_top"] or (p["is_thrust"] and r.wave_dir == "down"):
        st.error(f"### 🔴 {p['headline']}")
    else:
        st.warning(f"### ⚪ {p['headline']}")

    g1, g2 = st.columns([3, 2])
    with g1:
        st.markdown(f"**Posisi:** {r.wave_pattern} — {p['now']}")
        st.markdown(f"**Apa yang terjadi:** {p['entry_explain']}")
        st.markdown(f"**ENTRY:** ✅ {p['entry_rule']}")
        st.markdown(f"**STOP/batal:** 🛑 {p['stop_rule']}")
    with g2:
        st.markdown(f"**🎯 Target {p['topbottom']}:** {p['target_price_txt']}")
        st.markdown(f"**📅 Reversal:** {p['rev_date_txt']}{p['strength_txt']}")
        st.markdown(f"**➡ Arah:** {p['side']}")
        st.info(p["align_note"])
    st.caption("Aturan Miner: target itu ZONA (bukan 1 garis), pakai harga PENUTUPAN, "
               "tunggu konfirmasi. *Learn to trade, not forecast.*")

    # ---------- multi-timeframe correlation (auto, no fetch, instant) ----------
    st.markdown("### 🔭 Korelasi Timeframe (multi-degree)")
    st.caption("Arah dari timeframe BESAR (2 teratas), entry dari yang KECIL. "
               "Di-resample dari data — instan, nggak perlu klik.")
    mtf_key = f"{resolved}|{interval}"
    if st.session_state.get("_mtf_key") != mtf_key:
        try:
            rows, _ = multi_tf_view(df, interval, ma)
        except Exception:  # noqa: BLE001
            rows = None
        st.session_state["_mtf_key"] = mtf_key
        st.session_state["_mtf"] = rows
    rows = st.session_state.get("_mtf")
    if rows:
        head, entry = dtf_guidance(rows)
        cols = st.columns(3)
        for col, rr in zip(cols, rows):
            dirc = {"BULL": "🟢", "BEAR": "🔴"}.get(rr.get("dir"), "⚪")
            col.metric(f"{rr['tf']} (set {rr['set']})",
                       f"{dirc} {rr.get('dir')}",
                       help=f"zona {rr.get('zone')}" +
                            (f" · {rr.get('cross')}" if rr.get("cross") else ""))
        if "BESAR: NAIK" in head:
            st.success(f"**{head}**")
        elif "BESAR: TURUN" in head:
            st.error(f"**{head}**")
        else:
            st.warning(f"**{head}**")
        st.markdown(f"**Entry:** {entry}")
    else:
        st.caption("⚠️ Data multi-TF belum bisa diambil (cek koneksi / ticker).")

    # ---------- technical detail (power users) ----------
    with st.expander("🔧 Detail teknikal (buat yang mau angka mentahnya)"):
        f, s, dlb = r.htf_status, r.dtosc_status, r.dtosc_dlb
        m1, m2, m3 = st.columns(3)
        m1.metric(f"FRAME · TF atas {r.htf_label}", f"{f['dir']} / {f['zone']}",
                  help="Cuma entry searah ini (momentum timeframe besar).")
        m2.metric(f"DTosc {r.interval} (K={s['K']} D={s['D']})",
                  f"{s['dir']} / {s['zone']}", delta=s.get("cross") or None)
        m3.metric(f"DLB set{dlb['set']}", f"{dlb['dir']} / {dlb['zone']}",
                  delta="AGREE" if dlb["agree"] else "DISAGREE")

        st.markdown(f"**Pattern:** {r.wave_pattern} · **Wave:** {r.current_wave} · "
                    f"**Expect:** {r.expect}")
        if r.alternate:
            st.markdown(f"**Hitungan alternatif:** {r.alternate}")
        st.caption(f"Legs: {r.wave_detail} · pivot threshold {r.swing_pct}%")

        st.markdown(f"**Price — {r.eow_kind}** (zona, bukan garis)")
        if r.price_zones:
            if not any(z["groups"] >= 2 for z in r.price_zones):
                st.caption("Belum ada konvergensi ≥2 set — ini projeksi tunggal "
                           "(Miner pakai ZONA tempat ≥2 set ketemu).")
            zr = [{"Zone": i, "Low": round(z["low"], 6), "High": round(z["high"], 6),
                   "Mid": round(z["mid"], 6), "Sets": z["groups"], "Score": z["score"],
                   "★": "★" if z["groups"] >= 2 else "", "Members": ", ".join(z["members"])}
                  for i, z in enumerate(r.price_zones, 1)]
            st.dataframe(_pd.DataFrame(zr), width="stretch", hide_index=True)

        td1, td2 = st.columns(2)
        with td1:
            st.markdown("**Time Band**")
            if r.time_band_dates:
                st.info(f"{fmt_date(r.time_band_dates[0])} → {fmt_date(r.time_band_dates[1])}")
            else:
                st.caption("butuh ≥3 high & ≥2 low")
        with td2:
            st.markdown("**Cluster tanggal (DTP)**")
            st.write(", ".join(f"{fmt_date(dt)} (×{h})"
                               for dt, h in r.time_cluster_dates[:3]) or "—")

        st.markdown("**Trigger / Void (close)**")
        if r.decision.get("trigger"):
            t, dt = r.decision["trigger"]
            st.success(f"Trigger — {t} · ref {fmt_date(dt)}")
        if r.decision.get("void"):
            v, dt = r.decision["void"]
            st.warning(f"Void — {v} · ref {fmt_date(dt)}")

        a, b2, c2, d = DTOSC_SETS[2] if r.dtosc_status else (13, 8, 5, 5)
        st.markdown("**Formula DTosc** (reverse-engineered):")
        st.code(
            "RSI(close, a)  ->  Stoch over b  ->  K = MA(stoch, c)  ->  D = MA(K, d)\n"
            "set 1=(8,5,3,3)  set 2=(13,8,5,5)  set 3=(21,13,8,8)  set 4=(34,21,13,13)\n"
            "Overbought=75  Oversold=25 | reversal = K cross D",
            language="text")
        st.caption("Strukturnya (StochRSI double-smooth, parameter Fibonacci, OB75/OS25, "
                   "RSI pakai CLOSE) sesuai ThinkScript/ProRealCode + buku Miner. Default "
                   "MA = **EMA** (versi ThinkScript yang ada match ke chart Miner asli). "
                   "Toggle ke SMA kalau perlu. Set auto dari interval (Miner mapping). "
                   "Jujur: ~90-95% exact, bukan klaim 100% — Miner nggak buka source.")

    st.caption("⚠️ Hitungan wave & pivot ini OTOMATIS (starting point) — edge Miner "
               "itu diskresioner. Buat angka persis dia, pakai Manual EOW di sidebar. "
               "Bukan nasihat keuangan.")


if __name__ == "__main__":
    # Streamlit Cloud runs this file; render the app UI.
    # (CLI still available programmatically via main()/analyze().)
    run_app()
