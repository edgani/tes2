"""
engines/signal_decay_engine.py — Information Decay Half-Life v1.0
Filter signal noise vs structural. Kalau IDHL < 1 hari = jangan trade.
"""
from __future__ import annotations
import math, logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("signal_decay_engine")

class SignalDecayEngine:
    """
    IDHL = ln(2) / λ_info
    λ_info = −ln(ρ₁) / Δt
    ρ₁ = autocorrelation lag-1 dari signal residual (price - model)
    """

    def __init__(self, min_history: int = 30):
        self.min_history = min_history

    @staticmethod
    def _safe_series(s):
        if s is None:
            return pd.Series(dtype=float)
        try:
            return pd.to_numeric(pd.Series(s), errors="coerce").dropna()
        except Exception:
            return pd.Series(dtype=float)

    def compute_idhl(self, series: pd.Series, model_fit: Optional[pd.Series] = None) -> float:
        """
        model_fit: fitted values dari model (misal SMA20). Kalau None, pakai demeaned.
        Returns IDHL dalam hari. Kalau < 1 = NOISE, 1-5 = TACTICAL, >10 = STRUCTURAL.
        """
        s = self._safe_series(series)
        if len(s) < self.min_history:
            return 0.0

        if model_fit is not None and len(model_fit) == len(s):
            residual = s.values - model_fit.values
        else:
            residual = s.values - np.mean(s.values)

        # Autocorrelation lag-1
        if np.std(residual) < 1e-9:
            return 0.0

        rho1 = np.corrcoef(residual[:-1], residual[1:])[0, 1]
        if not math.isfinite(rho1) or rho1 <= 0 or rho1 >= 1:
            return 0.0

        dt = 1.0  # 1 day
        lambda_info = -math.log(rho1) / dt
        if lambda_info <= 0:
            return 999.0  # persistent signal

        idhl = math.log(2) / lambda_info
        return round(idhl, 2)

    def classify(self, idhl: float) -> str:
        if idhl < 1.0:
            return "NOISE"
        elif idhl < 5.0:
            return "TACTICAL"
        elif idhl < 10.0:
            return "SWING"
        else:
            return "STRUCTURAL"

    def compute_for_ticker(self, ticker: str, prices, model_fit=None) -> Dict:
        s = self._safe_series(prices)
        idhl = self.compute_idhl(s, model_fit)
        return {
            "ticker": ticker,
            "idhl": idhl,
            "classification": self.classify(idhl),
            "tradeable": idhl >= 1.0,
            "notes": "IDHL {:.1f} days — {}".format(idhl, self.classify(idhl)),
        }

    def batch(self, prices_map: Dict[str, pd.Series], model_fits: Optional[Dict] = None) -> Dict[str, Dict]:
        out = {}
        model_fits = model_fits or {}
        for t, s in prices_map.items():
            out[t] = self.compute_for_ticker(t, s, model_fits.get(t))
        return out
