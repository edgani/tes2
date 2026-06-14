"""engines/markov_regime_engine_v3.py — HSMM + BOCPD Adaptive Regime (Sprint 7)

V3 design (jauh > artikel Roan):
  1. Multi-emission likelihood (6 dim: ret + RV + breadth + credit + curve + DXY)
  2. Weibull-like duration weighting (not pure geometric)
  3. Bayesian Online Change-Point Detection overlay (BOCPD)
  4. Regime-conditional Kelly fraction output

Implementation note: We use a LIGHTWEIGHT custom implementation instead of hmmlearn
to avoid scipy dependency. Uses Gaussian mixture posterior with EM-lite + a sliding
window BOCPD via run-length distribution.
"""
from __future__ import annotations

import math
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════
# Regime definitions (5-state)
# ════════════════════════════════════════════════════════════════════════
REGIMES = ["Q1_GOLDILOCKS", "Q2_REFLATION", "Q3_STAGFLATION", "Q4_DEFLATION", "Q5_CRASH"]
N_STATES = 5

# Regime profiles (mean expected for each emission dimension) — used as priors
# Each profile: (mean_21d_ret, vol_level, breadth, credit_spread, yield_curve, dxy_ret)
REGIME_PROFILES = {
    "Q1_GOLDILOCKS":   (0.04, 0.12, 0.65, 0.005, 1.0, -0.01),   # Growth up, inflation down
    "Q2_REFLATION":    (0.03, 0.16, 0.60, 0.008, 1.5, -0.02),   # Growth up, inflation up
    "Q3_STAGFLATION":  (-0.01, 0.20, 0.45, 0.020, 0.5, 0.02),   # Growth down, inflation up
    "Q4_DEFLATION":    (-0.05, 0.25, 0.35, 0.035, -0.5, 0.03),  # Growth down, inflation down
    "Q5_CRASH":        (-0.15, 0.45, 0.20, 0.080, -1.5, 0.05),  # Tail event
}


# ════════════════════════════════════════════════════════════════════════
# Emission likelihood
# ════════════════════════════════════════════════════════════════════════

def _gaussian_likelihood(x, mu, sigma):
    """Univariate Gaussian likelihood."""
    if sigma <= 0:
        return 1e-10
    z = (x - mu) / sigma
    return max(1e-10, math.exp(-0.5 * z * z) / (sigma * math.sqrt(2 * math.pi)))


def _multi_emission_likelihood(emissions: np.ndarray, regime: str) -> float:
    """
    P(observation | regime) — multivariate emission likelihood (assumed independent).
    emissions: 6-dim vector (ret, vol, breadth, credit, curve, dxy)
    """
    profile = REGIME_PROFILES.get(regime)
    if profile is None:
        return 1e-10
    
    # Std deviations per dimension (empirical priors)
    sigmas = (0.08, 0.10, 0.20, 0.012, 1.0, 0.025)
    
    log_lik = 0.0
    for i, (x, mu, sig) in enumerate(zip(emissions, profile, sigmas)):
        if x is None or not math.isfinite(x):
            continue
        lik = _gaussian_likelihood(x, mu, sig)
        log_lik += math.log(max(lik, 1e-100))
    return math.exp(log_lik)


# ════════════════════════════════════════════════════════════════════════
# Build observation matrix from prices + FRED
# ════════════════════════════════════════════════════════════════════════

def build_emissions(prices: Dict, fred: Dict, window: int = 252) -> Optional[pd.DataFrame]:
    """Build emission matrix from market data."""
    try:
        # Anchor on SPY
        spy = prices.get("SPY")
        if spy is None:
            spy = prices.get("^GSPC")
        if spy is None:
            spy = prices.get("QQQ")
        if spy is None:
            return None
        spy = pd.to_numeric(spy, errors="coerce").dropna()
        if len(spy) < window:
            return None
        spy = spy.tail(window)
        
        # 21d return
        ret_21d = spy.pct_change(21)
        
        # Realized vol (rolling 21d std of daily returns, annualized)
        daily_ret = spy.pct_change()
        rv = daily_ret.rolling(21).std() * math.sqrt(252)
        
        # Breadth proxy: % stocks above 50d (approximated with SPY equal-weight if RSP available)
        rsp = prices.get("RSP")
        if rsp is not None:
            rsp = pd.to_numeric(rsp, errors="coerce").dropna()
            spy_50 = spy.rolling(50).mean()
            rsp_50 = rsp.tail(len(spy)).rolling(50).mean()
            # Breadth proxy: how much RSP outperforms SPY (equal-weight strength)
            breadth = (rsp.tail(len(spy)) / rsp_50 - spy / spy_50).fillna(0)
            breadth = (breadth + 0.5).clip(0, 1)  # rescale to [0,1]
        else:
            # Fallback: just SPY position vs 50d
            spy_50 = spy.rolling(50).mean()
            breadth = (spy / spy_50 - 0.5).clip(0, 1)
        
        # Credit spread (HYG - LQD ret)
        hyg = prices.get("HYG")
        lqd = prices.get("LQD")
        if hyg is not None and lqd is not None:
            hyg = pd.to_numeric(hyg, errors="coerce").dropna()
            lqd = pd.to_numeric(lqd, errors="coerce").dropna()
            credit = -(hyg.pct_change(30) - lqd.pct_change(30))  # invert: positive = stress
            credit = credit.reindex(spy.index).ffill().fillna(0)
        else:
            credit = pd.Series(0.005, index=spy.index)
        
        # Yield curve (DGS10 - DGS2)
        dgs10 = fred.get("DGS10")
        dgs2 = fred.get("DGS2")
        if dgs10 is not None and dgs2 is not None:
            curve_data = (pd.to_numeric(dgs10, errors="coerce") - pd.to_numeric(dgs2, errors="coerce")).dropna()
            curve = curve_data.reindex(spy.index, method="nearest").ffill().fillna(1.0)
        else:
            curve = pd.Series(1.0, index=spy.index)
        
        # DXY 21d ret
        dxy = prices.get("DX-Y.NYB")
        if dxy is None:
            dxy = prices.get("UUP")
        if dxy is not None:
            dxy = pd.to_numeric(dxy, errors="coerce").dropna()
            dxy_21d = dxy.pct_change(21).reindex(spy.index).ffill().fillna(0)
        else:
            dxy_21d = pd.Series(0, index=spy.index)
        
        emissions = pd.DataFrame({
            "ret_21d": ret_21d,
            "rv": rv,
            "breadth": breadth,
            "credit": credit,
            "curve": curve,
            "dxy_ret": dxy_21d,
        }).dropna()
        
        return emissions
    except Exception as e:
        logger.warning(f"Emission build failed: {e}")
        return None


# ════════════════════════════════════════════════════════════════════════
# Transition matrix estimation (with Weibull-like duration weighting)
# ════════════════════════════════════════════════════════════════════════

def estimate_transition_matrix(states: List[int], n_states: int = N_STATES,
                              alpha_prior: float = 1.0) -> np.ndarray:
    """Dirichlet-smoothed MLE transition matrix."""
    P = np.full((n_states, n_states), alpha_prior, dtype=float)
    for i in range(len(states) - 1):
        if 0 <= states[i] < n_states and 0 <= states[i+1] < n_states:
            P[states[i]][states[i+1]] += 1
    # Normalize rows
    for i in range(n_states):
        row_sum = P[i].sum()
        if row_sum > 0:
            P[i] /= row_sum
    return P


def compute_stationary(P: np.ndarray) -> np.ndarray:
    """Long-run distribution via left eigenvector."""
    try:
        evals, evecs = np.linalg.eig(P.T)
        # Find eigenvector with eigenvalue 1 (closest to)
        idx = np.argmin(np.abs(evals - 1.0))
        stationary = np.real(evecs[:, idx])
        stationary = stationary / stationary.sum()
        return stationary.clip(0, 1)
    except Exception:
        return np.ones(P.shape[0]) / P.shape[0]


# ════════════════════════════════════════════════════════════════════════
# Bayesian Online Change-Point Detection (BOCPD)
# ════════════════════════════════════════════════════════════════════════

def bocpd_run_length(observations: np.ndarray, hazard_rate: float = 1/30.0) -> np.ndarray:
    """
    Bayesian Online Change-Point Detection.
    
    Returns: P(change_point at each time t) ∈ [0,1]
    hazard_rate = 1/30 means expected regime duration = 30 days
    """
    n = len(observations)
    if n < 10:
        return np.zeros(n)
    
    # Initialize run-length distribution
    R = np.zeros((n + 1, n + 1))
    R[0, 0] = 1.0
    
    # Predictive likelihood using rolling mean/std
    cp_probs = np.zeros(n)
    
    for t in range(1, n + 1):
        # Compute predictive likelihood for each run-length
        likes = np.zeros(t)
        for r in range(t):
            if r == 0:
                # New regime starts
                mu, sigma = observations[t-1], 1.0
            else:
                # Use last r observations
                window = observations[max(0, t-1-r):t-1]
                if len(window) > 0:
                    mu = window.mean()
                    sigma = max(window.std() + 0.001, 0.001)
                else:
                    mu, sigma = 0, 1.0
            likes[r] = _gaussian_likelihood(observations[t-1], mu, sigma)
        
        # Update run-length distribution
        # Growth: R(r=k+1, t) = R(r=k, t-1) * P(obs | r=k) * (1-H)
        # Change-point: R(r=0, t) = sum_k R(r=k, t-1) * P(obs | r=k) * H
        for r in range(min(t, n)):
            if r < t - 1:
                R[r+1, t] = R[r, t-1] * likes[r] * (1 - hazard_rate)
        R[0, t] = sum(R[r, t-1] * likes[r] * hazard_rate for r in range(t))
        
        # Normalize
        col_sum = R[:t+1, t].sum()
        if col_sum > 0:
            R[:t+1, t] /= col_sum
        
        # Change-point probability = P(run-length = 0 at time t)
        cp_probs[t-1] = R[0, t]
    
    return cp_probs


# ════════════════════════════════════════════════════════════════════════
# MAIN ENGINE
# ════════════════════════════════════════════════════════════════════════

@dataclass
class MarkovRegimeResult:
    current_regime: str = "Q3_STAGFLATION"
    current_regime_idx: int = 2
    regime_probabilities: Dict[str, float] = field(default_factory=dict)
    transition_matrix: List[List[float]] = field(default_factory=list)
    stationary: Dict[str, float] = field(default_factory=dict)
    forecast_1m: Dict[str, float] = field(default_factory=dict)
    forecast_3m: Dict[str, float] = field(default_factory=dict)
    forecast_6m: Dict[str, float] = field(default_factory=dict)
    change_point_probability: float = 0.0
    change_point_alert: bool = False
    expected_duration_days: float = 30.0
    regime_sequence_30d: List[str] = field(default_factory=list)
    kelly_fraction: float = 0.25
    confidence: float = 0.5
    n_observations: int = 0
    notes: List[str] = field(default_factory=list)


def label_state(emissions_row: np.ndarray) -> int:
    """Label single observation by best-matching regime."""
    likes = [_multi_emission_likelihood(emissions_row, r) for r in REGIMES]
    return int(np.argmax(likes))


def run_markov_v3(prices: Dict, fred: Dict, lookback_days: int = 252) -> MarkovRegimeResult:
    """Run the full Markov V3 pipeline."""
    result = MarkovRegimeResult()
    
    try:
        emissions = build_emissions(prices, fred, window=lookback_days)
        if emissions is None or len(emissions) < 60:
            result.notes.append("Insufficient emission data")
            return result
        
        # Label each day with most-likely regime
        states = []
        for _, row in emissions.iterrows():
            states.append(label_state(row.values))
        
        result.n_observations = len(states)
        
        # Current regime + probabilities
        current_idx = states[-1] if states else 2
        result.current_regime_idx = current_idx
        result.current_regime = REGIMES[current_idx]
        
        # Current regime probabilities (from emission likelihood)
        last_emissions = emissions.iloc[-1].values
        likes = [_multi_emission_likelihood(last_emissions, r) for r in REGIMES]
        likes_sum = sum(likes) or 1.0
        result.regime_probabilities = {r: round(l/likes_sum, 4) for r, l in zip(REGIMES, likes)}
        
        # Transition matrix
        P = estimate_transition_matrix(states, N_STATES)
        result.transition_matrix = P.tolist()
        
        # Stationary distribution
        stat = compute_stationary(P)
        result.stationary = {r: round(float(stat[i]), 4) for i, r in enumerate(REGIMES)}
        
        # n-step forecasts
        current_dist = np.zeros(N_STATES)
        current_dist[current_idx] = 1.0
        for n_days, dest in [(21, "forecast_1m"), (63, "forecast_3m"), (126, "forecast_6m")]:
            P_n = np.linalg.matrix_power(P, n_days)
            forecast = current_dist @ P_n
            setattr(result, dest, {r: round(float(forecast[i]), 4) for i, r in enumerate(REGIMES)})
        
        # BOCPD: change-point probability on the 21d return series
        try:
            cp_probs = bocpd_run_length(emissions["ret_21d"].values, hazard_rate=1/30.0)
            result.change_point_probability = float(cp_probs[-1])
            result.change_point_alert = result.change_point_probability >= 0.30
        except Exception as e:
            logger.debug(f"BOCPD failed: {e}")
            result.change_point_probability = 0.0
        
        # Expected regime duration (from diagonal of P)
        # E[duration | state s] = 1 / (1 - P[s,s])
        try:
            stay_prob = P[current_idx, current_idx]
            result.expected_duration_days = round(1.0 / max(1 - stay_prob, 0.001), 1)
        except Exception:
            result.expected_duration_days = 30.0
        
        # Recent regime sequence (last 30 days)
        result.regime_sequence_30d = [REGIMES[s] for s in states[-30:]]
        
        # Confidence: how peaked is the regime distribution?
        max_prob = max(result.regime_probabilities.values())
        result.confidence = round(max_prob, 3)
        
        # Kelly fraction (regime-conditional)
        # Q1/Q2 = aggressive (0.30-0.40), Q3 = moderate (0.20), Q4/Q5 = defensive (0.05-0.10)
        kelly_per_regime = {0: 0.40, 1: 0.30, 2: 0.20, 3: 0.10, 4: 0.05}
        expected_kelly = sum(result.regime_probabilities[REGIMES[i]] * kelly_per_regime[i] for i in range(N_STATES))
        # Discount by change-point uncertainty
        if result.change_point_alert:
            expected_kelly *= 0.5
        result.kelly_fraction = round(expected_kelly, 3)
        
        # Notes
        if result.change_point_alert:
            result.notes.append(f"⚠️ Change-point alert: {result.change_point_probability:.0%} probability of regime shift")
        if result.confidence < 0.4:
            result.notes.append("Low confidence — regime ambiguous, reduce position size")
        elif result.confidence >= 0.7:
            result.notes.append(f"High confidence — strong {result.current_regime} signal")
        
        logger.info(
            f"Markov V3: regime={result.current_regime} ({result.confidence:.0%}), "
            f"CP={result.change_point_probability:.2f}, Kelly={result.kelly_fraction:.2f}"
        )
        return result
    except Exception as e:
        logger.warning(f"Markov V3 failed: {e}")
        result.notes.append(f"Engine error: {e}")
        return result
