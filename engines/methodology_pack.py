"""engines/methodology_pack.py — Consolidated Investor Methodologies (Sprint 10)

ALL methodology-driven (NOT portfolio matching). Each function asks:
"If I were [Investor], what would I do with this ticker/market state?"

Engines packed (compact for efficiency):
  1. YVES LAMOUREUX     — Behavioral relabeling, narrative divergence
  2. SOROS              — Reflexivity stages (Inception → Acceleration → Twilight → Reversal)
  3. SCHADNER           — Transition risk, regime-conditional vol, fat-tail premium
  4. DRUCKENMILLER      — Liquidity-first, position-size by macro asymmetry
  5. TIER 1 ALPHA       — Dealer gamma + 0DTE flow + mechanical structure
  6. PROFPLUM99         — Options flow / UOA contextualization (Hedgeye layer)

Each evaluator returns:
  {matched: bool, score: 0-100, role: str, thesis: str, rationale: [str]}
"""
from __future__ import annotations
import math, logging
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════
# 1. YVES LAMOUREUX — Behavioral Relabeling
# ════════════════════════════════════════════════════════════════════════
# Yves' core: when CROWD label diverges from FLOW data → opportunity window.
# E.g., crowd says "bubble" + flow says "rotation" = behavioral divergence.

YVES_NARRATIVE_FRAMES = {
    "bubble_vs_rotation": {
        "crowd_label": "bubble",
        "smart_money_label": "capital rotation",
        "applies_to": ["NVDA", "AVGO", "TSM", "AMD", "BE", "VST", "CEG", "CRWV", "LITE",
                       "MU", "GOOGL", "AMZN", "META"],
        "thesis": "Crowd: fear-based bubble label. Smart money: structural flow from hyperscaler capex to silicon FCF. $12T funded.",
    },
    "stagflation_vs_inflation_kuznets": {
        "crowd_label": "stagflation crash",
        "smart_money_label": "fiscal dominance + real asset bid",
        "applies_to": ["GLD", "SLV", "GDX", "GDXJ", "BTC-USD", "VST", "CCJ"],
        "thesis": "Crowd: stagflation = sell everything. Smart money: real assets bid as fiat monetized + interest cost > defense.",
    },
    "ai_replace_workers_vs_payroll_tam": {
        "crowd_label": "AI bubble — no profits",
        "smart_money_label": "$4T digital + $6T physical AI TAM vs payroll",
        "applies_to": ["GOOGL", "AMZN", "MSFT", "NVDA", "PLTR"],
        "thesis": "COATUE radical reframe: size AI against payroll, NOT IT budget. $10T+ TAM unlocked.",
    },
    "intel_dead_vs_strategic": {
        "crowd_label": "Intel is dead",
        "smart_money_label": "US-backed turnaround binary",
        "applies_to": ["INTC"],
        "thesis": "Crowd capitulated. Leopold: USG won't let Intel die (national security). Use CALLS for binary.",
    },
    "bitcoin_miner_extinct_vs_stranded_power": {
        "crowd_label": "BTC miners doomed by halvings",
        "smart_money_label": "stranded power assets for AI hosting",
        "applies_to": ["CORZ", "IREN", "APLD", "CIFR", "RIOT", "MARA", "BTDR"],
        "thesis": "Crowd: BTC mining unsustainable. Smart money: pre-connected power infra = AI hosting goldmine.",
    },
}


def evaluate_yves(ticker: str, prices_series=None, news_sentiment: Optional[float] = None) -> Dict:
    """
    Yves behavioral framework:
    1. Match ticker to known narrative-divergence frame
    2. Check momentum vs sentiment divergence
    """
    t = ticker.upper()
    result = {"framework": "Yves", "matched": False, "score": 0, "role": None,
              "thesis": None, "rationale": [], "narrative_divergence": False}
    
    for frame_name, frame in YVES_NARRATIVE_FRAMES.items():
        if t in frame["applies_to"]:
            result.update({
                "matched": True,
                "score": 80,
                "role": f"Behavioral Divergence — {frame_name.replace('_', ' ').title()}",
                "thesis": frame["thesis"],
                "narrative_divergence": True,
            })
            result["rationale"].append(
                f"Crowd says: '{frame['crowd_label']}' | Smart money: '{frame['smart_money_label']}'"
            )
            break
    
    # Momentum vs sentiment divergence check
    if prices_series is not None and news_sentiment is not None:
        try:
            s = pd.to_numeric(prices_series, errors="coerce").dropna()
            if len(s) >= 21:
                mom_21d = float(s.iloc[-1] / s.iloc[-21] - 1)
                # Positive price + negative news → contrarian opportunity
                if mom_21d > 0.05 and news_sentiment < -0.2:
                    result["matched"] = True
                    result["score"] = max(result["score"], 75)
                    result["rationale"].append(
                        f"⚡ Behavioral divergence: price +{mom_21d:.0%} 21d while news sentiment {news_sentiment:+.2f}"
                    )
                    result["narrative_divergence"] = True
                elif mom_21d < -0.05 and news_sentiment > 0.2:
                    result["matched"] = True
                    result["score"] = max(result["score"], 70)
                    result["rationale"].append(
                        f"⚠️ Reverse divergence: price {mom_21d:.0%} 21d but news sentiment {news_sentiment:+.2f}"
                    )
        except Exception:
            pass
    
    return result


# ════════════════════════════════════════════════════════════════════════
# 2. SOROS — Reflexivity Stage Analysis
# ════════════════════════════════════════════════════════════════════════
# Boom-bust stages: Inception → Acceleration → Testing → Twilight → Reversal
# Position playbook differs DRASTICALLY per stage.

SOROS_STAGE_PLAYBOOK = {
    "INCEPTION": {"score": 75, "position": "Build initial", "size": 0.5,
                  "thesis": "Trend underway, doubted. Best risk/reward."},
    "ACCELERATION": {"score": 85, "position": "Ride trend", "size": 1.0,
                     "thesis": "Self-reinforcing. Late but acceptable. Tighten stop."},
    "TESTING": {"score": 55, "position": "Trim, hold core", "size": 0.5,
                "thesis": "Reality test. Sentiment wobbling. Take chips off table."},
    "TWILIGHT": {"score": 30, "position": "Exit most", "size": 0.2,
                 "thesis": "Cracks visible. Smart money exiting. Hold trim only."},
    "REVERSAL": {"score": 90, "position": "REVERSE position (short)", "size": -1.0,
                 "thesis": "Bubble burst. Best risk/reward to SHORT — fade extremes."},
}


def evaluate_soros(boom_bust_stage: str, super_bubble_score: float = 0,
                   ticker: str = "") -> Dict:
    """Soros reflexivity: stage = playbook"""
    result = {"framework": "Soros", "matched": False, "score": 0, "role": None,
              "thesis": None, "rationale": [], "position_size_multiplier": 1.0}
    
    pb = SOROS_STAGE_PLAYBOOK.get(boom_bust_stage)
    if pb:
        result.update({
            "matched": True,
            "score": pb["score"],
            "role": f"Soros — {boom_bust_stage}",
            "thesis": pb["thesis"],
            "stage": boom_bust_stage,
            "position_size_multiplier": pb["size"],
            "playbook": pb["position"],
        })
        result["rationale"].append(f"{boom_bust_stage}: {pb['thesis']} → {pb['position']} (size {pb['size']:+.1f}x)")
        
        # Super-bubble overlay
        if super_bubble_score:
            try:
                s = float(super_bubble_score)
                if s >= 70 and boom_bust_stage in ("TWILIGHT", "TESTING"):
                    result["score"] += 10
                    result["rationale"].append(f"⚠️ Super-bubble score {s:.0f}/100 — exit accelerated")
                elif s >= 70 and boom_bust_stage == "ACCELERATION":
                    result["rationale"].append(f"🚨 Super-bubble {s:.0f}/100 IN acceleration = peak euphoria warning")
            except Exception:
                pass
    
    return result


# ════════════════════════════════════════════════════════════════════════
# 3. SCHADNER — Vol Risk Management + Transition Risk + BS Decomposition
# ════════════════════════════════════════════════════════════════════════
# W-Schadner: regime-conditional vol, fat-tail premium, transition risk
# Core: vol surface KNOWS more about regime change than spot price.
# Augmented: Black-Scholes IV decomposition into diffusive + jump components.

def schadner_bs_decomposition(rv_21: float, rv_60: float, rv_252: float,
                              vix: float) -> Dict:
    """
    Decompose total implied vol premium into:
      - Diffusive component (Black-Scholes baseline, ~RV)
      - Jump risk premium (fat-tail mispricing)
      - Transition premium (regime-change expectation)
    
    Returns relative richness of each layer.
    """
    if rv_21 <= 0 or rv_60 <= 0:
        return {"ok": False}
    
    # Diffusive baseline (annualized, BS assumption: continuous returns)
    diffusive_baseline = rv_60  # smoothed RV as Black-Scholes diffusive proxy
    
    # Total implied premium proxy (VIX is annualized %, scale to decimal)
    total_iv_implied = (vix / 100) if vix > 0 else rv_60
    
    # Jump risk premium = total IV - diffusive (kurtosis premium)
    jump_premium = max(0, total_iv_implied - diffusive_baseline)
    jump_premium_pct = jump_premium / max(diffusive_baseline, 0.001)
    
    # Transition premium = recent RV deviation from longer baseline
    if rv_252 > 0:
        transition_signal = (rv_21 - rv_252) / max(rv_252, 0.001)
    else:
        transition_signal = (rv_21 - rv_60) / max(rv_60, 0.001)
    
    # Recommendations
    structure = None
    rationale = []
    if jump_premium_pct > 0.30:
        structure = "BUY_CONVEXITY"
        rationale.append(f"Jump premium {jump_premium_pct*100:.0f}% rich — BS underprices tails. Buy OTM calls/puts.")
    elif jump_premium_pct < 0.10 and rv_21 < rv_60 * 0.85:
        structure = "SELL_PREMIUM_WITH_TAIL_HEDGE"
        rationale.append("Diffusive vol cheap + low jump premium. Sell iron condor + cheap OTM wing hedge.")
    
    if abs(transition_signal) > 0.30:
        rationale.append(
            f"⚠️ Transition signal {transition_signal*100:+.0f}% — regime instability. "
            "Schadner: BS Greeks unreliable when transition active. Reduce vol size."
        )
    
    return {
        "ok": True,
        "diffusive_baseline_pct": round(diffusive_baseline * 100, 2),
        "total_iv_implied_pct": round(total_iv_implied * 100, 2),
        "jump_premium_pct": round(jump_premium_pct * 100, 2),
        "transition_signal_pct": round(transition_signal * 100, 2),
        "recommended_structure": structure,
        "bs_rationale": rationale,
    }


def evaluate_schadner(ticker: str, prices_series=None, vix: float = 20.0,
                      markov_v3: Optional[Dict] = None) -> Dict:
    """
    Schadner methodology with BS decomposition:
    - Detect realized vol REGIME CHANGE (not just level)
    - Decompose IV into diffusive + jump + transition components
    - Cross-reference with Markov change-point alert
    - Recommend structure (buy convexity vs sell premium + tail hedge)
    """
    result = {"framework": "VolDecomp", "matched": False, "score": 0, "role": None,
              "thesis": None, "rationale": [], "transition_risk": "LOW",
              "bs_decomposition": None}
    
    if prices_series is None:
        return result
    
    try:
        s = pd.to_numeric(prices_series, errors="coerce").dropna()
        if len(s) < 60:
            return result
        rets = s.pct_change().dropna()
        rv_21 = float(rets.tail(21).std() * math.sqrt(252))
        rv_60 = float(rets.tail(60).std() * math.sqrt(252))
        rv_252 = float(rets.tail(252).std() * math.sqrt(252)) if len(rets) >= 252 else rv_60
        
        # Vol regime classification
        vol_ratio = rv_21 / max(rv_60, 0.001)
        transition_score = 0
        
        if vol_ratio > 1.5:
            result["transition_risk"] = "HIGH_EXPANSION"
            transition_score = 80
            result["rationale"].append(f"⚠️ Vol expanding: 21d RV {rv_21*100:.1f}% vs 60d {rv_60*100:.1f}% (ratio {vol_ratio:.2f})")
        elif vol_ratio < 0.65:
            result["transition_risk"] = "VOL_COMPRESSION"
            transition_score = 60
            result["rationale"].append(f"⚡ Vol compressing: ratio {vol_ratio:.2f} — coil before breakout")
        elif vol_ratio > 1.2:
            result["transition_risk"] = "MILD_EXPANSION"
            transition_score = 50
        
        # Cross-check with Markov change-point alert
        if markov_v3 and markov_v3.get("change_point_alert"):
            transition_score += 20
            result["rationale"].append(
                f"🚨 Markov CP alert {markov_v3.get('change_point_probability', 0):.0%} "
                f"— Schadner sees regime transition forming"
            )
        
        # VIX context
        if vix >= 25:
            transition_score = min(100, transition_score + 10)
            result["rationale"].append(f"VIX {vix:.0f} elevated — tail premium expanding")
        
        # ── Black-Scholes IV Decomposition (the NEW layer) ──
        bs = schadner_bs_decomposition(rv_21, rv_60, rv_252, vix)
        if bs.get("ok"):
            result["bs_decomposition"] = bs
            for r in bs.get("bs_rationale", []):
                result["rationale"].append(r)
            # Boost score if BS gives clear structure recommendation
            if bs.get("recommended_structure"):
                transition_score = min(100, transition_score + 10)
        
        if transition_score >= 50:
            result["matched"] = True
            result["score"] = transition_score
            result["role"] = f"Schadner — {result['transition_risk']}"
            
            # Build thesis from BS recommendation if available
            structure = (bs or {}).get("recommended_structure")
            if structure == "BUY_CONVEXITY":
                result["thesis"] = (
                    "Vol surface signals regime transition + jump premium rich. "
                    "Buy convexity: long straddles, OTM calls/puts. BS underprices tails."
                )
            elif structure == "SELL_PREMIUM_WITH_TAIL_HEDGE":
                result["thesis"] = (
                    "Diffusive vol cheap + low jump premium. Sell iron condor + buy cheap OTM wing. "
                    "Schadner: collect premium but hedge transition tail."
                )
            else:
                result["thesis"] = (
                    "Vol regime in transition. " +
                    ("Buy convexity (long straddles, VIX calls)." if "EXPANSION" in result["transition_risk"]
                     else "Sell premium into compression but hedge tail.")
                )
    except Exception as e:
        logger.debug(f"Schadner eval failed for {ticker}: {e}")
    
    return result


# ════════════════════════════════════════════════════════════════════════
# 4. DRUCKENMILLER — Liquidity-First Macro
# ════════════════════════════════════════════════════════════════════════
# "I never give a damn about earnings. I look at liquidity."
# Core: Fed balance sheet trajectory + global liquidity drives all assets.

DRUCKENMILLER_LIQUIDITY_PLAYS = {
    # Long when liquidity expanding
    "QQQ": {"liquidity_beta": 1.5, "thesis": "Long-duration growth = liquidity sensitive"},
    "BTC-USD": {"liquidity_beta": 2.5, "thesis": "Maximum-duration liquidity asset"},
    "GLD": {"liquidity_beta": 1.3, "thesis": "Real asset when real yields fall"},
    "NVDA": {"liquidity_beta": 1.8, "thesis": "Speculative leader benefits from easing"},
    "TSLA": {"liquidity_beta": 2.0, "thesis": "High-multiple growth + liquidity"},
    "MSTR": {"liquidity_beta": 2.8, "thesis": "Leveraged BTC = max liquidity beta"},
    "ARKK": {"liquidity_beta": 2.2, "thesis": "Disruption basket = high beta"},
    # Negative beta to tight liquidity
    "IWM": {"liquidity_beta": 1.4, "thesis": "Small caps suffer in tightening", "fragile": True},
    "KRE": {"liquidity_beta": 1.2, "thesis": "Regional banks deposit flight risk", "fragile": True},
    "XLF": {"liquidity_beta": 1.1, "thesis": "Bank NIM + credit risk"},
}


def evaluate_druckenmiller(ticker: str, fred: Optional[Dict] = None) -> Dict:
    """Druckenmiller: liquidity drives everything. Check Fed balance sheet trend."""
    result = {"framework": "Druckenmiller", "matched": False, "score": 0, "role": None,
              "thesis": None, "rationale": [], "liquidity_regime": "NEUTRAL"}
    
    t = ticker.upper()
    if t not in DRUCKENMILLER_LIQUIDITY_PLAYS:
        return result
    
    # Detect liquidity regime from Fed balance sheet (WALCL)
    liquidity_easing = None
    try:
        if fred and fred.get("WALCL") is not None:
            walcl = pd.to_numeric(fred["WALCL"], errors="coerce").dropna()
            if len(walcl) >= 120:
                recent = walcl.tail(60).mean()
                prior = walcl.iloc[-120:-60].mean()
                if recent > prior * 1.005:
                    liquidity_easing = True
                    result["liquidity_regime"] = "EASING"
                elif recent < prior * 0.995:
                    liquidity_easing = False
                    result["liquidity_regime"] = "TIGHTENING"
                else:
                    result["liquidity_regime"] = "STABLE"
    except Exception:
        pass
    
    play = DRUCKENMILLER_LIQUIDITY_PLAYS[t]
    beta = play["liquidity_beta"]
    
    if liquidity_easing is True:
        result["matched"] = True
        result["score"] = min(95, 60 + beta * 15)
        result["role"] = f"Druckenmiller LONG (β={beta:.1f}) — Liquidity EASING"
        result["thesis"] = play["thesis"]
        result["direction_bias"] = "LONG"
        result["rationale"].append(f"Fed balance sheet expanding. Liquidity-β {beta:.1f}x play.")
    elif liquidity_easing is False:
        if play.get("fragile"):
            result["matched"] = True
            result["score"] = 75
            result["role"] = f"Druckenmiller SHORT (fragile) — Liquidity TIGHTENING"
            result["thesis"] = play["thesis"]
            result["direction_bias"] = "SHORT"
            result["rationale"].append(f"Tightening + fragile asset. Druckenmiller short setup.")
        else:
            result["matched"] = True
            result["score"] = 40
            result["role"] = f"Druckenmiller AVOID — Liquidity TIGHTENING"
            result["thesis"] = "Reduce exposure. Liquidity-β plays don't work in tightening."
    else:
        # Neutral
        result["matched"] = True
        result["score"] = 50
        result["role"] = f"Druckenmiller MONITOR (β={beta:.1f})"
        result["thesis"] = "Liquidity regime ambiguous. Wait for Fed signal."
    
    return result


# ════════════════════════════════════════════════════════════════════════
# 5. TIER 1 ALPHA — Dealer Mechanical Structure
# ════════════════════════════════════════════════════════════════════════
# JPMorgan estimate 90% volume = systematic.
# Front-run The Machine via dealer positioning + 0DTE flow + vol term structure.

def evaluate_tier1alpha(ticker: str, gamma_data: Dict = None, prices_series=None,
                       vix: float = 20.0) -> Dict:
    """
    Tier 1 Alpha methodology:
    - Dealer gamma positioning (positive = pinning, negative = trend amplification)
    - 0DTE flow concentration (proxy)
    - Vol term structure (implied vs realized)
    """
    result = {"framework": "Tier1Alpha", "matched": False, "score": 0, "role": None,
              "thesis": None, "rationale": [], "mechanical_regime": None}
    
    if not gamma_data or not gamma_data.get("ok"):
        return result
    
    regime = (gamma_data.get("regime") or "").upper()
    max_pain = gamma_data.get("max_pain")
    call_wall = gamma_data.get("call_wall")
    put_wall = gamma_data.get("put_wall")
    
    score = 0
    rationale = []
    
    if regime in ("POSITIVE", "DEEP_POSITIVE"):
        result["mechanical_regime"] = "PINNING"
        score = 75
        rationale.append("Dealers LONG gamma → mean reversion + range-bound. Pin to Max Pain.")
        if max_pain:
            rationale.append(f"Magnet level: ${max_pain:.2f}")
    elif regime in ("NEGATIVE", "DEEP_NEGATIVE"):
        result["mechanical_regime"] = "AMPLIFICATION"
        score = 85
        rationale.append("Dealers SHORT gamma → trend amplification. Breakouts accelerate.")
        rationale.append("Key levels become acceleration zones, not support/resistance.")
    elif regime in ("NEUTRAL", "FLAT"):
        result["mechanical_regime"] = "TRANSITION"
        score = 60
        rationale.append("Gamma flip zone. Direction TBD by next macro print.")
    
    # 0DTE proxy: VIX vs RV (if available)
    if prices_series is not None and vix > 0:
        try:
            s = pd.to_numeric(prices_series, errors="coerce").dropna()
            if len(s) >= 21:
                rv = float(s.pct_change().tail(21).std() * math.sqrt(252) * 100)
                ratio = vix / max(rv, 1)
                if ratio < 0.8:
                    rationale.append(f"⚡ VIX/RV {ratio:.2f} — vol mispriced LOW, 0DTE call buyers underrepresented")
                    score = min(100, score + 10)
                elif ratio > 1.3:
                    rationale.append(f"VIX/RV {ratio:.2f} — vol mispriced HIGH, fade 0DTE put buying")
        except Exception:
            pass
    
    if score > 0:
        result["matched"] = True
        result["score"] = score
        result["role"] = f"Tier1Alpha — {result['mechanical_regime']}"
        result["thesis"] = " ".join(rationale[:2])
        result["rationale"] = rationale
    
    return result


# ════════════════════════════════════════════════════════════════════════
# 6. PROFPLUM99 — Options Flow Contextualization
# ════════════════════════════════════════════════════════════════════════
# Flow is NOT direction. Context with Risk Range is everything.
# UOA + Risk Range location = accumulation/distribution signal.

def evaluate_profplum99(ticker: str, gamma_data: Dict = None, greeks_data: Dict = None,
                        risk_range: Dict = None, composite_signal: Dict = None) -> Dict:
    """
    profplum99 methodology:
    - Unusual options activity (UOA) context
    - Cross-reference with Risk Range location (Trade low/high)
    - Sweep type detection (proxy)
    """
    result = {"framework": "FlowContext", "matched": False, "score": 0, "role": None,
              "thesis": None, "rationale": [], "flow_interpretation": None}
    
    if not (gamma_data and gamma_data.get("ok")) and not (greeks_data and greeks_data.get("ok")):
        return result
    
    # Get gamma + greek signals
    delta_signal = ""
    if greeks_data:
        delta_signal = (greeks_data.get("delta", "") or "").lower()
        composite = (greeks_data.get("composite", "") or "").upper()
    else:
        composite = ""
    
    # Get price location within Risk Range
    if not risk_range:
        return result
    
    trade = risk_range.get("trade", {})
    trade_l = trade.get("lrr")
    trade_r = trade.get("trr")
    px = risk_range.get("px")
    
    if not (trade_l and trade_r and px):
        return result
    
    position_in_range = (px - trade_l) / max(trade_r - trade_l, 0.001)
    
    score = 0
    rationale = []
    
    # Long delta + price at Trade low = accumulation
    if "long" in delta_signal and position_in_range <= 0.35:
        result["flow_interpretation"] = "ACCUMULATION"
        score = 85
        rationale.append("✅ ACCUMULATION: long-delta flow at Trade low — institutional buy zone")
    # Long delta + price at Trade high = late chasing (fade)
    elif "long" in delta_signal and position_in_range >= 0.65:
        result["flow_interpretation"] = "LATE_CHASING"
        score = 70
        rationale.append("⚠️ LATE CHASING: long-delta flow at Trade high — fade FOMO")
    # Short delta + price at Trade high = distribution
    elif "short" in delta_signal and position_in_range >= 0.65:
        result["flow_interpretation"] = "DISTRIBUTION"
        score = 85
        rationale.append("🔴 DISTRIBUTION: short-delta flow at Trade high — institutional sell zone")
    # Short delta + price at Trade low = hedging (not directional)
    elif "short" in delta_signal and position_in_range <= 0.35:
        result["flow_interpretation"] = "HEDGING"
        score = 55
        rationale.append("Short-delta at Trade low = likely hedging, NOT new short conviction")
    elif composite == "BULLISH" or composite == "BEARISH":
        result["flow_interpretation"] = "DIRECTIONAL"
        score = 65
        rationale.append(f"Directional bias: {composite}")
    
    # Cross-check with composite signal
    if composite_signal:
        cs_dir = composite_signal.get("direction")
        if result["flow_interpretation"] == "ACCUMULATION" and cs_dir == "LONG":
            score = min(100, score + 15)
            rationale.append(f"✓ Composite signal confirms accumulation (direction {cs_dir}, conf {composite_signal.get('confidence',0):.0%})")
        elif result["flow_interpretation"] == "DISTRIBUTION" and cs_dir == "SHORT":
            score = min(100, score + 15)
            rationale.append(f"✓ Composite signal confirms distribution")
        elif result["flow_interpretation"] in ("ACCUMULATION", "DISTRIBUTION") and cs_dir == "AVOID":
            score *= 0.6
            rationale.append("⚠️ Multi-signal contradicts flow — reduce conviction")
    
    if score >= 50:
        result["matched"] = True
        result["score"] = round(score, 1)
        result["role"] = f"profplum99 — {result['flow_interpretation']}"
        result["thesis"] = rationale[0] if rationale else ""
        result["rationale"] = rationale
    
    return result


# ════════════════════════════════════════════════════════════════════════
# UNIFIED METHODOLOGY DISPATCHER
# ════════════════════════════════════════════════════════════════════════

def evaluate_all_pack(
    ticker: str,
    prices_series=None,
    boom_bust_stage: str = "ACCELERATION",
    super_bubble_score: float = 0,
    vix: float = 20.0,
    fred: Optional[Dict] = None,
    gamma_data: Optional[Dict] = None,
    greeks_data: Optional[Dict] = None,
    markov_v3: Optional[Dict] = None,
    risk_range: Optional[Dict] = None,
    composite_signal: Optional[Dict] = None,
    news_sentiment: Optional[float] = None,
) -> Dict:
    """Run all 6 methodology evaluations for a ticker."""
    return {
        "yves": evaluate_yves(ticker, prices_series, news_sentiment),
        "soros": evaluate_soros(boom_bust_stage, super_bubble_score, ticker),
        "schadner": evaluate_schadner(ticker, prices_series, vix, markov_v3),
        "druckenmiller": evaluate_druckenmiller(ticker, fred),
        "tier1alpha": evaluate_tier1alpha(ticker, gamma_data, prices_series, vix),
        "profplum99": evaluate_profplum99(ticker, gamma_data, greeks_data, risk_range, composite_signal),
    }
