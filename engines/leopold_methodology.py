"""engines/leopold_methodology.py — Leopold's Thought Process (Sprint 9)

Replicates Leopold's 5-step framework + 4 Bet Layers methodology, NOT his portfolio.

5-Step Framework:
  1. Build Worldview (macro thesis first)
  2. Identify Physical Constraints (Count OOMs)
  3. Go Upstream (skip apps, find what feeds NVDA)
  4. Find Mispriced/Written-Off names
  5. Express with Asymmetry (options for binary outcomes)

4 Core Bet Layers:
  Layer 1: Power (electrons) - grid bottleneck
  Layer 2: Stranded Power Assets (BTC miners with pre-connected power)
  Layer 3: Silicon (written-off names)
  Layer 4: Photons & Memory (datacenter networking + storage)

Methodology output per ticker:
  - bottleneck_layer (1-4 or None)
  - upstream_distance (0=AI app, 1=NVDA/cloud, 2=power/silicon, 3=raw materials)
  - written_off_score (high short interest + improving fundamentals)
  - asymmetry_setup (whether options recommended over equity)
  - oom_relevance (does this benefit from compute scaling?)
"""
from __future__ import annotations

import math
import logging
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════
# OOM TRACKER (Leopold's quantitative driver)
# ════════════════════════════════════════════════════════════════════════

OOM_DRIVERS = {
    "raw_compute": {
        "rate_per_year_ooms": 0.5,
        "description": "Physical GPU capacity doubling rate",
        "binding_constraint": "Power generation + grid connection",
        "ticker_beneficiaries": ["NVDA", "TSM", "AVGO"],
    },
    "algorithmic_efficiency": {
        "rate_per_year_ooms": 0.5,
        "description": "Model efficiency gains per unit of compute",
        "binding_constraint": "Cumulatively pushes inference scaling, not less demand",
        "ticker_beneficiaries": [],  # not a single-ticker bet
    },
    "unhobbling": {
        "rate_per_year_ooms": 0.3,
        "description": "Chatbot → agent → drop-in worker capability gains (quantified as step-change equivalent)",
        "binding_constraint": "Inference compute explosion (CPU-heavy for agentic)",
        "ticker_beneficiaries": ["AMD", "MU", "000660.KS"],  # CPU + memory
    },
}


def compute_oom_trajectory() -> Dict:
    """Aggregate OOM rate of change.

    Leopold's essay: "training compute on track to grow ~10x per year" = 1 OOM/year.
    Components: 0.5 (raw compute) + 0.5 (algo efficiency) + 0.3 (unhobbling step-change) = 1.3 OOMs/year
    The unhobbling 0.3 is a conservative quantification of the step-change capability gains
    (chatbot → agent → drop-in worker) that drive inference compute explosion.
    """
    total_ooms_per_year = sum(
        v["rate_per_year_ooms"] for v in OOM_DRIVERS.values()
        if isinstance(v["rate_per_year_ooms"], (int, float))
    )
    return {
        "annual_ooms": round(total_ooms_per_year, 2),
        "annual_multiplier": 10 ** total_ooms_per_year,  # ~20x/year with unhobbling
        "4yr_cumulative_ooms": round(total_ooms_per_year * 4, 2),
        "4yr_cumulative_multiplier": 10 ** (total_ooms_per_year * 4),  # ~160,000x in 4 years
        "drivers": OOM_DRIVERS,
        "thesis": "Compute scaling FORCES physical bottlenecks. 1.3 OOMs/year = ~20x annual growth. Software/algo can't substitute.",
    }


# ════════════════════════════════════════════════════════════════════════
# BOTTLENECK LAYER CLASSIFIER (4 layers)
# ════════════════════════════════════════════════════════════════════════

BOTTLENECK_LAYERS = {
    "Layer1_Power": {
        "description": "Electricity generation, grid, on-site power",
        "characteristics": [
            "Generates or transmits electricity",
            "Has grid bypass capability",
            "Long capacity buildout (5+ years)",
        ],
        "tickers": {
            "BE": {"role": "On-site fuel cells (Oracle validated)", "score": 95},
            "VST": {"role": "Texas grid + gas baseload", "score": 90},
            "CEG": {"role": "Existing nuclear fleet", "score": 92},
            "TLN": {"role": "Nuclear restart story", "score": 85},
            "GEV": {"role": "Grid + turbine equipment", "score": 88},
            "PWR": {"role": "Grid construction services", "score": 78},
            "ETN": {"role": "Electrical equipment", "score": 75},
            "VRT": {"role": "Datacenter power + cooling", "score": 82},
        },
        "entry_logic": "Grid-bypass story + datacenter offtake validation",
    },
    "Layer2_StrandedPower": {
        "description": "BTC miners with pre-connected power infrastructure pivoting to AI",
        "characteristics": [
            "BTC mining operation with active power connections",
            "Land/permits already secured",
            "AI hosting deals announced or in progress",
        ],
        "tickers": {
            "CORZ": {"role": "Core Scientific — 12-yr CoreWeave HPC contracts", "score": 95},
            "IREN": {"role": "Iren AI hosting hybrid", "score": 88},
            "APLD": {"role": "Applied Digital AI pivot", "score": 85},
            "CIFR": {"role": "Cipher Mining power-first", "score": 80},
            "RIOT": {"role": "Riot Platforms stranded power", "score": 75},
            "MARA": {"role": "MARA Exaion stake", "score": 78},
            "BTDR": {"role": "Bitdeer pivot", "score": 73},
        },
        "entry_logic": "Already have power infra, AI hosting can't replicate cost+timeline",
    },
    "Layer3_WrittenOffSilicon": {
        "description": "Silicon names Wall Street tulis off but supply chain-critical",
        "characteristics": [
            "Down 30%+ from peak with sell-side capitulation",
            "Government strategic interest (national security)",
            "Specialty foundry / custom silicon role",
        ],
        "tickers": {
            "INTC": {"role": "US gov-backed fab turnaround", "score": 90, "asymmetry": "calls only"},
            "TSEM": {"role": "Tower analog/specialty foundry", "score": 80},
            "AVGO": {"role": "Custom silicon for hyperscaler ASICs", "score": 88},
            "GFS": {"role": "GlobalFoundries specialty nodes", "score": 75},
        },
        "entry_logic": "Contrarian. Beli saat analyst rating 'sell'. Options untuk binary outcome.",
    },
    "Layer4_PhotonsMemory": {
        "description": "Optical networking + storage (datacenter-scale AI bottlenecks)",
        "characteristics": [
            "Photonics/optics for AI datacenter networking (copper insufficient)",
            "HBM memory for AI training",
            "NAND storage for AI inference data",
        ],
        "tickers": {
            "LITE": {"role": "Lumentum — Nvidia $2B optics investment", "score": 92},
            "COHR": {"role": "Coherent — hyperscale photonics", "score": 88},
            "MRVL": {"role": "Marvell — optical DSP", "score": 82},
            "MU": {"role": "Micron HBM3 demand", "score": 85},
            "STX": {"role": "Seagate mass storage for training", "score": 75},
            "SNDK": {"role": "SanDisk NAND for inference", "score": 78},
            "WDC": {"role": "WDC hyperscaler HDD/SSD", "score": 72},
        },
        "entry_logic": "Datacenter buildout DEMANDS optics + memory. Compounder type holdings.",
    },
}


def classify_bottleneck_layer(ticker: str) -> Optional[Dict]:
    """Determine which Leopold bottleneck layer ticker belongs to."""
    t = ticker.upper()
    for layer_name, layer_data in BOTTLENECK_LAYERS.items():
        if t in layer_data["tickers"]:
            ticker_info = layer_data["tickers"][t]
            return {
                "layer": layer_name,
                "layer_description": layer_data["description"],
                "role": ticker_info["role"],
                "score": ticker_info["score"],
                "entry_logic": layer_data["entry_logic"],
                "asymmetry_recommended": "calls only" in ticker_info.get("asymmetry", ""),
            }
    return None


# ════════════════════════════════════════════════════════════════════════
# UPSTREAM MAPPER (Step 3: skip the obvious)
# ════════════════════════════════════════════════════════════════════════

UPSTREAM_CHAIN = {
    # Distance 0: Direct AI consumer / app
    0: {"label": "AI App/Model", "examples": ["MSFT", "GOOGL", "META", "AMZN", "ORCL"]},
    # Distance 1: AI compute provider
    1: {"label": "AI Compute Cloud", "examples": ["NVDA", "CRWV", "ORCL"]},
    # Distance 2: Silicon + Power supplier
    2: {"label": "Silicon + Power Supplier", "examples": ["TSM", "AVGO", "AMD", "INTC", "BE", "VST", "CEG"]},
    # Distance 3: Photons + Memory + Stranded Assets
    3: {"label": "Photons/Memory/Stranded", "examples": ["LITE", "COHR", "MU", "CORZ", "IREN"]},
    # Distance 4: Raw materials + Equipment
    4: {"label": "Raw Materials/Equipment", "examples": ["AMAT", "LRCX", "KLAC", "ASML", "URA", "CCJ"]},
}


def map_upstream_distance(ticker: str) -> Optional[Dict]:
    """How far upstream from end AI consumer?"""
    t = ticker.upper()
    for dist, data in UPSTREAM_CHAIN.items():
        if t in data["examples"]:
            return {
                "distance": dist,
                "label": data["label"],
                "leopold_preferred": dist >= 2,  # Skip 0-1, prefer 2+
                "rationale": (
                    f"Distance {dist}: {data['label']}. " +
                    ("✓ Leopold preferred (upstream from priced-in trade)" if dist >= 2 else
                     "❌ Too obvious — already priced in")
                ),
            }
    return None


# ════════════════════════════════════════════════════════════════════════
# WRITTEN-OFF DETECTOR (Step 4)
# Use price action proxy: -30% from 52w high + high short interest + recent base
# ════════════════════════════════════════════════════════════════════════

def detect_written_off(ticker: str, prices_series) -> Optional[Dict]:
    """Detect Leopold 'written-off' setup: oversold + basing + contrarian opportunity."""
    if prices_series is None:
        return None
    try:
        s = pd.to_numeric(prices_series, errors="coerce").dropna()
        if len(s) < 252:
            return None
        peak_52w = float(s.tail(252).max())
        current = float(s.iloc[-1])
        drawdown_pct = (current / peak_52w - 1) * 100
        
        # Base detection: last 60d range
        recent_60 = s.tail(60)
        range_60 = float(recent_60.max() - recent_60.min())
        avg_60 = float(recent_60.mean())
        range_pct = range_60 / avg_60 * 100 if avg_60 > 0 else 100
        
        # Momentum: 21d return
        if len(s) >= 22:
            mom_21d = float(s.iloc[-1] / s.iloc[-22] - 1)
        else:
            mom_21d = 0
        
        is_written_off = drawdown_pct <= -25
        is_basing = range_pct < 15  # tight range = base
        is_recovering = mom_21d > 0.05  # +5%/21d = uptick from base
        
        score = 0
        if is_written_off:
            score += 40
        if is_basing:
            score += 30
        if is_recovering and is_written_off:
            score += 30
        
        return {
            "is_written_off": is_written_off,
            "is_basing": is_basing,
            "is_recovering_off_base": is_recovering and is_written_off,
            "drawdown_from_52w_high_pct": round(drawdown_pct, 1),
            "range_60d_pct": round(range_pct, 1),
            "momentum_21d_pct": round(mom_21d * 100, 2),
            "written_off_score": score,
            "asymmetry_recommended": is_written_off and is_recovering,  # binary outcome → options
        }
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════════════
# MASTER LEOPOLD METHODOLOGY EVALUATION
# ════════════════════════════════════════════════════════════════════════

def evaluate_leopold_methodology(ticker: str, prices_series=None) -> Dict:
    """
    Run all 5 Leopold steps for a single ticker.
    """
    out = {
        "ticker": ticker,
        "matched": False,
        "leopold_score": 0,
        "bottleneck_layer": None,
        "upstream_distance": None,
        "written_off": None,
        "asymmetry_setup": None,
        "rationale": [],
        "rules_passed": [],
    }
    
    # Step 2-3: Bottleneck Layer (rule-based classification)
    layer = classify_bottleneck_layer(ticker)
    if layer:
        out["bottleneck_layer"] = layer
        out["matched"] = True
        out["leopold_score"] += layer["score"] * 0.5  # 50% of score from layer
        out["rules_passed"].append(f"Layer {layer['layer'].split('_')[0]}: {layer['role']}")
    
    # Step 3: Upstream Distance
    upstream = map_upstream_distance(ticker)
    if upstream:
        out["upstream_distance"] = upstream
        if upstream["leopold_preferred"]:
            out["leopold_score"] += 15
            out["rules_passed"].append(f"Upstream: distance {upstream['distance']} ({upstream['label']})")
        else:
            out["rationale"].append(f"⚠️ Too downstream (distance {upstream['distance']}) — priced in")
    
    # Step 4: Written-Off detector
    if prices_series is not None:
        wo = detect_written_off(ticker, prices_series)
        if wo:
            out["written_off"] = wo
            out["leopold_score"] += wo["written_off_score"] * 0.3  # up to +30
            if wo["is_written_off"]:
                out["rules_passed"].append(
                    f"Written off {wo['drawdown_from_52w_high_pct']:+.0f}% from 52w high"
                )
            if wo["is_recovering_off_base"]:
                out["rules_passed"].append("Recovering off base (Leopold buy zone)")
                out["asymmetry_setup"] = "CALLS — binary outcome, defined downside"
    
    # Step 5: Asymmetry recommendation
    if not out["asymmetry_setup"] and layer and layer.get("asymmetry_recommended"):
        out["asymmetry_setup"] = "CALLS — binary turnaround outcome"
    
    out["leopold_score"] = min(100, round(out["leopold_score"], 1))
    return out


def run_leopold_scan(tickers: List[str], prices: Dict) -> Dict:
    """Batch run Leopold methodology on multiple tickers."""
    out = {
        "ok": True,
        "oom_trajectory": compute_oom_trajectory(),
        "per_ticker": {},
        "top_picks_by_layer": {l: [] for l in BOTTLENECK_LAYERS.keys()},
        "asymmetry_setups": [],  # options-recommended
        "written_off_recovering": [],  # Leopold's classic Intel setup
    }
    
    for t in tickers:
        result = evaluate_leopold_methodology(t, prices.get(t))
        if result["matched"]:
            out["per_ticker"][t] = result
            layer = result.get("bottleneck_layer", {})
            layer_name = layer.get("layer")
            if layer_name in out["top_picks_by_layer"]:
                out["top_picks_by_layer"][layer_name].append({
                    "ticker": t, "score": result["leopold_score"],
                    "role": layer.get("role"),
                })
            if result.get("asymmetry_setup"):
                out["asymmetry_setups"].append({
                    "ticker": t, "setup": result["asymmetry_setup"],
                    "score": result["leopold_score"],
                })
            wo = result.get("written_off", {})
            if wo and wo.get("is_recovering_off_base"):
                out["written_off_recovering"].append({
                    "ticker": t, "drawdown_pct": wo["drawdown_from_52w_high_pct"],
                    "score": wo["written_off_score"],
                })
    
    # Sort all
    for layer_name in out["top_picks_by_layer"]:
        out["top_picks_by_layer"][layer_name].sort(key=lambda x: x["score"], reverse=True)
    out["asymmetry_setups"].sort(key=lambda x: x["score"], reverse=True)
    out["written_off_recovering"].sort(key=lambda x: x["score"], reverse=True)
    
    return out
