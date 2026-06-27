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
    """Legacy crude overlap classifier (kept as fallback)."""
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
        return float((df["Close"].pct_change().abs().rolling(n).mean()).iloc[-1] or 0.02)
    h, l, c = df["High"], df["Low"], df["Close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l).abs(), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr = tr.rolling(n).mean()
    return float((atr / c).dropna().iloc[-1])


def auto_swing_pct(df: pd.DataFrame, series: pd.Series) -> float:
    """Adaptive zigzag threshold: ~3x ATR%, then refine to a sane pivot count."""
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
        f"W1={W1:.4g} W2={W2:.4g} W3={W3:.4g} W4={W4:.4g}")
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
        f"prior={prior:.4g} A={A:.4g} B={B:.4g} (B/A={B/A:.2f})")
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
    # thrust continues the trend INTO the triangle (direction from pre-triangle leg)
    pre_up = s[1].price > s[0].price  # first leg direction proxy
    # after a contracting triangle the thrust is usually opposite the last leg
    last_up = s[-1].price > s[-2].price
    thrust_up = not last_up
    target_mid = e.price + (width if thrust_up else -width)
    score = 2.6 + 0.15 * shrink + 0.15 * overlaps - 0
    wc = WaveCount(
        "TRIANGLE", "up" if thrust_up else "down",
        "Wave-E of triangle (W4/B) — thrust pending", "thrust",
        [e], score, shrink >= 4 and overlaps >= 3,
        f"{'up' if thrust_up else 'down'} thrust ~{target_mid:.4g} after E completes",
        f"legs={[round(x,3) for x in legs]} width={width:.4g}")
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
        if wc.direction == "down":          # C down, then resume UP
            res["trigger"] = (f"correction complete / BULL on CLOSE > "
                              f"{B.price:.6g} (Wave-B)", B.date)
            res["void"] = (f"read invalid on CLOSE < {prior_start.price:.6g} "
                           f"(prior-trend start)", prior_start.date)
        else:                                # C up, then resume DOWN
            res["trigger"] = (f"correction complete / BEAR on CLOSE < "
                              f"{B.price:.6g} (Wave-B)", B.date)
            res["void"] = (f"read invalid on CLOSE > {prior_start.price:.6g} "
                           f"(prior-trend start)", prior_start.date)
    elif wc.proj_kind == "eow5" and len(pp) >= 4:
        W4 = pp[3]
        if wc.direction == "up":             # top forming -> reversal DOWN
            res["trigger"] = (f"Wave-5 top complete / BEAR on CLOSE < "
                              f"{W4.price:.6g} (W4 low)", W4.date)
        else:                                # bottom forming -> reversal UP
            res["trigger"] = (f"Wave-5 bottom complete / BULL on CLOSE > "
                              f"{W4.price:.6g} (W4 high)", W4.date)
    elif wc.proj_kind == "thrust" and hasattr(wc, "_thrust"):
        e, _w, up = wc._thrust
        d0 = pp[0].date if pp else None
        if up:
            res["trigger"] = (f"UP thrust on CLOSE > {e:.6g} (above Wave-E)", d0)
        else:
            res["trigger"] = (f"DOWN thrust on CLOSE < {e:.6g} (below Wave-E)", d0)
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
    swing_pct: float = 0.0
    wave_pattern: str = "UNKNOWN"
    current_wave: str = ""
    confidence: str = "LOW"
    expect: str = ""
    wave_detail: str = ""
    alternate: str = ""
    price_zones: list[dict] = field(default_factory=list)
    time_band_dates: Optional[tuple] = None
    time_cluster_dates: list = field(default_factory=list)
    decision: dict = field(default_factory=dict)
    eow_kind: str = ""


def analyze(ticker: str = None, market: str = "auto", interval: str = "1d",
            basis: str = "close", swing_pct: Optional[float] = None,
            dtosc_set: int = 2, ma: str = "sma", htf: Optional[str] = None,
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

    # --- adaptive pivots + AUTO wave labeling ---
    pct = swing_pct if swing_pct is not None else auto_swing_pct(df, series)
    piv = zigzag_pivots(series, pct)
    primary, alt = label_structure(piv)
    highs = [p for p in piv if p.kind == "H"]
    lows = [p for p in piv if p.kind == "L"]
    ref = float(series.iloc[-1])

    # --- AUTO price target zones from the detected count ---
    price_zones, eow_kind = [], "structure unclear"
    comp = {}
    if primary and primary.proj_pivots:
        pp = [p.price for p in primary.proj_pivots]
        if primary.proj_kind == "eow5" and len(pp) >= 4:
            comp = eow_5_targets(pp[0], pp[1], pp[2], pp[3])
            eow_kind = "EOW-5 (impulse W5)"
        elif primary.proj_kind == "eowc" and len(pp) >= 4:
            comp = eow_c_targets(pp[0], pp[1], pp[2], pp[3])
            eow_kind = "EOW-C (correction Wave-C)"
        elif primary.proj_kind == "thrust" and hasattr(primary, "_thrust"):
            e, w, up = primary._thrust
            sign = 1.0 if up else -1.0
            comp = {"Thrust": {f"{r:.3f}x thrust": e + sign * w * r
                               for r in (0.75, 1.0, 1.272, 1.618)}}
            eow_kind = "TRIANGLE thrust (post-E)"
    if comp:
        price_zones = cluster_zones(comp, ref, tol_pct=0.6, top=4)

    # --- time band + ATP/TimeRet from the labeled swings ---
    tband = time_band(highs, lows)
    tband_dates = None
    if tband:
        tband_dates = (idx_to_date(series.index, tband[0]),
                       idx_to_date(series.index, tband[1]))
    tcluster_dates = []
    if primary and len(primary.proj_pivots) >= 3:
        pp = primary.proj_pivots
        tcomp = {"TimeRet": time_ret(pp[0].idx, pp[1].idx),
                 "ATP": atp_time(pp[0].idx, pp[1].idx, pp[-1].idx)}
        for bar_idx, hits in time_cluster(tcomp, win=1):
            tcluster_dates.append((idx_to_date(series.index, bar_idx), hits))

    dec = decision_levels(primary, piv)

    alt_str = ""
    if alt:
        alt_str = f"{alt.pattern} / {alt.current_wave} (conf {alt.confidence})"

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


if __name__ == "__main__":
    main()
