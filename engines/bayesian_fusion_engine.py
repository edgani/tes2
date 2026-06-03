"""
engines/bayesian_fusion_engine.py — Bayesian Precision-Weighted Fusion v1.0
Ganti arbitrary weighting (30/30/20/20) dengan auto-weight by precision (1/σ²).
"""
from __future__ import annotations
import math, logging
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger("bayesian_fusion_engine")

class BayesianFusionEngine:
    """
    Fuse multiple signal sources dengan precision weighting.
    Source dengan σ rendah (precise) dapat weight lebih tinggi otomatis.
    """

    def __init__(self, default_sigma: float = 0.30):
        self.default_sigma = default_sigma

    def _precision(self, sigma: float) -> float:
        if sigma <= 0 or not math.isfinite(sigma):
            sigma = self.default_sigma
        return 1.0 / (sigma ** 2)

    def fuse(
        self,
        signals: Dict[str, float],      # {"yves": 0.7, "cem": 0.6, "soros": 0.4, "options": 0.8}
        sigmas: Dict[str, float],       # {"yves": 0.25, "cem": 0.15, "soros": 0.35, "options": 0.20}
        source_names: Optional[List[str]] = None,
    ) -> Dict:
        """
        Returns fused signal, confidence, dan per-source weights.
        """
        if source_names is None:
            source_names = list(signals.keys())

        weighted_sum = 0.0
        total_precision = 0.0
        weights = {}

        for name in source_names:
            s = signals.get(name, 0.0)
            sigma = sigmas.get(name, self.default_sigma)
            tau = self._precision(sigma)
            weighted_sum += tau * s
            total_precision += tau
            weights[name] = tau

        if total_precision <= 0:
            return {
                "fused_signal": 0.0,
                "confidence": 0.0,
                "weights": {k: 0 for k in source_names},
                "notes": "No valid precision sources",
            }

        fused = weighted_sum / total_precision
        # Confidence = total precision normalized (higher = more agreement across precise sources)
        confidence = min(1.0, math.sqrt(total_precision) / 10.0)

        # Normalize weights to sum 1
        for k in weights:
            weights[k] = round(weights[k] / total_precision, 3)

        return {
            "fused_signal": round(fused, 4),
            "confidence": round(confidence, 3),
            "weights": weights,
            "notes": "Precision-weighted | High-σ sources auto-discounted",
        }

    def fuse_for_ticker(
        self,
        ticker: str,
        yves_score: float = 0.0,
        yves_sigma: float = 0.30,
        cem_score: float = 0.0,
        cem_sigma: float = 0.20,
        soros_score: float = 0.0,
        soros_sigma: float = 0.35,
        options_score: float = 0.0,
        options_sigma: float = 0.25,
        onchain_score: float = 0.0,
        onchain_sigma: float = 0.40,
    ) -> Dict:
        """
        Convenience wrapper untuk MacroRegime ticker.
        """
        signals = {
            "yves": yves_score,
            "cem": cem_score,
            "soros": soros_score,
            "options": options_score,
            "onchain": onchain_score,
        }
        sigmas = {
            "yves": yves_sigma,
            "cem": cem_sigma,
            "soros": soros_sigma,
            "options": options_sigma,
            "onchain": onchain_sigma,
        }
        result = self.fuse(signals, sigmas)
        result["ticker"] = ticker
        return result

    def batch_fuse(self, ticker_data: List[Dict]) -> Dict[str, Dict]:
        """
        ticker_data: list of dict dengan keys ticker, yves_score, yves_sigma, etc.
        """
        out = {}
        for d in ticker_data:
            t = d.get("ticker", "UNKNOWN")
            out[t] = self.fuse_for_ticker(
                t,
                yves_score=d.get("yves_score", 0),
                yves_sigma=d.get("yves_sigma", 0.30),
                cem_score=d.get("cem_score", 0),
                cem_sigma=d.get("cem_sigma", 0.20),
                soros_score=d.get("soros_score", 0),
                soros_sigma=d.get("soros_sigma", 0.35),
                options_score=d.get("options_score", 0),
                options_sigma=d.get("options_sigma", 0.25),
                onchain_score=d.get("onchain_score", 0),
                onchain_sigma=d.get("onchain_sigma", 0.40),
            )
        return out
