"""
engines/fractional_kelly_engine.py — Fractional Kelly + Drawdown Control v1.0
Fix full Kelly gambler's ruin. f_safe = c × f* where c = maxDD / (f* × 2.5)
"""
from __future__ import annotations
import math, logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("fractional_kelly_engine")

class FractionalKellyEngine:
    """
    Position sizing yang survive tail events.
    """

    def __init__(
        self,
        max_drawdown_target: float = 0.20,  # 20% max drawdown
        kelly_fraction: float = 0.25,       # quarter Kelly default
        min_position_pct: float = 0.01,     # 1% minimum
        max_position_pct: float = 0.15,     # 15% maximum per position
        portfolio_value: float = 100_000,
    ):
        self.max_dd_target = max_drawdown_target
        self.kelly_fraction = kelly_fraction
        self.min_position_pct = min_position_pct
        self.max_position_pct = max_position_pct
        self.portfolio_value = portfolio_value

    def compute_kelly(
        self,
        win_rate: float,
        avg_win_pct: float,
        avg_loss_pct: float,
    ) -> Tuple[float, float]:
        """
        Returns (f_raw, f_safe).
        f_raw = full Kelly fraction
        f_safe = drawdown-adjusted Kelly
        """
        if avg_loss_pct <= 0 or win_rate <= 0 or win_rate >= 1:
            return 0.0, 0.0

        # Edge = expected return per unit bet
        b = avg_win_pct / avg_loss_pct  # payoff ratio
        f_raw = (win_rate * (b + 1) - 1) / b
        f_raw = max(0, min(1, f_raw))

        # Drawdown adjustment
        if f_raw > 0:
            c = self.max_dd_target / (f_raw * 2.5)
            c = min(1.0, max(0.1, c))  # cap between 10%-100% of raw Kelly
        else:
            c = 0.0

        f_safe = f_raw * c * self.kelly_fraction
        f_safe = max(self.min_position_pct, min(self.max_position_pct, f_safe))

        return round(f_raw, 4), round(f_safe, 4)

    def size_position(
        self,
        win_rate: float,
        avg_win_pct: float,
        avg_loss_pct: float,
        conviction_boost: float = 1.0,  # 0.5-1.5 multiplier dari external signal
        reflexivity_penalty: float = 1.0,  # 0.5 kalau RC > 2.0
    ) -> Dict:
        f_raw, f_safe = self.compute_kelly(win_rate, avg_win_pct, avg_loss_pct)

        # Apply modifiers
        adjusted_pct = f_safe * conviction_boost * reflexivity_penalty
        adjusted_pct = max(self.min_position_pct, min(self.max_position_pct, adjusted_pct))
        dollar_size = adjusted_pct * self.portfolio_value

        return {
            "f_raw": f_raw,
            "f_safe": f_safe,
            "adjusted_pct": round(adjusted_pct, 4),
            "dollar_size": round(dollar_size, 2),
            "max_drawdown_target": self.max_dd_target,
            "c_factor": round(self.max_dd_target / (f_raw * 2.5), 3) if f_raw > 0 else 0,
            "notes": "Fractional Kelly {:.0%} of raw {:.1%} | MaxDD {}%".format(
                self.kelly_fraction, f_raw, int(self.max_dd_target*100)
            ),
        }

    def portfolio_sizing(
        self,
        setups: List[Dict],
        max_total_exposure: float = 0.80,
    ) -> List[Dict]:
        """
        Size multiple positions dengan correlation penalty.
        setups: list of dict dengan keys win_rate, avg_win_pct, avg_loss_pct, rc, idhl
        """
        sized = []
        total_exposure = 0.0

        for s in sorted(setups, key=lambda x: x.get("simulation", {}).get("robustness_score", 0), reverse=True):
            sim = s.get("simulation", {})
            wr = sim.get("win_rate", 0.55) if isinstance(sim, dict) else 0.55
            exp_ret = sim.get("exp_return_pct", 0.05) if isinstance(sim, dict) else 0.05
            dd = sim.get("avg_drawdown_pct", 0.04) if isinstance(sim, dict) else 0.04

            avg_win = exp_ret
            avg_loss = dd

            rc = s.get("rc", 0) or 0
            reflexivity_penalty = 0.5 if rc > 2.0 else 0.8 if rc > 0.5 else 1.0

            idhl = s.get("idhl", 0) or 0
            conviction = 1.2 if idhl > 10 else 1.0 if idhl > 5 else 0.8

            size = self.size_position(wr, avg_win, avg_loss, conviction, reflexivity_penalty)

            if total_exposure + size["adjusted_pct"] > max_total_exposure:
                remaining = max_total_exposure - total_exposure
                if remaining < self.min_position_pct:
                    break
                size["adjusted_pct"] = round(remaining, 4)
                size["dollar_size"] = round(remaining * self.portfolio_value, 2)
                size["notes"] += " | CAPPED by max exposure"

            total_exposure += size["adjusted_pct"]
            sized.append({
                "ticker": s.get("ticker"),
                "direction": s.get("direction"),
                **size,
            })

        return sized
