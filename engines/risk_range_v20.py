"""risk_range_v20.py — Hedgeye TRR/LRR v20.3b (FULL Pine Script port)

Upgraded from v20.2 with:
  • Auto-tune multipliers per ticker (25+ asset classes via regex)
  • VIX-symbol mapping per asset (VIX/VXN/RVX/GVZ/OVX/CVIX)
  • Phase state machine with hysteresis (TRADE/TREND/TAIL)
  • Bubble Strength Index (BSI) — volume+wick+delta multi-factor
  • RTA signals: BUY_DIP/ADD/HOLD/TRIM/TRIM_RIP/SHORT_RIP/COVER
  • Spring/Upthrust/Coiled Spring detection
  • Composite vPOC + VAH/VAL (when intraday OHLCV available)

CALIBRATION (⚠️ IN-SAMPLE / anecdotal — NOT walk-forward validated):
  Multipliers were tuned to match these 4 public Hedgeye prints. With only 4
  points and no out-of-sample test, "avg error 0.4%" is a fit statistic, not
  validation. Treat as plausible-but-unproven until OOS-tested across many
  dates × assets (TODO: see S2 backlog).
  SPX Feb 27, 2024:  predicted 4965/5114 vs actual 4950/5119 → 0.3% / 0.1%
  SPX Apr 13, 2020:  predicted 2718/2957 vs actual 2726/2959 → 0.3% / 0.07%
  Gold Oct 16, 2025: predicted 4127/4346 vs actual 4092/4362 → 0.8% / 0.4%
  WTI May 21, 2026:  predicted ~$99 TRR vs actual $98.52    → 0.5%

KEY MECHANICS:
- Basis = previous close (NOT SMA)
- Asymmetric skew (SKEW_MAG=0.55, ratio ~2.30 in trend direction)
- Mandelbrot Hurst fractal adjustment
- VASP: Vol-of-Vol × RV-momentum scaling
- Phase state hysteresis prevents whipsaw
"""
from __future__ import annotations
import math
import re
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# CONFIG — Pine Script defaults
# ═══════════════════════════════════════════════════════════════════════════

TRADE_LEN = 15
TREND_LEN = 63
TAIL_LEN = 756
VOL_LEN = 14

M_TRADE_BASE = 1.50
M_TREND_BASE = 2.75
M_TAIL_BASE = 5.50
SKEW_MAG = 0.55

VASP_VOV_WEIGHT = 0.30
VASP_RV_MOM_WEIGHT = 0.10
WIDTH_FLOOR = 0.30
FRACTAL_WEIGHT = 0.35
HURST_MAX_LAG = 20

# Phase state machine
TRADE_PHASE_THRESH = 0.20
TREND_PHASE_THRESH = 0.14
TAIL_PHASE_THRESH = 0.10
PHASE_NEUTRAL_TRADE = 0.06
PHASE_NEUTRAL_TREND = 0.05
PHASE_NEUTRAL_TAIL = 0.03

QUAD_VOL_ADJ = {"Q1": 0.95, "Q2": 1.00, "Q3": 1.10, "Q4": 1.30}


# ═══════════════════════════════════════════════════════════════════════════
# AUTO-TUNE PER TICKER (25+ asset classes)
# ═══════════════════════════════════════════════════════════════════════════

# Pattern → (mTrade, mTrend, iv_symbol)
AUTO_TUNE_RULES = [
    # US equity indices
    (r"(\^GSPC|SPY|\^SPX|ES=F|MES1|SPX)", 1.50, 2.75, "^VIX"),
    (r"(\^NDX|QQQ|NQ=F|MNQ1|NDX)", 1.60, 2.90, "^VXN"),
    (r"(\^RUT|IWM|RTY|M2K1|RUT)", 1.80, 3.10, "^RVX"),
    (r"(\^DJI|YM1|DIA|DJI)", 1.40, 2.60, "^VIX"),
    # Commodities
    (r"(GC=F|GLD|XAUUSD|MGC1|GLDM)", 2.20, 4.00, "^GVZ"),
    (r"(SI=F|SLV|XAGUSD)", 2.50, 4.50, "^GVZ"),
    (r"(CL=F|USO|WTI|MCL1|BZ=F|XLE|XOP)", 1.80, 3.20, "^OVX"),
    (r"(NG=F|UNG|NATGAS)", 2.50, 4.00, "^OVX"),
    (r"(HG=F|COPPER|CPER)", 2.00, 3.50, None),
    # Crypto
    (r"(BTC|XBT|BITCOIN)", 2.00, 3.50, None),
    (r"(ETH|ETHEREUM)", 2.20, 3.80, None),
    (r"(SOL-USD|XRP|ADA|DOGE)", 2.40, 4.00, None),
    # FX
    (r"EURUSD", 1.20, 2.20, "^CVIX"),
    (r"GBPUSD", 1.30, 2.40, "^CVIX"),
    (r"USDJPY|JPY=X", 1.10, 2.00, "^CVIX"),
    (r"(AUDUSD|NZDUSD)", 1.40, 2.60, "^CVIX"),
    (r"(USDCAD|USDCHF)", 1.20, 2.20, "^CVIX"),
    (r"USDIDR|IDR=X", 1.30, 2.30, None),
    # High-vol US single stocks (Mag7 + AI darlings)
    (r"^(TSLA|NVDA|AMD|PLTR|SMCI|MSTR|COIN|NVTS|SIVE)$", 2.00, 3.50, None),
    # Mega-cap stable
    (r"^(AAPL|MSFT|GOOGL|GOOG|AMZN|TSM|AVGO)$", 1.70, 3.00, None),
    # Communication / SaaS
    (r"^(META|NFLX|CRM|ADBE)$", 1.80, 3.20, None),
    # Big banks
    (r"^(JPM|BAC|GS|WFC|MS|C)$", 1.40, 2.50, None),
    # Memory / storage
    (r"^(MU|WDC|STX|SNDK)$", 2.00, 3.50, None),
    # Optical / CPO mid-caps (high beta)
    (r"^(COHR|LITE|AAOI|POET|MRVL|CRDO|SITM|AXTI|GLW)$", 2.20, 3.80, None),
    # IHSG
    (r"(IHSG|\^JKSE|JKSE|JCI)", 1.60, 2.80, None),
    (r"\.JK$", 1.70, 2.90, None),  # IHSG single tickers
]


def auto_tune(ticker: str) -> Tuple[float, float, Optional[str]]:
    """Return (mTrade, mTrend, iv_symbol) per ticker pattern."""
    if not ticker:
        return M_TRADE_BASE, M_TREND_BASE, None
    t = ticker.upper()
    for pattern, mt, mtr, iv in AUTO_TUNE_RULES:
        if re.search(pattern, t):
            return mt, mtr, iv
    return M_TRADE_BASE, M_TREND_BASE, None


# ═══════════════════════════════════════════════════════════════════════════
# ATR-WIDTH MODEL (MQA v21 script-faithful) — width = ATR × mult × modifiers
# Default. Edward's calibration ($98.52 WTI = SMA63 + ATR×0.711) is ATR-based,
# and the MQA v21 Pine uses ATR. Set WIDTH_MODE="vasp" for the legacy RV/IV model.
# ═══════════════════════════════════════════════════════════════════════════
WIDTH_MODE = "atr"

# ATR-scale multipliers (mTrade, mTrend, mTail) ported from the MQA v21 auto-tune.
# Scale differs from the VASP table (ATR base, not annualized realized vol).
ATR_MULT_RULES = [
    (r"(\^GSPC|SPY|\^SPX|ES=F|MES1|SPX)", 0.45, 0.65, 1.30),
    (r"(\^NDX|QQQ|NQ=F|MNQ1|NDX)", 0.50, 0.70, 1.40),
    (r"(\^RUT|IWM|RTY|M2K1|RUT)", 0.55, 0.80, 1.50),
    (r"(\^DJI|YM1|DIA|DJI)", 0.40, 0.60, 1.20),
    (r"(GC=F|GLD|XAUUSD|MGC1|GLDM)", 0.65, 0.95, 1.80),
    (r"(SI=F|SLV|XAGUSD)", 0.75, 1.10, 2.00),
    (r"(CL=F|USO|WTI|MCL1|BZ=F|XLE|XOP)", 0.55, 0.711, 1.50),
    (r"(NG=F|UNG|NATGAS)", 0.80, 1.20, 2.20),
    (r"(HG=F|COPPER|CPER)", 0.60, 0.90, 1.70),
    (r"(BTC|XBT|BITCOIN)", 0.70, 1.00, 1.90),
    (r"(ETH|ETHEREUM)", 0.75, 1.10, 2.00),
    (r"(SOL-USD|XRP|ADA|DOGE)", 0.80, 1.15, 2.10),
    (r"EURUSD", 0.35, 0.50, 1.00),
    (r"GBPUSD", 0.40, 0.55, 1.10),
    (r"USDJPY|JPY=X", 0.30, 0.45, 0.90),
    (r"(AUDUSD|NZDUSD)", 0.40, 0.60, 1.20),
    (r"(USDCAD|USDCHF)", 0.35, 0.50, 1.00),
    (r"USDIDR|IDR=X", 0.40, 0.60, 1.20),
    (r"^(TSLA|NVDA|AMD|PLTR|SMCI|MSTR|COIN|NVTS|SIVE)$", 0.65, 0.95, 1.80),
    (r"^(AAPL|MSFT|GOOGL|GOOG|AMZN|TSM|AVGO)$", 0.55, 0.80, 1.50),
    (r"^(META|NFLX|CRM|ADBE)$", 0.60, 0.85, 1.60),
    (r"^(JPM|BAC|GS|WFC|MS|C)$", 0.45, 0.65, 1.30),
    (r"^(MU|WDC|STX|SNDK)$", 0.65, 0.95, 1.80),
    (r"^(COHR|LITE|AAOI|POET|MRVL|CRDO|SITM|AXTI|GLW)$", 0.70, 1.00, 1.85),
    (r"(IHSG|\^JKSE|JKSE|JCI)", 0.50, 0.75, 1.40),
    (r"\.JK$", 0.55, 0.80, 1.50),
]
ATR_MULT_DEFAULT = (0.50, 0.711, 1.50)


def _atr_tune(ticker: str) -> Tuple[float, float, float]:
    """Return (mTrade, mTrend, mTail) ATR-scale multipliers per ticker (MQA v21)."""
    if not ticker:
        return ATR_MULT_DEFAULT
    t = ticker.upper()
    for pattern, mt, mtr, mta in ATR_MULT_RULES:
        if re.search(pattern, t):
            return mt, mtr, mta
    return ATR_MULT_DEFAULT


def _atr_now_and_sma(s: pd.Series, ohlcv: Optional[pd.DataFrame],
                     period: int = 14, sma_len: int = 20) -> Tuple[float, float]:
    """ATR(period) latest + SMA(sma_len) of the ATR series, for vol-of-vol = ROC of ATR
    (MQA v21 [ADD-VOV]). True range when OHLCV present; else close-to-close TR (synthetic)."""
    try:
        if ohlcv is not None and all(c in ohlcv.columns for c in ("high", "low", "close")):
            h = pd.to_numeric(ohlcv["high"], errors="coerce")
            l = pd.to_numeric(ohlcv["low"], errors="coerce")
            c = pd.to_numeric(ohlcv["close"], errors="coerce")
            prev_c = c.shift(1)
            tr = pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
        else:
            tr = s.diff().abs()
        tr = tr.dropna()
        if len(tr) < period:
            atr_now = float(tr.mean()) if len(tr) else 0.0
            return atr_now, atr_now
        atr_series = tr.rolling(period).mean().dropna()
        atr_now = float(atr_series.iloc[-1])
        atr_sma = float(atr_series.tail(sma_len).mean()) if len(atr_series) >= 1 else atr_now
        return atr_now, (atr_sma if atr_sma > 0 else atr_now)
    except Exception:
        return 0.0, 0.0


def _volume_factor(ohlcv: Optional[pd.DataFrame]) -> float:
    """Conditional volume inflator/deflator (MQA v21 [ADD-VOL]). Diverging high vol widens;
    confirming high vol tightens; low vol widens slightly. No volume data → neutral 1.0."""
    try:
        if ohlcv is None or "volume" not in ohlcv.columns or "close" not in ohlcv.columns:
            return 1.0
        v = pd.to_numeric(ohlcv["volume"], errors="coerce").dropna()
        c = pd.to_numeric(ohlcv["close"], errors="coerce").dropna()
        if len(v) < 21 or len(c) < 2:
            return 1.0
        vol_ma = float(v.tail(20).mean())
        if vol_ma <= 0:
            return 1.0
        vol_roc = (float(v.iloc[-1]) - vol_ma) / vol_ma
        price_up = float(c.iloc[-1]) > float(c.iloc[-2])
        v_up = float(v.iloc[-1]) > float(v.iloc[-2])
        confirm = (price_up and v_up) or ((not price_up) and (not v_up))
        diverge = (price_up and not v_up) or ((not price_up) and v_up)
        if vol_roc > 0.30 and diverge:
            return 1.0 + min(vol_roc * 0.25, 0.30)
        if vol_roc > 0.30 and confirm:
            return 1.0 - min(vol_roc * 0.10, 0.15)
        if vol_roc < -0.20:
            return 1.0 + abs(vol_roc) * 0.15
        return 1.0
    except Exception:
        return 1.0


# ═══════════════════════════════════════════════════════════════════════════
# CORE MATH
# ═══════════════════════════════════════════════════════════════════════════

def _hurst(returns: np.ndarray, max_lag: int = HURST_MAX_LAG) -> float:
    """R/S analysis Hurst exponent. Returns 0.5 if insufficient data."""
    if len(returns) < max_lag * 2:
        return 0.5
    try:
        n = len(returns)
        tau, lags = [], []
        for lag in range(2, min(max_lag, n // 4) + 1):
            diffs = np.abs(returns[lag:] - returns[:-lag])
            if len(diffs) == 0:
                continue
            avg = diffs.mean()
            if avg > 0:
                tau.append(np.log(avg))
                lags.append(lag)
        if len(tau) < 2:
            return 0.5
        slope = np.polyfit(np.log(lags), tau, 1)[0]
        return float(np.clip(slope, 0.1, 0.9))
    except Exception:
        return 0.5


def _apply_skew(width: float, phase: int, skew_mag: float) -> Tuple[float, float]:
    """Returns (lower_width, upper_width) per Pine Script f_apply_skew."""
    if phase == 1:
        return width * (1.0 + skew_mag), width * (1.0 - skew_mag * 0.6)
    elif phase == -1:
        return width * (1.0 - skew_mag * 0.6), width * (1.0 + skew_mag)
    return width, width


def _hysteresis(score: float, threshold: float, neutral_zone: float, prev: int) -> int:
    """Pine Script f_state_hysteresis port."""
    if score > threshold:
        return 1
    elif score < -threshold:
        return -1
    elif abs(score) <= neutral_zone:
        return 0
    return prev


# ═══════════════════════════════════════════════════════════════════════════
# BUBBLE STRENGTH INDEX (BSI) — for OHLCV input
# ═══════════════════════════════════════════════════════════════════════════

def calc_bsi(ohlcv: pd.DataFrame, vol_lookback: int = 20) -> Dict:
    """Pine Script BSI port. Requires OHLCV DataFrame.

    Returns latest bar BSI + bubble flags.
    """
    if ohlcv is None or len(ohlcv) < vol_lookback + 1:
        return {"bsi": 0.0, "vol_z": 0.0, "available": False}
    cols = {c.lower(): c for c in ohlcv.columns}
    o = ohlcv[cols.get("open", "Open")]
    h = ohlcv[cols.get("high", "High")]
    l = ohlcv[cols.get("low", "Low")]
    c = ohlcv[cols.get("close", "Close")]
    v = ohlcv[cols.get("volume", "Volume")]

    vol_avg = v.rolling(vol_lookback).mean()
    vol_sd = v.rolling(vol_lookback).std()
    vol_z = (v - vol_avg) / vol_sd.replace(0, np.nan)
    vol_z_last = float(vol_z.iloc[-1]) if not pd.isna(vol_z.iloc[-1]) else 0.0

    rng = (h - l).iloc[-1]
    body = abs((c - o).iloc[-1])
    if rng <= 0:
        return {"bsi": 0.0, "vol_z": vol_z_last, "available": True, "low_range": True}

    close_pos = (c.iloc[-1] - l.iloc[-1]) / rng
    upper_wk = (h.iloc[-1] - max(o.iloc[-1], c.iloc[-1])) / rng
    lower_wk = (min(o.iloc[-1], c.iloc[-1]) - l.iloc[-1]) / rng
    body_rat = body / rng

    # Delta proxy
    delta_buy = v.iloc[-1] * (0.5 + close_pos * 0.5) if c.iloc[-1] >= o.iloc[-1] else v.iloc[-1] * close_pos
    delta_ratio = abs(2 * delta_buy - v.iloc[-1]) / v.iloc[-1] if v.iloc[-1] > 0 else 0.0

    # BSI components (Pine: _vi + _wd + _ps + _di)
    vi = np.clip(vol_z_last / 4.0, 0, 1) * 2.0
    wd = max(upper_wk, lower_wk) * 1.5
    ps = 1.0 - abs(close_pos - 0.5) * 2.0
    di = delta_ratio * 0.5
    bsi = min(vi + wd + ps + di, 5.0)

    # Bubble flags
    is_big = vol_z_last >= 2.0
    candle_ok = body_rat <= 0.80
    buy_bubble = is_big and candle_ok and close_pos > 0.55 and lower_wk > 0.10
    sell_bubble = is_big and candle_ok and close_pos < 0.45 and upper_wk > 0.10
    trap_buy = is_big and candle_ok and upper_wk > 0.40 and c.iloc[-1] < o.iloc[-1] and close_pos < 0.35
    trap_sell = is_big and candle_ok and lower_wk > 0.40 and c.iloc[-1] > o.iloc[-1] and close_pos > 0.65
    bull_abs = is_big and delta_ratio < 0.40 and body_rat < 0.35 and c.iloc[-1] >= o.iloc[-1] and lower_wk > 0.15
    bear_abs = is_big and delta_ratio < 0.25 and body_rat < 0.35 and c.iloc[-1] < o.iloc[-1] and upper_wk > 0.15

    return {
        "bsi": round(float(bsi), 3),
        "vol_z": round(vol_z_last, 3),
        "close_pos": round(float(close_pos), 3),
        "body_ratio": round(float(body_rat), 3),
        "upper_wick": round(float(upper_wk), 3),
        "lower_wick": round(float(lower_wk), 3),
        "delta_ratio": round(float(delta_ratio), 3),
        "buy_bubble": bool(buy_bubble),
        "sell_bubble": bool(sell_bubble),
        "trap_buyers": bool(trap_buy),
        "trap_sellers": bool(trap_sell),
        "bull_absorption": bool(bull_abs),
        "bear_absorption": bool(bear_abs),
        "strong": bool(bsi >= 1.5),
        "available": True,
    }


# ═══════════════════════════════════════════════════════════════════════════
# MAIN ENGINE
# ═══════════════════════════════════════════════════════════════════════════

def calculate_trr_lrr_v20(
    ticker: str,
    prices: pd.Series,
    external_iv: Optional[float] = None,
    current_quad: str = "Q3",
    realized_vol_override: Optional[float] = None,
    ohlcv: Optional[pd.DataFrame] = None,
    iv_dict: Optional[Dict[str, float]] = None,
    use_auto_tune: bool = True,
) -> Optional[Dict]:
    """Compute Hedgeye TRR/LRR v20.3b with auto-tune + BSI.

    Args:
        ticker: symbol
        prices: pd.Series of closing prices
        external_iv: VIX/VXN/OVX/GVZ level (e.g. 18.5)
        current_quad: Q1/Q2/Q3/Q4
        realized_vol_override: override for backtests
        ohlcv: optional OHLCV DataFrame for BSI calculation
        iv_dict: dict of IV symbol → level (for auto-tune resolution)
        use_auto_tune: use per-ticker calibrated multipliers
    """
    s = pd.to_numeric(prices, errors="coerce").dropna()
    if len(s) < 63:
        return None

    px = float(s.iloc[-1])
    basis = float(s.iloc[-2])  # previous close
    if not math.isfinite(px) or px <= 0:
        return None

    # Auto-tune
    if use_auto_tune:
        m_trade, m_trend, iv_symbol = auto_tune(ticker)
        if external_iv is None and iv_dict and iv_symbol and iv_symbol in iv_dict:
            external_iv = iv_dict[iv_symbol]
    else:
        m_trade, m_trend, iv_symbol = M_TRADE_BASE, M_TREND_BASE, None
    m_tail = M_TAIL_BASE

    # Log returns
    log_ret = np.log(s.values[1:] / s.values[:-1])
    log_ret = log_ret[~np.isnan(log_ret)]

    # Realized vol
    if realized_vol_override is not None:
        realized_vol = realized_vol_override
    else:
        rv_window = min(VOL_LEN, len(log_ret))
        realized_vol = float(np.std(log_ret[-rv_window:]) * np.sqrt(252)) if rv_window > 1 else 0.20

    # Vol source: external IV preferred
    if external_iv is not None and external_iv > 0:
        vol_source = external_iv / 100.0 if external_iv > 1.0 else external_iv
        vol_src_used = "external_iv"
    else:
        vol_source = realized_vol
        vol_src_used = "realized"

    # VASP
    if len(log_ret) >= 20:
        rolling_vol = pd.Series(log_ret).rolling(VOL_LEN).std().dropna()
        vol_of_vol = float(rolling_vol.tail(20).std()) if len(rolling_vol) >= 20 else 0.01
    else:
        vol_of_vol = 0.01

    if len(log_ret) >= 50:
        rv_baseline = float(np.std(log_ret[-50:]) * np.sqrt(252))
        rv_momentum = (realized_vol / rv_baseline - 1.0) if rv_baseline > 0 else 0.0
    else:
        rv_momentum = 0.0

    vov_term = 1.0 + max(vol_of_vol * VASP_VOV_WEIGHT, -0.5)
    rv_term = 1.0 + rv_momentum * VASP_RV_MOM_WEIGHT
    vasp_mult = max(vov_term * rv_term, WIDTH_FLOOR)
    vasp_vol = vol_source * vasp_mult
    daily_vol = vasp_vol / math.sqrt(252)

    # Hurst per duration
    H_trade = _hurst(log_ret[-TRADE_LEN:]) if len(log_ret) >= TRADE_LEN * 2 else 0.5
    H_trend = _hurst(log_ret[-TREND_LEN:]) if len(log_ret) >= TREND_LEN * 2 else 0.5
    has_full_tail = len(log_ret) >= TAIL_LEN
    H_tail = _hurst(log_ret[-TAIL_LEN:]) if has_full_tail else 0.5

    f_trade = 1.0 + (2.0 - H_trade - 1.5) * FRACTAL_WEIGHT
    f_trend = 1.0 + (2.0 - H_trend - 1.5) * FRACTAL_WEIGHT
    f_tail = 1.0 + (2.0 - H_tail - 1.5) * FRACTAL_WEIGHT

    # Quad adjustment
    quad_adj = QUAD_VOL_ADJ.get(current_quad, 1.0)

    # Base widths — ATR model (MQA v21 script) by default; VASP (RV/IV) as fallback.
    if WIDTH_MODE == "atr":
        atr_now, atr_sma = _atr_now_and_sma(s, ohlcv, period=14, sma_len=20)
        vov_factor = (1.0 + (atr_now / atr_sma - 1.0) * 0.30) if atr_sma > 0 else 1.0
        vol_factor = _volume_factor(ohlcv)
        m_trade_a, m_trend_a, m_tail_a = _atr_tune(ticker)
        base_trade_w = atr_now * m_trade_a * vol_factor * vov_factor * f_trade
        base_trend_w = atr_now * m_trend_a * vol_factor * vov_factor * f_trend
        base_tail_w = atr_now * m_tail_a * vol_factor * vov_factor * f_tail
    else:
        base_trade_w = px * daily_vol * m_trade * f_trade * quad_adj
        base_trend_w = px * daily_vol * m_trend * f_trend * quad_adj
        base_tail_w = px * daily_vol * m_tail * f_tail * quad_adj

    # Phase determination for skew
    ma_short = float(s.tail(21).mean())
    ma_long = float(s.tail(min(63, len(s))).mean())
    if ma_short > ma_long * 1.005:
        phase = 1
        phase_str = "BULL"
    elif ma_short < ma_long * 0.995:
        phase = -1
        phase_str = "BEAR"
    else:
        phase = 0
        phase_str = "NEUTRAL"

    # Apply asymmetric skew
    trade_lower, trade_upper = _apply_skew(base_trade_w, phase, SKEW_MAG)
    trend_lower, trend_upper = _apply_skew(base_trend_w, phase, SKEW_MAG * 0.6)
    tail_lower, tail_upper = _apply_skew(base_tail_w, phase, SKEW_MAG * 0.3)

    # ── BASIS per duration (MQA v21 [FIX-BASIS]) ──
    # TRADE = prior close (static daily, front-runs 1-mo momentum) · TREND = SMA63 · TAIL = SMA756.
    # Previously ALL three used prior close → mis-centered TREND/TAIL. Now matches Hedgeye + the
    # MQA v21 Pine script: TREND TRR = SMA63 + width, TAIL TRR = SMA756 + width.
    basis_trade = basis  # prior close
    basis_trend = float(s.tail(min(TREND_LEN, len(s))).mean())
    basis_tail = float(s.tail(min(TAIL_LEN, len(s))).mean())

    # Final TRR/LRR — each duration centered on its OWN basis
    trade_trr = basis_trade + trade_upper
    trade_lrr = basis_trade - trade_lower
    trend_trr = basis_trend + trend_upper
    trend_lrr = basis_trend - trend_lower
    tail_trr = basis_tail + tail_upper
    tail_lrr = basis_tail - tail_lower

    # Phase state via hysteresis (TRADE/TREND/TAIL)
    trade_mid_width = (trade_lower + trade_upper) * 0.5
    trend_mid_width = (trend_lower + trend_upper) * 0.5
    tail_mid_width = (tail_lower + tail_upper) * 0.5

    # FIX S1-a: anchor phase score to each duration's MEAN, not prev-close.
    # (px - basis) is a ~1-day move ≈ 0 vs a multi-day width → score ≈ 0 → phase
    # always neutral → engine silently collapsed to a 21/63 MA cross. Anchoring to
    # each duration's mean makes TRADE/TREND/TAIL phase genuinely independent.
    anchor_trade = float(s.tail(TRADE_LEN).mean())
    anchor_trend = float(s.tail(min(TREND_LEN, len(s))).mean())
    anchor_tail = float(s.tail(min(TAIL_LEN, len(s))).mean())

    trade_score = (px - anchor_trade) / max(trade_mid_width, px * 0.001)
    trend_score = (px - anchor_trend) / max(trend_mid_width, px * 0.001)
    tail_score = (px - anchor_tail) / max(tail_mid_width, px * 0.001)

    # Vol regime modifier (for thresholds)
    rv_base = float(pd.Series(log_ret).rolling(50).std().mean() * np.sqrt(252)) if len(log_ret) >= 50 else realized_vol
    vol_regime = min(realized_vol / (rv_base * 1.25), 1.0) if rv_base > 0 else 0.5

    eff_trade_thresh = TRADE_PHASE_THRESH * (1.0 + vol_regime * 0.25)
    eff_trend_thresh = TREND_PHASE_THRESH * (1.0 + vol_regime * 0.20)
    eff_tail_thresh = TAIL_PHASE_THRESH * (1.0 + vol_regime * 0.15)

    trade_phase = _hysteresis(trade_score, eff_trade_thresh, PHASE_NEUTRAL_TRADE, phase)
    trend_phase = _hysteresis(trend_score, eff_trend_thresh, PHASE_NEUTRAL_TREND, phase)
    tail_phase = _hysteresis(tail_score, eff_tail_thresh, PHASE_NEUTRAL_TAIL, phase)

    # ATR for breakout confirmation — S3-b: true ATR (H/L/C) when OHLCV is
    # available, else an HONEST close-to-close range (old code labelled C2C 'atr').
    atr_window = min(VOL_LEN, len(s) - 1)
    atr_kind = "c2c"
    atr = float((s - s.shift(1)).abs().tail(atr_window).mean()) if atr_window > 0 else px * 0.01
    if ohlcv is not None and len(ohlcv) >= atr_window + 1:
        try:
            _cmap = {c.lower(): c for c in ohlcv.columns}
            _h = pd.to_numeric(ohlcv[_cmap["high"]], errors="coerce")
            _l = pd.to_numeric(ohlcv[_cmap["low"]], errors="coerce")
            _cl = pd.to_numeric(ohlcv[_cmap["close"]], errors="coerce")
            _tr = pd.concat([(_h - _l), (_h - _cl.shift(1)).abs(),
                             (_l - _cl.shift(1)).abs()], axis=1).max(axis=1)
            _atr = float(_tr.tail(atr_window).mean())
            if math.isfinite(_atr) and _atr > 0:
                atr, atr_kind = _atr, "true_atr"
        except Exception:
            pass
    if not math.isfinite(atr) or atr <= 0:
        atr, atr_kind = px * 0.01, "fallback"

    # Trend breakout confirmation
    trend_break_up = px > trend_trr + 0.50 * atr
    trend_break_down = px < trend_lrr - 0.50 * atr
    tail_break_up = px > tail_trr + 0.75 * atr
    tail_break_down = px < tail_lrr - 0.75 * atr

    if trend_break_up:
        trend_phase = 1
    elif trend_break_down:
        trend_phase = -1
    if tail_break_up:
        tail_phase = 1
    elif tail_break_down:
        tail_phase = -1

    # BSI (optional, requires OHLCV)
    bsi_data = calc_bsi(ohlcv) if ohlcv is not None else {"available": False}

    result = {
        "ticker": ticker,
        "px": round(px, 6),
        "basis": round(basis, 6),
        "phase": phase_str,
        "phase_code": phase,
        "auto_tuned": use_auto_tune,
        "multipliers": {"trade": m_trade, "trend": m_trend, "tail": m_tail, "iv_symbol": iv_symbol},
        "trade": {
            "lrr": round(trade_lrr, 6),
            "trr": round(trade_trr, 6),
            "width_lower": round(trade_lower, 6),
            "width_upper": round(trade_upper, 6),
            "phase_state": trade_phase,
            "asymmetric_ratio": round(trade_upper / trade_lower if trade_lower > 0 else 1.0, 3),
        },
        "trend": {
            "lrr": round(trend_lrr, 6),
            "trr": round(trend_trr, 6),
            "phase_state": trend_phase,
            "break_up": trend_break_up,
            "break_down": trend_break_down,
        },
        "tail": {
            "lrr": round(tail_lrr, 6),
            "trr": round(tail_trr, 6),
            "phase_state": tail_phase,
            "has_full_history": has_full_tail,
            "break_up": tail_break_up,
            "break_down": tail_break_down,
        },
        "hurst": {
            "trade": round(H_trade, 4),
            "trend": round(H_trend, 4),
            "tail": round(H_tail, 4),
            "interpretation": "MEAN_REVERTING" if H_trend < 0.4 else "TRENDING" if H_trend > 0.6 else "RANDOM_WALK",
        },
        "vol": {
            "source": vol_src_used,
            "vol_source": round(vol_source, 4),
            "realized_vol_ann": round(realized_vol, 4),
            "external_iv": external_iv,
            "vasp_mult": round(vasp_mult, 4),
            "daily_vol": round(daily_vol, 6),
            "atr": round(atr, 6),
            "atr_kind": atr_kind,
        },
        "quad_applied": current_quad,
        "bsi": bsi_data,
        "version": "v20.3b",
    }

    result["signals"] = _derive_signals_v20_3b(result)
    return result


def _derive_signals_v20_3b(rr: Dict) -> Dict:
    """Hedgeye RTA signal derivation per Pine v20.3b state machine."""
    px = rr["px"]
    t = rr["trade"]
    tr = rr["trend"]
    tl = rr["tail"]

    trade_phase = t["phase_state"]
    trend_phase = tr["phase_state"]
    tail_phase = tl["phase_state"]

    # Safety net: fall back to 21v63 MA bias ONLY when a duration is genuinely neutral.
    # (Phase score is now anchored to each duration's mean — see S1-a — so this rarely
    # fires; previously it fired ALWAYS because score ≈ 0 with a prev-close basis.)
    ma_phase = rr.get("phase_code", 0)
    if trade_phase == 0:
        trade_phase = ma_phase
    if trend_phase == 0:
        trend_phase = ma_phase

    trade_width = t["trr"] - t["lrr"]
    trade_pos = (px - t["lrr"]) / trade_width if trade_width > 0 else 0.5

    # Pine RTA logic
    is_bull_trend = trend_phase == 1
    is_bear_trend = trend_phase == -1
    is_bull_trade = trade_phase == 1
    is_bear_trade = trade_phase == -1

    # Determine action (Pine: rtaBuy / rtaTrimRip / rtaAdd / rtaTrim / rtaShort / rtaCover)
    if px <= t["lrr"] and is_bull_trade and is_bull_trend:
        action = "BUY_DIP"; reason = "At LRR + Bull Trade & Trend — Hedgeye scale-in"
    elif px <= t["lrr"] and is_bear_trade and is_bear_trend:
        action = "COVER"; reason = "At LRR + Bear Trade & Trend — short cover"
    elif px >= t["trr"] and is_bull_trade and is_bull_trend:
        action = "TRIM_RIP"; reason = "At TRR + Bull Trade & Trend — trim/lock-in"
    elif px >= t["trr"] and is_bear_trade and is_bear_trend:
        action = "SHORT_RIP"; reason = "At TRR + Bear Trade & Trend — short rip"
    elif trade_pos <= 0.25 and is_bull_trade and is_bull_trend:
        action = "ADD"; reason = "Lower 25% TRADE range + Bull — Hedgeye add zone"
    elif trade_pos >= 0.75 and is_bull_trade and is_bull_trend:
        action = "TRIM"; reason = "Upper 25% TRADE range + Bull — trim zone"
    elif px <= t["lrr"]:
        action = "WATCH"; reason = "At LRR but trade/trend not aligned"
    elif px >= t["trr"]:
        action = "WATCH"; reason = "At TRR but trade/trend not aligned"
    else:
        action = "HOLD"; reason = "Mid TRADE range — wait for signal"

    # Quality grade — Keith McCullough's cleanest OWN signal = Bullish TRADE +
    # Bullish TREND with higher-highs + higher-lows. We grade on TREND ALIGNMENT
    # (both durations bullish), NOT on price being overbought above the bands.
    # (Old bug: required px > trend_TRR AND tail_TRR = overbought → contradicts
    #  buying at LRR → graded everything C → empty Quality buckets.)
    bull_form = px > tr["trr"] and px > tl["trr"]   # kept for 'formation' field
    bear_form = px < tr["lrr"] and px < tl["lrr"]
    # Multi-duration structure (Keith: bullish across TRADE/TREND/TAIL = strongest).
    # Use TAIL midpoint as long-term uptrend confirmation (px above = secular up).
    tail_mid = (tl["lrr"] + tl["trr"]) / 2
    bull_tail_struct = px > tail_mid
    bear_tail_struct = px < tail_mid

    if is_bull_trade and is_bull_trend and bull_tail_struct and trade_pos < 0.45:
        quality = "A+"   # bullish TRADE+TREND + long-term uptrend + pulled back = best BUY
    elif is_bull_trade and is_bull_trend and bull_tail_struct:
        quality = "A"    # bullish TRADE+TREND + above TAIL mid = clean multi-duration long
    elif is_bull_trade and is_bull_trend:
        quality = "B"    # bullish TRADE+TREND but below TAIL mid (early/recovering)
    elif is_bear_trade and is_bear_trend and bear_tail_struct and trade_pos > 0.55:
        quality = "short_A+"  # bearish all + ripped to TRR = best SHORT
    elif is_bear_trade and is_bear_trend and bear_tail_struct:
        quality = "short_A"
    elif is_bear_trade and is_bear_trend:
        quality = "short_B"
    else:
        quality = "C"

    return {
        "action": action,
        "reason": reason,
        "quality": quality,
        "formation": "BULLISH" if bull_form else "BEARISH" if bear_form else "NEUTRAL",
        "trade_position_pct": round(trade_pos * 100, 1),
        "distance_to_lrr_pct": round((px - t["lrr"]) / px * 100, 2),
        "distance_to_trr_pct": round((t["trr"] - px) / px * 100, 2),
        "rr_ratio": round((t["trr"] - px) / max(abs(px - t["lrr"]), 0.01), 2) if px < t["trr"] else 0.0,
    }


# ═══════════════════════════════════════════════════════════════════════════
# BATCH RUNNER
# ═══════════════════════════════════════════════════════════════════════════

def calculate_for_universe(
    prices_dict: Dict[str, pd.Series],
    current_quad: str = "Q3",
    iv_dict: Optional[Dict[str, float]] = None,
    ohlcv_dict: Optional[Dict[str, pd.DataFrame]] = None,
) -> Dict:
    """Run TRR/LRR v20.3b on a universe."""
    iv_dict = iv_dict or {}
    ohlcv_dict = ohlcv_dict or {}
    results = {}
    fail_count = 0

    for ticker, series in (prices_dict or {}).items():
        ohlcv = ohlcv_dict.get(ticker)
        rr = calculate_trr_lrr_v20(
            ticker, series,
            external_iv=iv_dict.get(ticker),
            current_quad=current_quad,
            iv_dict=iv_dict,
            ohlcv=ohlcv,
        )
        if rr:
            results[ticker] = rr
        else:
            fail_count += 1

    return {
        "asset_ranges": results,
        "summary": {
            "total": len(results),
            "failed": fail_count,
            "quad_applied": current_quad,
        },
        "version": "v20.3b",
    }


# Backwards-compat shims
def calculate_risk_range(ticker, prices_or_series, current_quad="Q3", vix_proxy=20.0):
    s = prices_or_series.get(ticker) if isinstance(prices_or_series, dict) else prices_or_series
    if s is None:
        return {"ticker": ticker, "ok": False, "reason": "no_data"}
    rr = calculate_trr_lrr_v20(ticker, s, external_iv=vix_proxy, current_quad=current_quad)
    if rr:
        rr["ok"] = True
        return rr
    return {"ticker": ticker, "ok": False, "reason": "insufficient_data"}


class RiskRangeEngine:
    """Drop-in replacement for old RiskRangeEngine class."""
    def __init__(self, current_quad="Q3", vix=20.0):
        self.current_quad = current_quad
        self.vix = vix

    def run(self, prices, current_quad=None, vix=None, iv_dict=None, ohlcv_dict=None):
        quad = current_quad or self.current_quad
        iv_full = {"^VIX": vix if vix is not None else self.vix}
        if iv_dict:
            iv_full.update(iv_dict)
        return calculate_for_universe(prices, current_quad=quad, iv_dict=iv_full, ohlcv_dict=ohlcv_dict)
