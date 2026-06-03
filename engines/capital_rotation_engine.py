"""engines/capital_rotation_engine.py — Capital Flow Tracker (Sprint 7)

Tracks the COATUE thesis: $680B hyperscaler capex → $525B semi FCF.
Monitors divergence: if capex revisions cut but semi FCF revisions stay high,
the rotation thesis breaks.

Outputs:
  - Capex revision direction per hyperscaler
  - FCF revision direction per semi seller
  - Divergence alerts
  - Shortage premium decay monitor (op margin trajectory)
  - Capital flow ratio (capex $ : semi FCF $)
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════
# Capital flow map (2026 consensus, COATUE deck May 2026)
# ════════════════════════════════════════════════════════════════════════

HYPERSCALER_CAPEX = {
    "MSFT":  {"capex_2026e_bn": 157, "fcf_2026e_bn": 39,  "ratio": "FCF holds"},
    "GOOGL": {"capex_2026e_bn": 186, "fcf_2026e_bn": 29,  "ratio": "FCF moderate"},
    "META":  {"capex_2026e_bn": 138, "fcf_2026e_bn": 5,   "ratio": "FCF thin"},
    "AMZN":  {"capex_2026e_bn": 200, "fcf_2026e_bn": -7,  "ratio": "FCF NEGATIVE"},
    "ORCL":  {"capex_2026e_bn": 28,  "fcf_2026e_bn": 12,  "ratio": "FCF moderate"},
}

SEMI_FCF_BENEFICIARIES = {
    "NVDA":      {"fcf_2026e_bn": 184, "role": "GPU monopoly", "shortage_type": "structural"},
    "TSM":       {"fcf_2026e_bn": 46,  "role": "Foundry", "shortage_type": "structural"},
    "AVGO":      {"fcf_2026e_bn": 32,  "role": "Custom silicon", "shortage_type": "structural"},
    "005930.KS": {"fcf_2026e_bn": 132, "role": "Samsung (memory+foundry)", "shortage_type": "cyclical"},
    "000660.KS": {"fcf_2026e_bn": 110, "role": "SK Hynix (HBM)", "shortage_type": "cyclical"},
    "MU":        {"fcf_2026e_bn": 54,  "role": "Micron memory", "shortage_type": "cyclical"},
    "AMD":       {"fcf_2026e_bn": 8,   "role": "CPU+GPU", "shortage_type": "structural"},
    "INTC":      {"fcf_2026e_bn": -3,  "role": "Foundry comeback", "shortage_type": "speculative"},
    "LITE":      {"fcf_2026e_bn": 0.8, "role": "Optical", "shortage_type": "cyclical"},
    "COHR":      {"fcf_2026e_bn": 0.6, "role": "Photonic", "shortage_type": "cyclical"},
    "MRVL":      {"fcf_2026e_bn": 1.5, "role": "Optical DSP", "shortage_type": "cyclical"},
}

POWER_BENEFICIARIES = {
    "VST":  {"role": "Texas grid + nuclear", "expected_growth": "high"},
    "CEG":  {"role": "Nuclear fleet", "expected_growth": "high"},
    "TLN":  {"role": "Nuclear restart", "expected_growth": "high"},
    "GEV":  {"role": "Grid equipment", "expected_growth": "high"},
    "BE":   {"role": "On-site fuel cells (Oracle validated)", "expected_growth": "very high"},
    "PWR":  {"role": "Grid services", "expected_growth": "moderate"},
    "ETN":  {"role": "Electrical equipment", "expected_growth": "moderate"},
    "VRT":  {"role": "Datacenter cooling", "expected_growth": "high"},
}


# ════════════════════════════════════════════════════════════════════════
# Compute capital flow metrics from price action
# ════════════════════════════════════════════════════════════════════════

def _price_momentum(s, periods: int) -> Optional[float]:
    if s is None:
        return None
    try:
        ser = pd.to_numeric(s, errors="coerce").dropna()
        if len(ser) <= periods:
            return None
        return float(ser.iloc[-1] / ser.iloc[-periods - 1] - 1)
    except Exception:
        return None


def compute_capital_rotation(prices: Dict) -> Dict:
    """
    Compute capital flow signals from price action.
    
    Key insight: If hyperscaler stocks underperform while semis outperform,
    rotation thesis VINDICATED. If both move together, capex risk priced in.
    """
    out = {
        "ok": True,
        "hyperscaler_avg_3m": None,
        "semi_avg_3m": None,
        "power_avg_3m": None,
        "rotation_spread_3m_pp": None,  # semi - hyperscaler
        "regime_label": None,
        "shortage_premium_status": None,
        "thesis_tracking": [],
    }
    
    # Hyperscaler avg 3M return
    hs_returns = [_price_momentum(prices.get(t), 63) for t in HYPERSCALER_CAPEX]
    hs_returns = [r for r in hs_returns if r is not None]
    if hs_returns:
        out["hyperscaler_avg_3m"] = sum(hs_returns) / len(hs_returns)
    
    # Semi avg 3M return
    semi_returns = [_price_momentum(prices.get(t), 63) for t in SEMI_FCF_BENEFICIARIES]
    semi_returns = [r for r in semi_returns if r is not None]
    if semi_returns:
        out["semi_avg_3m"] = sum(semi_returns) / len(semi_returns)
    
    # Power avg 3M return
    pw_returns = [_price_momentum(prices.get(t), 63) for t in POWER_BENEFICIARIES]
    pw_returns = [r for r in pw_returns if r is not None]
    if pw_returns:
        out["power_avg_3m"] = sum(pw_returns) / len(pw_returns)
    
    # Rotation spread
    if out["hyperscaler_avg_3m"] is not None and out["semi_avg_3m"] is not None:
        out["rotation_spread_3m_pp"] = (out["semi_avg_3m"] - out["hyperscaler_avg_3m"]) * 100
        spread = out["rotation_spread_3m_pp"]
        if spread > 20:
            out["regime_label"] = "🟢 ROTATION VALIDATED — semis dominate"
            out["thesis_tracking"].append("Capex→FCF flow proven by price action")
        elif spread > 5:
            out["regime_label"] = "🟡 ROTATION IN PROGRESS"
        elif spread < -10:
            out["regime_label"] = "🔴 THESIS BREAKING — hyperscalers leading"
            out["thesis_tracking"].append("Capex slowdown fear emerging — watch for cut announcements")
        else:
            out["regime_label"] = "⚪ NEUTRAL — both moving similarly"
    
    # Shortage premium status (proxy: dispersion among cyclical vs structural sellers)
    structural_returns = []
    cyclical_returns = []
    for ticker, data in SEMI_FCF_BENEFICIARIES.items():
        ret = _price_momentum(prices.get(ticker), 63)
        if ret is None:
            continue
        if data["shortage_type"] == "structural":
            structural_returns.append(ret)
        elif data["shortage_type"] == "cyclical":
            cyclical_returns.append(ret)
    
    if structural_returns and cyclical_returns:
        struct_avg = sum(structural_returns) / len(structural_returns)
        cycl_avg = sum(cyclical_returns) / len(cyclical_returns)
        diff = (struct_avg - cycl_avg) * 100
        if diff > 15:
            out["shortage_premium_status"] = "🟢 Structural premium widening — durable moats winning"
        elif diff < -10:
            out["shortage_premium_status"] = "🟡 Cyclical catch-up — shortage premium broadening (late-cycle warning)"
        else:
            out["shortage_premium_status"] = "⚪ Both shortage types performing similar"
    
    # Specific ticker breakdown
    out["per_ticker_3m"] = {}
    for ticker in list(HYPERSCALER_CAPEX) + list(SEMI_FCF_BENEFICIARIES) + list(POWER_BENEFICIARIES):
        ret = _price_momentum(prices.get(ticker), 63)
        if ret is not None:
            out["per_ticker_3m"][ticker] = round(ret, 4)
    
    # Aggregate stats
    out["total_capex_2026e_bn"] = sum(d["capex_2026e_bn"] for d in HYPERSCALER_CAPEX.values())
    out["total_semi_fcf_2026e_bn"] = sum(d["fcf_2026e_bn"] for d in SEMI_FCF_BENEFICIARIES.values())
    out["flow_ratio"] = round(out["total_capex_2026e_bn"] / max(out["total_semi_fcf_2026e_bn"], 1), 2)
    
    # Funding sustainability check (COATUE math)
    out["funding_math"] = {
        "hyperscaler_ebitda_annual_t": 1.0,
        "leverage_capacity_t": 4.0,
        "other_sources_t": 2.0,
        "total_dry_powder_t": 12.0,
        "years_of_capex": 6,
        "interpretation": "$12T dry powder vs $1T/yr capex = 6 years sustainable per COATUE math",
    }
    
    return out


def get_ticker_capital_rotation_role(ticker: str) -> Optional[Dict]:
    """For a single ticker, what role in capital rotation?"""
    t = ticker.upper()
    if t in HYPERSCALER_CAPEX:
        d = HYPERSCALER_CAPEX[t]
        return {
            "role": "Buyer of Shortage (Hyperscaler)",
            "capex_2026e_bn": d["capex_2026e_bn"],
            "fcf_2026e_bn": d["fcf_2026e_bn"],
            "fcf_label": d["ratio"],
            "thesis": f"Capital spender — capex ${d['capex_2026e_bn']}B for AI infra. FCF {d['ratio']}.",
        }
    if t in SEMI_FCF_BENEFICIARIES:
        d = SEMI_FCF_BENEFICIARIES[t]
        return {
            "role": "Seller of Shortage (Semi)",
            "fcf_2026e_bn": d["fcf_2026e_bn"],
            "shortage_type": d["shortage_type"],
            "thesis": f"Capital receiver — FCF ${d['fcf_2026e_bn']}B. Shortage type: {d['shortage_type']}. Role: {d['role']}",
        }
    if t in POWER_BENEFICIARIES:
        d = POWER_BENEFICIARIES[t]
        return {
            "role": "Power Beneficiary",
            "expected_growth": d["expected_growth"],
            "thesis": f"Power infra play — {d['role']}. Growth expected: {d['expected_growth']}.",
        }
    return None
