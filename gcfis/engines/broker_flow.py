"""broker_flow.py — order-flow INTENT classifier (bandarmologi / BRAIN-style).
Separates BUILDING vs SCALPING vs ABSORBING vs PANIC vs DELIBERATE distribution.
IHSG uses broker codes; other markets pass size-bucket/tick-classified flow (same schema)."""
from __future__ import annotations
import numpy as np

def _label(net, gross, ng, size_pct, agg_share, pass_share, price_down):
    if gross <= 0:
        return "INACTIVE"
    if abs(ng) < 0.35:
        return "ABSORBING" if (pass_share > 0.6 and net > 0 and price_down) else "MARKET_MAKING"
    if net > 0:
        if size_pct < 0.4 and agg_share < 0.5:
            return "SCALPING"
        return "BUILDING_LONG" if agg_share >= 0.5 else "ACCUMULATING"
    else:
        if size_pct < 0.4 and agg_share > 0.6:
            return "PANIC_SELLING"          # retail capitulation
        return "DELIBERATE_SELLING"         # distribution

def run_broker_flow(brokers: list[dict], price_down: bool = True) -> dict:
    """brokers: list of {broker, agg_buy, pass_buy, agg_sell, pass_sell, is_foreign?}."""
    if not brokers:
        return {"ok": False, "reason": "no broker flow data"}
    rows = []
    for b in brokers:
        ab, pb = b.get("agg_buy", 0), b.get("pass_buy", 0)
        as_, ps = b.get("agg_sell", 0), b.get("pass_sell", 0)
        buy, sell = ab + pb, as_ + ps
        net = buy - sell; gross = buy + sell
        ng = net / gross if gross else 0.0
        agg = ab + as_; agg_share = agg / gross if gross else 0.0
        pass_share = (pb + ps) / gross if gross else 0.0
        rows.append({**b, "net": net, "gross": gross, "ng": ng, "agg_share": agg_share, "pass_share": pass_share})
    gmax = max(r["gross"] for r in rows) or 1
    for r in rows:
        r["size_pct"] = r["gross"] / gmax
        r["label"] = _label(r["net"], r["gross"], r["ng"], r["size_pct"], r["agg_share"], r["pass_share"], price_down)
    # smart-money net: down-weight scalpers/market-makers, up-weight foreign & directional
    smart = 0.0
    for r in rows:
        w = 0.1 if r["label"] in ("SCALPING", "MARKET_MAKING") else 1.0
        w *= 1.3 if r.get("is_foreign") else 1.0
        w *= min(abs(r["ng"]) + 0.2, 1.0)
        smart += w * r["net"]
    verdict = ("NET_ACCUMULATION" if smart > 0 else "NET_DISTRIBUTION")
    return {"ok": True, "smart_money_net": round(float(smart), 1), "verdict": verdict,
            "brokers": [{"broker": r.get("broker", "?"), "label": r["label"], "net": r["net"],
                         "ng": round(r["ng"], 2), "size_pct": round(r["size_pct"], 2)} for r in rows]}
