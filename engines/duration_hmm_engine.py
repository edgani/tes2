"""
engines/duration_hmm_engine.py — Duration-Dependent Hidden Markov Model v1.0
Upgrade dari standard HMM: transition probability increases dengan regime duration.
Capture realistic persistence (bull market 2021 = 18 bulan, bukan 6.7 hari).
"""
from __future__ import annotations
import math, logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger("duration_hmm_engine")

@dataclass
class DurationHMMState:
    regime: str
    duration: int  # days in current regime
    confidence: float
    transition_prob: float  # P(transition | duration)

class DurationHMMEngine:
    """
    3-state HMM dengan Weibull hazard function:
      h(d) = (k/λ) × (d/λ)^(k-1)
      P(transition | d) = base_P × (1 + α × h(d))
    """

    STATES = ["BULL", "BEAR", "SIDEWAYS"]

    def __init__(
        self,
        base_transition_matrix: Optional[np.ndarray] = None,
        weibull_k: float = 1.5,      # shape (k>1 = increasing hazard)
        weibull_lambda: float = 30.0,  # scale (days)
        alpha: float = 0.05,          # sensitivity to duration
    ):
        # Base transition matrix (stationary estimate)
        if base_transition_matrix is not None:
            self.P_base = base_transition_matrix
        else:
            # Default: slight persistence
            self.P_base = np.array([
                [0.85, 0.10, 0.05],   # BULL → BULL, BEAR, SIDEWAYS
                [0.10, 0.80, 0.10],   # BEAR → BULL, BEAR, SIDEWAYS
                [0.15, 0.15, 0.70],   # SIDEWAYS → BULL, BEAR, SIDEWAYS
            ])
        self.k = weibull_k
        self.lam = weibull_lambda
        self.alpha = alpha
        self.state_history: List[str] = []
        self.duration_history: List[int] = []

    def weibull_hazard(self, duration: int) -> float:
        if duration <= 0:
            return 0.0
        d = float(duration)
        return (self.k / self.lam) * ((d / self.lam) ** (self.k - 1))

    def duration_adjusted_transition(self, current_state: str, duration: int) -> np.ndarray:
        """
        Adjust base transition matrix berdasarkan duration di current state.
        """
        idx = self.STATES.index(current_state)
        h = self.weibull_hazard(duration)
        boost = 1.0 + self.alpha * h

        # Increase probability of LEAVING current state
        P = self.P_base.copy()
        p_stay = P[idx, idx]
        p_leave = 1.0 - p_stay

        # New stay probability decreases dengan duration
        new_stay = max(0.10, p_stay / boost)
        scale = (1.0 - new_stay) / p_leave if p_leave > 0 else 1.0

        for j in range(len(self.STATES)):
            if j == idx:
                P[idx, j] = new_stay
            else:
                P[idx, j] = min(0.90, P[idx, j] * scale)

        # Renormalize row
        row_sum = P[idx].sum()
        if row_sum > 0:
            P[idx] = P[idx] / row_sum

        return P

    def fit(self, prices: pd.Series, regime_labels: Optional[List[str]] = None) -> List[DurationHMMState]:
        """
        Fit duration-aware regime sequence dari price series.
        regime_labels: kalau None, infer dari price momentum (SMA20 vs SMA50).
        """
        s = pd.to_numeric(pd.Series(prices), errors="coerce").dropna()
        if len(s) < 50:
            return []

        if regime_labels is None:
            sma20 = s.rolling(20).mean()
            sma50 = s.rolling(50).mean()
            momentum = (sma20 - sma50) / sma50
            regime_labels = []
            for m in momentum.dropna():
                if m > 0.03:
                    regime_labels.append("BULL")
                elif m < -0.03:
                    regime_labels.append("BEAR")
                else:
                    regime_labels.append("SIDEWAYS")

        states = []
        current = regime_labels[0]
        duration = 1

        for label in regime_labels[1:]:
            P_adj = self.duration_adjusted_transition(current, duration)
            idx_from = self.STATES.index(current)
            idx_to = self.STATES.index(label)
            trans_prob = P_adj[idx_from, idx_to]

            states.append(DurationHMMState(
                regime=current,
                duration=duration,
                confidence=round(P_adj[idx_from, idx_from], 3),
                transition_prob=round(trans_prob, 4),
            ))

            if label == current:
                duration += 1
            else:
                current = label
                duration = 1

        # Append final
        P_adj = self.duration_adjusted_transition(current, duration)
        idx = self.STATES.index(current)
        states.append(DurationHMMState(
            regime=current,
            duration=duration,
            confidence=round(P_adj[idx, idx], 3),
            transition_prob=round(1.0 - P_adj[idx, idx], 4),
        ))

        self.state_history = [s.regime for s in states]
        self.duration_history = [s.duration for s in states]
        return states

    def current_regime(self) -> Optional[DurationHMMState]:
        if not self.state_history:
            return None
        # Return latest dengan duration adjusted confidence
        latest = self.state_history[-1]
        dur = self.duration_history[-1] if self.duration_history else 1
        P_adj = self.duration_adjusted_transition(latest, dur)
        idx = self.STATES.index(latest)
        return DurationHMMState(
            regime=latest,
            duration=dur,
            confidence=round(P_adj[idx, idx], 3),
            transition_prob=round(1.0 - P_adj[idx, idx], 4),
        )

    def forecast(self, steps: int = 5) -> Dict[str, List[float]]:
        """
        Forward forecast regime probabilities.
        """
        current = self.current_regime()
        if current is None:
            return {s: [0.33]*steps for s in self.STATES}

        idx = self.STATES.index(current.regime)
        P = self.duration_adjusted_transition(current.regime, current.duration)
        probs = {s: [] for s in self.STATES}
        dist = np.zeros(len(self.STATES))
        dist[idx] = 1.0

        for _ in range(steps):
            dist = dist @ P
            for i, s in enumerate(self.STATES):
                probs[s].append(round(dist[i], 3))
            # Increase duration for next step (simulate staying)
            P = self.duration_adjusted_transition(self.STATES[np.argmax(dist)], current.duration + 1)

        return probs


def run_duration_hmm(prices: pd.Series, **kwargs) -> Dict:
    """Convenience wrapper untuk integrate ke orchestrator."""
    engine = DurationHMMEngine(**kwargs)
    states = engine.fit(prices)
    current = engine.current_regime()
    forecast = engine.forecast(steps=5)

    return {
        "current_regime": current.regime if current else "UNKNOWN",
        "duration": current.duration if current else 0,
        "confidence": current.confidence if current else 0,
        "transition_prob": current.transition_prob if current else 0,
        "forecast_1d": {s: forecast[s][0] for s in forecast},
        "forecast_5d": {s: forecast[s][-1] for s in forecast},
        "n_states_recorded": len(states),
        "notes": [
            "Duration-Dependent HMM with Weibull hazard",
            "k={} λ={}d α={}".format(engine.k, engine.lam, engine.alpha),
        ],
    }
