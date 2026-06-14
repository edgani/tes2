"""engines/fx_carry_engine.py — FX Carry / Rate-Differential Positioning

The one major FX-positioning input the system lacked. Carry (the interest-rate
differential between the two currencies in a pair) is the dominant medium-term FX driver:
a currency with a higher and RISING rate differential attracts flows. This complements the
COT (cftc_cot_scraper) and USD-correlation engines already present.

Uses FRED harmonized long-term gov-bond yields (IRLTLT01<CC>M156N), available for all G10.
Defensive: accepts a pre-fetched `fred` dict, else self-fetches via fredapi (FRED_API_KEY
env), else returns neutral. Monthly series → a positioning bias, not a tick signal.
"""
from __future__ import annotations
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# FRED harmonized long-term (10Y-ish) gov-bond yield, monthly, per country
_RATE_SERIES = {
    "USD": "IRLTLT01USM156N", "EUR": "IRLTLT01EZM156N", "JPY": "IRLTLT01JPM156N",
    "GBP": "IRLTLT01GBM156N", "CAD": "IRLTLT01CAM156N", "AUD": "IRLTLT01AUM156N",
    "CHF": "IRLTLT01CHM156N", "NZD": "IRLTLT01NZM156N",
}

# pair → (base, quote). Carry(pair) = rate(base) - rate(quote).
_PAIRS = {
    "EURUSD=X": ("EUR", "USD"), "GBPUSD=X": ("GBP", "USD"),
    "AUDUSD=X": ("AUD", "USD"), "NZDUSD=X": ("NZD", "USD"),
    "USDJPY=X": ("USD", "JPY"), "USDCAD=X": ("USD", "CAD"),
    "USDCHF=X": ("USD", "CHF"), "DX-Y.NYB": ("USD", "EUR"),  # DXY ≈ USD vs basket (EUR proxy)
}


def _series_last_and_prev(fred: Dict, code: str, months_back: int = 3):
    """Return (latest, value ~months_back ago) for a FRED series stored in `fred`.
    Accepts a scalar (latest only) or a list/Series of observations."""
    v = fred.get(code) if fred else None
    if v is None:
        return None, None
    try:
        import pandas as pd
        if isinstance(v, (int, float)):
            return float(v), None
        s = pd.Series(v).dropna()
        if len(s) == 0:
            return None, None
        latest = float(s.iloc[-1])
        prev = float(s.iloc[-(months_back + 1)]) if len(s) > months_back else None
        return latest, prev
    except Exception:
        try:
            return float(v), None
        except Exception:
            return None, None


def _maybe_self_fetch(needed_codes) -> Dict:
    """Best-effort self-fetch of rate series via fredapi (FRED_API_KEY env). Returns {} on
    any failure — never raises."""
    import os
    key = os.environ.get("FRED_API_KEY")
    if not key:
        return {}
    try:
        from fredapi import Fred
        f = Fred(api_key=key)
        out = {}
        for c in needed_codes:
            try:
                out[c] = f.get_series(c).dropna()
            except Exception:
                continue
        return out
    except Exception as e:
        logger.debug(f"fx_carry self-fetch unavailable: {e}")
        return {}


def analyze_fx_carry(fred: Optional[Dict] = None, pairs: Optional[list] = None) -> Dict:
    """Per-pair carry differential + 3M trend → carry bias.

    Returns {ok, pairs: {PAIR: {carry_diff, carry_3m_change, bias, note}}, source}.
    bias: STRONG_CARRY_LONG / CARRY_LONG / NEUTRAL / CARRY_SHORT / STRONG_CARRY_SHORT
    (expressed in the PAIR's direction — i.e. long the pair).
    """
    pairs = pairs or list(_PAIRS.keys())
    fred = dict(fred or {})
    # fill any missing rate series via self-fetch (optional)
    needed = {_RATE_SERIES[c] for p in pairs for c in _PAIRS.get(p, ()) if c in _RATE_SERIES}
    if not all(code in fred for code in needed):
        fetched = _maybe_self_fetch([c for c in needed if c not in fred])
        fred.update(fetched)
    source = "fred"

    rates, rate_chg = {}, {}
    for ccy, code in _RATE_SERIES.items():
        latest, prev = _series_last_and_prev(fred, code)
        if latest is not None:
            rates[ccy] = latest
            if prev is not None:
                rate_chg[ccy] = latest - prev

    result = {}
    for p in pairs:
        leg = _PAIRS.get(p)
        if not leg:
            continue
        base, quote = leg
        rb, rq = rates.get(base), rates.get(quote)
        if rb is None or rq is None:
            result[p] = {"carry_diff": None, "carry_3m_change": None,
                         "bias": "NEUTRAL", "note": "Rate data unavailable."}
            continue
        diff = rb - rq                                   # carry in pair terms (long-pair)
        chg = None
        if base in rate_chg and quote in rate_chg:
            chg = rate_chg[base] - rate_chg[quote]       # widening(+) / narrowing(-)
        widening = (chg or 0) > 0.05
        narrowing = (chg or 0) < -0.05
        if diff > 1.0 and not narrowing:
            bias = "STRONG_CARRY_LONG" if widening else "CARRY_LONG"
        elif diff > 0.25:
            bias = "CARRY_LONG"
        elif diff < -1.0 and not widening:
            bias = "STRONG_CARRY_SHORT" if narrowing else "CARRY_SHORT"
        elif diff < -0.25:
            bias = "CARRY_SHORT"
        else:
            bias = "NEUTRAL"
        trend = (f", differential {'widening' if widening else 'narrowing' if narrowing else 'flat'}"
                 f" ({chg:+.2f}pp/3m)" if chg is not None else "")
        note = (f"{base} {rb:.2f}% vs {quote} {rq:.2f}% → carry {diff:+.2f}pp{trend}. "
                f"Positioning bias for {p}: {bias.replace('_', ' ').lower()}.")
        result[p] = {"carry_diff": round(diff, 2),
                     "carry_3m_change": (round(chg, 2) if chg is not None else None),
                     "base_rate": round(rb, 2), "quote_rate": round(rq, 2),
                     "bias": bias, "note": note}

    return {"ok": bool(rates), "pairs": result, "source": source,
            "note": ("" if rates else "No FRED rate data (pass `fred` or set FRED_API_KEY).")}
