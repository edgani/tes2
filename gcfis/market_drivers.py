"""market_drivers.py — researched surge-up / surge-down driver matrix PER MARKET (June 2026).
Each driver: series id (to wire), sign (+1: factor UP → market UP), horizon (ST days–weeks /
MT 1–6mo / LT 6mo+), strength 1–3, and the empirical note. read_all() computes a robust z of the
CHANGE of any series supplied (change-centric, never level) and aggregates a per-market bias.
HONEST: with no data fed, it returns the MAP with reading=None — it never fabricates a reading."""
from __future__ import annotations
import numpy as np, pandas as pd
from .core.change_core import robust_z, last

D = lambda f, s, sg, h, st, n: {"factor": f, "series": s, "sign": sg, "horizon": h, "strength": st, "note": n}

DRIVERS = {
 "us": [
  D("Fed net liquidity Δ (BS−TGA−RRP)", "FEDLIQ", +1, "ST", 3, "weekly liquidity add/drain moves index within days–weeks"),
  D("Dealer gamma regime", "GEX_SPX", +1, "ST", 3, "GEX<0 amplifies moves (momentum), GEX>0 pins (fade extremes)"),
  D("Credit stress (HY OAS)", "HY_OAS", -1, "ST", 3, "spread widening leads equity drawdowns; the risk-off tell"),
  D("Data surprise vs expectation", "SURPRISE_US", +1, "ST", 2, "price reacts to actual−implied, not the absolute print"),
  D("Earnings revision breadth", "EARNREV", +1, "MT", 3, "revisions up = institutions forced to chase; core MT driver"),
  D("Real 10Y yield Δ", "TIPS10Y", -1, "MT", 2, "real-yield spikes compress duration/growth multiples"),
  D("ISM new orders", "ISM_NO", +1, "MT", 2, "leads EPS cycle ~1–2 quarters"),
  D("Global M2 / liquidity cycle", "G4M2", +1, "LT", 2, "multi-quarter valuation tide"),
  D("EPS growth", "EPS", +1, "LT", 3, "the LT anchor; everything else is timing")],
 "crypto": [
  D("Spot-ETF net flows", "ETF_BTC_FLOW", +1, "ST", 3, "most reliable ST driver 2026; 0–2wk lead, ETFs hold ~6%+ of supply"),
  D("Funding / perp leverage", "FUNDING", -1, "ST", 2, "extreme positive funding = crowded longs = flush fuel"),
  D("Stablecoin mcap Δ", "STABLE_MC", +1, "ST", 2, "dry powder entering/leaving the venue"),
  D("DXY Δ", "DXY", -1, "ST", 2, "same-day→1mo transmission; dollar squeeze drains crypto"),
  D("FX-adj G4/USD liquidity", "G4M2", +1, "MT", 3, "best MT state variable, 1–3mo lead; USD-sourced liquidity is what reaches BTC (China M2 blocked)"),
  D("Real yields Δ", "TIPS10Y", -1, "MT", 2, "opportunity-cost channel"),
  D("LTH supply inactivity", "LTH_SUPPLY", +1, "LT", 2, "dormant supply → small demand moves price a lot"),
  D("Adoption / regulation", "ADOPT", +1, "LT", 2, "institutional access widening")],
 "fx": [
  D("2Y rate-differential repricing", "RATE_DIFF_2Y", +1, "ST", 3, "front-end repricing is the day-to-week driver"),
  D("Risk-off (VIX/credit)", "VIX", +1, "ST", 2, "risk-off bids USD vs EM/high-beta"),
  D("Real rate differential", "REAL_DIFF", +1, "MT", 3, "the MT anchor of currency direction"),
  D("BoP / current account", "BOP", +1, "MT", 2, "external funding cushion (IDR: Q1-26 BoP −$9.1bn = the pressure)"),
  D("Terms of trade (CPO/coal/nickel for IDR)", "TOT_ID", +1, "MT", 2, "commodity income props the local ccy"),
  D("PPP valuation gap", "PPP", -1, "LT", 1, "mean-reverts over years, useless for timing"),
  D("Fiscal trajectory", "FISCAL", -1, "LT", 2, "deficits erode the ccy over cycles")],
 "gold": [
  D("Real 10Y TIPS yield Δ", "TIPS10Y", -1, "ST", 3, "THE anchor: ~$40–60/oz per 25bp (Goldman); rate-hike repricing = the May-26 dump"),
  D("DXY Δ", "DXY", -1, "ST", 2, "priced in USD; weak dollar = global purchasing-power tailwind"),
  D("Deleveraging / margin-call tape", "XASSET_DELEV", -1, "ST", 3, "liquidation sells the crowded winner: 'sell what you can'"),
  D("Geopolitical premium (Hormuz)", "GEOPOL", +1, "ST", 2, "haven bid; resolution removes it"),
  D("Gold ETF flows", "ETF_GOLD", +1, "ST", 2, "the marginal financial bid"),
  D("Central-bank buying", "CB_GOLD", +1, "MT", 3, "~1,000t/yr 2022-25 (vs ~200t prior decade); 2026 cooling but EM bid intact"),
  D("Fed path (cuts)", "FED_PATH", +1, "MT", 2, "cuts → real yields down → gold up"),
  D("Fiscal deficits / debasement", "FISCAL", +1, "LT", 2, "6–7% GDP deficits = structural debasement hedge bid"),
  D("De-dollarization / reserve diversification", "DEDOLLAR", +1, "LT", 2, "multi-year reserve shift")],
 "oil": [
  D("Hormuz / geopolitical supply shock", "GEOPOL", +1, "ST", 3, "~20% of global flows; 14+ mb/d shut in 2026 — THE dominant driver now"),
  D("EIA weekly inventories", "EIA_CRUDE_INV", -1, "ST", 3, "draws = bullish; 7 straight US draw weeks, record global draws"),
  D("OPEC+ quota decisions", "OPEC", -1, "ST", 2, "supply adds bearish, cuts bullish; policy now hostage to Hormuz"),
  D("Spare capacity buffer", "SPARE_CAP", -1, "MT", 3, "UAE exit cut buffer 3.8→2.5 mb/d: thinner buffer = higher shock beta"),
  D("Demand growth (China/India/EM)", "OIL_DEMAND", +1, "MT", 2, "~1.4 mb/d 2026 growth pre-shock baseline"),
  D("Term structure (backwardation)", "OIL_TS", +1, "MT", 2, "backwardation = physical tightness"),
  D("Upstream capex cycle", "CAPEX", +1, "LT", 2, "underinvestment = future supply gap")],
 "idx": [
  D("Foreign net flow persistence", "FFLOW_IDX", +1, "ST", 3, "THE swing factor; MSCI passive can move composite 1–2%/day; YTD-26 ~Rp49T net sell"),
  D("USDIDR Δ (rupiah)", "USDIDR", -1, "ST", 3, "rupiah breakdown = foreign sell loop; Rp18,000 = the confidence line"),
  D("BI rate action", "BI_RATE", +1, "ST", 2, "defends IDR AND mechanically lifts the index (banks ≈51% of weight)"),
  D("DXY / Fed path", "DXY", -1, "ST", 2, "dollar squeeze = EM outflow"),
  D("Ratings outlook", "RATING_ID", +1, "MT", 3, "downgrade rumor alone cratered the tape (May-26)"),
  D("BoP / current account", "BOP", +1, "MT", 2, "external cushion; Q1-26 deficit −$9.1bn"),
  D("Commodity terms of trade (CPO/coal/nickel)", "TOT_ID", +1, "MT", 2, "exporter heavyweights gain on weak IDR + firm commodities"),
  D("Reform / policy credibility", "POLICY_ID", +1, "LT", 2, "what brings the foreign bid back structurally"),
  D("Demographics / earnings", "EPS_ID", +1, "LT", 2, "the LT compounding base")],
}
_HW = {"ST": 0.45, "MT": 0.35, "LT": 0.20}

def ticker_driver_market(ticker: str, market: str) -> str:
    t = str(ticker).upper()
    if market == "commodity":
        return "gold" if ("XAU" in t or "GOLD" in t or "GC" in t) else "oil"
    return market if market in DRIVERS else "us"

def read_all(data: dict | None) -> dict:
    """data: {series_id: pd.Series}. Returns per-market driver rows with z-of-CHANGE readings + bias."""
    out = {}
    for mkt, rows in DRIVERS.items():
        readings, num = [], 0.0
        den = 0.0
        for d in rows:
            z = None
            s = (data or {}).get(d["series"])
            if s is not None:
                try:
                    ser = pd.to_numeric(pd.Series(s), errors="coerce").dropna()
                    if len(ser) > 40:
                        z = float(last(robust_z(ser.diff()), 0.0))
                except Exception:
                    z = None
            row = dict(d)
            row["reading_z"] = round(z, 2) if z is not None else None
            if z is not None:
                w = _HW[d["horizon"]] * d["strength"]
                num += w * d["sign"] * z; den += w
            readings.append(row)
        score = round(num / den, 2) if den else None
        if score is None:
            bias = "NO_DATA"
        elif fed_n := sum(1 for r in readings if r["reading_z"] is not None):
            full = fed_n >= 2
            bias = (("LONG" if full else "LEAN_LONG") if score > 0.5 else
                    ("SHORT" if full else "LEAN_SHORT") if score < -0.5 else "NEUTRAL")
        else:
            bias = "NO_DATA"
        out[mkt] = {"drivers": readings, "bias": bias, "score": score,
                    "fed": int(sum(1 for r in readings if r["reading_z"] is not None))}
    return out
