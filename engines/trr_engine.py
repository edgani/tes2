"""trr_engine.py — Hedgeye Risk Range Engine v20.2
Ported from Pine Script with:
- 3 timeframes: TRADE (15D), TREND (63D), TAIL (252D)
- Asymmetric ATR bands (bull vs bear regime)
- Previous-close basis for range anchoring
- Hurst exponent for mean-reversion detection
- Formation classification: BULLISH / BEARISH / BASE / CAUTION
"""
import pandas as pd
import numpy as np
import math

def _atr(series: pd.Series, length: int) -> float:
    """Average True Range using previous close basis."""
    if len(series) < length + 1:
        return series.std() if len(series) > 1 else 0.0
    high = series.rolling(2).max().iloc[-length:]
    low = series.rolling(2).min().iloc[-length:]
    prev_close = series.shift(1).iloc[-length:]
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return float(tr.mean())

def _sma(series: pd.Series, length: int) -> float:
    return float(series.tail(length).mean())

def _hurst(series: pd.Series, max_lag: int = 20) -> float:
    """Simplified Hurst exponent via R/S analysis."""
    if len(series) < max_lag * 2:
        return 0.5
    s = series.dropna().values
    if len(s) < max_lag * 2:
        return 0.5
    lags = range(2, min(max_lag, len(s)//4))
    tau = []
    rs = []
    for lag in lags:
        chunks = len(s) // lag
        if chunks < 2:
            continue
        rss = []
        for i in range(chunks):
            chunk = s[i*lag:(i+1)*lag]
            if len(chunk) < 2:
                continue
            mean_chunk = np.mean(chunk)
            dev = chunk - mean_chunk
            cumdev = np.cumsum(dev)
            R = max(cumdev) - min(cumdev)
            S = np.std(chunk)
            if S > 0:
                rss.append(R / S)
        if rss:
            tau.append(lag)
            rs.append(np.mean(rss))
    if len(tau) < 2:
        return 0.5
    log_tau = np.log(tau)
    log_rs = np.log(rs)
    hurst = np.polyfit(log_tau, log_rs, 1)[0]
    return float(hurst)

def calc_trr_lrr(series: pd.Series) -> dict:
    """
    Calculate Hedgeye-style TRR/LRR for TRADE, TREND, TAIL.
    Returns dict with all range levels + formation + side.
    """
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) < 63:
        return None

    px = float(s.iloc[-1])
    basis = float(s.iloc[-2])  # Previous close basis

    # ── Volatility calculations ──
    trade_atr = _atr(s, 15)
    trend_atr = _atr(s, 63)
    tail_atr = _atr(s, 252) if len(s) >= 252 else trend_atr * 1.6

    trade_std = float(s.tail(15).std())
    trend_std = float(s.tail(63).std())
    tail_std = float(s.tail(252).std()) if len(s) >= 252 else trend_std * 1.6

    daily_vol = float(s.tail(20).pct_change().dropna().std()) if len(s) >= 21 else 0.0
    realized_vol = daily_vol * math.sqrt(252) if daily_vol > 0 else 0.0

    # ── Regime detection (bull vs bear) ──
    # Using Trend SMA slope and price vs Trend SMA
    sma63 = _sma(s, 63)
    sma252 = _sma(s, 252) if len(s) >= 252 else sma63

    # Bull market = price > SMA63 > SMA252 (or proxy)
    is_bull = px > sma63 and sma63 >= sma252 * 0.98
    is_bear = px < sma63 and sma63 <= sma252 * 1.02

    # ── Multipliers (calibrated) ──
    # In bull market: tight TRR (harder to break out), wide LRR (support holds)
    # In bear market: wide TRR (resistance), tight LRR (breaks down easily)
    if is_bull:
        trade_l_mult, trade_r_mult = 1.2, 0.6
        trend_l_mult, trend_r_mult = 1.0, 0.711  # User calibrated: SMA63 + ATR*0.711 = $98.52
        tail_l_mult, tail_r_mult = 1.4, 1.0
    elif is_bear:
        trade_l_mult, trade_r_mult = 0.6, 1.2
        trend_l_mult, trend_r_mult = 0.711, 1.0
        tail_l_mult, tail_r_mult = 1.0, 1.4
    else:
        trade_l_mult, trade_r_mult = 0.9, 0.9
        trend_l_mult, trend_r_mult = 0.85, 0.85
        tail_l_mult, tail_r_mult = 1.2, 1.2

    # ── Range calculations (previous-close basis) ──
    # LRR = basis - ATR * multiplier
    # TRR = basis + ATR * multiplier
    trade_lrr = basis - trade_atr * trade_l_mult
    trade_trr = basis + trade_atr * trade_r_mult
    trend_lrr = basis - trend_atr * trend_l_mult
    trend_trr = basis + trend_atr * trend_r_mult
    tail_lrr = basis - tail_atr * tail_l_mult
    tail_trr = basis + tail_atr * tail_r_mult

    # ── Formation classification ──
    # BULLISH: Price > Trend TRR AND > Tail TRR (breaking out across all timeframes)
    # BEARISH: Price < Trend LRR AND < Tail LRR (breaking down across all timeframes)
    # BASE: Within Trend range, within Tail range
    # CAUTION: Outside Trade range but inside Trend range (early warning)

    above_trade = px > trade_trr
    below_trade = px < trade_lrr
    above_trend = px > trend_trr
    below_trend = px < trend_lrr
    above_tail = px > tail_trr
    below_tail = px < tail_lrr

    if above_trend and above_tail:
        formation = "BULLISH_BREAKOUT"
        side = "long"
    elif below_trend and below_tail:
        formation = "BEARISH_BREAKDOWN"
        side = "short"
    elif above_trade and not above_trend:
        formation = "BULLISH_CAUTION"
        side = "long"
    elif below_trade and not below_trend:
        formation = "BEARISH_CAUTION"
        side = "short"
    elif px > sma63 and px > trend_lrr:
        formation = "BULLISH_BASE"
        side = "long"
    elif px < sma63 and px < trend_trr:
        formation = "BEARISH_BASE"
        side = "short"
    else:
        formation = "NEUTRAL_BASE"
        side = "neutral"

    # ── Hurst exponents per timeframe ──
    h_trade = _hurst(s.tail(30), 10)
    h_trend = _hurst(s.tail(100), 20)
    h_tail = _hurst(s, 50) if len(s) >= 100 else h_trend

    return {
        "price": px,
        "basis": basis,
        "formation": formation,
        "side": side,
        "trade_lrr": round(trade_lrr, 4),
        "trade_trr": round(trade_trr, 4),
        "trend_lrr": round(trend_lrr, 4),
        "trend_trr": round(trend_trr, 4),
        "tail_lrr": round(tail_lrr, 4),
        "tail_trr": round(tail_trr, 4),
        "daily_vol": round(daily_vol, 4),
        "realized_vol": round(realized_vol, 4),
        "hurst": {
            "trade": round(h_trade, 2),
            "trend": round(h_trend, 2),
            "tail": round(h_tail, 2),
        },
        "sma63": round(sma63, 4),
        "sma252": round(sma252, 4) if len(s) >= 252 else None,
        "is_bull": is_bull,
        "is_bear": is_bear,
    }
