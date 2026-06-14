"""engines/coatue_methodology.py — COATUE Shortage Economy + Decay (Sprint 9)

Replicates COATUE's methodology (not their portfolio):
  1. Sellers vs Buyers of Shortage classification
  2. Shortage Premium Decay Monitor (op margin trajectory)
  3. Capital Rotation Direction (capex spender vs FCF receiver)
  4. Agentic Big Bang Beneficiary (CPU rotation, memory bottleneck)
  5. TAM-vs-Payroll scoring (radical reframe)
  6. Token Volume / ARR Velocity tracking
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

import pandas as pd
import math

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════
# SHORTAGE ECONOMY MATH (from COATUE deck)
# ════════════════════════════════════════════════════════════════════════

SHORTAGE_MATH_TEMPLATE = {
    "pre_shortage": {"revenue": 100, "cogs": 50, "opex": 10, "ebit": 40, "margin": 0.40},
    "double_price": {"revenue": 200, "cogs": 50, "opex": 15, "ebit": 135, "margin": 0.675},
    "quadruple_price": {"revenue": 400, "cogs": 50, "opex": 20, "ebit": 330, "margin": 0.825},
}

# Real margin data from COATUE deck (validation of shortage thesis)
ACTUAL_MARGIN_EXPANSION = {
    "MU": {"op_margin_baseline": 0.16, "op_margin_now": 0.69, "decay_risk": "HIGH",
           "rationale": "Cyclical pricing power without structural moat"},
    "STX": {"op_margin_baseline": 0.17, "op_margin_now": 0.38, "decay_risk": "MEDIUM",
            "rationale": "Storage cycle, less HBM exposure"},
    "WDC": {"op_margin_baseline": 0.10, "op_margin_now": 0.32, "decay_risk": "HIGH"},
    "NVDA": {"op_margin_baseline": 0.40, "op_margin_now": 0.62, "decay_risk": "LOW",
             "rationale": "Software moat via CUDA, durable"},
}


# ════════════════════════════════════════════════════════════════════════
# SELLERS OF SHORTAGE classification
# ════════════════════════════════════════════════════════════════════════

SHORTAGE_SELLERS = {
    # Tier S: Durable structural moat
    "NVDA": {"category": "GPU Software Moat", "moat": "CUDA", "decay_risk": "LOW", "score": 95},
    "AVGO": {"category": "Custom Silicon", "moat": "Hyperscaler partnerships", "decay_risk": "LOW", "score": 90},
    
    # Tier A: Critical bottleneck but cyclical
    "TSM":  {"category": "Foundry", "moat": "Manufacturing monopoly", "decay_risk": "LOW", "score": 92},
    "BE":   {"category": "Fuel Cells", "moat": "On-site power", "decay_risk": "LOW", "score": 88},
    "VST":  {"category": "Power Gen", "moat": "Texas grid + nuclear", "decay_risk": "LOW", "score": 85},
    "CEG":  {"category": "Nuclear", "moat": "Existing reactor fleet", "decay_risk": "LOW", "score": 88},
    
    # Tier B: Cyclical with shortage decay risk
    "MU":   {"category": "Memory Cyclical", "moat": "Cyclical pricing", "decay_risk": "HIGH", "score": 70},
    "STX":  {"category": "Storage", "moat": "None durable", "decay_risk": "HIGH", "score": 65},
    "SNDK": {"category": "NAND", "moat": "None durable", "decay_risk": "HIGH", "score": 60},
    "LITE": {"category": "Optical", "moat": "Photonic capacity", "decay_risk": "MEDIUM", "score": 78},
    "COHR": {"category": "Photonic", "moat": "Capacity constraint", "decay_risk": "MEDIUM", "score": 75},
    "MRVL": {"category": "Optical DSP", "moat": "Datacenter networking", "decay_risk": "MEDIUM", "score": 72},
    "GEV":  {"category": "Grid Equipment", "moat": "Power gen", "decay_risk": "LOW", "score": 82},
}


# ════════════════════════════════════════════════════════════════════════
# BUYERS OF SHORTAGE (mispriced in opposite direction)
# ════════════════════════════════════════════════════════════════════════

SHORTAGE_BUYERS = {
    "GOOGL": {"score": 90, "rationale": "TPU + Gemini + Cloud 63% YoY + Waymo physical AI. Cleanest buyer."},
    "AMZN":  {"score": 87, "rationale": "AWS fastest growth 15Q + Trainium + agentic commerce"},
    "MSFT":  {"score": 70, "rationale": "Largest AI rev but OpenAI partnership divergence risk"},
    "META":  {"score": 55, "rationale": "Defensive capex protecting ad business — no enterprise AI monetization"},
    "ORCL":  {"score": 60, "rationale": "Sub-scale OCI, dependent on Nvidia/OpenAI hosting"},
}


# ════════════════════════════════════════════════════════════════════════
# AGENTIC BIG BANG BENEFICIARIES
# ════════════════════════════════════════════════════════════════════════

AGENTIC_ROTATION_PLAYS = {
    "AMD":  {"thesis": "CPU rotation cleanest pure-play — server share 50%+, taking from Intel", "score": 90},
    "MU":   {"thesis": "Agentic context windows = RAM-intensive HBM demand", "score": 80},
    "000660.KS": {"thesis": "SK Hynix HBM3E lead", "score": 82},
    "ANET": {"thesis": "Networking for agentic clusters", "score": 75},
}


# ════════════════════════════════════════════════════════════════════════
# TAM AGAINST PAYROLL (COATUE radical reframe)
# ════════════════════════════════════════════════════════════════════════

TAM_PAYROLL_DATA = {
    "Consumer_AI": {"tam_t": 0.3, "note": "Paid + ad-supported"},
    "Developer_Coding": {"tam_t": 2.0, "note": "40% of $5T global engineering payroll"},
    "Non_Developer_White_Collar": {"tam_t": 2.0, "note": "50% of $4T SG&A payroll"},
    "Digital_AI_Total": {"tam_t": 4.0, "note": "Sum of above"},
    "Physical_AI": {"tam_t": 6.0, "note": "Humanoids + AV + industrial automation"},
}


# ════════════════════════════════════════════════════════════════════════
# TOKEN VOLUME / ARR TRAJECTORY (proof of demand)
# ════════════════════════════════════════════════════════════════════════

TOKEN_VOLUME_TRAJECTORY = {
    "Q4_2024": {"tokens_t": 0.5, "label": "Baseline"},
    "Q4_2025": {"tokens_t": 16.4, "label": "Inflection — 12x YoY"},
    "April_2026": {"tokens_t": 35, "label": "Hyper-exponential — agentic adoption"},
    "growth_pa": 12,  # 12x per year, faster than Moore's Law
}

ARR_TRAJECTORY = {
    "Oct_2023": {"arr_bn": 2, "comparison": "Baseline"},
    "Early_2024": {"arr_bn": 3.4, "comparison": "Datadog scale"},
    "Jan_2025": {"arr_bn": 8.4, "comparison": "Workday scale"},
    "Mid_2025": {"arr_bn": 13.3, "comparison": "ServiceNow scale"},
    "Late_2025": {"arr_bn": 23.8, "comparison": "Adobe scale"},
    "Early_2026": {"arr_bn": 37.9, "comparison": "Salesforce scale (took SF 25 years)"},
    "April_2026": {"arr_bn": 55, "comparison": "Past every public software incumbent"},
}


# ════════════════════════════════════════════════════════════════════════
# FUNDING SUSTAINABILITY MATH ($12T)
# ════════════════════════════════════════════════════════════════════════

FUNDING_MATH_2026_2031 = {
    "hyperscaler_ebitda_t": 6.0,
    "leverage_capacity_t": 4.0,
    "other_t": 2.0,
    "total_dry_powder_t": 12.0,
    "annual_capex_2027_estimate_t": 1.0,
    "years_runway": 6,
    "thesis": "$12T vs $1T/yr = 6 years sustainable. Not bubble — structural reallocation.",
}


# ════════════════════════════════════════════════════════════════════════
# SHORTAGE DECAY MONITOR (uses price action proxy)
# ════════════════════════════════════════════════════════════════════════

def detect_shortage_decay(ticker: str, prices_series) -> Optional[Dict]:
    """
    Detect signs that shortage premium is decaying.
    Proxy: deceleration of 6-month momentum vs 1-year momentum.
    """
    if prices_series is None or ticker not in SHORTAGE_SELLERS:
        return None
    try:
        s = pd.to_numeric(prices_series, errors="coerce").dropna()
        if len(s) < 252:
            return None
        current = float(s.iloc[-1])
        m_6m = float(s.iloc[-1] / s.iloc[-126] - 1) if len(s) > 126 else 0
        m_12m = float(s.iloc[-1] / s.iloc[-252] - 1) if len(s) > 252 else 0
        # If 6M < 12M annualized, momentum decelerating
        m_12m_annualized = m_12m  # already annualized
        m_6m_annualized = (1 + m_6m) ** 2 - 1 if m_6m > -0.5 else m_6m * 2
        deceleration = m_6m_annualized - m_12m_annualized
        
        coatue_data = SHORTAGE_SELLERS.get(ticker, {})
        baseline_risk = coatue_data.get("decay_risk", "LOW")
        
        # Decay alert if: high decay risk ticker + decelerating momentum
        decay_alert = False
        alert_level = "NONE"
        if baseline_risk == "HIGH" and deceleration < -0.10:
            decay_alert = True
            alert_level = "ACTIVE"
        elif baseline_risk == "MEDIUM" and deceleration < -0.20:
            decay_alert = True
            alert_level = "WARNING"
        
        return {
            "decay_risk_baseline": baseline_risk,
            "momentum_12m_pct": round(m_12m * 100, 1),
            "momentum_6m_annualized_pct": round(m_6m_annualized * 100, 1),
            "deceleration_pct": round(deceleration * 100, 2),
            "decay_alert": decay_alert,
            "alert_level": alert_level,
            "moat": coatue_data.get("moat", "—"),
        }
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════════════
# CAPITAL ROTATION SPREAD MONITOR
# ════════════════════════════════════════════════════════════════════════

def compute_capital_rotation_spread(prices: Dict) -> Dict:
    """
    Compute spread: Sellers avg 3M return vs Buyers avg 3M return.
    COATUE Apr 2026 saw ~100pp spread (sellers +107%, buyers +4%).
    """
    out = {
        "ok": True, "sellers_avg_3m_pct": None, "buyers_avg_3m_pct": None,
        "spread_3m_pp": None, "interpretation": None,
    }
    
    def get_3m_return(ticker):
        s = prices.get(ticker)
        if s is None:
            return None
        try:
            ser = pd.to_numeric(s, errors="coerce").dropna()
            if len(ser) <= 63:
                return None
            return float(ser.iloc[-1] / ser.iloc[-63] - 1)
        except Exception:
            return None
    
    seller_returns = [get_3m_return(t) for t in SHORTAGE_SELLERS]
    buyer_returns = [get_3m_return(t) for t in SHORTAGE_BUYERS]
    seller_returns = [r for r in seller_returns if r is not None]
    buyer_returns = [r for r in buyer_returns if r is not None]
    
    if seller_returns:
        out["sellers_avg_3m_pct"] = round(sum(seller_returns) / len(seller_returns) * 100, 2)
    if buyer_returns:
        out["buyers_avg_3m_pct"] = round(sum(buyer_returns) / len(buyer_returns) * 100, 2)
    
    if out["sellers_avg_3m_pct"] is not None and out["buyers_avg_3m_pct"] is not None:
        spread = out["sellers_avg_3m_pct"] - out["buyers_avg_3m_pct"]
        out["spread_3m_pp"] = round(spread, 2)
        if spread > 30:
            out["interpretation"] = "🟢 STRONG ROTATION — sellers dominate. COATUE thesis validated."
        elif spread > 10:
            out["interpretation"] = "🟡 ROTATION IN PROGRESS"
        elif spread < -10:
            out["interpretation"] = "🔴 BUYERS LEADING — rotation thesis breaking, watch capex cuts"
        else:
            out["interpretation"] = "⚪ NEUTRAL — sectors moving together"
    
    return out


# ════════════════════════════════════════════════════════════════════════
# MASTER COATUE EVALUATION
# ════════════════════════════════════════════════════════════════════════

def evaluate_coatue_methodology(ticker: str, prices_series=None) -> Dict:
    """Run COATUE methodology checklist on single ticker."""
    out = {
        "ticker": ticker,
        "matched": False,
        "coatue_score": 0,
        "role": None,
        "moat": None,
        "decay_status": None,
        "agentic_play": None,
        "rationale": [],
    }
    
    t = ticker.upper()
    
    # 1. Sellers of Shortage
    if t in SHORTAGE_SELLERS:
        d = SHORTAGE_SELLERS[t]
        out["matched"] = True
        out["coatue_score"] = d["score"]
        out["role"] = f"Seller of Shortage — {d['category']}"
        out["moat"] = d["moat"]
        out["rationale"].append(f"COATUE seller of shortage. Moat: {d['moat']}. Decay risk: {d['decay_risk']}.")
        
        # Shortage decay check
        decay = detect_shortage_decay(t, prices_series)
        if decay:
            out["decay_status"] = decay
            if decay["decay_alert"]:
                out["rationale"].append(
                    f"⚠️ SHORTAGE DECAY {decay['alert_level']}: momentum decelerating {decay['deceleration_pct']:+.0f}%pp"
                )
                # Reduce score if decay active
                if decay["alert_level"] == "ACTIVE":
                    out["coatue_score"] *= 0.7
    
    # 2. Buyers of Shortage
    elif t in SHORTAGE_BUYERS:
        d = SHORTAGE_BUYERS[t]
        out["matched"] = True
        out["coatue_score"] = d["score"]
        out["role"] = "Buyer of Shortage"
        out["rationale"].append(d["rationale"])
    
    # 3. Agentic Big Bang play
    if t in AGENTIC_ROTATION_PLAYS:
        d = AGENTIC_ROTATION_PLAYS[t]
        out["agentic_play"] = d
        out["matched"] = True
        out["coatue_score"] = max(out["coatue_score"], d["score"])
        out["rationale"].append(f"Agentic Big Bang: {d['thesis']}")
    
    out["coatue_score"] = round(out["coatue_score"], 1)
    return out


def run_coatue_scan(tickers: List[str], prices: Dict) -> Dict:
    """Batch COATUE methodology evaluation."""
    out = {
        "ok": True,
        "shortage_economy_math": SHORTAGE_MATH_TEMPLATE,
        "tam_payroll": TAM_PAYROLL_DATA,
        "token_volume": TOKEN_VOLUME_TRAJECTORY,
        "arr_trajectory": ARR_TRAJECTORY,
        "funding_math": FUNDING_MATH_2026_2031,
        "capital_rotation_spread": compute_capital_rotation_spread(prices),
        "per_ticker": {},
        "decay_alerts": [],
        "agentic_plays": [],
        "sellers_top": [],
        "buyers_top": [],
    }
    
    for t in tickers:
        result = evaluate_coatue_methodology(t, prices.get(t))
        if result["matched"]:
            out["per_ticker"][t] = result
            if (result.get("decay_status") or {}).get("decay_alert"):
                out["decay_alerts"].append({
                    "ticker": t, "alert": result["decay_status"]["alert_level"],
                    "deceleration": result["decay_status"]["deceleration_pct"],
                })
            if result.get("agentic_play"):
                out["agentic_plays"].append({
                    "ticker": t, "thesis": result["agentic_play"]["thesis"],
                    "score": result["coatue_score"],
                })
            if "Seller" in (result.get("role") or ""):
                out["sellers_top"].append({"ticker": t, "score": result["coatue_score"], "role": result["role"]})
            elif "Buyer" in (result.get("role") or ""):
                out["buyers_top"].append({"ticker": t, "score": result["coatue_score"], "role": result["role"]})
    
    out["sellers_top"].sort(key=lambda x: x["score"], reverse=True)
    out["buyers_top"].sort(key=lambda x: x["score"], reverse=True)
    return out
