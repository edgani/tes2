"""engines/bottleneck_discovery_v3.py — Bottleneck Discovery Engine v3.0
Deep bottleneck detection: supply chain, capacity constraints, margin pressure, order book analysis.
"""
import logging, math
import pandas as pd
from typing import Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)

BOTTLENECK_TEMPLATES = [
    {
        "id": "ai_compute",
        "name": "AI Compute Bottleneck",
        "indicators": ["nvda", "amd", "smci", "vst", "etn", "cohr"],
        "signals": ["gpu_shortage", "data_center_capacity", "power_constraint"],
        "thresholds": {"nvda_r1m": 0.15, "smci_r1m": 0.20, "power_news": True},
    },
    {
        "id": "energy_transition",
        "name": "Energy Transition Bottleneck",
        "indicators": ["cl=f", "xle", "cvx", "xom", "fro", "vst"],
        "signals": ["oil_supply_gap", "refinery_capacity", "lng_demand"],
        "thresholds": {"cl_r1m": 0.10, "xle_r1m": 0.08, "oil_news": True},
    },
    {
        "id": "semiconductor_supply",
        "name": "Semiconductor Supply Chain",
        "indicators": ["smh", "tsm", "avgo", "mu", "asml", "lrcx"],
        "signals": ["wafer_capacity", "hbm_shortage", "lithography_backlog"],
        "thresholds": {"smh_r1m": 0.10, "tsm_r1m": 0.08, "chip_news": True},
    },
    {
        "id": "labor_constraint",
        "name": "Labor Market Bottleneck",
        "indicators": ["unrate", "payems", "icsa", "indeed"],
        "signals": ["wage_pressure", "job_openings", "strike_activity"],
        "thresholds": {"unrate": 3.5, "wage_growth": 0.04},
    },
    {
        "id": "shipping_logistics",
        "name": "Shipping & Logistics Bottleneck",
        "indicators": ["fro", "zim", "matx", "dac", "ups", "fdx"],
        "signals": ["container_rates", "port_congestion", "fuel_surcharge"],
        "thresholds": {"fro_r1m": 0.15, "zim_r1m": 0.10},
    },
    {
        "id": "housing_supply",
        "name": "Housing Supply Bottleneck",
        "indicators": ["houst", "len", "dhi", "phm", "tol", "nvr"],
        "signals": ["permits_decline", "mortgage_rate_spike", "inventory_shortage"],
        "thresholds": {"houst": 1200, "mortgage_rate": 7.0},
    },
    {
        "id": "critical_minerals",
        "name": "Critical Minerals Bottleneck",
        "indicators": ["ncc", "nem", "fcx", "alb", "sqm", "pil"],
        "signals": ["lithium_supply", "copper_deficit", "nickel_constraint"],
        "thresholds": {"copper_r1m": 0.10, "lithium_r1m": 0.15},
    },
]

class BottleneckDiscoveryV3:
    """Deep bottleneck detection with multi-factor scoring."""

    def __init__(self):
        pass

    def _ticker_momentum(self, ticker: str, prices: Dict) -> float:
        s = prices.get(ticker)
        if s is None or len(s) < 22:
            return 0.0
        try:
            import pandas as pd
            s = pd.to_numeric(s, errors="coerce").dropna()
            if len(s) < 22:
                return 0.0
            return float(s.iloc[-1] / s.iloc[-22] - 1)
        except Exception:
            return 0.0

    def _detect_bottleneck(self, template: Dict, prices: Dict, fred: Dict, news_analysis: Dict) -> Dict:
        """Detect if a bottleneck template is active."""
        scores = {"price_momentum": 0, "news_signal": 0, "macro_alignment": 0, "composite": 0}
        # Price momentum check
        for indicator in template.get("indicators", []):
            mom = self._ticker_momentum(indicator, prices)
            if abs(mom) > 0.05:
                scores["price_momentum"] += min(1.0, abs(mom) * 3)
        scores["price_momentum"] = min(1.0, scores["price_momentum"] / max(len(template.get("indicators", [])), 1))
        # News signal
        emergent = (news_analysis or {}).get("emergent_narratives", [])
        for en in emergent:
            name = (en.get("name") or "").lower()
            if any(sig in name for sig in template.get("signals", [])):
                scores["news_signal"] += 0.5
            # Check if any indicator ticker mentioned
            for ind in template.get("indicators", []):
                if ind.lower().replace("=", "") in name:
                    scores["news_signal"] += 0.3
        scores["news_signal"] = min(1.0, scores["news_signal"])
        # Macro alignment
        thresholds = template.get("thresholds", {})
        if "unrate" in thresholds:
            unrate = fred.get("UNRATE")
            if unrate is not None and len(unrate) > 0:
                try:
                    val = float(unrate.iloc[-1])
                    if val < thresholds["unrate"]:
                        scores["macro_alignment"] += 0.5
                except Exception:
                    pass
        if "houst" in thresholds:
            houst = fred.get("HOUST")
            if houst is not None and len(houst) > 0:
                try:
                    val = float(houst.iloc[-1])
                    if val < thresholds["houst"]:
                        scores["macro_alignment"] += 0.5
                except Exception:
                    pass
        scores["macro_alignment"] = min(1.0, scores["macro_alignment"])
        # Composite
        scores["composite"] = scores["price_momentum"] * 0.4 + scores["news_signal"] * 0.35 + scores["macro_alignment"] * 0.25
        return scores

    def run(self, prices: Dict, fred: Dict, news_analysis: Dict) -> Dict:
        """Main entry: detect all bottlenecks."""
        active = []
        watch = []
        for template in BOTTLENECK_TEMPLATES:
            scores = self._detect_bottleneck(template, prices, fred, news_analysis)
            if scores["composite"] >= 0.45:
                active.append({
                    "id": template["id"],
                    "name": template["name"],
                    "confidence": round(scores["composite"], 2),
                    "scores": {k: round(v, 2) for k, v in scores.items()},
                    "indicators": template["indicators"],
                    "signals": template["signals"],
                    "status": "ACTIVE",
                })
            elif scores["composite"] >= 0.25:
                watch.append({
                    "id": template["id"],
                    "name": template["name"],
                    "confidence": round(scores["composite"], 2),
                    "scores": {k: round(v, 2) for k, v in scores.items()},
                    "status": "WATCH",
                })
        # Build consensus heatmap
        heatmap = []
        for a in active:
            for ind in a["indicators"][:3]:
                px = None
                s = prices.get(ind)
                if s is not None and len(s) > 0:
                    try:
                        px = float(pd.to_numeric(s, errors="coerce").dropna().iloc[-1])
                    except Exception:
                        pass
                heatmap.append({
                    "ticker": ind,
                    "bottleneck": a["name"],
                    "confidence": a["confidence"],
                    "price": px,
                })
        return {
            "active_bottlenecks": active,
            "watch_bottlenecks": watch,
            "consensus_heatmap": heatmap,
            "summary": f"{len(active)} active, {len(watch)} watching",
            "total_detected": len(active) + len(watch),
        }


def run_bottleneck_discovery_v3(prices: Dict, fred: Dict, news_analysis: Dict) -> Dict:
    engine = BottleneckDiscoveryV3()
    return engine.run(prices, fred, news_analysis)
