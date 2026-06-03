"""keith_signal_sync.py - Keith McCullough Signal Sync v39
P0 Override Engine for MacroRegime Dashboard.

Based on deep research of Keith McCullough public signals (Hedgeye tweets, 
ETF Pro newsletters, Macro Show clips, podcast interviews).

Duration Framework:
- TRADE (3 weeks / immediate-term): Entry/exit timing
- TREND (3 months / intermediate): Position direction
- TAIL (3 years / long-term): Strategic allocation

Override Rule:
- Keith TRADE signal = highest weight for entry timing
- Keith TREND signal = highest weight for position direction
- If TRADE != TREND → show BOTH with duration labels
- If Keith says BEARISH TRADE + Dashboard says LONG → override to AVOID/WAIT
"""

from datetime import datetime, timedelta
from typing import Dict, Optional

# ═══════════════════════════════════════════════════════════════════════
# KEITH SIGNAL MAP (Updated: May 23 2026)
# Sources: 
#   - Keith tweet Apr 29 2026: "Gold's immediate-term TRADE Signal remains Bearish"
#   - Keith tweet: "USD Index remains Bullish TREND @Hedgeye"
#   - ETF Pro March 2026: "Energy exposure = highest-conviction allocation"
#   - ETF Pro March 2026: "UUP no longer on short book, USD Neutral TRADE"
#   - Macro Show May 23 2026: "Signal (Very) Bullish For Gold" — NEW, may flip TRADE
# ═══════════════════════════════════════════════════════════════════════

# Duration-aware signal map: {ticker: {duration: signal}}
# Signal: "BULLISH" | "BEARISH" | "NEUTRAL"
# Duration: "TRADE" (3w) | "TREND" (3m) | "TAIL" (3y)

KEITH_SIGNAL_MAP = {
    # GOLD — Conflicting signals, using most recent explicit TRADE signal
    # Apr 29: BEARISH TRADE | May 23 video: possibly flipping — conservative = BEARISH TRADE until confirmed
    "GC=F":    {"TRADE": "BEARISH", "TREND": "BULLISH", "TAIL": "BULLISH", 
                "source": "Keith tweet Apr 29 2026 + ETF Pro Mar 2026", 
                "note": "TRADE bearish = don't chase now. Wait pullback to LRR. TREND bullish = hold existing."},
    "GLD":     {"TRADE": "BEARISH", "TREND": "BULLISH", "TAIL": "BULLISH",
                "source": "Keith tweet Apr 29 2026 + ETF Pro Mar 2026",
                "note": "Same as GC=F. ETF Pro has GLD in long book = TREND bullish."},
    "AAAU":    {"TRADE": "BEARISH", "TREND": "BULLISH", "TAIL": "BULLISH",
                "source": "ETF Pro Mar 2026",
                "note": "Physical gold +74% since Feb 2025 add."},

    # USD — Bullish TREND, Neutral TRADE (was bearish, recovering)
    "DX-Y.NYB": {"TRADE": "NEUTRAL", "TREND": "BULLISH", "TAIL": "NEUTRAL",
                 "source": "Keith tweet + ETF Pro Mar 2026",
                 "note": "USD breaking out on TRADE duration. UUP removed from short book."},
    "UUP":      {"TRADE": "NEUTRAL", "TREND": "BULLISH", "TAIL": "NEUTRAL",
                 "source": "ETF Pro Mar 2026",
                 "note": "UUP no longer short = USD signal improved."},

    # ENERGY — Bullish across all durations
    "XLE":     {"TRADE": "BULLISH", "TREND": "BULLISH", "TAIL": "BULLISH",
                "source": "Keith tweet + ETF Pro Mar 2026",
                "note": "Energy = highest-conviction allocation. Oil up +7.9% last month."},
    "USO":     {"TRADE": "BULLISH", "TREND": "BULLISH", "TAIL": "BULLISH",
                "source": "ETF Pro Mar 2026",
                "note": "WTI TRR up at $77+. Oil up, Dollar up = textbook Quad 3."},
    "XOP":     {"TRADE": "BULLISH", "TREND": "BULLISH", "TAIL": "BULLISH",
                "source": "ETF Pro Mar 2026",
                "note": "XOP +13.5% since add."},
    "OIH":     {"TRADE": "BULLISH", "TREND": "BULLISH", "TAIL": "BULLISH",
                "source": "ETF Pro Mar 2026",
                "note": "OIH +5.7% since add."},

    # COPPER — Bullish (but podcast mentioned declining — using explicit signal)
    "HG=F":    {"TRADE": "BULLISH", "TREND": "BULLISH", "TAIL": "NEUTRAL",
                "source": "Hedgeye Risk Range May 2024 + ETF Pro",
                "note": "Copper 4.47-4.75 bullish range. But China slowdown risk."},

    # SILVER — Conflicting. ETF Pro says LONG SLV, but tweet said Bearish TREND
    # Conservative: use BEARISH TREND from explicit tweet over ETF allocation
    "SLV":     {"TRADE": "BEARISH", "TREND": "BEARISH", "TAIL": "NEUTRAL",
                "source": "Keith tweet",
                "note": "Keith: Silver remain Bearish TRENDS. Avoid until trend flip."},
    "SI=F":    {"TRADE": "BEARISH", "TREND": "BEARISH", "TAIL": "NEUTRAL",
                "source": "Keith tweet",
                "note": "Same as SLV."},

    # BONDS / DURATION — Bullish (yields falling = bond prices rising)
    "TLT":     {"TRADE": "BULLISH", "TREND": "BULLISH", "TAIL": "BULLISH",
                "source": "ETF Pro Mar 2026",
                "note": "2s, 10s, 30s all Bearish TRADE/TREND = lower yields = long duration."},
    "IEF":     {"TRADE": "BULLISH", "TREND": "BULLISH", "TAIL": "NEUTRAL",
                "source": "ETF Pro Mar 2026",
                "note": "Intermediate duration play."},
    "LQD":     {"TRADE": "BULLISH", "TREND": "BULLISH", "TAIL": "NEUTRAL",
                "source": "ETF Pro Mar 2026",
                "note": "Investment grade credit."},

    # UTILITIES — Bullish (Quad 4/3 defensive)
    "XLU":     {"TRADE": "BULLISH", "TREND": "BULLISH", "TAIL": "NEUTRAL",
                "source": "ETF Pro Mar 2026",
                "note": "Quad 3/4 defensive. Long duration proxy."},

    # TECH / MOAB — BEARISH (bubble bursting)
    "XLK":     {"TRADE": "BEARISH", "TREND": "BEARISH", "TAIL": "BEARISH",
                "source": "ETF Pro Mar 2026",
                "note": "Short #MOAB Tech. Bag7 down -24.7% from Oct 2025 peak."},
    "SKYY":    {"TRADE": "BEARISH", "TREND": "BEARISH", "TAIL": "BEARISH",
                "source": "ETF Pro Mar 2026",
                "note": "Cloud computing short. AI commoditization pressure."},
    "NVDA":    {"TRADE": "BEARISH", "TREND": "BEARISH", "TAIL": "NEUTRAL",
                "source": "ETF Pro Mar 2026 + Macro Show",
                "note": "Monster lower high vs $207 all-time. Fractal structure = lower highs."},
    "QQQ":     {"TRADE": "BEARISH", "TREND": "BEARISH", "TAIL": "NEUTRAL",
                "source": "ETF Pro Mar 2026",
                "note": "Nasdaq 100. #MOAB tech exposure."},

    # BITCOIN / CRYPTO — BEARISH (crash mode)
    "BTC-USD": {"TRADE": "BEARISH", "TREND": "BEARISH", "TAIL": "NEUTRAL",
                "source": "ETF Pro Mar 2026 + Macro Show May 23 2026",
                "note": "Bitcoin -47% from Oct 2025 high. Crash Signal intact. TRR lower-highs at $69k."},
    "BITS":    {"TRADE": "BEARISH", "TREND": "BEARISH", "TAIL": "NEUTRAL",
                "source": "ETF Pro Mar 2026",
                "note": "Bitcoin-sensitive equities short."},
    "WGMI":    {"TRADE": "BEARISH", "TREND": "BEARISH", "TAIL": "NEUTRAL",
                "source": "ETF Pro Mar 2026",
                "note": "Bitcoin miners getting destroyed."},

    # INDONESIA — BEARISH (moved to short book)
    "EIDO":    {"TRADE": "BEARISH", "TREND": "BEARISH", "TAIL": "NEUTRAL",
                "source": "ETF Pro Mar 2026",
                "note": "Indonesia (IDX) moved to short book. Quad setup deteriorating."},
    "IDX":     {"TRADE": "BEARISH", "TREND": "BEARISH", "TAIL": "NEUTRAL",
                "source": "ETF Pro Mar 2026",
                "note": "Same as EIDO."},

    # FINANCIALS — BEARISH (Quad 3 short)
    "XLF":     {"TRADE": "BEARISH", "TREND": "BEARISH", "TAIL": "NEUTRAL",
                "source": "ETF Pro Mar 2026",
                "note": "Short financials. Stagflation = NIM pressure."},

    # CONSUMER DISCRETIONARY — BEARISH
    "XLY":     {"TRADE": "BEARISH", "TREND": "BEARISH", "TAIL": "NEUTRAL",
                "source": "ETF Pro Mar 2026",
                "note": "Short consumer discretionary. Quad 3 carnage."},

    # HOUSING — Bullish (rate sensitivity)
    "ITB":     {"TRADE": "BULLISH", "TREND": "BULLISH", "TAIL": "NEUTRAL",
                "source": "ETF Pro Mar 2026",
                "note": "Housing = rate-sensitivity play. Lower yields = bullish housing."},

    # STEEL — Bullish (Trump tariffs)
    "SLX":     {"TRADE": "BULLISH", "TREND": "BULLISH", "TAIL": "NEUTRAL",
                "source": "ETF Pro Mar 2026",
                "note": "Steel = Trump tariff play."},

    # MEXICO — Bullish (nearshoring)
    "EWW":     {"TRADE": "BULLISH", "TREND": "BULLISH", "TAIL": "NEUTRAL",
                "source": "ETF Pro Mar 2026",
                "note": "Mexico = nearshoring beneficiary. #1 US trading partner."},

    # INDIA — Bullish
    "GLIN":    {"TRADE": "BULLISH", "TREND": "BULLISH", "TAIL": "NEUTRAL",
                "source": "ETF Pro Mar 2026",
                "note": "India = Quad 1 country exposure."},
    "INDA":    {"TRADE": "BULLISH", "TREND": "BULLISH", "TAIL": "NEUTRAL",
                "source": "ETF Pro Mar 2026",
                "note": "Same as GLIN."},
}

# Aliases for common ticker variants
TICKER_ALIASES = {
    "GOLD": "GC=F",
    "GOLD1": "GLD",
    "DXY": "DX-Y.NYB",
    "DOLLAR": "UUP",
    "OIL": "USO",
    "CRUDE": "CL=F",
    "COPPER": "HG=F",
    "SILVER1": "SLV",
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "NASDAQ": "QQQ",
    "SP500": "SPY",
    "RUSSELL": "IWM",
    "TREASURY": "TLT",
    "BONDS": "TLT",
    "INDONESIA": "EIDO",
    "IHSG": "^JKSE",
}


def _resolve_ticker(ticker: str) -> str:
    """Resolve ticker aliases to canonical form."""
    t = ticker.upper().strip().replace("$", "")
    return TICKER_ALIASES.get(t, t)


def get_keith_signal(ticker: str, duration: str = "TRADE") -> Optional[Dict]:
    """Get Keith signal for a ticker at specific duration.

    Args:
        ticker: Ticker symbol
        duration: "TRADE" | "TREND" | "TAIL" | "ALL"

    Returns:
        Dict with signal info or None if no signal
    """
    canonical = _resolve_ticker(ticker)
    data = KEITH_SIGNAL_MAP.get(canonical)
    if not data:
        return None

    if duration == "ALL":
        return {
            "ticker": ticker,
            "canonical": canonical,
            "trade": data.get("TRADE", "NEUTRAL"),
            "trend": data.get("TREND", "NEUTRAL"),
            "tail": data.get("TAIL", "NEUTRAL"),
            "source": data.get("source", ""),
            "note": data.get("note", ""),
        }

    sig = data.get(duration, "NEUTRAL")
    return {
        "ticker": ticker,
        "canonical": canonical,
        "duration": duration,
        "signal": sig,
        "source": data.get("source", ""),
        "note": data.get("note", ""),
    }


def resolve_direction(ticker: str, dashboard_direction: str = "NEUTRAL") -> Dict:
    """Resolve dashboard direction vs Keith signal. P0 override.

    Logic:
    1. If Keith TRADE signal exists and != dashboard → OVERRIDE
    2. If Keith TREND signal exists and != dashboard → WARNING (not override, show both)
    3. If no Keith signal → pass through dashboard direction

    Returns:
        {
            "direction": final_direction,
            "original_direction": dashboard_direction,
            "override": bool,
            "basis": str,  # human-readable reason
            "keith_trade": str,
            "keith_trend": str,
            "duration_mismatch": bool,  # TRADE != TREND
        }
    """
    canonical = _resolve_ticker(ticker)
    data = KEITH_SIGNAL_MAP.get(canonical)

    if not data:
        # No Keith signal → pass through
        return {
            "direction": dashboard_direction,
            "original_direction": dashboard_direction,
            "override": False,
            "basis": "No Keith signal — using dashboard",
            "keith_trade": "NEUTRAL",
            "keith_trend": "NEUTRAL",
            "duration_mismatch": False,
        }

    keith_trade = data.get("TRADE", "NEUTRAL")
    keith_trend = data.get("TREND", "NEUTRAL")
    keith_tail = data.get("TAIL", "NEUTRAL")

    duration_mismatch = keith_trade != keith_trend

    # Normalize dashboard direction
    dash = str(dashboard_direction).upper()
    if dash not in ("LONG", "SHORT", "NEUTRAL"):
        dash = "NEUTRAL"

    # P0 Override Rule: TRADE signal takes precedence for entry timing
    override = False
    final_direction = dash
    basis_parts = []

    if keith_trade == "BEARISH" and dash == "LONG":
        override = True
        final_direction = "AVOID"  # Don't short unless dashboard also says short
        basis_parts.append(f"🎙️ Keith TRADE=BEARISH vs Dashboard=LONG → AVOID")
        basis_parts.append(f"   Wait for pullback to Trade LRR. TREND={keith_trend}")

    elif keith_trade == "BULLISH" and dash == "SHORT":
        override = True
        final_direction = "AVOID"
        basis_parts.append(f"🎙️ Keith TRADE=BULLISH vs Dashboard=SHORT → AVOID")
        basis_parts.append(f"   Don't short into Keith bullish signal. TREND={keith_trend}")

    elif keith_trade == "BULLISH" and dash == "NEUTRAL":
        # Upgrade to LONG if Keith is bullish
        final_direction = "LONG"
        basis_parts.append(f"🎙️ Keith TRADE=BULLISH → Upgrade from NEUTRAL to LONG")

    elif keith_trade == "BEARISH" and dash == "NEUTRAL":
        # Downgrade to AVOID
        final_direction = "AVOID"
        basis_parts.append(f"🎙️ Keith TRADE=BEARISH → Downgrade from NEUTRAL to AVOID")

    elif keith_trade == "NEUTRAL":
        # No TRADE signal → use TREND as guidance
        if keith_trend == "BULLISH" and dash == "SHORT":
            final_direction = "AVOID"
            basis_parts.append(f"🎙️ Keith TREND=BULLISH vs Dashboard=SHORT → AVOID (no TRADE signal)")
        elif keith_trend == "BEARISH" and dash == "LONG":
            final_direction = "AVOID"
            basis_parts.append(f"🎙️ Keith TREND=BEARISH vs Dashboard=LONG → AVOID (no TRADE signal)")
        else:
            basis_parts.append(f"🎙️ Keith TRADE=NEUTRAL → Pass through dashboard ({dash})")

    else:
        # Keith and dashboard agree
        basis_parts.append(f"🎙️ Keith TRADE={keith_trade} = Dashboard={dash} → Agree")

    # Add duration mismatch warning
    if duration_mismatch:
        basis_parts.append(f"⚠️ Duration mismatch: TRADE={keith_trade} ≠ TREND={keith_trend}")
        basis_parts.append(f"   Action: Follow TRADE for entry, TREND for position sizing")

    # Add source
    basis_parts.append(f"📰 Source: {data.get('source', 'Hedgeye')}")
    if data.get("note"):
        basis_parts.append(f"📝 {data['note']}")

    return {
        "direction": final_direction,
        "original_direction": dash,
        "override": override,
        "basis": " | ".join(basis_parts),
        "keith_trade": keith_trade,
        "keith_trend": keith_trend,
        "keith_tail": keith_tail,
        "duration_mismatch": duration_mismatch,
        "source": data.get("source", ""),
        "note": data.get("note", ""),
    }


def should_avoid(ticker: str, dashboard_direction: str = "LONG") -> bool:
    """Quick check: should this ticker be avoided based on Keith signal?"""
    result = resolve_direction(ticker, dashboard_direction)
    return result["direction"] in ("AVOID", "NEUTRAL") and result["override"]


def get_all_keith_signals() -> Dict[str, Dict]:
    """Return all Keith signals for external use."""
    return {
        t: {
            "TRADE": d.get("TRADE", "NEUTRAL"),
            "TREND": d.get("TREND", "NEUTRAL"),
            "TAIL": d.get("TAIL", "NEUTRAL"),
            "source": d.get("source", ""),
            "note": d.get("note", ""),
        }
        for t, d in KEITH_SIGNAL_MAP.items()
    }


def get_keith_summary() -> Dict:
    """Summary stats of Keith signal coverage."""
    total = len(KEITH_SIGNAL_MAP)
    bullish_trade = sum(1 for d in KEITH_SIGNAL_MAP.values() if d.get("TRADE") == "BULLISH")
    bearish_trade = sum(1 for d in KEITH_SIGNAL_MAP.values() if d.get("TRADE") == "BEARISH")
    neutral_trade = sum(1 for d in KEITH_SIGNAL_MAP.values() if d.get("TRADE") == "NEUTRAL")

    bullish_trend = sum(1 for d in KEITH_SIGNAL_MAP.values() if d.get("TREND") == "BULLISH")
    bearish_trend = sum(1 for d in KEITH_SIGNAL_MAP.values() if d.get("TREND") == "BEARISH")

    mismatches = sum(1 for d in KEITH_SIGNAL_MAP.values() if d.get("TRADE") != d.get("TREND"))

    return {
        "total_signals": total,
        "trade_bullish": bullish_trade,
        "trade_bearish": bearish_trade,
        "trade_neutral": neutral_trade,
        "trend_bullish": bullish_trend,
        "trend_bearish": bearish_trend,
        "duration_mismatches": mismatches,
        "last_updated": "2026-05-23",
        "sources": ["Keith McCullough tweets", "Hedgeye ETF Pro newsletters", "Macro Show clips", "Podcast interviews"],
    }
