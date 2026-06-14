"""
engines/integrator_guide.py — Integration Hub v2.0 (Attachment 4 Clean — No Alert/Paper Trade)
Wire 8 engine baru ke Orchestrator. Import & panggil enhance_snapshot(snap, prices).
"""
from __future__ import annotations
import logging
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger("integrator_guide")

# ── Import 8 engine baru (defensive fallbacks) ──
try:
    from engines.walkforward_engine import WalkForwardEngine, filter_by_walkforward
except Exception as e:
    logger.warning(f"WalkForwardEngine import failed: {e}")
    WalkForwardEngine = None
    def filter_by_walkforward(rows, wf, require_pass=True): return rows

try:
    from engines.signal_decay_engine import SignalDecayEngine
except Exception as e:
    logger.warning(f"SignalDecayEngine import failed: {e}")
    SignalDecayEngine = None

try:
    from engines.reflexivity_coefficient import ReflexivityEngine
except Exception as e:
    logger.warning(f"ReflexivityEngine import failed: {e}")
    ReflexivityEngine = None

try:
    from engines.anti_fragility_engine import AntiFragilityEngine
except Exception as e:
    logger.warning(f"AntiFragilityEngine import failed: {e}")
    AntiFragilityEngine = None

try:
    from engines.fractional_kelly_engine import FractionalKellyEngine
except Exception as e:
    logger.warning(f"FractionalKellyEngine import failed: {e}")
    FractionalKellyEngine = None

try:
    from engines.bayesian_fusion_engine import BayesianFusionEngine
except Exception as e:
    logger.warning(f"BayesianFusionEngine import failed: {e}")
    BayesianFusionEngine = None

try:
    from engines.duration_hmm_engine import run_duration_hmm
except Exception as e:
    logger.warning(f"DurationHMM import failed: {e}")
    run_duration_hmm = None

try:
    from engines.cri_v2_engine import CRIv2Engine
except Exception as e:
    logger.warning(f"CRIv2Engine import failed: {e}")
    CRIv2Engine = None


def enhance_snapshot(snap: Dict, prices: Dict, portfolio_value: float = 100_000) -> Dict:
    """
    MAIN INTEGRATION FUNCTION.
    Terima snapshot dari orchestrator, enrich dengan 8 engine baru.
    Panggil ini di akhir run_orchestrator() sebelum return result.
    """
    if not snap or not snap.get("ok"):
        return snap

    logger.info("=" * 60)
    logger.info("ATTACHMENT 4 ENGINE INTEGRATION — Enhancing snapshot...")

    # ── 1. IDHL per ticker ──
    if SignalDecayEngine is not None:
        logger.info("[1/8] Computing IDHL (Signal Decay)...")
        try:
            sd_engine = SignalDecayEngine()
            idhl_results = {}
            for t, s in prices.items():
                idhl_results[t] = sd_engine.compute_for_ticker(t, s)
            snap["idhl_data"] = idhl_results
            # Attach ke alpha items
            for item in snap.get("alpha_center", {}).get("all", []):
                t = item.get("ticker")
                if t in idhl_results:
                    item["idhl"] = idhl_results[t]["idhl"]
                    item["idhl_class"] = idhl_results[t]["classification"]
                    item["idhl_tradeable"] = idhl_results[t]["tradeable"]
            logger.info(f"IDHL computed for {len(idhl_results)} tickers")
        except Exception as e:
            logger.error(f"IDHL failed: {e}")

    # ── 2. RC (Reflexivity Coefficient) per ticker ──
    if ReflexivityEngine is not None:
        logger.info("[2/8] Computing RC (Reflexivity)...")
        try:
            rc_engine = ReflexivityEngine()
            rc_results = {}
            for t, s in prices.items():
                opts = snap.get("greeks_data", {}).get(t, {}) if snap.get("greeks_data") else {}
                pc = opts.get("pc_ratio", 1.0) if isinstance(opts, dict) else 1.0
                sentiment = pd.Series([1.0 / max(pc, 0.1)] * 20)
                rc_results[t] = rc_engine.compute_rc(s, sentiment)
            snap["rc_data"] = rc_results
            for item in snap.get("alpha_center", {}).get("all", []):
                t = item.get("ticker")
                if t in rc_results:
                    item["rc"] = rc_results[t]["rc"]
                    item["rc_level"] = rc_results[t]["level"]
                    if rc_results[t]["level"] == "HIGH" and item.get("direction") == "LONG":
                        item["rc_override"] = "HOLD — Soros loop active, avoid directional"
            logger.info(f"RC computed for {len(rc_results)} tickers")
        except Exception as e:
            logger.error(f"RC failed: {e}")

    # ── 3. AFS (Anti-Fragility Score) portfolio level ──
    if AntiFragilityEngine is not None:
        logger.info("[3/8] Computing AFS (Anti-Fragility)...")
        try:
            afs_engine = AntiFragilityEngine()
            sizing = snap.get("portfolio_sizing_v2", {})
            cash_pct = sizing.get("cash_pct", 0.25) if isinstance(sizing, dict) else 0.25
            afs_result = afs_engine.compute_afs(prices, cash_pct=cash_pct)
            snap["afs_data"] = afs_result
            logger.info(f"AFS = {afs_result['afs']} ({afs_result['label']})")
        except Exception as e:
            logger.error(f"AFS failed: {e}")

    # ── 4. Walk-Forward Backtest untuk alpha items ──
    if WalkForwardEngine is not None:
        logger.info("[4/8] Running Walk-Forward Backtest...")
        try:
            wf_engine = WalkForwardEngine()
            setups = []
            for item in snap.get("alpha_center", {}).get("all", []):
                setups.append({
                    "ticker": item.get("ticker"),
                    "direction": item.get("direction", "LONG"),
                    "entry": item.get("entry", 0),
                    "stop": item.get("stop_loss", 0),
                    "target": item.get("target_1", 0),
                })
            wf_results = {}
            for setup in setups[:20]:
                t = setup["ticker"]
                if t in prices:
                    wf_results[t] = wf_engine.run(
                        t, prices[t], setup["direction"],
                        setup["entry"], setup["stop"], setup["target"]
                    )
            snap["walkforward_results"] = {
                t: {
                    "consistency": r.consistency_score,
                    "robustness": r.robustness_score,
                    "avg_win_rate": r.avg_win_rate,
                    "avg_sharpe": r.avg_sharpe,
                    "passes_gate": r.passes_gate,
                    "n_windows": r.n_windows,
                }
                for t, r in wf_results.items()
            }
            all_items = snap.get("alpha_center", {}).get("all", [])
            filtered = []
            for item in all_items:
                t = item.get("ticker")
                wf = wf_results.get(t)
                if wf:
                    item["walkforward"] = {
                        "consistency": wf.consistency_score,
                        "robustness": wf.robustness_score,
                        "passes_gate": wf.passes_gate,
                    }
                    if wf.passes_gate:
                        filtered.append(item)
                else:
                    filtered.append(item)
            snap["alpha_center"]["all"] = filtered
            snap["alpha_center"]["level_1"] = [i for i in filtered if i.get("grade") == "A"]
            snap["alpha_center"]["level_2"] = [i for i in filtered if i.get("grade") == "B"]
            logger.info(f"Walk-Forward: {len(wf_results)} setups tested")
        except Exception as e:
            logger.error(f"Walk-Forward failed: {e}")

    # ── 5. Fractional Kelly Sizing ──
    if FractionalKellyEngine is not None:
        logger.info("[5/8] Computing Fractional Kelly Sizing...")
        try:
            kelly_engine = FractionalKellyEngine(portfolio_value=portfolio_value)
            sized = kelly_engine.portfolio_sizing(snap.get("alpha_center", {}).get("all", []))
            snap["fractional_kelly"] = {
                "positions": sized,
                "total_exposure": sum(p["adjusted_pct"] for p in sized),
                "notes": "Fractional Kelly with drawdown control",
            }
            logger.info(f"Kelly sized {len(sized)} positions")
        except Exception as e:
            logger.error(f"Kelly sizing failed: {e}")

    # ── 6. Bayesian Fusion untuk thesis ──
    if BayesianFusionEngine is not None:
        logger.info("[6/8] Computing Bayesian Fusion...")
        try:
            bayes = BayesianFusionEngine()
            fused = bayes.fuse_for_ticker(
                "SPY",
                yves_score=snap.get("behavioral_macro", {}).get("bullish", 30) / 100,
                yves_sigma=0.30,
                cem_score=0.6,
                cem_sigma=0.20,
                soros_score=snap.get("reflexivity", {}).get("super_bubble_score", 5) / 10,
                soros_sigma=0.35,
                options_score=0.7 if snap.get("gamma_data") else 0.5,
                options_sigma=0.25,
            )
            snap["bayesian_fusion"] = fused
            logger.info(f"Bayesian fusion: {fused['fused_signal']:.2f} (conf {fused['confidence']:.0%})")
        except Exception as e:
            logger.error(f"Bayesian fusion failed: {e}")

    # ── 7. Duration-Dependent HMM untuk key tickers ──
    if run_duration_hmm is not None:
        logger.info("[7/8] Computing Duration-Dependent HMM...")
        try:
            key_tickers = ["SPY", "QQQ", "GLD", "TLT", "BTC-USD"]
            hmm_results = {}
            for t in key_tickers:
                if t in prices:
                    hmm_results[t] = run_duration_hmm(prices[t])
            snap["duration_hmm"] = hmm_results
            logger.info(f"Duration HMM: {len(hmm_results)} tickers")
        except Exception as e:
            logger.error(f"Duration HMM failed: {e}")

    # ── 8. CRI_v2 untuk options flow ──
    if CRIv2Engine is not None:
        logger.info("[8/8] Computing CRI_v2...")
        try:
            cri_engine = CRIv2Engine()
            cri_results = {}
            for t in ["SPY", "QQQ", "IWM", "NVDA", "TSLA"]:
                if t in prices:
                    opts = snap.get("yfinance_options", {}).get(t, {}) if snap.get("yfinance_options") else {}
                    tau = opts.get("days_to_expiry", 21) if isinstance(opts, dict) else 21
                    cri_results[t] = cri_engine.compute(prices[t], tau_rem=tau)
            snap["cri_v2_data"] = cri_results
            logger.info(f"CRI_v2: {len(cri_results)} tickers")
        except Exception as e:
            logger.error(f"CRI_v2 failed: {e}")

    logger.info("Attachment 4 integration complete (9 engines).")
    logger.info("=" * 60)
    return snap


def get_enhanced_summary(snap: Dict) -> Dict:
    """Build summary dict untuk UI display (app.py integration)."""
    base = snap.get("summary", {})
    idhl_data = snap.get("idhl_data", {})
    avg_idhl = sum(d.get("idhl", 0) for d in idhl_data.values()) / max(len(idhl_data), 1) if idhl_data else 0
    base.update({
        "v32_idhl_avg": round(avg_idhl, 2),
        "v32_rc_high_count": sum(1 for d in snap.get("rc_data", {}).values() if d.get("level") == "HIGH"),
        "v32_afs": snap.get("afs_data", {}).get("afs", 0),
        "v32_afs_label": snap.get("afs_data", {}).get("label", "—"),
        "v32_wf_passed": sum(1 for d in snap.get("walkforward_results", {}).values() if d.get("passes_gate")),
        "v32_wf_total": len(snap.get("walkforward_results", {})),
        "v32_kelly_positions": len(snap.get("fractional_kelly", {}).get("positions", [])),
        "v32_bayesian_fused": snap.get("bayesian_fusion", {}).get("fused_signal", 0),
    })
    return base
