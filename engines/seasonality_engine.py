"""engines/seasonality_engine.py — Calendar Seasonality (price-based)

Fills the seasonality slot the commodity structure panel already displays
(market_card_renderer reads sd["seasonality_month"] / sd["seasonality_avg"], which was
otherwise defaulted). Computes, from price history, the average return for the CURRENT
calendar month across prior years + a hit-rate, so commodities/FX/any asset get a real
seasonal bias instead of a hardcoded default. Pure price — fully self-contained.
"""
from __future__ import annotations
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_MONTHS = ["January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December"]


def compute_seasonality(prices, asof_month: Optional[int] = None, min_years: int = 4) -> Dict:
    """Average monthly return for the current month across prior years + hit-rate.

    Args:
        prices: pd.Series of closes indexed by date (DatetimeIndex preferred). If the
                index isn't datetime, returns a neutral result (can't bucket by month).
        asof_month: 1-12; defaults to the current month of the data's last timestamp.
        min_years: minimum distinct years required to report a non-neutral signal.
    Returns: {ok, month, month_name, seasonality_avg(%), hit_rate(%), years, bias, note}
    """
    import pandas as pd
    import numpy as np

    neutral = {"ok": False, "month": asof_month or 0, "month_name": "",
               "seasonality_avg": 0.0, "hit_rate": 50.0, "years": 0,
               "bias": "NEUTRAL", "note": "Insufficient dated history for seasonality."}
    try:
        s = pd.Series(prices).dropna()
        if not isinstance(s.index, pd.DatetimeIndex):
            s.index = pd.to_datetime(s.index, errors="coerce")
        s = s[~s.index.isna()]
        if len(s) < 252:
            return neutral
    except Exception:
        return neutral

    # month-end series → monthly returns
    try:
        m = s.resample("ME").last().dropna()
    except Exception:
        m = s.resample("M").last().dropna()
    mret = m.pct_change().dropna()
    if len(mret) < 12:
        return neutral

    month = int(asof_month or s.index[-1].month)
    same = mret[mret.index.month == month]
    years = int(same.shape[0])
    if years < min_years:
        return {**neutral, "month": month, "month_name": _MONTHS[month - 1],
                "years": years, "note": f"Only {years} prior {_MONTHS[month-1]} samples (<{min_years})."}

    avg = float(same.mean()) * 100.0
    hit = float((same > 0).mean()) * 100.0
    if avg > 1.0 and hit >= 60:
        bias = "BULLISH"
    elif avg < -1.0 and hit <= 40:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"
    note = (f"{_MONTHS[month-1]} avg {avg:+.1f}% over {years}y, {hit:.0f}% positive → "
            f"seasonal {bias.lower()} bias.")
    return {"ok": True, "month": month, "month_name": _MONTHS[month - 1],
            "seasonality_avg": round(avg, 2), "hit_rate": round(hit, 1),
            "years": years, "bias": bias, "note": note}


def seasonality_for_display(prices) -> Dict:
    """Shape compatible with the commodity structure panel's expected keys."""
    r = compute_seasonality(prices)
    return {"seasonality_month": r["month_name"] or _MONTHS[0],
            "seasonality_avg": r["seasonality_avg"],
            "seasonality_hit_rate": r["hit_rate"],
            "seasonality_bias": r["bias"], "seasonality_note": r["note"]}


def compute_universe_seasonality(prices: Dict) -> Dict:
    out = {}
    for t, s in (prices or {}).items():
        try:
            out[t] = compute_seasonality(s)
        except Exception as e:
            logger.debug(f"seasonality failed for {t}: {e}")
    return out
