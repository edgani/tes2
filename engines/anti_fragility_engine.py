"""
engines/anti_fragility_engine.py — Anti-Fragility Score v1.0
AFS > 2.0 = Anti-fragile (gains from disorder). AFS < 1.0 = Fragile (blows up in tails).
"""
from __future__ import annotations
import math, logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("anti_fragility_engine")

class AntiFragilityEngine:
    """
    AFS = (Positive Convexity × Regime Diversity × Liquidity Buffer) / Correlation Concentration
    """

    def __init__(self, lookback: int = 60):
        self.lookback = lookback

    @staticmethod
    def _safe_series(s):
        if s is None:
            return pd.Series(dtype=float)
        try:
            return pd.to_numeric(pd.Series(s), errors="coerce").dropna()
        except Exception:
            return pd.Series(dtype=float)

    def positive_convexity(self, prices_map: Dict[str, pd.Series], options_map: Optional[Dict] = None) -> float:
        """
        Tail protection ratio: payoff dari posisi asimetrik (long gamma, long vol, hedges).
        Proxy: rata-rata skewness dari returns (positive skew = convexity).
        """
        skews = []
        for t, s in prices_map.items():
            ss = self._safe_series(s).tail(self.lookback)
            if len(ss) < 20:
                continue
            rets = ss.pct_change().dropna()
            if len(rets) < 10:
                continue
            skew = float(rets.skew()) if hasattr(rets, "skew") else 0.0
            skews.append(max(0, skew))  # only positive skew counts as convexity
        return np.mean(skews) if skews else 0.0

    def regime_diversity(self, prices_map: Dict[str, pd.Series]) -> float:
        """
        Sharpe ratio averaged across bull/bear/sideways regimes.
        Proxy: std of rolling 20-day Sharpe across assets.
        """
        sharpe_list = []
        for t, s in prices_map.items():
            ss = self._safe_series(s).tail(self.lookback)
            if len(ss) < 30:
                continue
            rets = ss.pct_change().dropna()
            if len(rets) < 20:
                continue
            mean_ret = rets.mean()
            std_ret = rets.std()
            if std_ret > 0:
                sharpe = mean_ret / std_ret * np.sqrt(252)
                sharpe_list.append(sharpe)
        if not sharpe_list:
            return 0.0
        # Diversity = abs(mean) / std (higher = more consistent across assets)
        return abs(np.mean(sharpe_list)) / max(np.std(sharpe_list), 0.1)

    def liquidity_buffer(self, cash_pct: float = 0.25, liquid_assets_pct: float = 0.0) -> float:
        """Cash + T-bill / total portfolio."""
        return cash_pct + liquid_assets_pct

    def correlation_concentration(self, prices_map: Dict[str, pd.Series]) -> float:
        """
        Herfindahl index dari pairwise correlations.
        Higher = more concentrated correlation = fragile.
        """
        tickers = list(prices_map.keys())[:20]  # limit for performance
        if len(tickers) < 2:
            return 1.0  # max concentration

        rets = {}
        for t in tickers:
            s = self._safe_series(prices_map[t]).tail(self.lookback)
            if len(s) < 20:
                continue
            r = s.pct_change().dropna()
            if len(r) >= 10:
                rets[t] = r

        if len(rets) < 2:
            return 1.0

        # Pairwise correlations
        corr_vals = []
        keys = list(rets.keys())
        for i in range(len(keys)):
            for j in range(i+1, len(keys)):
                a = rets[keys[i]].values[-min(len(rets[keys[i]]), len(rets[keys[j]])):]
                b = rets[keys[j]].values[-min(len(rets[keys[i]]), len(rets[keys[j]])):]
                if np.std(a) > 0 and np.std(b) > 0:
                    c = np.corrcoef(a, b)[0, 1]
                    if math.isfinite(c):
                        corr_vals.append(abs(c))

        if not corr_vals:
            return 1.0

        # Herfindahl: sum of squared shares
        total = sum(corr_vals)
        if total == 0:
            return 1.0
        shares = [c / total for c in corr_vals]
        hhi = sum(s**2 for s in shares)
        return hhi * len(corr_vals)  # scale by n_pairs so range ~0.5-5

    def compute_afs(
        self,
        prices_map: Dict[str, pd.Series],
        cash_pct: float = 0.25,
        options_map: Optional[Dict] = None,
    ) -> Dict:
        pc = self.positive_convexity(prices_map, options_map)
        rd = self.regime_diversity(prices_map)
        lb = self.liquidity_buffer(cash_pct)
        cc = self.correlation_concentration(prices_map)

        afs = (pc * rd * lb) / max(cc, 0.1)

        if afs > 2.0:
            label = "ANTI-FRAGILE"
            color = "#3FB950"
            advice = "Gains from disorder. Size up, add tail hedges only for income."
        elif afs > 1.0:
            label = "RESILIENT"
            color = "#D29922"
            advice = "Survives normal stress. Maintain current allocation."
        else:
            label = "FRAGILE"
            color = "#F85149"
            advice = "Blows up in tail events. Raise cash 30%, reduce correlation overlap."

        return {
            "afs": round(afs, 3),
            "label": label,
            "color": color,
            "advice": advice,
            "components": {
                "positive_convexity": round(pc, 3),
                "regime_diversity": round(rd, 3),
                "liquidity_buffer": round(lb, 3),
                "correlation_concentration": round(cc, 3),
            }
        }
