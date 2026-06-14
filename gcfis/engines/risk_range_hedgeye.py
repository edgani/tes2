"""risk_range_hedgeye.py — Hedgeye Risk Range, Python port of MQA v25.1 (TRADE/TREND/TAIL).

Faithful to Hedgeye's PUBLISHED structure (verified vs app.hedgeye.com/education):
  - 3 durations: TRADE (~3wk / 15d, entries+exits), TREND (~3mo / 63d, direction),
    TAIL (~3yr / 756d, long-term). Durations set the BASIS; ONE immediate-term
    volatility (ATR14) sets the WIDTH, scaled by per-duration multipliers.
  - 3 inputs: price, volume, volatility.
  - Usage: buy LRR / trim TRR — but ONLY in the TREND-formation direction; a break
    of TREND/TAIL support => exit.

Multiplier calibration is from MQA v25.1, anchored to 4 public Hedgeye prints
(IN-SAMPLE — NOT out-of-sample validated). Treat as a faithful prior; validate edge
in the Research Lab. Daily-bar note: MQA's LTF footprint-delta flow is unavailable on
daily bars, so flow uses the CLV (close-location-value) proxy — exactly MQA's
documented fallback. No fabrication.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

# ── per-ticker auto-tune (TRADE, TREND, TAIL ATR multipliers), ported from MQA f_auto_tune ──
_AUTOTUNE = [
    (("SPX", "SPY", "ES1!", "MES1!", "^GSPC"), 0.45, 0.65, 1.30),
    (("NDX", "QQQ", "NQ1!", "MNQ1!", "US100", "NAS100", "USTEC", "^NDX"), 0.50, 0.70, 1.40),
    (("RUT", "IWM", "RTY", "M2K1!"), 0.55, 0.80, 1.50),
    (("DJI", "YM1!", "DIA"), 0.40, 0.60, 1.20),
    (("GC1!", "GLD", "XAUUSD", "MGC1!"), 0.65, 0.95, 1.80),
    (("SI1!", "SLV", "XAGUSD"), 0.75, 1.10, 2.00),
    (("CL1!", "USOIL", "WTI", "MCL1!"), 0.55, 0.711, 1.50),
    (("NG1!", "UNG", "NATGAS"), 0.80, 1.20, 2.20),
    (("HG1!", "COPPER"), 0.60, 0.90, 1.70),
    (("BTC", "XBT", "BITCOIN"), 0.70, 1.00, 1.90),
    (("ETH", "ETHEREUM"), 0.75, 1.10, 2.00),
    (("EURUSD",), 0.35, 0.50, 1.00),
    (("GBPUSD",), 0.40, 0.55, 1.10),
    (("USDJPY",), 0.30, 0.45, 0.90),
    (("AUDUSD", "NZDUSD"), 0.40, 0.60, 1.20),
    (("USDCAD", "USDCHF"), 0.35, 0.50, 1.00),
    (("TSLA", "NVDA", "AMD", "PLTR"), 0.65, 0.95, 1.80),
    (("AAPL", "MSFT", "GOOGL", "AMZN"), 0.55, 0.80, 1.50),
    (("META", "NFLX", "CRM"), 0.60, 0.85, 1.60),
    (("JPM", "BAC", "GS", "WFC"), 0.45, 0.65, 1.30),
    (("IHSG", "JKSE", "JCI", ".JK"), 0.50, 0.75, 1.40),
]
_DEFAULT_MULT = (0.50, 0.711, 1.50)


def autotune(ticker):
    if not ticker:
        return _DEFAULT_MULT
    t = str(ticker).upper()
    for subs, mt, mtr, mta in _AUTOTUNE:
        if any(s in t for s in subs):
            return (mt, mtr, mta)
    return _DEFAULT_MULT


# ── helpers ──
def _wilder_atr(h, l, c, n=14):
    pc = c.shift(1)
    tr = pd.concat([(h - l).abs(), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


def _pctrank(s, win):
    return s.rolling(win, min_periods=max(10, win // 5)).apply(
        lambda a: (a[-1] >= a).mean(), raw=True) * 100.0


def _clamp(x, lo, hi):
    return np.minimum(hi, np.maximum(lo, x))


def _hysteresis(score, th, neu):
    sc = score.to_numpy()
    st = np.zeros(len(sc))
    prev = 0
    for i in range(len(sc)):
        s = sc[i]
        if np.isnan(s):
            st[i] = prev
            continue
        if s > th:
            prev = 1
        elif s < -th:
            prev = -1
        elif abs(s) <= neu:
            prev = 0
        st[i] = prev
    return pd.Series(st, index=score.index)


def _last(s, default=np.nan):
    s2 = pd.Series(s).dropna()
    return s2.iloc[-1] if len(s2) else default


def compute_risk_range(df, ticker=None, use_skew=True, smooth=True, smooth_bars=5, cap=0.15):
    """df: DataFrame with open/high/low/close[/volume] (any case). Returns latest TRR/LRR per
    horizon + formation + phase + RTA signal + response-zone + series for plotting."""
    d = df.rename(columns=str.lower).copy()
    o, h, l, c = d["open"].astype(float), d["high"].astype(float), d["low"].astype(float), d["close"].astype(float)
    v = d["volume"].astype(float) if "volume" in d.columns else pd.Series(np.nan, index=d.index)
    mt, mtr, mta = autotune(ticker)

    atr = _wilder_atr(h, l, c, 14)
    logret = np.log(c / c.shift(1).replace(0, np.nan))

    # vol-state = vov(0.40) + regime(0.35) + forward-vol(0.25), clamped
    atrsma = atr.rolling(20, min_periods=5).mean()
    vov = (atr / atrsma - 1.0).fillna(0.0)
    vovf = 1.0 + vov * 0.30
    rvrank = _pctrank(c.rolling(20, min_periods=5).std(), 252)
    regmult = pd.Series(
        np.where(rvrank > 80, 1.30, np.where(rvrank > 60, 1.18, np.where(rvrank > 40, 1.08, 0.92))),
        index=c.index).where(~rvrank.isna(), 1.0)
    rvs = logret.rolling(20, min_periods=5).std()
    rvl = logret.rolling(100, min_periods=20).std()
    fwdvol = _clamp((rvs / rvl).fillna(1.0), 0.6, 1.6)
    volstate = _clamp(vovf * 0.40 + regmult * 0.35 + fwdvol * 0.25, 0.75, 1.55)

    # Amihud illiquidity amplifier
    dvol = (c * v).replace(0, np.nan)
    illiq = (logret.abs() / dvol)
    illiqrank = _pctrank(illiq.ffill(), 50)
    amihud = _clamp(1.0 + (illiqrank.fillna(50.0) / 100.0 - 0.5) * 0.30, 0.85, 1.30)

    # anti-wiggle: EWMA the combined vol multiplier + cap per-bar change
    volmult_raw = volstate * amihud
    volmult_ema = volmult_raw.ewm(span=smooth_bars, adjust=False).mean()
    if smooth:
        vm = volmult_ema.to_numpy().astype(float).copy()
        for i in range(1, len(vm)):
            if np.isnan(vm[i]) or np.isnan(vm[i - 1]):
                continue
            lo, hi = vm[i - 1] * (1.0 - cap), vm[i - 1] * (1.0 + cap)
            vm[i] = min(hi, max(lo, vm[i]))
        volmult = pd.Series(vm, index=c.index)
    else:
        volmult = volmult_raw

    # volume factor (conditional widen/narrow)
    volma = v.rolling(20, min_periods=5).mean()
    volroc = ((v - volma) / volma).fillna(0.0)
    priceup = c > c.shift(1)
    volconf = (priceup & (v > v.shift(1))) | (~priceup & (v < v.shift(1)))
    voldiv = (priceup & (v < v.shift(1))) | (~priceup & (v > v.shift(1)))
    vf = np.ones(len(c))
    vf = np.where((volroc > 0.30) & voldiv, 1.0 + np.minimum(volroc * 0.25, 0.30), vf)
    vf = np.where((volroc > 0.30) & volconf, 1.0 - np.minimum(volroc * 0.10, 0.15), vf)
    vf = np.where(volroc < -0.20, 1.0 + volroc.abs() * 0.15, vf)
    volfactor = pd.Series(vf, index=c.index)

    # flow proxy (CLV) + semivol asymmetry skew
    clv = (((c - l) - (h - c)) / (h - l).replace(0, np.nan)).fillna(0.0)
    flow = clv.ewm(span=10, adjust=False).mean().clip(-1, 1)
    ret = c / c.shift(1) - 1.0
    dn = np.sqrt((ret.clip(upper=0) ** 2).rolling(20, min_periods=5).mean())
    up = np.sqrt((ret.clip(lower=0) ** 2).rolling(20, min_periods=5).mean())
    semiskew = ((dn - up) / (dn + up)).fillna(0.0)
    asym = _clamp(semiskew * 0.50 - flow * 0.40, -0.95, 0.95) if use_skew else pd.Series(0.0, index=c.index)

    # Kaufman efficiency ratio (regime / drift weight)
    ernum = (c - c.shift(20)).abs()
    erden = (c - c.shift(1)).abs().rolling(20, min_periods=5).sum()
    er = (ernum / erden.replace(0, np.nan)).fillna(0.0)

    # basis: TRADE=prior close, TREND=SMA63, TAIL=SMA756
    basis_trade = c.shift(1).fillna(c)
    basis_trend = c.rolling(63, min_periods=20).mean()
    basis_tail = c.rolling(756, min_periods=120).mean()
    gap = (o - c.shift(1)).abs()
    isgap = gap > atr * 0.50
    gapadd = pd.Series(np.where(isgap, gap * 0.70, 0.0), index=c.index)
    basis_trade_g = pd.Series(np.where(isgap, basis_trade + (o - basis_trade) * 0.50, basis_trade), index=c.index)
    driftw = _clamp(0.40 + er, 0.40, 1.0)
    drift = flow * atr * 0.30 * driftw
    basis_trade_f = basis_trade_g + drift

    def band(basis, mult, lmul, umul, add0=0.0):
        raww = atr * mult * volfactor
        return basis - (raww * volmult * lmul + add0), basis + (raww * volmult * umul + add0)

    trade_lrr, trade_trr = band(basis_trade_f, mt, 1 + asym, 1 - asym * 0.6, gapadd)
    trend_lrr, trend_trr = band(basis_trend, mtr, 1 + asym * 0.6, 1 - asym * 0.36)
    tail_lrr, tail_trr = band(basis_tail, mta, 1 + asym * 0.3, 1 - asym * 0.18)

    # formation (Hedgeye): price > TREND > TAIL = bullish; price < TREND < TAIL = bearish
    bull = (c > basis_trend) & (basis_trend > basis_tail)
    bear = (c < basis_trend) & (basis_trend < basis_tail)

    # phase state machine (hysteresis)
    trade_score = (c - basis_trade_f) / (trade_trr - trade_lrr).replace(0, np.nan)
    trend_score = (c - basis_trend) / (trend_trr - trend_lrr).replace(0, np.nan)
    tail_score = (c - basis_tail) / (tail_trr - tail_lrr).replace(0, np.nan)
    trade_phase = _hysteresis(trade_score.fillna(0.0), 0.20, 0.06)
    tail_phase = _hysteresis(tail_score.fillna(0.0), 0.10, 0.03)
    # TREND phase is formation-anchored (price vs SMA63), per Hedgeye direction gate
    trend_phase = pd.Series(np.where(c > basis_trend, 1, np.where(c < basis_trend, -1, 0)), index=c.index)

    # RTA signals — gated on TRADE × TREND alignment (the Hedgeye buy-low/sell-high rules)
    rng = (trade_trr - trade_lrr)
    near_low = c <= (trade_lrr + rng * 0.25)
    near_high = c >= (trade_trr - rng * 0.25)
    bull_align = (trade_phase == 1) & (trend_phase == 1)
    bear_align = (trade_phase == -1) & (trend_phase == -1)
    rta = np.full(len(c), "", dtype=object)
    rta = np.where((c <= trade_lrr) & bull_align, "BUY", rta)
    rta = np.where(near_low & bull_align & (rta == ""), "ADD", rta)
    rta = np.where((c >= trade_trr) & bull_align, "TRIM_RIP", rta)
    rta = np.where(near_high & bull_align & (rta == ""), "TRIM", rta)
    rta = np.where((c >= trade_trr) & bear_align, "SHORT", rta)
    rta = np.where((c <= trade_lrr) & bear_align, "COVER", rta)
    rta = pd.Series(rta, index=c.index)

    # response-zone (path-dependent meaning AT the band)
    rrpos = ((c - trade_lrr) / rng.replace(0, np.nan)).fillna(0.5)
    dipped = l.rolling(5).min().shift(1) < trade_lrr.shift(1)
    poked = h.rolling(5).max().shift(1) > trade_trr.shift(1)
    tight = (h.rolling(5).max() - l.rolling(5).min()) < atr * 1.6
    accept2 = (c > trade_trr) & (c.shift(1) > trade_trr.shift(1))
    newlow5 = l <= l.rolling(5).min()
    resp = np.full(len(c), "MID", dtype=object)
    resp = np.where(dipped & (c > trade_lrr), "RECLAIM", resp)
    resp = np.where((rrpos < 0.25) & newlow5 & (flow < 0) & (resp == "MID"), "NO_BID", resp)
    resp = np.where((rrpos < 0.25) & tight & (flow >= 0) & (resp == "MID"), "ABSORPTION", resp)
    resp = np.where(accept2 & (resp == "MID"), "ACCEPTANCE", resp)
    resp = np.where(poked & (c < trade_trr) & (resp == "MID"), "REJECTION", resp)
    resp = pd.Series(resp, index=c.index)

    form = "BULLISH" if bool(_last(bull, False)) else "BEARISH" if bool(_last(bear, False)) else "NEUTRAL"
    idx = [str(x.date()) if hasattr(x, "date") else str(x) for x in c.index]
    return {
        "ticker": ticker, "multipliers": {"trade": mt, "trend": mtr, "tail": mta},
        "close": round(float(_last(c)), 4),
        "formation": form,
        "rta": (str(_last(rta, "")) or "—"),
        "response": str(_last(resp, "MID")),
        "trade": {"lrr": round(float(_last(trade_lrr)), 4), "trr": round(float(_last(trade_trr)), 4), "phase": int(_last(trade_phase, 0))},
        "trend": {"lrr": round(float(_last(trend_lrr)), 4), "trr": round(float(_last(trend_trr)), 4), "phase": int(_last(trend_phase, 0))},
        "tail": {"lrr": round(float(_last(tail_lrr)), 4), "trr": round(float(_last(tail_trr)), 4), "phase": int(_last(tail_phase, 0))},
        "efficiency_ratio": round(float(_last(er, 0.0)), 3),
        "vol_state": round(float(_last(volstate, 1.0)), 3),
        "atr14": round(float(_last(atr, 0.0)), 4),
        "series": {
            "index": idx,
            "close": [round(float(x), 4) if pd.notna(x) else None for x in c],
            "trade_lrr": [round(float(x), 4) if pd.notna(x) else None for x in trade_lrr],
            "trade_trr": [round(float(x), 4) if pd.notna(x) else None for x in trade_trr],
            "trend_lrr": [round(float(x), 4) if pd.notna(x) else None for x in trend_lrr],
            "trend_trr": [round(float(x), 4) if pd.notna(x) else None for x in trend_trr],
            "bull": [1 if bool(x) else 0 for x in bull],
            "bear": [1 if bool(x) else 0 for x in bear],
        },
    }
