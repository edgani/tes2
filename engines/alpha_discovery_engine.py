"""
alpha_discovery_engine.py - Alpha Discovery Engine v1.0
=========================================================
Finds "ALPHA" tickers - early-stage, non-consensus, high-potential tickers
that haven't been discovered by institutions yet.

Think PLTR in 2023, SNSK now, SIVE - tickers that are NOT mainstream but
have huge potential. Integrates with macroregime orchestrator.py pipeline.

Scoring System (0-100):
- technical_alpha: 25 pts  (MQA v17 signal strength: Risk Range + Phase + Formation)
- macro_alpha:     25 pts  (Bottleneck + Quad alignment + Front-run catalyst)
- asymmetry:       20 pts  (Risk/Reward ratio: low LRR entry, high TRR target)
- catalyst:        15 pts  (Upcoming event within 60 days)
- crowdedness:     15 pts  (1 - institutional ownership pct; lower = higher score)

Compatible with orchestrator.py snap dict format.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("alpha_discovery_engine")

# ---------------------------------------------------------------------------
# CRITERIA WEIGHTS
# ---------------------------------------------------------------------------
CRITERIA = {
    "technical_alpha": 25,   # MQA v17 signal strength (Risk Range + Phase + Formation)
    "macro_alpha": 25,       # Bottleneck + Quad alignment + Front-run catalyst
    "asymmetry": 20,         # Risk/Reward ratio (low LRR entry, high TRR target)
    "catalyst": 15,          # Upcoming event within 60 days
    "crowdedness": 15,       # 1 - institutional ownership pct (lower = higher score)
}

GRADE_THRESHOLDS = {
    "A": 85,   # Exceptional alpha opportunity
    "B": 70,   # Strong alpha opportunity
    "C": 55,   # Moderate alpha opportunity
    "D": 40,   # Weak alpha opportunity
    "F": 0,    # No alpha (exclude)
}

# Major ETF constituents - proxy for "crowded" trades
_MAJOR_ETF_CONSTITUENTS = {
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "TSLA",
    "BRK-B", "AVGO", "JPM", "V", "WMT", "UNH", "MA", "XOM", "PG",
    "HD", "CVX", "MRK", "KO", "LLY", "ABBV", "PEP", "BAC", "COST",
    "TMO", "ABT", "MCD", "ACN", "ADBE", "DIS", "CSCO", "VZ", "WFC",
    "DHR", "NEE", "TXN", "PM", "NKE", "RTX", "PFE", "BMY", "UPS",
    "QCOM", "INTC", "LOW", "AMGN", "HON", "IBM", "GS", "CAT", "DE",
    "GE", "MDT", "T", "BLK", "AMAT", "SBUX", "MS", "ELV", "NOW",
    "AXP", "SCHW", "C", "LMT", "ISRG", "SPGI", "PLD", "ADI", "SYK",
    "GILD", "BKNG", "TJX", "VRTX", "ZTS", "MMC", "ADP", "REGN", "SO",
    "BSX", "CVS", "PGR", "MU", "ETN", "CI", "SLB", "CME", "EQIX",
    "ICE", "PANW", "KLAC", "MO", "SNOW", "DUK", "AON", "SHW", "ITW",
    "CSX", "CL", "FTNT", "CMCSA", "HCA", "GD", "NOC", "ECL", "FDX",
    "PYPL", "AIG", "USB", "CCI", "EMR", "TGT", "NSC", "FISV", "GM",
    "ATVI", "ORCL", "CRM", "NFLX", "AMD", "UBER", "COIN", "HOOD",
    # ETFs
    "QQQ", "SMH", "SOXX", "XLK", "XLF", "XLE", "XLI", "XLP", "XLU",
    "XLB", "XRT", "KRE", "IBB", "TLT", "IEF", "LQD", "HYG", "EMB",
    "GLD", "SLV", "USO", "UNG", "DBC",
}


@dataclass
class AlphaDiscoveryConfig:
    """Configuration for the Alpha Discovery Engine."""
    weights: Dict[str, int] = field(default_factory=lambda: dict(CRITERIA))
    grade_thresholds: Dict[str, int] = field(default_factory=lambda: dict(GRADE_THRESHOLDS))
    min_alpha_score: int = 50
    min_dimension_score: int = 5
    asymmetry_rr_excellent: float = 15.0
    asymmetry_rr_good: float = 10.0
    asymmetry_rr_decent: float = 7.0
    asymmetry_rr_moderate: float = 5.0
    phase_bullish_bonus: int = 15
    phase_trade1_bonus: int = 8
    coiled_spring_bonus: int = 10
    price_near_lrr_bonus: int = 5
    bottleneck_beneficiary_bonus: int = 12
    leopold_asymmetry_bonus: int = 10
    frontrun_top_bonus: int = 8
    frontrun_high_bonus: int = 5
    composite_long_bonus: int = 5
    default_crowdedness_score: int = 10
    frontrun_uncrowded_bonus: int = 3
    discovery_found_bonus: int = 2
    catalyst_window_days: int = 60
    early_stage_window_days: int = 30


def _clamp(val: float, lo: float, hi: float) -> float:
    """Clamp a value between lo and hi."""
    return max(lo, min(hi, val))


def _safe_get(d: dict, *keys, default=None):
    """Safely navigate nested dicts."""
    for key in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(key, default)
        if d is None:
            return default
    return d


def _is_major_etf_constituent(ticker: str) -> bool:
    """Check if a ticker is likely a major ETF constituent (more crowded)."""
    return ticker.upper() in _MAJOR_ETF_CONSTITUENTS


def _score_to_grade(score: int, thresholds: Dict[str, int]) -> str:
    """Convert numeric score to letter grade."""
    for grade in ("A", "B", "C", "D"):
        if score >= thresholds.get(grade, 0):
            return grade
    return "F"


def _generate_thesis(ticker: str, sources: List[str], snap: dict) -> str:
    """Generate a human-readable thesis string for an alpha ticker."""
    theses = []
    if "bottleneck" in sources:
        theses.append("Supply chain bottleneck beneficiary")
    if "front_run" in sources:
        theses.append("Pre-catalyst front-run opportunity")
    if "leopold" in sources:
        theses.append("Asymmetry setup (Leopold methodology)")
    if "coatue" in sources:
        theses.append("Coatue signal alignment")
    if "karsan" in sources:
        theses.append("Volatility convexity setup (Karsan)")
    if "composite" in sources:
        theses.append("Multi-signal composite alignment")
    if "discovery" in sources:
        theses.append("Discovery brain early detection")
    if "walkforward" in sources:
        theses.append("Walk-forward backtest validated")
    if "gatekeeper" in sources:
        theses.append("Alpha gatekeeper passed")
    if "thought" in sources:
        theses.append("Thesis-driven conviction match")
    if not theses:
        thought = _safe_get(snap, "thought_process", ticker, default={})
        if thought and thought.get("matched_frameworks"):
            frameworks = thought.get("matched_frameworks", [])
            if frameworks:
                theses.append("Framework match: {}".format(frameworks[0]))
    if not theses:
        theses.append("Multi-factor alpha convergence")
    return "; ".join(theses[:3])


def _generate_why(ticker: str, breakdown: dict, sources: List[str]) -> str:
    """Generate a 'why' explanation string."""
    parts = []
    ta = breakdown.get("technical_alpha", 0)
    if ta >= 20:
        parts.append("Bullish formation with coiled spring")
    elif ta >= 15:
        parts.append("Accumulation phase building")
    elif ta >= 10:
        parts.append("Technical setup developing")
    ma = breakdown.get("macro_alpha", 0)
    if ma >= 20:
        parts.append("Multi-macro catalyst alignment")
    elif ma >= 15:
        parts.append("Macro tailwind identified")
    elif ma >= 10:
        parts.append("Emerging macro theme")
    asym = breakdown.get("asymmetry", 0)
    if asym >= 15:
        parts.append("Favorable risk/reward (>10% RR)")
    elif asym >= 10:
        parts.append("Positive asymmetry")
    cr = breakdown.get("crowdedness", 0)
    if cr >= 12:
        parts.append("Low institutional coverage")
    elif cr >= 10:
        parts.append("Early-stage discovery")
    if not parts:
        parts.append("Non-consensus alpha opportunity")
    return "; ".join(parts[:4])


def _determine_direction(ticker: str, snap: dict, risk_range_result: dict) -> str:
    """Determine the trade direction for an alpha ticker."""
    if risk_range_result.get("bull_form"):
        return "LONG"
    if risk_range_result.get("bear_form"):
        return "SHORT"
    cs = _safe_get(snap, "composite_signals", ticker, default={})
    if cs and cs.get("direction") in ("LONG", "SHORT"):
        return cs.get("direction")
    coatue = _safe_get(snap, "coatue_scan", "per_ticker", ticker, default={})
    if coatue and coatue.get("signal") in ("BUY", "SELL"):
        return "LONG" if coatue.get("signal") == "BUY" else "SHORT"
    leopold = _safe_get(snap, "leopold_scan", default={})
    for setup in leopold.get("asymmetry_setups", []):
        if setup.get("ticker") == ticker and setup.get("direction"):
            return setup.get("direction")
    if risk_range_result.get("trade_phase", 0) > 0:
        return "LONG"
    elif risk_range_result.get("trade_phase", 0) < 0:
        return "SHORT"
    return "LONG"


def _determine_timing(ticker: str, breakdown: dict, sources: List[str]) -> str:
    """Determine the expected timing for the alpha to materialize."""
    catalyst_score = breakdown.get("catalyst", 0)
    if catalyst_score >= 12:
        return "Within 14 days"
    elif catalyst_score >= 10:
        return "Within 30 days"
    elif catalyst_score >= 7:
        return "Within 60 days"
    elif "front_run" in sources or "catalyst" in sources:
        return "Within 60 days"
    else:
        return "Within 90 days"


def _determine_market_type(ticker: str, snap: dict) -> str:
    """Determine the market type for a ticker."""
    fr = snap.get("front_run_candidates", [])
    for item in fr:
        if item.get("ticker") == ticker and item.get("market_type"):
            return item.get("market_type")
    t = ticker.upper()
    if t.endswith(".JK"):
        return "ihsg"
    if "-USD" in t or "/USD" in t or t in ("BTC-USD", "ETH-USD", "SOL-USD"):
        return "crypto"
    if len(t) == 6 and not t.isalpha():
        return "forex"
    if t in ("CL=F", "GC=F", "SI=F", "NG=F", "ZB=F", "ZN=F", "ZC=F"):
        return "commodity"
    return "us_equity"



# ---------------------------------------------------------------------------
# SCORING FUNCTIONS
# ---------------------------------------------------------------------------

def score_technical_alpha(
    ticker: str,
    snap: dict,
    risk_range_result: dict,
    config: AlphaDiscoveryConfig = None
) -> int:
    """
    Score 0-25 based on MQA v17 signal strength.

    Scoring breakdown:
    - Bullish formation (bull_form): +15
    - Trade phase bullish (trade_phase == 1): +8
    - Trend phase alignment (+3)
    - Coiled spring (accumulation phase): +10
    - High compression (>70): +5, (>50): +3
    - RTA Buy signal: +4, RTA Add: +2
    - Hurst trending (>0.55): +2
    - Price near LRR (good entry): +5
    """
    cfg = config or AlphaDiscoveryConfig()
    score = 0

    try:
        # Phase alignment: bullish formation = maximum bonus
        if risk_range_result.get("bull_form"):
            score += cfg.phase_bullish_bonus
        elif risk_range_result.get("trade_phase") == 1:
            score += cfg.phase_trade1_bonus

        # Trend phase bonus (if aligned)
        if risk_range_result.get("trend_phase") == 1:
            score += 3

        # Coiled spring: accumulation phase detected
        if risk_range_result.get("coiled_spring"):
            score += cfg.coiled_spring_bonus

        # Compression score: high compression = explosive potential
        compression = risk_range_result.get("compression_score", 0)
        if isinstance(compression, (int, float)):
            if compression > 70:
                score += 5
            elif compression > 50:
                score += 3

        # RTA Buy signal present
        if risk_range_result.get("rta_buy"):
            score += 4

        # RTA Add signal present
        if risk_range_result.get("rta_add"):
            score += 2

        # Hurst exponent indicating trending regime
        h_trade = risk_range_result.get("H_trade", 0.5)
        if isinstance(h_trade, (int, float)) and h_trade > 0.55:
            score += 2

        # Price proximity to LRR (good entry zone)
        trade_lrr = risk_range_result.get("trade_lrr", 0)
        trade_trr = risk_range_result.get("trade_trr", 0)
        if isinstance(trade_lrr, (int, float)) and isinstance(trade_trr, (int, float)):
            if trade_trr > trade_lrr > 0:
                range_mid = (trade_trr + trade_lrr) / 2
                prices = snap.get("prices", {})
                price_series = prices.get(ticker, [])
                if price_series:
                    try:
                        current_price = float(price_series[-1])
                        if current_price <= trade_lrr * 1.02:
                            score += cfg.price_near_lrr_bonus
                        elif current_price <= range_mid:
                            score += 3
                    except (ValueError, TypeError):
                        pass

        return min(cfg.weights.get("technical_alpha", 25), score)

    except Exception as e:
        logger.debug("score_technical_alpha error for %s: %s", ticker, e)
        return 0


def score_macro_alpha(
    ticker: str,
    snap: dict,
    config: AlphaDiscoveryConfig = None
) -> int:
    """
    Score 0-25 based on macro signals.

    Scoring breakdown:
    - Bottleneck beneficiary (active): +12, (watch): +6
    - Leopold asymmetry setup: +10 (scaled by asym_score)
    - Leopold top picks: +6
    - Front-run priority (TOP): +8, (HIGH): +5
    - Composite LONG signal: +5
    - Alpha gatekeeper PASS: +4, +2 for score >=70
    - Walk-forward pass: +3
    - Thought process thesis match: +4 (+ up to 3 for frameworks)
    - Karsan convexity/squeeze: +4/+3
    - Coatue BUY: +3
    - Discovery brain detection: +2
    """
    cfg = config or AlphaDiscoveryConfig()
    score = 0

    try:
        # 1. Bottleneck beneficiary (active bottlenecks)
        bottleneck = snap.get("bottleneck_v3", {})
        for item in bottleneck.get("active_bottlenecks", []):
            beneficiaries = item.get("beneficiaries", [])
            if ticker in beneficiaries:
                score += cfg.bottleneck_beneficiary_bonus
                break

        # Bottleneck (watch list)
        for item in bottleneck.get("watch_bottlenecks", []):
            beneficiaries = item.get("beneficiaries", [])
            if ticker in beneficiaries:
                score += cfg.bottleneck_beneficiary_bonus // 2
                break

        # 2. Leopold asymmetry setup
        leopold = snap.get("leopold_scan", {})
        for setup in leopold.get("asymmetry_setups", []):
            if setup.get("ticker") == ticker:
                asym_score = setup.get("asymmetry_score", 70)
                bonus = cfg.leopold_asymmetry_bonus
                if isinstance(asym_score, (int, float)):
                    if asym_score >= 80:
                        bonus = cfg.leopold_asymmetry_bonus
                    elif asym_score >= 60:
                        bonus = cfg.leopold_asymmetry_bonus - 2
                    else:
                        bonus = cfg.leopold_asymmetry_bonus - 5
                score += max(0, bonus)
                break

        # 3. Leopold top picks by layer
        top_picks = leopold.get("top_picks_by_layer", {})
        for layer, picks in top_picks.items():
            if isinstance(picks, list) and ticker in picks:
                score += 6
                break
            elif isinstance(picks, dict) and ticker in picks:
                score += 6
                break

        # 4. Front-run priority
        fr = snap.get("front_run_candidates", [])
        for item in fr:
            if item.get("ticker") == ticker:
                priority = item.get("priority", "")
                if priority == "TOP":
                    score += cfg.frontrun_top_bonus
                elif priority == "HIGH":
                    score += cfg.frontrun_high_bonus
                else:
                    score += 3
                break

        # 5. Composite signal alignment
        cs = snap.get("composite_signals", {}).get(ticker)
        if cs and cs.get("direction") == "LONG":
            conf = cs.get("confidence", 0)
            if isinstance(conf, (int, float)) and conf >= 0.7:
                score += cfg.composite_long_bonus
            else:
                score += 3

        # 6. Alpha gatekeeper score
        gatekeeper = snap.get("alpha_gatekeeper", {}).get(ticker)
        if gatekeeper:
            gate_status = gatekeeper.get("gate_status", "")
            gate_score = gatekeeper.get("score", 0)
            if gate_status == "PASS":
                score += 4
            elif gate_status == "MARGINAL":
                score += 2
            if isinstance(gate_score, (int, float)) and gate_score >= 70:
                score += 2

        # 7. Walk-forward validation
        wf = snap.get("walkforward_results", {}).get(ticker)
        if wf:
            wf_score = wf.get("combined_gate_score", 0)
            if isinstance(wf_score, (int, float)) and wf_score >= 60:
                score += 3

        # 8. Thought process thesis match
        thought = snap.get("thought_process", {}).get(ticker)
        if thought:
            thesis_score = thought.get("thesis_score", 0)
            if isinstance(thesis_score, (int, float)):
                if thesis_score >= 75:
                    score += 4
                elif thesis_score >= 60:
                    score += 2
            frameworks = thought.get("matched_frameworks", [])
            if frameworks:
                score += min(len(frameworks), 3)

        # 9. Karsan scanner signal
        karsan = snap.get("karsan_scanner", {}).get(ticker)
        if karsan:
            setup_type = karsan.get("setup_type", "")
            if "convexity" in setup_type.lower():
                score += 4
            elif "squeeze" in setup_type.lower():
                score += 3

        # 10. Coatue signal
        coatue = snap.get("coatue_scan", {}).get(ticker)
        if coatue:
            signal = coatue.get("signal", "")
            if signal == "BUY":
                score += 3

        # 11. Discovery brain detection
        disc = snap.get("discovery_brain", {})
        for mode, items in disc.get("by_mode", {}).items():
            for item in items:
                if item.get("ticker") == ticker:
                    score += 2
                    break

        return min(cfg.weights.get("macro_alpha", 25), score)

    except Exception as e:
        logger.debug("score_macro_alpha error for %s: %s", ticker, e)
        return 0


def score_asymmetry(
    ticker: str,
    risk_range_result: dict,
    config: AlphaDiscoveryConfig = None
) -> int:
    """
    Score 0-20 based on Risk/Reward ratio.

    RR is calculated as: (TRR - LRR) / LRR * 100
    Higher RR = higher score (more asymmetric payoff).

    Scoring:
    - RR > 15%: 20 pts (exceptional asymmetry)
    - RR > 10%: 15 pts (strong asymmetry)
    - RR > 7%:  10 pts (good asymmetry)
    - RR > 5%:   7 pts (moderate asymmetry)
    - RR <= 5%:  5 pts (minimal asymmetry)
    """
    cfg = config or AlphaDiscoveryConfig()

    try:
        lrr = risk_range_result.get("trade_lrr", 0)
        trr = risk_range_result.get("trade_trr", 0)

        if not isinstance(lrr, (int, float)) or not isinstance(trr, (int, float)):
            return 5
        if lrr <= 0 or trr <= lrr:
            return 5

        rr = (trr - lrr) / lrr * 100.0

        if rr > cfg.asymmetry_rr_excellent:
            return 20
        elif rr > cfg.asymmetry_rr_good:
            return 15
        elif rr > cfg.asymmetry_rr_decent:
            return 10
        elif rr > cfg.asymmetry_rr_moderate:
            return 7
        return 5

    except Exception as e:
        logger.debug("score_asymmetry error for %s: %s", ticker, e)
        return 5


def score_catalyst(
    ticker: str,
    snap: dict,
    config: AlphaDiscoveryConfig = None
) -> int:
    """
    Score 0-15 based on upcoming catalysts.

    Scoring breakdown:
    - Front-run catalyst present: +10, projection target: +3
    - Discovery proactive: +8, adaptive: +4
    - News front-run signal: +5
    - Leopold written-off recovering: +4
    - Squeeze imminent: +6, strong candidate: +4
    - VRP calls to action: +3
    """
    cfg = config or AlphaDiscoveryConfig()
    score = 0

    try:
        # 1. Front-run catalyst
        fr = snap.get("front_run_candidates", [])
        for item in fr:
            if item.get("ticker") == ticker:
                if item.get("catalyst"):
                    score += 10
                proj = item.get("projection")
                if proj and isinstance(proj, dict) and proj.get("target_px"):
                    score += 3
                break

        # 2. Discovery proactive (pre-catalyst detection)
        disc = snap.get("discovery_brain", {})
        for item in disc.get("by_mode", {}).get("proactive", []):
            if item.get("ticker") == ticker:
                score += 8
                break

        # Discovery adaptive
        for item in disc.get("by_mode", {}).get("adaptive", []):
            if item.get("ticker") == ticker:
                score += 4
                break

        # 3. News narratives with catalyst
        news_nlp = snap.get("news_nlp", {})
        if isinstance(news_nlp, dict):
            ticker_news = news_nlp.get("ticker_specific", {}).get(ticker, {})
            front_run_signal = ticker_news.get("front_run_signal")
            if front_run_signal and front_run_signal not in ("NEGATIVE_HEADLINE_RISK",):
                score += 5

        # 4. Leopold written-off recovering = catalyst
        leopold = snap.get("leopold_scan", {})
        written_off = leopold.get("written_off_recovering", [])
        if isinstance(written_off, list):
            for item in written_off:
                item_ticker = item.get("ticker") if isinstance(item, dict) else item
                if item_ticker == ticker:
                    score += 4
                    break

        # 5. Squeeze scanner catalyst
        squeeze = snap.get("squeeze_scanner", {})
        if isinstance(squeeze, dict) and squeeze.get("ok"):
            for sq in squeeze.get("imminent_squeezes", []):
                if isinstance(sq, dict) and sq.get("ticker") == ticker:
                    score += 6
                    break
            for sq in squeeze.get("strong_candidates", []):
                if isinstance(sq, dict) and sq.get("ticker") == ticker:
                    score += 4
                    break

        # 6. VRP scanner calls to action
        vrp = snap.get("vrp_scanner", {})
        if isinstance(vrp, dict):
            for cta in vrp.get("calls_to_action", []):
                if isinstance(cta, dict) and cta.get("ticker") == ticker:
                    score += 3
                    break

        return min(cfg.weights.get("catalyst", 15), score)

    except Exception as e:
        logger.debug("score_catalyst error for %s: %s", ticker, e)
        return 0


def score_crowdedness(
    ticker: str,
    snap: dict,
    config: AlphaDiscoveryConfig = None
) -> int:
    """
    Score 0-15 based on how UN-crowded the trade is.

    Proxy for institutional ownership:
    - Major ETF constituent: -4 (more crowded)
    - Front-run candidate: +3 (potentially early)
    - Discovery brain found: +2 (not mainstream)
    - Leopold written-off: +3 (definitely uncrowded)
    - Squeeze watch list: +2 (building but not crowded)
    - No news coverage: +2 (truly hidden)
    - Small-cap proxy (price < 10): +2
    - Mega-cap proxy (price > 200): -2
    - Alpha gatekeeper high score: +2
    """
    cfg = config or AlphaDiscoveryConfig()
    score = cfg.default_crowdedness_score

    try:
        # 1. Major ETF constituent = more crowded
        if _is_major_etf_constituent(ticker):
            score -= 4

        # 2. Front-run candidate = potentially early
        fr_tickers = [item.get("ticker") for item in snap.get("front_run_candidates", [])]
        if ticker in fr_tickers:
            score += cfg.frontrun_uncrowded_bonus

        # 3. Discovery brain found it
        disc = snap.get("discovery_brain", {})
        for mode, items in disc.get("by_mode", {}).items():
            for item in items:
                if item.get("ticker") == ticker:
                    score += cfg.discovery_found_bonus
                    break

        # 4. Leopold written-off = uncrowded
        leopold = snap.get("leopold_scan", {})
        written_off = leopold.get("written_off_recovering", [])
        if isinstance(written_off, list):
            for item in written_off:
                item_ticker = item.get("ticker") if isinstance(item, dict) else item
                if item_ticker == ticker:
                    score += 3
                    break

        # 5. Squeeze scanner watch list
        squeeze = snap.get("squeeze_scanner", {})
        if isinstance(squeeze, dict) and squeeze.get("ok"):
            for sq in squeeze.get("watch_list", []):
                if isinstance(sq, dict) and sq.get("ticker") == ticker:
                    score += 2
                    break

        # 6. News coverage proxy
        news_nlp = snap.get("news_nlp", {})
        if isinstance(news_nlp, dict):
            ticker_news = news_nlp.get("ticker_specific", {}).get(ticker, {})
            bull_count = ticker_news.get("bull_count", 0)
            bear_count = ticker_news.get("bear_count", 0)
            total_mentions = bull_count + bear_count
            if total_mentions > 10:
                score -= 3
            elif total_mentions == 0:
                score += 2

        # 7. Market cap proxy via price
        prices = snap.get("prices", {})
        price_series = prices.get(ticker, [])
        if price_series:
            try:
                current_price = float(price_series[-1])
                if current_price < 10:
                    score += 2
                elif current_price > 200:
                    score -= 2
            except (ValueError, TypeError):
                pass

        # 8. Alpha gatekeeper high score
        gatekeeper = snap.get("alpha_gatekeeper", {}).get(ticker)
        if gatekeeper:
            gate_score = gatekeeper.get("score", 0)
            if isinstance(gate_score, (int, float)) and gate_score >= 70:
                score += 2

        return _clamp(score, 0, cfg.weights.get("crowdedness", 15))

    except Exception as e:
        logger.debug("score_crowdedness error for %s: %s", ticker, e)
        return cfg.default_crowdedness_score



# ---------------------------------------------------------------------------
# ALPHA DISCOVERY ENGINE CLASS
# ---------------------------------------------------------------------------

class AlphaDiscoveryEngine:
    """
    Alpha Discovery Engine - finds early-stage, non-consensus, high-potential tickers.

    Integrates with the macroregime orchestrator.py pipeline. Consumes the snap dict
    and risk_range_results to score each ticker across 5 alpha dimensions:

    1. Technical Alpha (25 pts): MQA v17 signal strength
    2. Macro Alpha (25 pts): Bottleneck + Quad alignment + Front-run catalyst
    3. Asymmetry (20 pts): Risk/Reward ratio
    4. Catalyst (15 pts): Upcoming event within 60 days
    5. Crowdedness (15 pts): How uncrowded the trade is

    Usage::

        engine = AlphaDiscoveryEngine()
        result = engine.discover(tickers, snap, risk_range_results)

        # Access alpha tickers
        alpha_tickers = result["alpha_tickers"]

        # Filter by category
        early_stage = engine.get_early_stage(alpha_tickers)
        pre_catalyst = engine.get_pre_catalyst(alpha_tickers)
        macro_alpha = engine.get_macro_alpha(alpha_tickers)
    """

    def __init__(self, config: AlphaDiscoveryConfig = None):
        """
        Initialize the Alpha Discovery Engine.

        Args:
            config: AlphaDiscoveryConfig instance. Uses defaults if None.
        """
        self.config = config or AlphaDiscoveryConfig()
        self.scored_tickers: Dict[str, dict] = {}
        logger.info("AlphaDiscoveryEngine initialized")

    def score_ticker(
        self,
        ticker: str,
        snap: dict,
        risk_range_result: dict
    ) -> dict:
        """
        Score a single ticker across all 5 alpha dimensions.

        Args:
            ticker: The ticker symbol to score.
            snap: The orchestrator snap dict containing all engine outputs.
            risk_range_result: The MQA v17 risk range result for this ticker.

        Returns:
            dict with keys:
                - ticker: str
                - total_score: int (0-100)
                - grade: str (A/B/C/D/F)
                - breakdown: dict of per-dimension scores
                - sources: list of signal sources found
                - direction: str (LONG/SHORT)
                - thesis: str (human-readable thesis)
                - why: str (explanation)
                - timing: str (expected timing)
                - market_type: str
        """
        try:
            if not risk_range_result or not isinstance(risk_range_result, dict):
                risk_range_result = {}

            technical = score_technical_alpha(ticker, snap, risk_range_result, self.config)
            macro = score_macro_alpha(ticker, snap, self.config)
            asymmetry = score_asymmetry(ticker, risk_range_result, self.config)
            catalyst = score_catalyst(ticker, snap, self.config)
            crowdedness = score_crowdedness(ticker, snap, self.config)

            total = technical + macro + asymmetry + catalyst + crowdedness
            grade = _score_to_grade(total, self.config.grade_thresholds)

            sources = self._identify_sources(ticker, snap)

            breakdown = {
                "technical_alpha": technical,
                "macro_alpha": macro,
                "asymmetry": asymmetry,
                "catalyst": catalyst,
                "crowdedness": crowdedness,
            }

            direction = _determine_direction(ticker, snap, risk_range_result)
            thesis = _generate_thesis(ticker, sources, snap)
            why = _generate_why(ticker, breakdown, sources)
            timing = _determine_timing(ticker, breakdown, sources)
            market_type = _determine_market_type(ticker, snap)

            result = {
                "ticker": ticker,
                "total_score": total,
                "grade": grade,
                "breakdown": breakdown,
                "sources": sources,
                "direction": direction,
                "thesis": thesis,
                "why": why,
                "timing": timing,
                "market_type": market_type,
            }

            self.scored_tickers[ticker] = result
            return result

        except Exception as e:
            logger.error("score_ticker failed for %s: %s", ticker, e)
            return {
                "ticker": ticker,
                "total_score": 0,
                "grade": "F",
                "breakdown": {
                    "technical_alpha": 0,
                    "macro_alpha": 0,
                    "asymmetry": 0,
                    "catalyst": 0,
                    "crowdedness": 0,
                },
                "sources": [],
                "direction": "LONG",
                "thesis": "Scoring error",
                "why": "Error: {}".format(str(e)[:50]),
                "timing": "Unknown",
                "market_type": "us_equity",
            }

    def _identify_sources(self, ticker: str, snap: dict) -> List[str]:
        """Identify which signal sources contributed for this ticker."""
        sources = []

        # Check bottleneck
        bottleneck = snap.get("bottleneck_v3", {})
        for item in bottleneck.get("active_bottlenecks", []):
            if ticker in item.get("beneficiaries", []):
                sources.append("bottleneck")
                break

        # Check front-run
        fr = snap.get("front_run_candidates", [])
        for item in fr:
            if item.get("ticker") == ticker:
                sources.append("front_run")
                break

        # Check Leopold
        leopold = snap.get("leopold_scan", {})
        for setup in leopold.get("asymmetry_setups", []):
            if setup.get("ticker") == ticker:
                sources.append("leopold")
                break

        # Check Coatue
        coatue = snap.get("coatue_scan", {}).get(ticker)
        if coatue:
            sources.append("coatue")

        # Check Karsan
        karsan = snap.get("karsan_scanner", {}).get(ticker)
        if karsan:
            sources.append("karsan")

        # Check composite
        cs = snap.get("composite_signals", {}).get(ticker)
        if cs:
            sources.append("composite")

        # Check discovery
        disc = snap.get("discovery_brain", {})
        for mode, items in disc.get("by_mode", {}).items():
            for item in items:
                if item.get("ticker") == ticker:
                    sources.append("discovery")
                    break

        # Check gatekeeper
        gatekeeper = snap.get("alpha_gatekeeper", {}).get(ticker)
        if gatekeeper and gatekeeper.get("gate_status") == "PASS":
            sources.append("gatekeeper")

        # Check walk-forward
        wf = snap.get("walkforward_results", {}).get(ticker)
        if wf:
            sources.append("walkforward")

        # Check thought process
        thought = snap.get("thought_process", {}).get(ticker)
        if thought:
            sources.append("thought")

        return sources

    def discover(
        self,
        tickers: List[str],
        snap: dict,
        risk_range_results: Dict[str, dict]
    ) -> dict:
        """
        Discover alpha tickers from a universe of tickers.

        This is the main entry point, compatible with the orchestrator.py pipeline.

        Args:
            tickers: List of ticker symbols to analyze.
            snap: The orchestrator snap dict containing all engine outputs.
            risk_range_results: Dict mapping ticker -> MQA v17 risk range result.

        Returns:
            dict with keys:
                - alpha_tickers: List of scored alpha ticker dicts (sorted by score)
                - grade_distribution: Dict of grade counts
                - top_by_criteria: Dict of top tickers per dimension
                - summary: Dict with aggregate stats
        """
        logger.info("AlphaDiscoveryEngine.discover: analyzing %d tickers", len(tickers))

        alpha_tickers = []
        grade_distribution = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}

        top_technical = []
        top_macro = []
        top_asymmetry = []
        top_catalyst = []
        top_crowdedness = []

        for ticker in tickers:
            try:
                rr_result = risk_range_results.get(ticker, {})
                if not isinstance(rr_result, dict):
                    rr_result = {}

                scored = self.score_ticker(ticker, snap, rr_result)

                if scored["total_score"] >= self.config.min_alpha_score:
                    alpha_tickers.append(scored)

                grade = scored.get("grade", "F")
                if grade in grade_distribution:
                    grade_distribution[grade] += 1

                bd = scored.get("breakdown", {})
                top_technical.append((ticker, bd.get("technical_alpha", 0)))
                top_macro.append((ticker, bd.get("macro_alpha", 0)))
                top_asymmetry.append((ticker, bd.get("asymmetry", 0)))
                top_catalyst.append((ticker, bd.get("catalyst", 0)))
                top_crowdedness.append((ticker, bd.get("crowdedness", 0)))

            except Exception as e:
                logger.debug("discover: error scoring %s: %s", ticker, e)
                continue

        # Sort alpha tickers by total score descending
        alpha_tickers.sort(key=lambda x: x["total_score"], reverse=True)

        def _top_tickers(scored_list, n=5):
            """Get top N tickers by dimension score, filtering to alpha-quality only."""
            alpha_set = {a["ticker"] for a in alpha_tickers}
            filtered = [(t, s) for t, s in scored_list if t in alpha_set]
            filtered.sort(key=lambda x: x[1], reverse=True)
            return [t for t, s in filtered[:n]]

        all_scored = list(self.scored_tickers.values())

        result = {
            "alpha_tickers": alpha_tickers,
            "grade_distribution": grade_distribution,
            "top_by_criteria": {
                "technical": _top_tickers(top_technical),
                "macro": _top_tickers(top_macro),
                "asymmetry": _top_tickers(top_asymmetry),
                "catalyst": _top_tickers(top_catalyst),
                "early_stage": self._get_early_stage_tickers(all_scored),
                "pre_catalyst": self._get_pre_catalyst_tickers(all_scored),
                "uncrowded": _top_tickers(top_crowdedness),
            },
            "summary": {
                "total_analyzed": len(tickers),
                "alpha_found": len(alpha_tickers),
                "alpha_pct": round(len(alpha_tickers) / max(len(tickers), 1) * 100, 1),
                "top_score": alpha_tickers[0]["total_score"] if alpha_tickers else 0,
                "avg_score": round(
                    sum(a["total_score"] for a in alpha_tickers) / max(len(alpha_tickers), 1), 1
                ) if alpha_tickers else 0,
                "grade_breakdown": grade_distribution,
            }
        }

        logger.info(
            "AlphaDiscoveryEngine: found %d alpha tickers (%.1f%% rate), top score: %d",
            result["summary"]["alpha_found"],
            result["summary"]["alpha_pct"],
            result["summary"]["top_score"]
        )

        return result

    def _get_early_stage_tickers(self, scored_tickers: List[dict]) -> List[str]:
        """Get tickers that appear to be in early-stage accumulation phase."""
        early = []
        for st in scored_tickers:
            ticker = st.get("ticker", "")
            bd = st.get("breakdown", {})
            sources = st.get("sources", [])

            is_early = False
            if bd.get("technical_alpha", 0) >= 15 and bd.get("crowdedness", 0) >= 10:
                is_early = True
            if "discovery" in sources and st.get("total_score", 0) >= 50:
                is_early = True
            if bd.get("crowdedness", 0) >= 12 and st.get("total_score", 0) >= 55:
                is_early = True
            if not _is_major_etf_constituent(ticker) and st.get("total_score", 0) >= 60:
                is_early = True

            if is_early and ticker not in early:
                early.append(ticker)

        return early[:10]

    def _get_pre_catalyst_tickers(self, scored_tickers: List[dict]) -> List[str]:
        """Get tickers with upcoming catalysts (high catalyst score)."""
        pre = []
        for st in scored_tickers:
            ticker = st.get("ticker", "")
            bd = st.get("breakdown", {})
            sources = st.get("sources", [])

            is_pre = False
            if bd.get("catalyst", 0) >= 8:
                is_pre = True
            if "front_run" in sources and st.get("total_score", 0) >= 50:
                is_pre = True
            if "discovery" in sources and bd.get("catalyst", 0) >= 5:
                is_pre = True

            if is_pre and ticker not in pre:
                pre.append(ticker)

        return pre[:10]

    def get_early_stage(self, alpha_tickers: List[dict]) -> List[dict]:
        """
        Filter alpha tickers to those in early-stage accumulation phase.

        Early-stage tickers are those that have not yet been discovered by
        mainstream investors but show technical and fundamental signals of
        impending momentum.

        Args:
            alpha_tickers: List of scored alpha ticker dicts from discover().

        Returns:
            List of alpha ticker dicts that are in early-stage accumulation.
        """
        early = []
        for at in alpha_tickers:
            ticker = at.get("ticker", "")
            bd = at.get("breakdown", {})
            sources = at.get("sources", [])

            is_early = False
            if bd.get("technical_alpha", 0) >= 15 and bd.get("crowdedness", 0) >= 10:
                is_early = True
            if "discovery" in sources and at.get("total_score", 0) >= 50:
                is_early = True
            if not _is_major_etf_constituent(ticker) and at.get("total_score", 0) >= 60:
                is_early = True
            if bd.get("crowdedness", 0) >= 13:
                is_early = True

            if is_early:
                early.append(at)

        early.sort(
            key=lambda x: x.get("breakdown", {}).get("crowdedness", 0) * x.get("total_score", 0),
            reverse=True
        )
        return early

    def get_pre_catalyst(self, alpha_tickers: List[dict]) -> List[dict]:
        """
        Filter alpha tickers to those with upcoming catalysts.

        Pre-catalyst tickers have identifiable events within the catalyst window
        (default 60 days) that could serve as a price revaluation trigger.

        Args:
            alpha_tickers: List of scored alpha ticker dicts from discover().

        Returns:
            List of alpha ticker dicts with upcoming catalysts.
        """
        pre = []
        for at in alpha_tickers:
            bd = at.get("breakdown", {})
            sources = at.get("sources", [])

            is_pre = False
            if bd.get("catalyst", 0) >= 8:
                is_pre = True
            if "front_run" in sources:
                is_pre = True
            if "discovery" in sources and bd.get("catalyst", 0) >= 5:
                is_pre = True
            if bd.get("catalyst", 0) >= 6 and at.get("total_score", 0) >= 65:
                is_pre = True

            if is_pre:
                pre.append(at)

        pre.sort(
            key=lambda x: (x.get("breakdown", {}).get("catalyst", 0), x.get("total_score", 0)),
            reverse=True
        )
        return pre

    def get_macro_alpha(self, alpha_tickers: List[dict]) -> List[dict]:
        """
        Filter alpha tickers to those with highest macro alignment scores.

        Macro alpha tickers are those with the strongest macro tailwinds:
        bottleneck beneficiaries, quad-aligned trades, and front-run candidates.

        Args:
            alpha_tickers: List of scored alpha ticker dicts from discover().

        Returns:
            List of alpha ticker dicts sorted by macro_alpha score.
        """
        sorted_by_macro = sorted(
            alpha_tickers,
            key=lambda x: x.get("breakdown", {}).get("macro_alpha", 0),
            reverse=True
        )
        return [a for a in sorted_by_macro if a.get("breakdown", {}).get("macro_alpha", 0) >= 10]

    def get_grade_summary(self, alpha_tickers: List[dict]) -> Dict[str, list]:
        """
        Group alpha tickers by grade.

        Args:
            alpha_tickers: List of scored alpha ticker dicts.

        Returns:
            Dict mapping grade -> list of tickers.
        """
        summary = {"A": [], "B": [], "C": [], "D": [], "F": []}
        for at in alpha_tickers:
            grade = at.get("grade", "F")
            if grade in summary:
                summary[grade].append(at.get("ticker", ""))
        return summary

    def get_top_by_dimension(
        self,
        alpha_tickers: List[dict],
        dimension: str,
        n: int = 5
    ) -> List[dict]:
        """
        Get top N alpha tickers by a specific scoring dimension.

        Args:
            alpha_tickers: List of scored alpha ticker dicts.
            dimension: One of "technical_alpha", "macro_alpha", "asymmetry",
                      "catalyst", "crowdedness".
            n: Number of tickers to return.

        Returns:
            List of top N alpha ticker dicts for that dimension.
        """
        if dimension not in CRITERIA:
            logger.warning("Unknown dimension: %s. Using total_score.", dimension)
            key_fn = lambda x: x.get("total_score", 0)
        else:
            key_fn = lambda x: x.get("breakdown", {}).get(dimension, 0)

        sorted_tickers = sorted(alpha_tickers, key=key_fn, reverse=True)
        return sorted_tickers[:n]

    def get_alpha_thesis_report(self, ticker: str, alpha_tickers: List[dict]) -> Optional[dict]:
        """
        Generate a detailed thesis report for a specific alpha ticker.

        Args:
            ticker: The ticker symbol.
            alpha_tickers: List of scored alpha ticker dicts from discover().

        Returns:
            Detailed report dict, or None if ticker not found.
        """
        for at in alpha_tickers:
            if at.get("ticker") == ticker:
                bd = at.get("breakdown", {})
                report = {
                    "ticker": ticker,
                    "total_score": at.get("total_score", 0),
                    "grade": at.get("grade", "F"),
                    "direction": at.get("direction", "LONG"),
                    "thesis": at.get("thesis", ""),
                    "why": at.get("why", ""),
                    "timing": at.get("timing", ""),
                    "market_type": at.get("market_type", "us_equity"),
                    "sources": at.get("sources", []),
                    "score_breakdown": {
                        "technical_alpha": {
                            "score": bd.get("technical_alpha", 0),
                            "max": CRITERIA["technical_alpha"],
                            "pct": round(bd.get("technical_alpha", 0) / CRITERIA["technical_alpha"] * 100, 1),
                        },
                        "macro_alpha": {
                            "score": bd.get("macro_alpha", 0),
                            "max": CRITERIA["macro_alpha"],
                            "pct": round(bd.get("macro_alpha", 0) / CRITERIA["macro_alpha"] * 100, 1),
                        },
                        "asymmetry": {
                            "score": bd.get("asymmetry", 0),
                            "max": CRITERIA["asymmetry"],
                            "pct": round(bd.get("asymmetry", 0) / CRITERIA["asymmetry"] * 100, 1),
                        },
                        "catalyst": {
                            "score": bd.get("catalyst", 0),
                            "max": CRITERIA["catalyst"],
                            "pct": round(bd.get("catalyst", 0) / CRITERIA["catalyst"] * 100, 1),
                        },
                        "crowdedness": {
                            "score": bd.get("crowdedness", 0),
                            "max": CRITERIA["crowdedness"],
                            "pct": round(bd.get("crowdedness", 0) / CRITERIA["crowdedness"] * 100, 1),
                        },
                    },
                }
                return report
        return None



# ---------------------------------------------------------------------------
# CONVENIENCE FUNCTIONS (module-level, for direct use)
# ---------------------------------------------------------------------------

def run_alpha_discovery(
    tickers: List[str],
    snap: dict,
    risk_range_results: Dict[str, dict],
    config: AlphaDiscoveryConfig = None
) -> dict:
    """
    Convenience function to run alpha discovery in one call.

    Compatible with orchestrator.py pipeline - call this function directly
    from the orchestrator's run() method.

    Args:
        tickers: List of ticker symbols.
        snap: Orchestrator snap dict.
        risk_range_results: Dict of ticker -> risk range results.
        config: Optional AlphaDiscoveryConfig.

    Returns:
        Full alpha discovery result dict.
    """
    engine = AlphaDiscoveryEngine(config=config)
    return engine.discover(tickers, snap, risk_range_results)


def filter_grade_a(alpha_result: dict) -> List[dict]:
    """Extract only Grade A alpha tickers from discovery result."""
    return [a for a in alpha_result.get("alpha_tickers", []) if a.get("grade") == "A"]


def filter_grade_a_b(alpha_result: dict) -> List[dict]:
    """Extract Grade A and B alpha tickers from discovery result."""
    return [a for a in alpha_result.get("alpha_tickers", []) if a.get("grade") in ("A", "B")]


def get_alpha_ticker_list(alpha_result: dict) -> List[str]:
    """Get just the ticker symbols from alpha discovery result."""
    return [a.get("ticker", "") for a in alpha_result.get("alpha_tickers", [])]


# ---------------------------------------------------------------------------
# SELF-TEST
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Build a minimal test snap matching orchestrator.py output format
    test_snap = {
        "prices": {
            "SNSK": [10.0, 10.5, 11.0, 10.8, 11.2, 11.5, 12.0, 11.8, 12.2, 12.5,
                     13.0, 12.8, 13.2, 13.5, 14.0, 13.8, 14.2, 14.5, 15.0, 14.8],
            "SIVE": [5.0, 5.1, 5.2, 5.0, 5.3, 5.4, 5.5, 5.3, 5.6, 5.7,
                     5.8, 5.6, 5.9, 6.0, 6.1, 6.0, 6.2, 6.3, 6.4, 6.5],
            "PLTR": [20.0, 21.0, 20.5, 22.0, 21.5, 23.0, 22.5, 24.0, 23.5, 25.0,
                     24.5, 26.0, 25.5, 27.0, 26.5, 28.0, 27.5, 29.0, 28.5, 30.0],
            "NVDA": [400.0, 405.0, 410.0, 408.0, 415.0, 420.0, 418.0, 425.0, 430.0, 428.0,
                     435.0, 440.0, 438.0, 445.0, 450.0, 448.0, 455.0, 460.0, 458.0, 465.0],
        },
        "bottleneck_v3": {
            "active_bottlenecks": [
                {"name": "CPO / Co-packaged Optics", "beneficiaries": ["SNSK", "SIVE", "NXT"]},
                {"name": "HBM3E Memory", "beneficiaries": ["SNSK", "MU"]},
            ],
            "watch_bottlenecks": [
                {"name": "Data Center Power", "beneficiaries": ["VST", "CEG"]},
            ],
        },
        "front_run_candidates": [
            {
                "ticker": "SNSK",
                "why_front_run": "CPO bottleneck early stage",
                "priority": "TOP",
                "catalyst": "Earnings beat expected",
                "market_type": "us_equity",
            },
            {
                "ticker": "SIVE",
                "why_front_run": "Semiconductor supply chain",
                "priority": "HIGH",
                "catalyst": "New contract announcement",
                "market_type": "us_equity",
            },
            {
                "ticker": "PLTR",
                "why_front_run": "AI government contracts",
                "priority": "HIGH",
                "market_type": "us_equity",
            },
        ],
        "leopold_scan": {
            "asymmetry_setups": [
                {"ticker": "SNSK", "asymmetry_score": 85, "layer": "CPO", "direction": "LONG"},
                {"ticker": "SIVE", "asymmetry_score": 78, "layer": "Optics", "direction": "LONG"},
            ],
            "top_picks_by_layer": {
                "cpo": ["SNSK", "NXT"],
                "optics": ["SIVE", "COHR"],
            },
            "written_off_recovering": [],
        },
        "coatue_scan": {
            "per_ticker": {
                "SNSK": {"signal": "BUY", "rationale": "Accumulation detected"},
                "PLTR": {"signal": "BUY", "rationale": "Momentum building"},
            },
        },
        "karsan_scanner": {
            "per_ticker": {
                "SIVE": {"setup_type": "convexity", "rationale": "Vol expansion incoming"},
            },
        },
        "thought_process": {
            "SNSK": {"thesis_score": 82, "matched_frameworks": ["bottleneck", "supply_chain"]},
            "SIVE": {"thesis_score": 75, "matched_frameworks": ["leopold", "technical"]},
            "PLTR": {"thesis_score": 68, "matched_frameworks": ["ai_theme"]},
        },
        "alpha_gatekeeper": {
            "SNSK": {"gate_status": "PASS", "score": 78},
            "SIVE": {"gate_status": "PASS", "score": 72},
            "PLTR": {"gate_status": "MARGINAL", "score": 62},
        },
        "walkforward_results": {
            "SNSK": {"combined_gate_score": 76},
            "SIVE": {"combined_gate_score": 68},
            "PLTR": {"combined_gate_score": 58},
        },
        "discovery_brain": {
            "by_mode": {
                "adaptive": [{"ticker": "SNSK", "signal": "emerging"}],
                "reactive": [],
                "proactive": [{"ticker": "SIVE", "signal": "pre_catalyst"}],
            },
            "top_10": [],
            "summary": {},
        },
        "composite_signals": {
            "SNSK": {"direction": "LONG", "confidence": 0.82},
            "SIVE": {"direction": "LONG", "confidence": 0.75},
            "PLTR": {"direction": "LONG", "confidence": 0.68},
        },
    }

    # Build test risk range results (MQA v17 format)
    test_rr = {
        "SNSK": {
            "trade_trr": 16.5, "trade_lrr": 10.0,
            "trend_trr": 18.0, "trend_lrr": 9.0,
            "tail_trr": 20.0, "tail_lrr": 8.0,
            "bull_form": True, "bear_form": False,
            "trade_phase": 1, "trend_phase": 1, "tail_phase": 1,
            "rta_buy": True, "rta_add": True,
            "coiled_spring": True, "compression_score": 75.0,
            "H_trade": 0.65, "H_trend": 0.60, "H_tail": 0.58,
        },
        "SIVE": {
            "trade_trr": 7.5, "trade_lrr": 4.8,
            "trend_trr": 8.5, "trend_lrr": 4.0,
            "tail_trr": 10.0, "tail_lrr": 3.5,
            "bull_form": False, "bear_form": False,
            "trade_phase": 1, "trend_phase": 0, "tail_phase": 0,
            "rta_buy": False, "rta_add": True,
            "coiled_spring": True, "compression_score": 65.0,
            "H_trade": 0.58, "H_trend": 0.52, "H_tail": 0.50,
        },
        "PLTR": {
            "trade_trr": 35.0, "trade_lrr": 22.0,
            "trend_trr": 38.0, "trend_lrr": 20.0,
            "tail_trr": 42.0, "tail_lrr": 18.0,
            "bull_form": True, "bear_form": False,
            "trade_phase": 1, "trend_phase": 1, "tail_phase": 1,
            "rta_buy": False, "rta_add": False,
            "coiled_spring": False, "compression_score": 40.0,
            "H_trade": 0.70, "H_trend": 0.65, "H_tail": 0.60,
        },
        "NVDA": {
            "trade_trr": 500.0, "trade_lrr": 380.0,
            "trend_trr": 520.0, "trend_lrr": 360.0,
            "tail_trr": 550.0, "tail_lrr": 340.0,
            "bull_form": True, "bear_form": False,
            "trade_phase": 1, "trend_phase": 1, "tail_phase": 1,
            "rta_buy": False, "rta_add": False,
            "coiled_spring": False, "compression_score": 30.0,
            "H_trade": 0.72, "H_trend": 0.68, "H_tail": 0.62,
        },
    }

    tickers = ["SNSK", "SIVE", "PLTR", "NVDA"]

    engine = AlphaDiscoveryEngine()
    result = engine.discover(tickers, test_snap, test_rr)

    print("\n" + "=" * 60)
    print("ALPHA DISCOVERY ENGINE - SELF TEST RESULTS")
    print("=" * 60)

    print("\n[Summary]")
    print("  Total tickers analyzed: %d" % result["summary"]["total_analyzed"])
    print("  Alpha tickers found:    %d" % result["summary"]["alpha_found"])
    print("  Alpha rate:             %.1f%%" % result["summary"]["alpha_pct"])
    print("  Top score:              %d" % result["summary"]["top_score"])
    print("  Avg score:              %.1f" % result["summary"]["avg_score"])

    print("\n  Grade Distribution: %s" % result["grade_distribution"])

    print("\n--- ALPHA TICKERS (sorted by score) ---")
    for at in result["alpha_tickers"]:
        bd = at["breakdown"]
        print("\n  %s | Score: %d | Grade: %s | Direction: %s" % (
            at["ticker"].ljust(6), at["total_score"], at["grade"], at["direction"]))
        print("    Tech:%2d/25  Macro:%2d/25  Asym:%2d/20  Cat:%2d/15  Crowd:%2d/15" % (
            bd["technical_alpha"], bd["macro_alpha"], bd["asymmetry"],
            bd["catalyst"], bd["crowdedness"]))
        print("    Sources: %s" % ", ".join(at["sources"]))
        print("    Thesis: %s" % at["thesis"])
        print("    Why: %s" % at["why"])

    print("\n--- TOP BY CRITERIA ---")
    for key, val in result["top_by_criteria"].items():
        print("  %-18s: %s" % (key, val))

    print("\n--- FILTER: EARLY STAGE ---")
    early = engine.get_early_stage(result["alpha_tickers"])
    for e in early:
        print("  %s: score=%d, crowdedness=%d" % (
            e["ticker"], e["total_score"], e["breakdown"]["crowdedness"]))

    print("\n--- FILTER: PRE-CATALYST ---")
    pre = engine.get_pre_catalyst(result["alpha_tickers"])
    for p in pre:
        print("  %s: score=%d, catalyst=%d" % (
            p["ticker"], p["total_score"], p["breakdown"]["catalyst"]))

    print("\n--- FILTER: MACRO ALPHA ---")
    macro = engine.get_macro_alpha(result["alpha_tickers"])
    for m in macro:
        print("  %s: score=%d, macro=%d" % (
            m["ticker"], m["total_score"], m["breakdown"]["macro_alpha"]))

    if result["alpha_tickers"]:
        top_ticker = result["alpha_tickers"][0]["ticker"]
        report = engine.get_alpha_thesis_report(top_ticker, result["alpha_tickers"])
        if report:
            print("\n--- THESIS REPORT: %s ---" % top_ticker)
            for key, val in report.items():
                print("  %s: %s" % (key, val))

    print("\n" + "=" * 60)
    print("SELF TEST COMPLETE")
    print("=" * 60)
