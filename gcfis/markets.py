"""markets.py — per-market structure registry (GCFIS doc 5: each market has different participants,
constraints, and forced-flow drivers; the SAME filter must NOT be applied to all). Drives long-only
enforcement, market-specific bottleneck priorities, and the dominant flow drivers to weight."""
from __future__ import annotations

MARKETS = {
    "idx":       {"long_only": True,  "label": "IHSG/IDX",
                  "drivers": ["foreign_flow", "broker_accumulation", "float", "absorption"],
                  "bottlenecks": ["float", "foreign_flow", "broker_cartel", "liquidity_vacuum"]},
    "us":        {"long_only": False, "label": "US equity",
                  "drivers": ["earnings_revision", "institutional_positioning", "dealer_gamma", "passive_flow"],
                  "bottlenecks": ["passive_flow", "dealer_gamma", "earnings_revision", "liquidity_concentration"]},
    "crypto":    {"long_only": False, "label": "crypto",
                  "drivers": ["leverage", "supply_inactivity", "whale_flow", "liquidation_clusters"],
                  "bottlenecks": ["liquidity_thinness", "forced_liquidation", "perp_leverage", "supply_inactivity"]},
    "fx":        {"long_only": False, "label": "FX",
                  "drivers": ["rate_differential", "dollar_liquidity", "positioning"],
                  "bottlenecks": ["carry_unwind", "cb_defense", "dollar_squeeze", "funding_stress"]},
    "commodity": {"long_only": False, "label": "commodity",
                  "drivers": ["inventory", "physical_tightness", "producer_hedging", "cta_positioning"],
                  "bottlenecks": ["physical_supply", "logistics", "producer_hedging", "geopolitical"]},
}
_CRYPTO = {"BTCUSD", "ETHUSD", "BTC-USD", "ETH-USD", "SOLUSD", "BTC", "ETH", "BNBUSD", "XRPUSD"}
_FX6 = {"EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD", "EURJPY", "GBPJPY", "EURGBP", "USDIDR", "DXY"}
_COMMOD = {"GC=F", "SI=F", "CL=F", "BZ=F", "NG=F", "HG=F", "XAUUSD", "XAGUSD", "WTI", "BRENT", "XAU", "XAG", "USOIL", "COPPER"}

def market_of(ticker, hint=None) -> str:
    if hint and hint in MARKETS:
        return hint
    t = str(ticker or "").upper()
    if t.endswith(".JK"):
        return "idx"
    if t in _COMMOD or t.startswith(("XAU", "XAG")):
        return "commodity"
    if t in _FX6 or t.endswith("=X"):
        return "fx"
    if t in _CRYPTO or "USDT" in t or "USDC" in t or "-PERP" in t:
        return "crypto"
    return "us"

def market_info(ticker, hint=None) -> dict:
    return MARKETS[market_of(ticker, hint)]

def is_long_only(ticker, hint=None) -> bool:
    return MARKETS[market_of(ticker, hint)]["long_only"]
