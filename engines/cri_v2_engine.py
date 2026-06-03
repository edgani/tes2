"""
engines/cri_v2_engine.py — Cliff Risk Index v2.0 (Price-Normalized)
Fix dimensional inconsistency dari RohOnChain CRI.
CRI_v2 = (Δp/p) × √(τ_rem/τ_max) → bounded [0,1], dimensionless.
"""
from __future__ import annotations
import math, logging
from typing import Dict, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("cri_v2_engine")

class CRIv2Engine:
    """
    Detect gamma squeeze / options repricing velocity yang proporsional.
    """

    def __init__(self, tau_max: int = 30):
        self.tau_max = tau_max  # max days to expiry reference

    @staticmethod
    def _safe_series(s):
        if s is None:
            return pd.Series(dtype=float)
        try:
            return pd.to_numeric(pd.Series(s), errors="coerce").dropna()
        except Exception:
            return pd.Series(dtype=float)

    def compute(
        self,
        price_series: pd.Series,
        options_price_series: Optional[pd.Series] = None,
        tau_rem: int = 21,
    ) -> Dict:
        """
        price_series: underlying price
        options_price_series: options price (e.g., ATM call). Kalau None, pakai underlying proxy.
        """
        p = self._safe_series(price_series)
        if len(p) < 6:
            return {"cri_v2": 0.0, "velocity": 0.0, "normalized": 0.0, "tau_factor": 0.0}

        if options_price_series is not None:
            o = self._safe_series(options_price_series).tail(len(p))
            # Align
            min_len = min(len(p), len(o))
            p_arr = p.values[-min_len:]
            o_arr = o.values[-min_len:]
            # Δp/p untuk options
            if len(o_arr) >= 2 and o_arr[-2] != 0:
                delta_p = abs(o_arr[-1] - o_arr[-2])
                p_ref = o_arr[-2]
            else:
                delta_p = 0
                p_ref = 1
        else:
            # Proxy dari underlying volatility spike
            p_arr = p.values
            if len(p_arr) >= 2 and p_arr[-2] != 0:
                delta_p = abs(p_arr[-1] - p_arr[-2])
                p_ref = p_arr[-2]
            else:
                delta_p = 0
                p_ref = 1

        if p_ref == 0:
            p_ref = 1e-6

        normalized = delta_p / p_ref
        tau_factor = math.sqrt(tau_rem / self.tau_max) if self.tau_max > 0 else 1.0
        cri_v2 = normalized * tau_factor
        cri_v2 = min(1.0, max(0.0, cri_v2))

        # Velocity classification
        if cri_v2 > 0.3:
            velocity = "EXTREME"
            emoji = "🔥"
        elif cri_v2 > 0.15:
            velocity = "HIGH"
            emoji = "⚡"
        elif cri_v2 > 0.05:
            velocity = "MODERATE"
            emoji = "📈"
        else:
            velocity = "LOW"
            emoji = "💤"

        return {
            "cri_v2": round(cri_v2, 4),
            "velocity": velocity,
            "emoji": emoji,
            "normalized": round(normalized, 4),
            "tau_factor": round(tau_factor, 3),
            "tau_rem": tau_rem,
            "interpretation": {
                "EXTREME": "Gamma squeeze imminent — MM hedging cascade likely.",
                "HIGH": "Rapid repricing — watch for vol expansion.",
                "MODERATE": "Normal options flow velocity.",
                "LOW": "Stale options pricing — low activity.",
            }.get(velocity, "—"),
        }

    def batch(self, prices_map: Dict, options_map: Optional[Dict] = None, tau_map: Optional[Dict] = None) -> Dict[str, Dict]:
        options_map = options_map or {}
        tau_map = tau_map or {}
        out = {}
        for t, p in prices_map.items():
            out[t] = self.compute(p, options_map.get(t), tau_map.get(t, 21))
        return out
