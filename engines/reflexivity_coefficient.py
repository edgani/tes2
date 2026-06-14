"""
engines/reflexivity_coefficient.py — Reflexivity Coefficient v1.0
Detect Soros feedback loop: price ↔ sentiment ↔ price.
RC > 2.0 = HIGH REFLEXIVITY → AVOID directional bets.
"""
from __future__ import annotations
import math, logging
from typing import Dict, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("reflexivity_coefficient")

class ReflexivityEngine:
    """
    RC = ρ(Price, Sentiment) × (σ_sentiment / σ_price) × Volume_t
    Sentiment proxy: bisa dari news sentiment score, options P/C ratio, atau funding rate.
    """

    def __init__(self, lookback: int = 20):
        self.lookback = lookback

    @staticmethod
    def _safe_series(s):
        if s is None:
            return pd.Series(dtype=float)
        try:
            return pd.to_numeric(pd.Series(s), errors="coerce").dropna()
        except Exception:
            return pd.Series(dtype=float)

    def compute_rc(
        self,
        price_series: pd.Series,
        sentiment_series: Optional[pd.Series] = None,
        volume_series: Optional[pd.Series] = None,
    ) -> Dict:
        """
        sentiment_series: proxy sentiment (e.g., P/C ratio inverted, funding rate, news score)
        volume_series: daily volume atau proxy (volatility × price)
        """
        p = self._safe_series(price_series).tail(self.lookback)
        if len(p) < self.lookback * 0.8:
            return {"rc": 0.0, "level": "UNKNOWN", "rho": 0.0, "vol_ratio": 0.0, "volume_factor": 0.0}

        # Sentiment proxy: kalau None, pakai price momentum sebagai self-referential proxy
        if sentiment_series is not None:
            sent = self._safe_series(sentiment_series).tail(self.lookback)
        else:
            # Self-referential: use price momentum as sentiment proxy (pure reflexivity)
            sent = p.pct_change().rolling(5).mean().dropna()
            p = p.iloc[-len(sent):]

        if len(sent) < 5 or len(p) < 5:
            return {"rc": 0.0, "level": "UNKNOWN", "rho": 0.0, "vol_ratio": 0.0, "volume_factor": 0.0}

        # Align lengths
        min_len = min(len(p), len(sent))
        p_arr = p.values[-min_len:]
        s_arr = sent.values[-min_len:]

        # Correlation
        if np.std(p_arr) < 1e-9 or np.std(s_arr) < 1e-9:
            rho = 0.0
        else:
            rho = np.corrcoef(p_arr, s_arr)[0, 1]
            if not math.isfinite(rho):
                rho = 0.0

        # Volatility ratio
        sigma_price = np.std(p_arr)
        sigma_sentiment = np.std(s_arr)
        vol_ratio = sigma_sentiment / max(sigma_price, 1e-9)

        # Volume factor (proxy: kalau volume_series None, pakai sigma_price sebagai proxy activity)
        if volume_series is not None:
            vol = self._safe_series(volume_series).tail(min_len)
            vol_factor = float(vol.mean()) / max(float(vol.std()), 1e-9) if len(vol) > 0 else 1.0
        else:
            vol_factor = sigma_price * 100  # scale up

        rc = abs(rho) * vol_ratio * vol_factor
        # Normalize: typical range 0-5, clamp untuk readability
        rc = min(10.0, max(0.0, rc))

        if rc > 2.0:
            level = "HIGH"
        elif rc > 0.5:
            level = "MEDIUM"
        else:
            level = "LOW"

        return {
            "rc": round(rc, 3),
            "level": level,
            "rho": round(rho, 3),
            "vol_ratio": round(vol_ratio, 3),
            "volume_factor": round(vol_factor, 3),
            "interpretation": {
                "HIGH": "🚫 Soros loop aktif — AVOID directional bets. Price drives sentiment drives price.",
                "MEDIUM": "⚠️ Reflexivity building — tighten stops, reduce size.",
                "LOW": "✅ Informational market — directional bets valid.",
            }.get(level, "—"),
        }

    def batch(self, prices_map, sentiment_map=None, volume_map=None) -> Dict[str, Dict]:
        sentiment_map = sentiment_map or {}
        volume_map = volume_map or {}
        out = {}
        for t, p in prices_map.items():
            out[t] = self.compute_rc(p, sentiment_map.get(t), volume_map.get(t))
        return out
