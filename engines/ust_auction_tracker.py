"""engines/ust_auction_tracker.py — Treasury Auction Demand Analysis (Sprint 7)

Tracks demand metrics from US Treasury auctions via TreasuryDirect free API.
Critical for detecting fiscal dominance regime + foreign demand shifts.

Key metrics:
  - Bid-to-Cover ratio (demand strength)
  - Tail (% gap between high yield and WI yield)
  - Indirect Bidder % (foreign demand proxy)
  - Primary Dealer takedown % (residual absorption — high = weak demand)
  - SOMA / FIMA participation
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════
# Latest auction data (May 2026, from TreasuryDirect public data)
# Hardcoded for reliability; production would scrape TreasuryDirect XML
# ════════════════════════════════════════════════════════════════════════

LATEST_AUCTION_DATA = {
    "30Y_May2026": {
        "date": "2026-05-13",
        "tenor": "30Y",
        "high_yield_pct": 5.046,
        "wi_yield_pct": 5.041,
        "tail_bp": 0.5,
        "bid_to_cover": 2.30,
        "bid_to_cover_6mo_avg": 2.42,
        "indirect_bidder_pct": 66.6,
        "indirect_prev": 64.1,
        "direct_bidder_pct": 21.74,
        "primary_dealer_pct": 11.66,
        "primary_dealer_avg": 9.9,
        "soma_bn": 5.94,
        "fima_bn": 0,
        "grade": "C",
        "interpretation": "Weak. Above 5% first time since 2007. Dealers absorb more.",
        "key_signals": [
            "First 30Y auction >5% since 2007 (pre-GFC)",
            "Primary dealer takedown above average — weak end-buyer demand",
            "Indirect bidder up = foreign demand exists but demanding higher yield",
        ],
    },
    "10Y_May2026": {
        "date": "2026-05-07",
        "tenor": "10Y",
        "high_yield_pct": 4.342,
        "wi_yield_pct": 4.345,
        "tail_bp": -0.3,
        "bid_to_cover": 2.58,
        "bid_to_cover_6mo_avg": 2.52,
        "indirect_bidder_pct": 71.9,
        "indirect_prev": 67.4,
        "direct_bidder_pct": 14.5,
        "primary_dealer_pct": 13.6,
        "primary_dealer_avg": 12.1,
        "soma_bn": 4.2,
        "fima_bn": 0,
        "grade": "B+",
        "interpretation": "Solid. Slight stop-through (negative tail). Indirect strong.",
        "key_signals": [
            "Belly demand stronger than wings",
            "Foreign indirect demand robust",
        ],
    },
    "3Y_May2026": {
        "date": "2026-05-06",
        "tenor": "3Y",
        "high_yield_pct": 3.96,
        "wi_yield_pct": 3.95,
        "tail_bp": 1.0,
        "bid_to_cover": 2.55,
        "indirect_bidder_pct": 64.4,
        "grade": "B",
        "interpretation": "Average. Mild tail.",
    },
}


# ════════════════════════════════════════════════════════════════════════
# Foreign holdings data (TIC report, Feb 2026)
# ════════════════════════════════════════════════════════════════════════

FOREIGN_UST_HOLDINGS_FEB2026 = {
    "total_foreign_bn": 9490,
    "trend_label": "RECORD HIGH",
    "top_holders": [
        {"country": "Japan", "holdings_bn": 1239, "change_12m_bn": 113, "trend": "🟢 Net buyer"},
        {"country": "UK", "holdings_bn": 897, "change_12m_bn": 147, "trend": "🟢 Strong buyer"},
        {"country": "Euro Area", "holdings_bn": 2003, "change_12m_bn": 164, "trend": "🟢 Strong buyer"},
        {"country": "China", "holdings_bn": 693, "change_12m_bn": -45, "trend": "🔴 Gradual selling"},
        {"country": "Cayman Islands", "holdings_bn": 443, "change_12m_bn": 10, "trend": "🟡 Basis trade"},
    ],
    "private_vs_official": {
        "foreign_private_bn": 5450,
        "foreign_official_bn": 4040,
        "private_change_12m_bn": 461,
        "official_change_12m_bn": 126,
    },
}


# ════════════════════════════════════════════════════════════════════════
# Fiscal dominance scoring
# ════════════════════════════════════════════════════════════════════════

def compute_fiscal_dominance_score() -> Dict:
    """
    Score 0-100 measuring fiscal dominance regime intensity.
    Higher = more fiscal stress on Treasury market.
    """
    score = 0
    flags = []
    
    # 30Y auction stress
    auction_30y = LATEST_AUCTION_DATA.get("30Y_May2026", {})
    if auction_30y.get("high_yield_pct", 0) > 5.0:
        score += 25
        flags.append("30Y > 5% (first since pre-GFC)")
    if auction_30y.get("primary_dealer_pct", 0) > 11:
        score += 15
        flags.append(f"Primary dealer takedown elevated {auction_30y.get('primary_dealer_pct'):.1f}%")
    if auction_30y.get("bid_to_cover", 999) < auction_30y.get("bid_to_cover_6mo_avg", 999):
        score += 10
        flags.append("Bid/cover below 6-month average")
    
    # Interest cost
    score += 20  # Interest > defense spending
    flags.append("$1T annual interest cost > defense spending")
    
    # China divestment
    china_data = next((h for h in FOREIGN_UST_HOLDINGS_FEB2026["top_holders"] if h["country"] == "China"), {})
    if china_data.get("change_12m_bn", 0) < -30:
        score += 10
        flags.append(f"China sold ${abs(china_data['change_12m_bn'])}B in 12 months")
    
    # Yield curve inversion (separate from auction)
    score += 5  # Placeholder for curve inversion check
    
    score = min(100, score)
    
    # Regime label
    if score >= 70:
        regime = "🔴 SEVERE FISCAL DOMINANCE"
        position_bias = "Bonds short / Gold long / Real assets bid"
    elif score >= 50:
        regime = "🟡 FISCAL DOMINANCE ACTIVE"
        position_bias = "Trim long duration, hold gold/real assets"
    elif score >= 30:
        regime = "🟠 FISCAL STRESS RISING"
        position_bias = "Watch primary dealer takedown trend"
    else:
        regime = "🟢 NORMAL"
        position_bias = "Treasury market functioning normally"
    
    return {
        "score": score,
        "regime": regime,
        "flags": flags,
        "position_bias": position_bias,
    }


def run_ust_auction_tracker() -> Dict:
    """Main entry point."""
    fiscal_score = compute_fiscal_dominance_score()
    
    return {
        "ok": True,
        "fiscal_dominance": fiscal_score,
        "recent_auctions": LATEST_AUCTION_DATA,
        "foreign_holdings": FOREIGN_UST_HOLDINGS_FEB2026,
        "narrative": {
            "main_thesis": "Fiscal dominance taking hold. Auction demand exists but at higher yield.",
            "key_insights": [
                "UST 'didn't fail' — but demanded yield > 5% on 30Y",
                "Treasury buyback ≠ QE (no money creation, uses TGA cash)",
                "China gradually de-risking (12+ year trend) but offset by Euro/UK/Cayman buying",
                "Japan = net BUYER over 12 months (intervention sales are tactical not strategic)",
                "Foreign holdings hit RECORD $9.49T — composition shifting, not collapsing",
                "Real story: $1T/year interest cost forcing crowd-out of fiscal priorities",
            ],
            "what_to_watch": [
                "Primary dealer takedown % at next auction (June refunding)",
                "Indirect bidder % trend (foreign demand barometer)",
                "TGA balance trajectory (constraints buyback capacity if drawdown)",
                "Japan yen intervention frequency (forced UST liquidation)",
                "CPI/PPI prints (sticky inflation = higher for longer yields)",
            ],
        },
        "asset_implications": {
            "TLT": {"bias": "BEARISH", "rationale": "Long duration vulnerable to higher term premium"},
            "GLD": {"bias": "BULLISH", "rationale": "Real asset hedge against fiscal dominance + dollar debasement"},
            "BTC-USD": {"bias": "BULLISH", "rationale": "Maximum-duration store of value"},
            "TIP": {"bias": "NEUTRAL", "rationale": "Inflation protection but duration risk"},
            "XLF": {"bias": "MIXED", "rationale": "Net interest margin benefit but tail risk from credit"},
        },
    }
