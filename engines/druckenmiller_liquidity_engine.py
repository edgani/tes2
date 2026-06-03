"""
druckenmiller_liquidity_engine.py — Druckenmiller Liquidity Analysis Engine
"It's not earnings, it's liquidity that moves markets."
— Stanley Druckenmiller, ~30% annual, ZERO down years
"""

import logging
import numpy as np
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class DruckenmillerLiquidityEngine:
    """Druckenmiller Liquidity Engine v1.0"""

    WEIGHTS = {
        'fed_balance_sheet': 0.30,
        'm2_growth': 0.25,
        'bank_credit': 0.20,
        'rates': 0.15,
        'credit_spread': 0.10,
    }

    REGIMES = {
        'EASE': (0.50, 1.00, "🟢"),
        'NEUTRAL_EASY': (0.10, 0.50, "🟡"),
        'NEUTRAL': (-0.10, 0.10, "⚪"),
        'TIGHTENING': (-0.50, -0.10, "🟠"),
        'CRISIS': (-1.00, -0.50, "🔴"),
    }

    def __init__(self, fred_loader=None):
        self.fred = fred_loader

    def _get_fred(self, sid, default=None):
        if self.fred is None: return default
        try:
            d = self.fred.get_series(sid)
            return float(d[-1]) if d and len(d) > 0 else default
        except: return default

    def _fed_score(self, v):
        return float(np.clip((v - 6_500_000) / 2_500_000, -1, 1)) if v else 0.0

    def _m2_score(self, v):
        return float(np.clip((v - 2.5) / 7.5, -1, 1)) if v else 0.0

    def _credit_score(self, v):
        return float(np.clip((v - 3.0) / 5.0, -1, 1)) if v else 0.0

    def _rates_score(self, v):
        return float(np.clip((3.0 - v) / 2.5, -1, 1)) if v else 0.0

    def _hy_score(self, v):
        return float(np.clip((650 - v) / 350, -1, 1)) if v else 0.0

    def calculate(self, fred_series=None):
        if fred_series:
            vals = {k: fred_series.get(k) for k in ['WALCL','M2SL','TOTBKCR','DGS10','BAMLH0A0HYM2']}
        else:
            vals = {k: self._get_fred(k) for k in ['WALCL','M2SL','TOTBKCR','DGS10','BAMLH0A0HYM2']}

        comps = {
            'fed_balance_sheet': self._fed_score(vals.get('WALCL')),
            'm2_growth': self._m2_score(vals.get('M2SL')),
            'bank_credit': self._credit_score(vals.get('TOTBKCR')),
            'rates': self._rates_score(vals.get('DGS10')),
            'credit_spread': self._hy_score(vals.get('BAMLH0A0HYM2')),
        }

        w = self.WEIGHTS
        score = sum(comps[k] * w[k] for k in w)

        regime = "NEUTRAL"
        emoji = "⚪"
        for n, (lo, hi, em) in self.REGIMES.items():
            if lo <= score < hi or (hi == 1.0 and score >= lo):
                regime, emoji = n, em
                break

        actions = {
            'EASE': "Full risk-on — growth stocks, long duration",
            'NEUTRAL_EASY': "Selective risk — balanced, high conviction",
            'NEUTRAL': "Defensive — reduce risk, raise cash",
            'TIGHTENING': "Risk-off — short credit, preserve capital",
            'CRISIS': "Maximum defense — long vol, gold, cash",
        }

        if score > 0.3:
            quad = "→ Quad 1/2 (Growth): Liquidity driving expansion"
        elif score > 0.0:
            quad = "→ Quad 1 (Goldilocks): Favorable for equities"
        elif score > -0.3:
            quad = "→ Quad 3/4 (Risk): Tightening ahead — defensive"
        else:
            quad = "→ Quad 4 (Deflation): Maximum risk — all defense"

        return {
            'score': round(float(score), 3),
            'regime': regime,
            'display': f"{emoji} {regime}",
            'action': actions.get(regime, "Monitor"),
            'components': {k: round(v, 3) for k, v in comps.items()},
            'quad_prediction': quad,
            'forward_looking': True,
            'horizon_months': 18,
        }


def run_druckenmiller_liquidity(fred_loader=None, fred_series=None):
    return DruckenmillerLiquidityEngine(fred_loader).calculate(fred_series)
