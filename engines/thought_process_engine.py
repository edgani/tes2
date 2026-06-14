"""engines/thought_process_engine.py — Methodology Orchestrator v2 (Sprint 9 REFACTOR)

REFACTORED: No more "portfolio matching." Now runs each investor's actual
METHODOLOGY against tickers using their respective engine modules.
"""
from __future__ import annotations
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


CITRINI_THEMES = {
    "GLP-1": {"primary": ["LLY", "NVO", "VKTX", "AMGN"],
              "second_order": {"WMT": "Consumption pattern shift"},
              "thesis": "Obesity drug TAM $100B+ by 2030"},
    "AI_INFRA_BOTTLENECK": {"primary": ["NVDA", "AVGO", "TSM", "VST", "CEG", "BE"],
                            "second_order": {"GEV": "Grid eq for AI power", "AMAT": "Semicap",
                                            "ASML": "EUV monopoly", "LITE": "Optics", "COHR": "Photonics"},
                            "thesis": "AI buildout supply chain bottlenecks"},
    "ENERGY_TRANSITION": {"primary": ["CCJ", "URA", "FCX", "MP"],
                          "second_order": {"BWXT": "Nuclear SMR", "ALB": "Lithium"},
                          "thesis": "Critical minerals + nuclear renaissance"},
    "FISCAL_DOMINANCE": {"primary": ["GLD", "SLV", "BTC-USD", "VST"],
                         "second_order": {"NEM": "Gold miner", "GDX": "Mining sector"},
                         "thesis": "Real asset bid as fiat debt monetizes"},
    "DEFENSE_REARMAMENT": {"primary": ["LMT", "NOC", "RTX", "GD"],
                           "second_order": {"PLTR": "Defense AI", "AVAV": "Drones"},
                           "thesis": "Post-Ukraine NATO 3% GDP target"},
}


def evaluate_citrini(ticker: str, quad: str) -> Dict:
    t = ticker.upper()
    for theme_name, theme_data in CITRINI_THEMES.items():
        if t in theme_data["primary"]:
            return {"framework": "Citrini", "matched": True, "score": 80,
                    "role": f"Thematic Primary — {theme_name.replace('_',' ').title()}",
                    "thesis": theme_data["thesis"], "theme": theme_name, "is_second_order": False}
        if t in theme_data.get("second_order", {}):
            return {"framework": "Citrini", "matched": True, "score": 70,
                    "role": f"Second-Order — {theme_name.replace('_',' ').title()}",
                    "thesis": f"Second-derivative: {theme_data['second_order'][t]}",
                    "theme": theme_name, "is_second_order": True}
    return {"framework": "Citrini", "matched": False, "score": 0, "role": None}


HEDGEYE_PLAYBOOK = {
    "Q1": {"longs": {"QQQ","SPY","XLK","XLC","XLY","ARKK","NVDA","AAPL","MSFT","GOOGL","META","AMZN","AMD","AVGO","BTC-USD","ETH-USD","MAGS"},
           "shorts": {"XLU","XLP","TLT","GLD","USO"},
           "thesis": "Goldilocks — Growth ↑ Inflation ↓"},
    "Q2": {"longs": {"XLF","XLE","XLI","XLB","KRE","IWM","XOM","CVX","OXY","FCX"},
           "shorts": {"TLT","IEF"}, "thesis": "Reflation — Growth ↑ Inflation ↑"},
    "Q3": {"longs": {"GLD","SLV","GDX","GDXJ","USO","XLE","XLP","XLU","XOM"},
           "shorts": {"QQQ","XLK","XLY","IWM","ARKK"},
           "thesis": "Stagflation — Growth ↓ Inflation ↑"},
    "Q4": {"longs": {"TLT","IEF","GLD","XLU","XLP","XLV"},
           "shorts": {"QQQ","XLK","IWM","XLY","XLF","XLE","BTC-USD"},
           "thesis": "Deflation — Growth ↓ Inflation ↓"},
}


def evaluate_hedgeye(ticker: str, quad: str) -> Dict:
    t = ticker.upper()
    pb = HEDGEYE_PLAYBOOK.get(quad, {})
    if t in pb.get("longs", set()):
        return {"framework": "Hedgeye", "matched": True, "score": 85,
                "role": f"Regime-Aligned LONG ({quad})", "thesis": pb["thesis"],
                "direction_bias": "LONG"}
    if t in pb.get("shorts", set()):
        return {"framework": "Hedgeye", "matched": True, "score": 85,
                "role": f"Regime-Aligned SHORT ({quad})", "thesis": pb["thesis"],
                "direction_bias": "SHORT"}
    return {"framework": "Hedgeye", "matched": False, "score": 0, "role": None}


def evaluate_all_methodologies(ticker: str, prices_series=None, quad: str = "Q3",
                                vix: float = 20.0,
                                # Sprint 10 extra context
                                boom_bust_stage: str = "ACCELERATION",
                                super_bubble_score: float = 0,
                                fred: dict = None,
                                gamma_data: dict = None,
                                greeks_data: dict = None,
                                markov_v3: dict = None,
                                risk_range: dict = None,
                                composite_signal: dict = None,
                                news_sentiment: float = None) -> Dict:
    """Run ticker through ALL methodology engines (Sprint 9 + Sprint 10)."""
    result = {
        "ticker": ticker, "matched_frameworks": [], "framework_breakdown": {},
        "thesis_score": 0, "primary_role": "Generic", "primary_thesis": "",
        "thesis_rationale": "", "asymmetry_setup": None, "vol_setup": None, "n_matches": 0,
    }
    rationales = []
    
    # 1. LEOPOLD (Sprint 9)
    try:
        from engines.leopold_methodology import evaluate_leopold_methodology
        leopold = evaluate_leopold_methodology(ticker, prices_series)
        result["framework_breakdown"]["leopold"] = leopold
        if leopold.get("matched"):
            result["matched_frameworks"].append("leopold")
            if leopold["leopold_score"] > result["thesis_score"]:
                result["thesis_score"] = leopold["leopold_score"]
                bl = leopold.get("bottleneck_layer") or {}
                result["primary_role"] = bl.get("role") or f"Leopold {bl.get('layer','-')}"
                result["primary_thesis"] = bl.get("entry_logic", "")
            if leopold.get("asymmetry_setup"):
                result["asymmetry_setup"] = leopold["asymmetry_setup"]
            for r in leopold.get("rules_passed", []):
                rationales.append(f"• **Leopold**: {r}")
    except Exception as e:
        logger.debug(f"Leopold eval failed for {ticker}: {e}")
    
    # 2. COATUE (Sprint 9)
    try:
        from engines.coatue_methodology import evaluate_coatue_methodology
        coatue = evaluate_coatue_methodology(ticker, prices_series)
        result["framework_breakdown"]["coatue"] = coatue
        if coatue.get("matched"):
            result["matched_frameworks"].append("coatue")
            if coatue["coatue_score"] > result["thesis_score"]:
                result["thesis_score"] = coatue["coatue_score"]
                result["primary_role"] = coatue.get("role", "COATUE")
                result["primary_thesis"] = (coatue.get("rationale") or [""])[0]
            for r in coatue.get("rationale", []):
                rationales.append(f"• **COATUE**: {r}")
    except Exception as e:
        logger.debug(f"COATUE eval failed for {ticker}: {e}")
    
    # 3. KARSAN (Sprint 9)
    try:
        from engines.karsan_vol_scanner import compute_karsan_score
        karsan = compute_karsan_score(ticker, prices_series, vix=vix)
        result["framework_breakdown"]["karsan"] = karsan
        if karsan.get("karsan_setup"):
            result["matched_frameworks"].append("karsan")
            result["vol_setup"] = karsan["karsan_setup"]
            karsan_score = 70 if "SQUEEZE_SETUP" in karsan["karsan_setup"] else 60
            if karsan_score > result["thesis_score"]:
                result["thesis_score"] = karsan_score
                result["primary_role"] = "Karsan " + karsan["karsan_setup"].split(" — ")[0]
                result["primary_thesis"] = karsan["karsan_setup"]
            for r in karsan.get("rationale", []):
                rationales.append(f"• **Karsan**: {r}")
    except Exception as e:
        logger.debug(f"Karsan eval failed for {ticker}: {e}")
    
    # 4. CITRINI
    citrini = evaluate_citrini(ticker, quad)
    result["framework_breakdown"]["citrini"] = citrini
    if citrini.get("matched"):
        result["matched_frameworks"].append("citrini")
        if citrini["score"] > result["thesis_score"]:
            result["thesis_score"] = citrini["score"]
            result["primary_role"] = citrini["role"]
            result["primary_thesis"] = citrini["thesis"]
        rationales.append(f"• **Citrini**: {citrini['role']} — {citrini['thesis']}")
    
    # 5. HEDGEYE
    hedgeye = evaluate_hedgeye(ticker, quad)
    result["framework_breakdown"]["hedgeye"] = hedgeye
    if hedgeye.get("matched"):
        result["matched_frameworks"].append("hedgeye")
        rationales.append(f"• **Hedgeye**: {hedgeye['role']} — {hedgeye['thesis']}")
        if hedgeye.get("direction_bias") == "LONG" and result["thesis_score"] > 50:
            result["thesis_score"] = min(100, result["thesis_score"] + 5)
    
    # ═══ SPRINT 10: methodology_pack (Yves+Soros+Schadner+Drucken+Tier1+profplum) ═══
    try:
        from engines.methodology_pack import evaluate_all_pack
        pack = evaluate_all_pack(
            ticker=ticker, prices_series=prices_series,
            boom_bust_stage=boom_bust_stage, super_bubble_score=super_bubble_score,
            vix=vix, fred=fred, gamma_data=gamma_data, greeks_data=greeks_data,
            markov_v3=markov_v3, risk_range=risk_range, composite_signal=composite_signal,
            news_sentiment=news_sentiment,
        )
        for fw_name, fw_result in pack.items():
            result["framework_breakdown"][fw_name] = fw_result
            if fw_result.get("matched"):
                result["matched_frameworks"].append(fw_name)
                if fw_result.get("score", 0) > result["thesis_score"]:
                    result["thesis_score"] = fw_result["score"]
                    result["primary_role"] = fw_result.get("role", fw_name)
                    result["primary_thesis"] = fw_result.get("thesis", "")
                for r in fw_result.get("rationale", [])[:2]:
                    rationales.append(f"• **{fw_name.title()}**: {r}")
    except Exception as e:
        logger.debug(f"Sprint 10 methodology_pack failed for {ticker}: {e}")
    
    result["thesis_rationale"] = "\n".join(rationales) if rationales else "No methodology match"
    result["n_matches"] = len(result["matched_frameworks"])
    result["thesis_score"] = round(result["thesis_score"], 1)
    return result


def analyze_multi(tickers, prices=None, quad="Q3", vix=20.0, **kwargs):
    prices = prices or {}
    results = {}
    for t in tickers:
        try:
            results[t] = evaluate_all_methodologies(t, prices.get(t), quad, vix)
        except Exception as e:
            logger.debug(f"Methodology eval failed for {t}: {e}")
    return results


compute_thesis = evaluate_all_methodologies


def get_top_theses(results, top_n=20):
    return sorted(results.values(), key=lambda x: x.get("thesis_score", 0), reverse=True)[:top_n]


def get_methodology_picks(results, methodology, min_score=60):
    out = []
    for ticker, r in results.items():
        if methodology in r.get("matched_frameworks", []):
            fw = r.get("framework_breakdown", {}).get(methodology, {})
            score = fw.get(f"{methodology}_score", 0) or fw.get("score", 0)
            if score >= min_score:
                out.append({"ticker": ticker, "score": score,
                            "role": fw.get("role"),
                            "rationale": fw.get("thesis", "—")})
    return sorted(out, key=lambda x: x.get("score", 0), reverse=True)
