"""
orchestrator.py — MacroRegime War Room Orchestrator v40-WARROOM

Redesigned from v39 to implement:
  - Multi-stage filter (Elimination → Regime Alignment → Competitive Ranking → Conviction)
  - Tier system (Tier 1/2/3) instead of threshold-based A/B/C
  - Confidence engine with causal chain scoring
  - Propagation engine for cross-asset lead/lag
  - What Changed engine for delta detection
  - Causal card engine for ticker intelligence
"""
from __future__ import annotations
import os, sys, json, math, time, logging
from datetime import datetime
from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("warroom_orchestrator")

# Import redesigned engines
try:
    from engines.warroom_engines import (
        MultiStageFilter, ConfidenceEngine, PropagationEngine,
        WhatChangedEngine, CausalCardEngine, FilteredTicker,
    )
    _WARROOM_ENGINES = True
except Exception as e:
    logger.error(f"Failed to import warroom_engines: {e}")
    _WARROOM_ENGINES = False

# Import legacy engines (backward compatible)
try:
    from data.loader import load_prices, load_snapshot, save_snapshot, snapshot_age_str
except Exception as e:
    logger.error(f"Failed to import data.loader: {e}")
    load_prices = None
    def load_snapshot(max_age_hours=12.0): return None
    def save_snapshot(x): pass
    def snapshot_age_str(): return "unknown"

try:
    from data.fred_loader import load_fred_bundle
except Exception as e:
    logger.error(f"Failed to import fred_loader: {e}")
    def load_fred_bundle(force_refresh=True):
        return {"series": {}, "meta": {"loaded": 0, "requested": 0}}

try:
    from engines.gip_engine import GIPEngine, get_playbook
except Exception as e:
    logger.error(f"Failed to import gip_engine: {e}")
    GIPEngine = None
    def get_playbook(sq, mq):
        return {"structural": sq, "monthly": mq, "best_assets": [], "worst_assets": [],
                "strategy": f"Trade {sq} regime.", "sectors_overweight": [], "sectors_underweight": [],
                "style": "", "fx": "", "bonds": ""}

try:
    from engines.risk_range_engine import RiskRangeEngine
except Exception as e:
    logger.error(f"Failed to import risk_range_engine: {e}")
    class RiskRangeEngine:
        def __init__(self, **kwargs): pass
        def run(self, prices): return {}

# Config imports
try:
    from config.settings import (
        US_SECTORS, US_FACTORS, FOREX_PAIRS, COMMODITIES, CRYPTO,
        BONDS, IHSG_UNIVERSE, MACRO_PROXIES,
    )
except Exception as e:
    logger.debug(f"Config import failed: {e}")
    US_SECTORS = {}; US_FACTORS = {}; FOREX_PAIRS = {}; COMMODITIES = {}; CRYPTO = {}
    BONDS = {}; IHSG_UNIVERSE = {}; MACRO_PROXIES = {}


def _safe_progress(cb, msg: str, pct: float):
    if cb is None:
        return
    try:
        cb(msg, float(pct))
    except Exception:
        pass


def _all_tickers() -> List[str]:
    """Aggregate all tickers from config."""
    pools = [
        list(US_SECTORS.keys()), list(US_FACTORS.keys()),
        list(FOREX_PAIRS.keys()), list(COMMODITIES.keys()),
        list(CRYPTO.keys()), list(BONDS.keys()),
        list(IHSG_UNIVERSE.keys()), list(MACRO_PROXIES.keys()),
        ["^VIX", "UUP", "EEM", "VWO", "^GSPC", "^IXIC", "^VVIX"],
    ]
    seen = set()
    out = []
    for p in pools:
        for t in p:
            if t and t not in seen:
                seen.add(t)
                out.append(t)
    return out


def _fred_fallback() -> Dict[str, pd.Series]:
    import numpy as np
    dates = pd.date_range(end=datetime.now(), periods=60, freq="MS")
    return {
        "INDPRO": pd.Series(np.linspace(100, 105, 60) + np.random.randn(60)*0.5, index=dates, name="INDPRO"),
        "CPI": pd.Series(np.linspace(300, 310, 60) + np.random.randn(60)*1, index=dates, name="CPI"),
        "UNRATE": pd.Series(np.linspace(3.5, 4.2, 60) + np.random.randn(60)*0.1, index=dates, name="UNRATE"),
        "DGS10": pd.Series(np.linspace(4.0, 4.5, 60) + np.random.randn(60)*0.1, index=dates, name="DGS10"),
        "DGS2": pd.Series(np.linspace(3.5, 4.0, 60) + np.random.randn(60)*0.1, index=dates, name="DGS2"),
        "FEDFUNDS": pd.Series([5.33]*60, index=dates, name="FEDFUNDS"),
        "PAYEMS": pd.Series(np.linspace(155000, 158000, 60), index=dates, name="PAYEMS"),
        "ICSA": pd.Series(np.linspace(220, 240, 60), index=dates, name="ICSA"),
        "HYOAS": pd.Series(np.linspace(3.5, 4.5, 60), index=dates, name="HYOAS"),
        "DGS3MO": pd.Series(np.linspace(4.2, 4.8, 60), index=dates, name="DGS3MO"),
    }


def _classify_market(ticker: str) -> str:
    if ticker in FOREX_PAIRS or "=" in ticker or ticker in ["DX-Y.NYB", "UUP"]:
        return "forex"
    if ticker in COMMODITIES or ticker in ["GC=F", "SI=F", "CL=F", "HG=F"]:
        return "commodity"
    if ticker in CRYPTO or ticker in ["BTC-USD", "ETH-USD", "SOL-USD"]:
        return "crypto"
    if ticker in IHSG_UNIVERSE or ticker.endswith(".JK"):
        return "ihsg"
    return "us_equity"


# ═══════════════════════════════════════════════════════════════════════════
# MAIN ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════

def run_warroom_orchestrator(
    progress_cb=None,
    use_cache: bool = True,
    max_age_hours: float = 12.0,
    portfolio_value: float = 100_000,
    quad_override: Optional[str] = None,
    **kwargs
) -> dict:
    """Build War Room snapshot with redesigned filtering and intelligence."""
    t0 = time.time()
    _safe_progress(progress_cb, "Initializing War Room orchestrator...", 0.01)

    result = {
        "ok": False,
        "errors": [],
        "_source": "live",
        "_generated_at": datetime.now().isoformat(),
        "build_time_s": 0,
        "prices": {},
        "fred_series": {},
        "fred_meta": {},
        "gip": {},
        "quad": "Q3",
        "monthly_quad": "Q2",
        "vix": 20.0,
        "dxy": 100.0,
        "risk_ranges": {},
        "health": {},
        "playbook": {},

        # War Room NEW outputs
        "filtered_tickers": {"tier1": [], "tier2": [], "tier3": [], "all": [], "eliminated": [], "stats": {}},
        "regime_pressures": [],
        "global_stress": {},
        "what_changed": [],
        "chain_reactions": {},
        "leadlag": [],
        "causal_cards": {},
        "confidence_scores": {},
        "propagation_network": {"nodes": [], "edges": []},

        # Legacy compatibility
        "alpha_center": {"all": [], "level_1": [], "level_2": [], "watch": [], "meta": {}},
        "composite_signals": {},
        "gamma_data": {},
        "gex_data": {},
        "vanna_data": {},
        "behavioral_macro": {},
        "news_narratives": {},
        "crypto_center": {},
        "crypto_tokens": {},
        "ihsg_foreign_flow": {},
        "ihsg_broker_proxy": {},
        "stress_test": [],
        "simulation_results": {},
        "simulation_summary": {},
        "walkforward_results": {},
        "summary": {},
    }

    try:
        # ── FRED Data ──
        _safe_progress(progress_cb, "Fetching FRED macro data...", 0.05)
        try:
            fred_bundle = load_fred_bundle(force_refresh=True)
            fred = fred_bundle.get("series", {})
            fred_meta = fred_bundle.get("meta", {})
            if fred_meta.get("loaded", 0) == 0:
                fred = _fred_fallback()
                fred_meta = {"loaded": 10, "requested": 10, "source": "synthetic_fallback"}
                result["errors"].append("fred: using synthetic fallback")
        except Exception as e:
            logger.error(f"FRED failed: {e}")
            fred = _fred_fallback()
            fred_meta = {"loaded": 10, "source": "error_fallback"}
            result["errors"].append(f"fred: {e}")

        result["fred_series"] = fred
        result["fred_meta"] = fred_meta

        # ── Prices ──
        _safe_progress(progress_cb, "Fetching prices...", 0.10)
        tickers = _all_tickers()
        prices = {}
        if load_prices is not None:
            try:
                prices = load_prices(tickers, days=756, max_age_hours=max_age_hours)
            except Exception as e:
                result["errors"].append(f"prices: {e}")
        result["prices"] = prices
        result["prices_loaded"] = len(prices)

        # ── VIX & DXY ──
        vix_last = 20.0
        vix_s = prices.get("^VIX")
        if vix_s is not None and len(vix_s) > 0:
            try: vix_last = float(pd.to_numeric(pd.Series(vix_s), errors="coerce").dropna().iloc[-1])
            except Exception: pass
        result["vix"] = vix_last

        dxy_last = 100.0
        dxy_s = prices.get("DX-Y.NYB")
        if dxy_s is not None and len(dxy_s) > 22:
            try: dxy_last = float(pd.to_numeric(pd.Series(dxy_s), errors="coerce").dropna().iloc[-1])
            except Exception: pass
        result["dxy"] = dxy_last

        # ── GIP Engine ──
        _safe_progress(progress_cb, "Running GIP regime model...", 0.20)
        quad = "Q3"
        monthly_quad = "Q2"
        if GIPEngine is not None:
            try:
                gip = GIPEngine().run(fred, prices)
                quad = getattr(gip, "structural_quad", "Q3") if not isinstance(gip, dict) else gip.get("structural_quad", "Q3")
                monthly_quad = getattr(gip, "monthly_quad", "Q2") if not isinstance(gip, dict) else gip.get("monthly_quad", "Q2")
                result["gip"] = gip if isinstance(gip, dict) else gip.__dict__ if hasattr(gip, "__dict__") else {}
            except Exception as e:
                result["errors"].append(f"gip: {e}")

        if quad_override and quad_override.startswith("Q"):
            quad = quad_override
        result["quad"] = quad
        result["monthly_quad"] = monthly_quad

        # ── Risk Ranges ──
        _safe_progress(progress_cb, "Computing Risk Ranges...", 0.30)
        try:
            rr = RiskRangeEngine(current_quad=quad, vix=vix_last).run(prices)
            result["risk_ranges"] = rr
        except Exception as e:
            result["errors"].append(f"risk_ranges: {e}")

        # ── Market Health (proxy) ──
        _safe_progress(progress_cb, "Computing market health...", 0.35)
        try:
            health_score = max(0, min(100, 50 - (vix_last - 20) * 2))
            result["health"] = {"score": health_score, "label": "HEALTHY" if health_score > 60 else "CAUTION" if health_score > 40 else "FRAGILE"}
        except Exception as e:
            result["errors"].append(f"health: {e}")

        # ── WAR ROOM ENGINES ──
        if _WARROOM_ENGINES:
            _safe_progress(progress_cb, "Running War Room intelligence engines...", 0.40)

            # 1. Build raw candidates from risk ranges + alpha center legacy
            raw_candidates = []
            ar = result["risk_ranges"].get("asset_ranges", {})
            for ticker, v in ar.items():
                comp = v.get("composite", "neutral")
                if comp == "neutral":
                    continue
                side = "long" if comp == "bullish" else "short"
                px = v.get("px", 0)
                tr = v.get("trade", {})
                lrr = tr.get("lrr", 0)
                trr = tr.get("trr", 0)
                spread = trr - lrr if trr and lrr else 0

                if side == "long":
                    entry = lrr; tp1 = lrr + spread * 0.5; tp2 = trr; stop = lrr - spread * 0.25
                else:
                    entry = trr; tp1 = trr - spread * 0.5; tp2 = lrr; stop = trr + spread * 0.25

                rr_val = abs(tp1 - entry) / max(abs(entry - stop), 0.01)
                pos = (px - lrr) / spread if spread > 0 else 0.5
                near_entry = (side == "long" and pos <= 0.35) or (side == "short" and pos >= 0.65)

                raw_candidates.append({
                    "ticker": ticker,
                    "composite": comp,
                    "direction": "LONG" if side == "long" else "SHORT",
                    "price": px,
                    "entry": entry,
                    "target_1": tp1,
                    "target_2": tp2,
                    "stop_loss": stop,
                    "rr": rr_val,
                    "near_entry": near_entry,
                    "market_type": _classify_market(ticker),
                    # Proxy scores for filter engine
                    "accumulation_score": 0.5,
                    "crowding_score": 0.5,
                    "gamma_score": 0.3,
                    "bottleneck_score": 0.3,
                    "propagation_score": 0.0,
                    "reflexivity_score": 0.0,
                    "liquidity_score": 1.0,
                    "news_signal": None,
                    "sector": "generic",
                })

            # 2. Multi-Stage Filter
            _safe_progress(progress_cb, "Stage 1-4: Multi-stage filtering...", 0.50)
            liquidity_regime = 50.0  # proxy
            shock_prob = min(1.0, (vix_last - 15) / 35)

            filter_engine = MultiStageFilter(prices, quad, vix_last, liquidity_regime, shock_prob)
            filtered = filter_engine.run(raw_candidates)
            result["filtered_tickers"] = filtered

            # 3. Confidence Engine
            _safe_progress(progress_cb, "Computing confidence scores...", 0.60)
            conf_engine = ConfidenceEngine(prices, quad, vix_last)
            confidence_scores = {}
            for item in filtered["all"]:
                t = item["ticker"]
                engine_signals = {
                    "risk_range": item["direction"],
                    "composite": item["direction"],
                }
                confidence_scores[t] = conf_engine.compute_confidence(t, engine_signals)
            result["confidence_scores"] = confidence_scores

            # 4. Propagation Engine
            _safe_progress(progress_cb, "Building propagation network...", 0.70)
            prop_engine = PropagationEngine(prices, fred)

            chain_reactions = {}
            for chain_name in ["ai_compute", "mideast_energy", "indonesia_resources"]:
                chain_reactions[chain_name] = prop_engine.detect_chain_reaction(chain_name)
            result["chain_reactions"] = chain_reactions

            # Lead/lag
            leaders = ["^VIX", "DX-Y.NYB", "CL=F", "TLT"]
            followers = ["SPY", "QQQ", "IWM", "GLD", "BTC-USD", "EEM"]
            result["leadlag"] = prop_engine.cross_asset_leadlag(leaders, followers)

            # Network
            active_tickers = [t["ticker"] for t in filtered["all"][:30]]
            nodes, edges = prop_engine.build_network(active_tickers)
            result["propagation_network"] = {
                "nodes": [{"name": n.name, "type": n.node_type, "pressure": n.pressure_intensity} for n in nodes],
                "edges": [{"source": e.source, "target": e.target, "criticality": e.criticality, "type": e.edge_type} for e in edges],
            }

            # 5. What Changed Engine
            _safe_progress(progress_cb, "Detecting regime deltas...", 0.75)
            # Try to load previous snapshot for delta
            prev_snap = None
            try:
                prev_snap = load_snapshot(max_age_hours=9999)
                if prev_snap:
                    prev_snap = {k: prev_snap[k] for k in ["quad", "vix", "dxy", "gamma_regime"] if k in prev_snap}
            except Exception:
                pass

            wc_engine = WhatChangedEngine(
                {"quad": quad, "vix": vix_last, "dxy": dxy_last, "gamma_regime": "NEUTRAL"},
                prev_snap,
            )
            result["what_changed"] = wc_engine.detect_changes()

            # 6. Causal Cards
            _safe_progress(progress_cb, "Building causal cards...", 0.80)
            news = result.get("news_narratives", {}).get("ticker_specific", {})
            bottleneck = result.get("bottleneck_research", {})
            causal_engine = CausalCardEngine(prices, news, bottleneck, result["propagation_network"])
            causal_cards = {}
            for item in filtered["tier1"] + filtered["tier2"]:
                t = item["ticker"]
                causal_cards[t] = causal_engine.generate_card(t, item["direction"], quad)
                # Attach to item
                item["causal"] = causal_cards[t]
            result["causal_cards"] = causal_cards

            # 7. Regime Pressures
            _safe_progress(progress_cb, "Computing regime pressures...", 0.85)
            # Use proxy from WhatChangedEngine logic (simplified)
            def _last(series_key, default=0):
                s = fred.get(series_key)
                if s is not None and len(s) > 0:
                    try: return float(pd.to_numeric(pd.Series(s), errors="coerce").dropna().iloc[-1])
                    except: return default
                return default

            dgs3mo = _last("DGS3MO", 4.5); fedfunds = _last("FEDFUNDS", 5.33)
            liquidity = (fedfunds - dgs3mo) / 2
            indpro = _last("INDPRO", 100); growth = (indpro - 100) / 10
            cpi = _last("CPI", 300); inflation = (cpi - 300) / 20
            volatility = (vix_last - 20) / 20
            hyoas = _last("HYOAS", 4.0); credit = -(hyoas - 4.0) / 3
            dollar = (dxy_last - 100) / 5
            dgs10 = _last("DGS10", 4.5); yields = (dgs10 - 4.5) / 2

            result["regime_pressures"] = [
                {"variable": "liquidity", "structural": round(liquidity, 2), "cyclical": round(liquidity*0.8, 2), "tactical": round(liquidity*0.6, 2), "short_term": round(liquidity*0.4, 2)},
                {"variable": "growth", "structural": round(growth, 2), "cyclical": round(growth*0.9, 2), "tactical": round(growth*0.7, 2), "short_term": round(growth*0.5, 2)},
                {"variable": "inflation", "structural": round(inflation, 2), "cyclical": round(inflation*0.8, 2), "tactical": round(inflation*0.6, 2), "short_term": round(inflation*0.4, 2)},
                {"variable": "volatility", "structural": round(volatility, 2), "cyclical": round(volatility*0.9, 2), "tactical": round(volatility*1.2, 2), "short_term": round(volatility*1.5, 2)},
                {"variable": "credit", "structural": round(credit, 2), "cyclical": round(credit*0.8, 2), "tactical": round(credit*1.1, 2), "short_term": round(credit*1.3, 2)},
                {"variable": "dollar", "structural": round(dollar, 2), "cyclical": round(dollar*0.7, 2), "tactical": round(dollar*0.9, 2), "short_term": round(dollar*1.1, 2)},
                {"variable": "yields", "structural": round(yields, 2), "cyclical": round(yields*0.8, 2), "tactical": round(yields*1.0, 2), "short_term": round(yields*1.2, 2)},
            ]

            # Global Stress
            result["global_stress"] = {
                "liquidity_stress": round(min(1.0, vix_last/40), 2),
                "systemic_fragility": round(shock_prob * 0.8, 2),
                "positioning_crowding": 0.5,
                "crash_probability": round(shock_prob, 3),
                "contagion_probability": round(min(1.0, (vix_last-20)/30), 3),
            }

        else:
            result["errors"].append("warroom_engines: not available — using legacy fallback")
            # Legacy fallback: populate alpha_center from risk ranges
            ar = result["risk_ranges"].get("asset_ranges", {})
            alpha_items = []
            for ticker, v in ar.items():
                comp = v.get("composite", "neutral")
                if comp == "neutral": continue
                side = "LONG" if comp == "bullish" else "SHORT"
                px = v.get("px", 0)
                tr = v.get("trade", {})
                alpha_items.append({
                    "ticker": ticker, "direction": side, "grade": "B",
                    "price": px, "entry": tr.get("lrr", 0), "target_1": tr.get("trr", 0),
                    "stop_loss": tr.get("lrr", 0) * 0.95, "rr": 1.5,
                })
            result["alpha_center"] = {"all": alpha_items, "level_1": [], "level_2": alpha_items, "watch": [], "meta": {"regime": quad}}

        # ── Playbook ──
        _safe_progress(progress_cb, "Building playbook...", 0.90)
        try:
            playbook = get_playbook(quad, monthly_quad)
            result["playbook"] = playbook
        except Exception as e:
            result["playbook"] = {"structural": quad, "monthly": monthly_quad, "strategy": f"Trade {quad}", "best_assets": [], "worst_assets": []}

        # ── Summary ──
        result["summary"] = {
            "regime": quad,
            "structural_quad": quad,
            "monthly_quad": monthly_quad,
            "vix": vix_last,
            "dxy": dxy_last,
            "prices_loaded": len(prices),
            "fred_loaded": fred_meta.get("loaded", 0),
            "errors": len(result["errors"]),
            "tier1_count": len(result["filtered_tickers"].get("tier1", [])),
            "tier2_count": len(result["filtered_tickers"].get("tier2", [])),
            "tier3_count": len(result["filtered_tickers"].get("tier3", [])),
            "eliminated_count": len(result["filtered_tickers"].get("eliminated", [])),
        }

        result["ok"] = True
        elapsed = time.time() - t0
        result["build_time_s"] = elapsed
        logger.info(f"War Room orchestrator complete in {elapsed:.1f}s")
        _safe_progress(progress_cb, f"Complete ({elapsed:.0f}s)", 1.0)

        try:
            save_snapshot(result)
        except Exception as e:
            logger.warning(f"Snapshot save failed: {e}")

    except Exception as e:
        logger.exception("War Room orchestrator fatal error")
        result["errors"].append(f"fatal: {e}")
        result["ok"] = False

    return result


def build_snapshot(
    progress_cb=None,
    portfolio_value: float = 100_000,
    quad_override: Optional[str] = None,
    **kwargs
) -> dict:
    """Legacy-compatible entry point."""
    return run_warroom_orchestrator(
        progress_cb=progress_cb,
        portfolio_value=portfolio_value,
        quad_override=quad_override,
        **kwargs
    )


def build_snapshot_v40(
    portfolio_value: float = 100000,
    quad_override: str = None,
    progress_cb=None,
    **kwargs,
) -> dict:
    """V40 entry point — delegates to War Room orchestrator."""
    return run_warroom_orchestrator(
        progress_cb=progress_cb,
        portfolio_value=portfolio_value,
        quad_override=quad_override,
        **kwargs
    )
