"""
engines/walkforward_engine.py — Walk-Forward Backtest + Pre-Flight Gate v1.0
Validasi setup historically sebelum ticker muncul di dashboard.
"""
from __future__ import annotations
import math, json, logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from datetime import datetime

import numpy as np
import pandas as pd

logger = logging.getLogger("walkforward_engine")

@dataclass
class WalkForwardResult:
    ticker: str
    direction: str
    consistency_score: float      # % windows yang pass threshold
    robustness_score: float       # min(worst_case) across windows
    avg_win_rate: float
    avg_sharpe: float
    avg_max_dd: float
    avg_kelly: float
    n_windows: int
    n_pass_windows: int
    passes_gate: bool
    walkforward_idhl: float        # decay half-life dari signal
    notes: List[str]

class WalkForwardEngine:
    """
    Rolling window backtest:
      train_days = 180  → fit risk range / options proxy
      test_days  = 21   → out-of-sample forward test
      step_days  = 5    → roll forward
    Untuk setiap window:
      1. Generate setup (entry/stop/target) dari train data
      2. Monte Carlo 100x dengan GBM paths di test period
      3. Record metrics
    Gate: consistency > 60% AND robustness > 65 → PASS
    """

    def __init__(
        self,
        train_days: int = 180,
        test_days: int = 21,
        step_days: int = 5,
        n_sims: int = 100,
        win_rate_threshold: float = 0.55,
        sharpe_threshold: float = 0.8,
        max_dd_threshold: float = 0.15,
        consistency_threshold: float = 0.60,
        robustness_threshold: float = 65.0,
    ):
        self.train_days = train_days
        self.test_days = test_days
        self.step_days = step_days
        self.n_sims = n_sims
        self.win_rate_threshold = win_rate_threshold
        self.sharpe_threshold = sharpe_threshold
        self.max_dd_threshold = max_dd_threshold
        self.consistency_threshold = consistency_threshold
        self.robustness_threshold = robustness_threshold

    # ── helpers ──
    @staticmethod
    def _safe_series(s) -> pd.Series:
        if s is None:
            return pd.Series(dtype=float)
        try:
            return pd.to_numeric(pd.Series(s), errors="coerce").dropna()
        except Exception:
            return pd.Series(dtype=float)

    @staticmethod
    def _gbm_paths(S0: float, mu: float, sigma: float, T: int, n_sims: int, seed: Optional[int] = None) -> np.ndarray:
        """Generate n_sims GBM paths of length T."""
        if seed is not None:
            np.random.seed(seed)
        dt = 1.0
        paths = np.zeros((n_sims, T))
        paths[:, 0] = S0
        for t in range(1, T):
            Z = np.random.standard_normal(n_sims)
            paths[:, t] = paths[:, t-1] * np.exp((mu - 0.5*sigma**2)*dt + sigma*np.sqrt(dt)*Z)
        return paths

    def _simulate_window(
        self,
        ticker: str,
        series: pd.Series,
        train_idx: slice,
        test_idx: slice,
        direction: str,
        entry: float,
        stop: float,
        target: float,
    ) -> Optional[Dict]:
        """Monte Carlo 1 window. Returns dict of metrics or None."""
        train = series.iloc[train_idx]
        test = series.iloc[test_idx]
        if len(train) < self.train_days * 0.8 or len(test) < self.test_days * 0.5:
            return None

        # GBM params dari train
        returns = train.pct_change().dropna()
        mu = float(returns.mean()) if len(returns) > 0 else 0.0
        sigma = float(returns.std()) if len(returns) > 0 else 0.01
        S0 = float(train.iloc[-1])
        T = len(test)

        paths = self._gbm_paths(S0, mu, sigma, T, self.n_sims, seed=42)

        wins = 0
        losses = 0
        pnl_list = []
        max_dd_list = []

        for i in range(self.n_sims):
            path = paths[i]
            hit_target = False
            hit_stop = False
            peak = path[0]
            trough = path[0]
            for px in path:
                if px > peak:
                    peak = px
                if px < trough:
                    trough = px
                if direction == "LONG":
                    if px >= target:
                        hit_target = True
                        break
                    if px <= stop:
                        hit_stop = True
                        break
                else:  # SHORT
                    if px <= target:
                        hit_target = True
                        break
                    if px >= stop:
                        hit_stop = True
                        break

            if hit_target:
                wins += 1
                pnl = abs(target - entry) / entry if entry != 0 else 0
            elif hit_stop:
                losses += 1
                pnl = -abs(stop - entry) / entry if entry != 0 else 0
            else:
                # Hold until end — mark-to-market
                final = path[-1]
                pnl = (final - entry) / entry if direction == "LONG" else (entry - final) / entry
                if entry != 0:
                    pnl /= abs(entry)
                else:
                    pnl = 0
                if pnl > 0:
                    wins += 1
                else:
                    losses += 1

            pnl_list.append(pnl)
            dd = (trough - peak) / peak if peak != 0 else 0
            max_dd_list.append(dd)

        total = wins + losses
        win_rate = wins / total if total > 0 else 0
        mean_pnl = np.mean(pnl_list)
        std_pnl = np.std(pnl_list) if np.std(pnl_list) > 0 else 1e-6
        sharpe = mean_pnl / std_pnl * np.sqrt(252 / T) if std_pnl > 0 else 0
        max_dd = abs(min(max_dd_list)) if max_dd_list else 0

        # Kelly fraction
        b = abs(target - entry) / max(abs(stop - entry), 1e-6) if entry != 0 else 1.0
        p = win_rate
        kelly_raw = (p * (b + 1) - 1) / b if b > 0 else 0
        kelly = max(0, min(1, kelly_raw))

        return {
            "win_rate": win_rate,
            "sharpe": sharpe,
            "max_dd": max_dd,
            "kelly": kelly,
            "mean_pnl": mean_pnl,
            "pass": win_rate >= self.win_rate_threshold and sharpe >= self.sharpe_threshold and max_dd <= self.max_dd_threshold,
        }

    def run(
        self,
        ticker: str,
        prices: pd.Series,
        direction: str,
        entry: float,
        stop: float,
        target: float,
    ) -> WalkForwardResult:
        """
        Main entry: run walk-forward backtest untuk 1 ticker + 1 setup.
        """
        series = self._safe_series(prices)
        if len(series) < self.train_days + self.test_days + 20:
            return WalkForwardResult(
                ticker=ticker, direction=direction,
                consistency_score=0, robustness_score=0,
                avg_win_rate=0, avg_sharpe=0, avg_max_dd=0, avg_kelly=0,
                n_windows=0, n_pass_windows=0, passes_gate=False,
                walkforward_idhl=0.0,
                notes=["Insufficient history (< {} days)".format(self.train_days + self.test_days)]
            )

        windows = []
        total_len = len(series)
        start = self.train_days
        while start + self.test_days <= total_len:
            train_idx = slice(start - self.train_days, start)
            test_idx = slice(start, start + self.test_days)
            res = self._simulate_window(ticker, series, train_idx, test_idx, direction, entry, stop, target)
            if res:
                windows.append(res)
            start += self.step_days

        if not windows:
            return WalkForwardResult(
                ticker=ticker, direction=direction,
                consistency_score=0, robustness_score=0,
                avg_win_rate=0, avg_sharpe=0, avg_max_dd=0, avg_kelly=0,
                n_windows=0, n_pass_windows=0, passes_gate=False,
                walkforward_idhl=0.0,
                notes=["No valid windows generated"]
            )

        n_pass = sum(1 for w in windows if w["pass"])
        consistency = n_pass / len(windows)
        robustness = min(w["win_rate"] * 100 for w in windows)  # worst-case win rate

        result = WalkForwardResult(
            ticker=ticker,
            direction=direction,
            consistency_score=round(consistency, 3),
            robustness_score=round(robustness, 1),
            avg_win_rate=round(np.mean([w["win_rate"] for w in windows]), 3),
            avg_sharpe=round(np.mean([w["sharpe"] for w in windows]), 3),
            avg_max_dd=round(np.mean([w["max_dd"] for w in windows]), 4),
            avg_kelly=round(np.mean([w["kelly"] for w in windows]), 3),
            n_windows=len(windows),
            n_pass_windows=n_pass,
            passes_gate=(consistency >= self.consistency_threshold and robustness >= self.robustness_threshold),
            walkforward_idhl=0.0,  # diisi oleh SignalDecayEngine
            notes=[
                "{} windows / {} pass".format(len(windows), n_pass),
                "Consistency {:.1%} | Robustness {:.1f}".format(consistency, robustness),
            ]
        )
        return result


def run_walkforward_batch(
    setups: List[Dict],
    prices_map: Dict[str, pd.Series],
    engine: Optional[WalkForwardEngine] = None,
) -> Dict[str, WalkForwardResult]:
    """
    setups: list of dict dengan keys: ticker, direction, entry, stop, target
    prices_map: {ticker: pd.Series}
    """
    if engine is None:
        engine = WalkForwardEngine()
    results = {}
    for setup in setups:
        t = setup.get("ticker")
        if t not in prices_map:
            continue
        res = engine.run(
            ticker=t,
            prices=prices_map[t],
            direction=setup.get("direction", "LONG"),
            entry=float(setup.get("entry", 0)),
            stop=float(setup.get("stop", 0)),
            target=float(setup.get("target", 0)),
        )
        results[t] = res
    return results


def filter_by_walkforward(
    rows: List[Dict],
    wf_results: Dict[str, WalkForwardResult],
    require_pass: bool = True,
) -> List[Dict]:
    """Filter ticker rows yang lolos walk-forward gate."""
    out = []
    for row in rows:
        t = row.get("ticker")
        wf = wf_results.get(t)
        if wf is None:
            continue
        row["walkforward"] = {
            "consistency": wf.consistency_score,
            "robustness": wf.robustness_score,
            "avg_win_rate": wf.avg_win_rate,
            "avg_sharpe": wf.avg_sharpe,
            "avg_max_dd": wf.avg_max_dd,
            "n_windows": wf.n_windows,
            "passes_gate": wf.passes_gate,
        }
        if not require_pass or wf.passes_gate:
            out.append(row)
    return out
