"""engines/treasury_liquidity.py — US Treasury + NY Fed Liquidity (FREE, NO KEY)

Adds authoritative government liquidity data the system wasn't using — and which is core
to the liquidity/Druckenmiller/GIP framework: net liquidity is a primary driver of risk
assets. Sources (all free, no API key, just a polite User-Agent):
  • US Treasury fiscaldata API  → TGA (Treasury General Account operating cash balance)
  • NY Fed markets API          → RRP (reverse repo) + SOFR
  • (optional) FRED WALCL        → Fed balance sheet, if a fred dict is passed

Net Liquidity ≈ Fed balance sheet − TGA − RRP. Rising net liquidity = liquidity flowing
into markets (risk-on); a draining RRP = cash re-entering the system. Uses stdlib urllib
(no extra deps) and is fully defensive — returns neutral on any failure.

NOTE: needs network at runtime (your env). Parsing logic verified against mock payloads;
the fetch itself can't run in the build sandbox (pip/github-only network).
"""
from __future__ import annotations
import json
import logging
import urllib.request
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_UA = {"User-Agent": "MacroRegimePro/1.0 (research)"}
_TGA_URL = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/"
            "accounting/dts/operating_cash_balance"
            "?fields=record_date,open_today_bal,account_type"
            "&filter=account_type:eq:Treasury%20General%20Account%20(TGA)%20Opening%20Balance"
            "&sort=-record_date&page[size]=10")
_RRP_URL = "https://markets.newyorkfed.org/api/rp/reverserepo/propositions/search.json?startDate=&endDate="
_RRP_LATEST = "https://markets.newyorkfed.org/api/rp/reverserepo/all/latest.json"
_SOFR_URL = "https://markets.newyorkfed.org/api/rates/secured/sofr/last/2.json"


def _get_json(url: str, timeout: int = 12) -> Optional[dict]:
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        logger.debug(f"fetch failed {url[:60]}…: {e}")
        return None


def fetch_tga() -> Dict:
    """Latest + prior TGA balance ($MM). Returns {ok, latest, prev, change, date}."""
    d = _get_json(_TGA_URL)
    try:
        rows = (d or {}).get("data", [])
        if not rows:
            return {"ok": False}
        latest = float(rows[0]["open_today_bal"])
        prev = float(rows[1]["open_today_bal"]) if len(rows) > 1 else None
        return {"ok": True, "latest": latest, "prev": prev,
                "change": (latest - prev) if prev is not None else None,
                "date": rows[0].get("record_date")}
    except Exception as e:
        logger.debug(f"TGA parse: {e}")
        return {"ok": False}


def fetch_rrp() -> Dict:
    """Latest reverse-repo accepted amount ($B)."""
    d = _get_json(_RRP_LATEST)
    try:
        ops = (d or {}).get("repo", {}).get("operations", []) or (d or {}).get("operations", [])
        if not ops:
            return {"ok": False}
        op = ops[0]
        amt = op.get("totalAmtAccepted") or op.get("totalAmtSubmitted")
        return {"ok": True, "amount": float(amt), "date": op.get("operationDate")}
    except Exception as e:
        logger.debug(f"RRP parse: {e}")
        return {"ok": False}


def fetch_sofr() -> Dict:
    d = _get_json(_SOFR_URL)
    try:
        refs = (d or {}).get("refRates", [])
        if not refs:
            return {"ok": False}
        return {"ok": True, "sofr": float(refs[0]["percentRate"]),
                "date": refs[0].get("effectiveDate")}
    except Exception as e:
        logger.debug(f"SOFR parse: {e}")
        return {"ok": False}


def _fred_walcl(fred: Optional[Dict]):
    """Fed balance sheet (WALCL, $MM) from a passed fred dict, if present."""
    if not fred:
        return None
    v = fred.get("WALCL")
    try:
        import pandas as pd
        if isinstance(v, (int, float)):
            return float(v)
        s = pd.Series(v).dropna()
        return float(s.iloc[-1]) if len(s) else None
    except Exception:
        return None


def analyze_liquidity(fred: Optional[Dict] = None) -> Dict:
    """Combine TGA + RRP (+ optional Fed BS) into a net-liquidity read + bias.

    Returns {ok, tga, rrp, sofr, net_liquidity_bn, signals[], bias, note}.
    bias: RISK_ON (liquidity expanding) / NEUTRAL / RISK_OFF (draining).
    """
    tga, rrp, sofr = fetch_tga(), fetch_rrp(), fetch_sofr()
    walcl = _fred_walcl(fred)  # $MM
    signals, score = [], 0

    # RRP draining = cash leaving the Fed back into the system = supportive
    if rrp.get("ok") and rrp.get("amount") is not None:
        # NY Fed RRP amounts are in $B already in this feed
        signals.append(f"RRP ${rrp['amount']:.0f}B")
    # TGA build = Treasury pulling cash OUT of the system (drains liquidity) = headwind
    if tga.get("ok") and tga.get("change") is not None:
        chg_bn = tga["change"] / 1000.0  # $MM → $B
        if chg_bn > 30:
            score -= 1; signals.append(f"TGA building +${chg_bn:.0f}B (drains liquidity)")
        elif chg_bn < -30:
            score += 1; signals.append(f"TGA drawing down ${abs(chg_bn):.0f}B (adds liquidity)")

    net_liq_bn = None
    if walcl is not None and tga.get("ok") and rrp.get("ok"):
        # WALCL & TGA in $MM; RRP in $B → normalize to $B
        net_liq_bn = walcl / 1000.0 - tga["latest"] / 1000.0 - rrp["amount"]
        signals.append(f"Net liquidity ≈ ${net_liq_bn:,.0f}B (Fed BS − TGA − RRP)")

    bias = "RISK_ON" if score > 0 else "RISK_OFF" if score < 0 else "NEUTRAL"
    note = ("Liquidity " + ("expanding — supportive for risk" if bias == "RISK_ON"
            else "draining — headwind for risk" if bias == "RISK_OFF"
            else "roughly flat") + ". " + "; ".join(signals)) if signals else \
           "Liquidity data unavailable (needs network)."

    return {"ok": bool(signals), "tga": tga, "rrp": rrp, "sofr": sofr,
            "net_liquidity_bn": net_liq_bn, "signals": signals, "bias": bias, "note": note}
