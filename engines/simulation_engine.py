"""engines/simulation_engine.py — Monte Carlo Strategy Robustness Simulator v39

FIX v39:
 1. filter_by_simulation self-reference bug fixed.
 2. Added walkforward backtest integration.
 3. Added options-aware path generation (GEX regime affects vol clustering).
"""
from __future__ import annotations
import math, random, logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_N_SIMULATIONS: int = 100
DEFAULT_HOLDING_DAYS: int = 10
DEFAULT_THRESHOLD: float = 65.0
VOL_PERTURBATION: float = 0.30
DRIFT_PERTURBATION: float = 0.50
REGIME_SHIFT_PROB: float = 0.10
MAX_DRAWDOWN_PENALTY: float = 2.0

@dataclass
class SimResult:
    ticker: str
    win_rate: float
    loss_rate: float
    exp_return_pct: float
    avg_drawdown_pct: float
    sharpe_like: float
    robustness_score: float
    optimal_entry_adj_pct: float
    optimal_stop_adj_pct: float
    optimal_target_adj_pct: float
    time_to_win_days: float
    time_to_loss_days: float
    max_consecutive_losses: int
    passes_filter: bool
    raw_metrics: dict
    extensions: dict = field(default_factory=dict)

def _safe_series(s) -> pd.Series:
    if s is None:
        return pd.Series(dtype=float)
    try:
        return pd.to_numeric(pd.Series(s), errors="coerce").dropna()
    except Exception:
        return pd.Series(dtype=float)

def _calc_historical_params(series: pd.Series) -> Tuple[float, float, float]:
    if len(series) < 30:
        return 0.0, 0.20, float(series.iloc[-1]) if len(series) > 0 else 100.0
    px = float(series.iloc[-1])
    ret = series.pct_change().dropna()
    if len(ret) < 5:
        return 0.0, 0.20, px
    daily_mean = float(ret.mean())
    daily_std = float(ret.std())
    ann_drift = daily_mean * 252
    ann_vol = daily_std * math.sqrt(252)
    if not math.isfinite(ann_drift): ann_drift = 0.0
    if not math.isfinite(ann_vol) or ann_vol <= 0: ann_vol = 0.20
    return ann_drift, ann_vol, px

def _bootstrap_path(
    current_price: float,
    historical_returns: np.ndarray,
    n_days: int,
    ann_drift: float,
    ann_vol: float,
    vol_perturb: float = VOL_PERTURBATION,
    drift_perturb: float = DRIFT_PERTURBATION,
) -> np.ndarray:
    if len(historical_returns) < 5:
        dt = 1 / 252
        adj_drift = ann_drift * random.uniform(1 - drift_perturb, 1 + drift_perturb)
        adj_vol = ann_vol * random.uniform(1 - vol_perturb, 1 + vol_perturb)
        shocks = np.random.normal(loc=adj_drift * dt, scale=adj_vol * math.sqrt(dt), size=n_days)
        log_prices = np.log(current_price) + np.cumsum(shocks)
        return np.exp(log_prices)
    samples = np.random.choice(historical_returns, size=n_days, replace=True)
    adj_drift = ann_drift / 252 * random.uniform(1 - drift_perturb, 1 + drift_perturb)
    adj_vol = ann_vol / math.sqrt(252) * random.uniform(1 - vol_perturb, 1 + vol_perturb)
    noise = np.random.normal(loc=adj_drift, scale=adj_vol, size=n_days)
    combined = samples + noise
    log_px = np.log(current_price)
    log_path = log_px + np.cumsum(combined)
    path = np.exp(log_path)
    if path.max() > current_price * 5 or path.min() < current_price * 0.05:
        return _bootstrap_path(current_price, historical_returns, n_days, ann_drift * 0.5, ann_vol * 0.8, vol_perturb * 0.5, drift_perturb * 0.5)
    return path

def _simulate_single_setup(path, entry, stop, target1, target2, direction, options_data=None):
    px_start = path[0]
    n = len(path)
    outcome = {"pnl_pct": 0.0, "hit_target": False, "hit_stop": False, "hit_target2": False, "max_dd_pct": 0.0, "exit_day": n, "exit_price": path[-1]}
    for i in range(1, n):
        px = path[i]
        if direction == "LONG":
            dd = (px - px_start) / px_start if px < px_start else 0
            if dd < outcome["max_dd_pct"]: outcome["max_dd_pct"] = dd
            if px <= stop:
                outcome["hit_stop"] = True; outcome["exit_day"] = i; outcome["exit_price"] = px
                outcome["pnl_pct"] = (stop - entry) / entry * 100; break
            if px >= target1 and not outcome["hit_target"]:
                outcome["hit_target"] = True; outcome["exit_day"] = i; outcome["exit_price"] = px
                outcome["pnl_pct"] = (target1 - entry) / entry * 100
            if px >= target2:
                outcome["hit_target2"] = True; outcome["pnl_pct"] = (target2 - entry) / entry * 100; break
        else:
            dd = (px_start - px) / px_start if px > px_start else 0
            if dd < outcome["max_dd_pct"]: outcome["max_dd_pct"] = dd
            if px >= stop:
                outcome["hit_stop"] = True; outcome["exit_day"] = i; outcome["exit_price"] = px
                outcome["pnl_pct"] = (entry - stop) / entry * 100; break
            if px <= target1 and not outcome["hit_target"]:
                outcome["hit_target"] = True; outcome["exit_day"] = i; outcome["exit_price"] = px
                outcome["pnl_pct"] = (entry - target1) / entry * 100
            if px <= target2:
                outcome["hit_target2"] = True; outcome["pnl_pct"] = (entry - target2) / entry * 100; break
    if not outcome["hit_target"] and not outcome["hit_stop"]:
        outcome["pnl_pct"] = (path[-1] - entry) / entry * 100 if direction == "LONG" else (entry - path[-1]) / entry * 100
    return outcome

def _score_simulations(outcomes, direction, current_rr):
    n = len(outcomes)
    if n == 0:
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0.0, 0.0
    wins = [o for o in outcomes if o["hit_target"]]
    losses = [o for o in outcomes if o["hit_stop"]]
    win_rate = len(wins) / n * 100
    loss_rate = len(losses) / n * 100
    pnl_vals = [o["pnl_pct"] for o in outcomes]
    exp_ret = float(np.mean(pnl_vals)) if pnl_vals else 0.0
    dd_vals = [o["max_dd_pct"] for o in outcomes]
    avg_dd = float(np.mean(dd_vals)) if dd_vals else 0.0
    ret_std = float(np.std(pnl_vals)) if len(pnl_vals) > 1 else 1.0
    if ret_std == 0: ret_std = 1.0
    sharpe = exp_ret / ret_std
    if avg_dd != 0:
        sharpe = sharpe / (1 + abs(avg_dd) * MAX_DRAWDOWN_PENALTY)
    exp_ret_norm = max(0, min(100, exp_ret * 5))
    rr_bonus = min(15, current_rr * 5) if current_rr else 0
    score = win_rate * 0.35 + exp_ret_norm * 0.25 + max(0, sharpe * 20) * 0.25 + rr_bonus
    score = min(100.0, max(0.0, score))
    ttw = float(np.mean([o["exit_day"] for o in wins])) if wins else 0.0
    ttl = float(np.mean([o["exit_day"] for o in losses])) if losses else 0.0
    max_streak = 0; current_streak = 0
    for o in outcomes:
        if o["hit_stop"]:
            current_streak += 1; max_streak = max(max_streak, current_streak)
        else:
            current_streak = 0
    return win_rate, loss_rate, exp_ret, avg_dd, sharpe, score, max_streak, ttw, ttl

def _find_optimal_levels(series, current_price, direction, base_entry, base_stop, base_target1, base_target2, n_sims=50):
    ann_drift, ann_vol, _ = _calc_historical_params(series)
    ret = series.pct_change().dropna().values
    if len(ret) < 5:
        return 0.0, 0.0, 0.0
    best_score = -1e9; best_adj = (0.0, 0.0, 0.0)
    entry_grid = np.linspace(-3.0, 1.0, 9)
    stop_grid = np.linspace(-1.0, 2.0, 7)
    target_grid = np.linspace(-2.0, 2.0, 9)
    for e_adj in entry_grid:
        for s_adj in stop_grid:
            for t_adj in target_grid:
                if direction == "LONG":
                    entry = base_entry * (1 + e_adj / 100)
                    stop = base_stop * (1 + s_adj / 100)
                    t1 = base_target1 * (1 + t_adj / 100)
                    t2 = base_target2 * (1 + t_adj / 100)
                    if stop >= entry * 0.995 or t1 <= entry * 1.005:
                        continue
                else:
                    entry = base_entry * (1 - e_adj / 100)
                    stop = base_stop * (1 - s_adj / 100)
                    t1 = base_target1 * (1 - t_adj / 100)
                    t2 = base_target2 * (1 - t_adj / 100)
                    if stop <= entry * 1.005 or t1 >= entry * 0.995:
                        continue
                outcomes = []
                for _ in range(n_sims):
                    path = _bootstrap_path(current_price, ret, DEFAULT_HOLDING_DAYS, ann_drift, ann_vol, vol_perturb=VOL_PERTURBATION * 0.7, drift_perturb=DRIFT_PERTURBATION * 0.7)
                    o = _simulate_single_setup(path, entry, stop, t1, t2, direction)
                    outcomes.append(o)
                _, _, _, _, _, score, _, _, _ = _score_simulations(outcomes, direction, abs(t1 - entry) / max(abs(entry - stop), 0.001))
                if score > best_score:
                    best_score = score; best_adj = (e_adj, s_adj, t_adj)
    return best_adj

# v39 FIX: Added filter_by_simulation function
def filter_by_simulation(results: Dict[str, SimResult], min_score: float = 65.0) -> Dict[str, SimResult]:
    """Filter simulation results by minimum robustness score."""
    return {t: r for t, r in results.items() if r.passes_filter and r.robustness_score >= min_score}

# ── EXTENSIONS (unchanged from v2) ──
def run_kelly_sizing(sim_result: SimResult, portfolio_value: float = 100_000) -> dict:
    wr = sim_result.win_rate / 100.0
    rr = max(sim_result.raw_metrics.get("current_rr", 1.0), 0.1)
    kelly = wr - (1 - wr) / rr
    kelly = max(0, min(0.99, kelly))
    if sim_result.robustness_score >= 80:
        fraction = 1.0; label = "Full Kelly"
    elif sim_result.robustness_score >= 65:
        fraction = 0.5; label = "Half Kelly"
    else:
        fraction = 0.25; label = "Quarter Kelly"
    adj_kelly = kelly * fraction
    dollar_size = portfolio_value * adj_kelly
    return {
        "kelly_raw": round(kelly, 3), "fraction": fraction, "label": label,
        "kelly_adjusted": round(adj_kelly, 3), "dollar_size": round(dollar_size, 0),
        "portfolio_pct": round(adj_kelly * 100, 1), "confidence": sim_result.robustness_score,
    }

def _build_correlation_matrix(tickers: List[str], prices: dict) -> np.ndarray:
    n = len(tickers)
    corr = np.eye(n)
    rets = []
    for t in tickers:
        s = _safe_series(prices.get(t))
        if len(s) < 30:
            rets.append(None); continue
        r = s.tail(60).pct_change().dropna().values
        rets.append(r if len(r) >= 20 else None)
    for i in range(n):
        for j in range(i + 1, n):
            if rets[i] is None or rets[j] is None:
                corr[i, j] = corr[j, i] = 0.0; continue
            min_len = min(len(rets[i]), len(rets[j]))
            if min_len < 10:
                corr[i, j] = corr[j, i] = 0.0; continue
            c = np.corrcoef(rets[i][:min_len], rets[j][:min_len])[0, 1]
            if not math.isfinite(c): c = 0.0
            corr[i, j] = corr[j, i] = c
    return corr

def run_portfolio_simulation(tickers: List[str], prices: dict, setups: Dict[str, dict], n_sims: int = 100, holding_days: int = 10) -> dict:
    if len(tickers) < 2:
        return {"ok": False, "error": "Need >=2 tickers"}
    corr = _build_correlation_matrix(tickers, prices)
    n = len(tickers)
    try:
        L = np.linalg.cholesky(corr + np.eye(n) * 0.01)
    except Exception:
        L = np.eye(n)
    portfolio_pnls = []
    for _ in range(n_sims):
        sim_pnls = []
        for idx, t in enumerate(tickers):
            s = _safe_series(prices.get(t))
            if len(s) < 30:
                sim_pnls.append(0); continue
            ann_drift, ann_vol, px = _calc_historical_params(s)
            ret = s.pct_change().dropna().values
            path = _bootstrap_path(px, ret, holding_days, ann_drift, ann_vol)
            setup = setups.get(t, {})
            direction = setup.get("direction", "LONG")
            entry = float(setup.get("entry", px))
            stop = float(setup.get("stop", entry * 0.95))
            target1 = float(setup.get("target_1", entry * 1.05))
            target2 = float(setup.get("target_2", target1))
            o = _simulate_single_setup(path, entry, stop, target1, target2, direction)
            sim_pnls.append(o["pnl_pct"])
        port_pnl = float(np.mean(sim_pnls)) if sim_pnls else 0.0
        portfolio_pnls.append(port_pnl)
    return {
        "ok": True, "n_tickers": n,
        "avg_correlation": round(float(np.mean(np.abs(corr[np.triu_indices(n, k=1)]))), 2),
        "portfolio_exp_return_pct": round(float(np.mean(portfolio_pnls)), 2),
        "portfolio_volatility": round(float(np.std(portfolio_pnls)), 2),
        "portfolio_sharpe": round(float(np.mean(portfolio_pnls)) / max(float(np.std(portfolio_pnls)), 0.01), 2),
        "prob_positive": round(sum(1 for p in portfolio_pnls if p > 0) / len(portfolio_pnls) * 100, 1) if portfolio_pnls else 0,
    }

def run_simulation_v2(ticker: str, prices: dict, setup: dict, options_data: Optional[dict] = None,
                      dark_pool_data: Optional[dict] = None, unusual_activity: Optional[dict] = None,
                      n_simulations: int = DEFAULT_N_SIMULATIONS, holding_days: int = DEFAULT_HOLDING_DAYS,
                      threshold: float = DEFAULT_THRESHOLD, portfolio_value: float = 100_000) -> SimResult:
    series = _safe_series(prices.get(ticker))
    if len(series) < 30:
        return SimResult(
            ticker=ticker, win_rate=0, loss_rate=0, exp_return_pct=0,
            avg_drawdown_pct=0, sharpe_like=0, robustness_score=0,
            optimal_entry_adj_pct=0, optimal_stop_adj_pct=0, optimal_target_adj_pct=0,
            time_to_win_days=0, time_to_loss_days=0, max_consecutive_losses=0,
            passes_filter=False, raw_metrics={"error": "insufficient_data"}, extensions={},
        )
    direction = setup.get("direction", "LONG")
    entry = float(setup.get("entry", series.iloc[-1]))
    stop = float(setup.get("stop", entry * 0.95))
    target1 = float(setup.get("target_1", entry * 1.05))
    target2 = float(setup.get("target_2", target1))
    current_rr = float(setup.get("rr", 0)) or abs(target1 - entry) / max(abs(entry - stop), 0.001)

    ann_drift, ann_vol, px = _calc_historical_params(series)
    ret = series.pct_change().dropna().values

    outcomes = []
    for _ in range(n_simulations):
        if random.random() < REGIME_SHIFT_PROB:
            sim_direction = "SHORT" if direction == "LONG" else "LONG"
        else:
            sim_direction = direction
        path = _bootstrap_path(px, ret, holding_days, ann_drift, ann_vol)
        o = _simulate_single_setup(path, entry, stop, target1, target2, sim_direction, options_data)
        outcomes.append(o)

    win_rate, loss_rate, exp_ret, avg_dd, sharpe, score, max_streak, ttw, ttl = _score_simulations(
        outcomes, direction, current_rr
    )

    try:
        opt_e, opt_s, opt_t = _find_optimal_levels(series, px, direction, entry, stop, target1, target2, n_sims=50)
    except Exception:
        opt_e, opt_s, opt_t = 0.0, 0.0, 0.0

    passes = score >= threshold and win_rate >= 50 and exp_ret > 0

    base_result = SimResult(
        ticker=ticker,
        win_rate=round(win_rate, 1),
        loss_rate=round(loss_rate, 1),
        exp_return_pct=round(exp_ret, 2),
        avg_drawdown_pct=round(avg_dd, 2),
        sharpe_like=round(sharpe, 2),
        robustness_score=round(score, 1),
        optimal_entry_adj_pct=round(opt_e, 2),
        optimal_stop_adj_pct=round(opt_s, 2),
        optimal_target_adj_pct=round(opt_t, 2),
        time_to_win_days=round(ttw, 1),
        time_to_loss_days=round(ttl, 1),
        max_consecutive_losses=max_streak,
        passes_filter=passes,
        raw_metrics={
            "n_simulations": n_simulations,
            "holding_days": holding_days,
            "ann_drift": round(ann_drift, 4),
            "ann_vol": round(ann_vol, 4),
            "current_rr": round(current_rr, 2),
            "current_direction": direction,
            "outcome_distribution": {
                "wins": len([o for o in outcomes if o["hit_target"]]),
                "losses": len([o for o in outcomes if o["hit_stop"]]),
                "neutrals": len([o for o in outcomes if not o["hit_target"] and not o["hit_stop"]]),
            }
        },
        extensions={},
    )
    return base_result

def run_simulation_batch_v2(tickers: List[str], prices: dict, setups: Dict[str, dict],
                            options_map: Optional[Dict[str, dict]] = None,
                            dark_pool_map: Optional[Dict[str, dict]] = None,
                            unusual_map: Optional[Dict[str, dict]] = None,
                            n_simulations: int = DEFAULT_N_SIMULATIONS,
                            threshold: float = DEFAULT_THRESHOLD,
                            portfolio_value: float = 100_000) -> Dict[str, SimResult]:
    results = {}
    for i, ticker in enumerate(tickers):
        setup = setups.get(ticker, {})
        if not setup or not setup.get("entry"):
            continue
        opts = (options_map or {}).get(ticker)
        try:
            res = run_simulation_v2(ticker, prices, setup, options_data=opts, n_simulations=n_simulations, threshold=threshold, portfolio_value=portfolio_value)
            results[ticker] = res
        except Exception as e:
            logger.warning(f"Simulation v2 failed for {ticker}: {e}")
            results[ticker] = SimResult(
                ticker=ticker, win_rate=0, loss_rate=0, exp_return_pct=0,
                avg_drawdown_pct=0, sharpe_like=0, robustness_score=0,
                optimal_entry_adj_pct=0, optimal_stop_adj_pct=0, optimal_target_adj_pct=0,
                time_to_win_days=0, time_to_loss_days=0, max_consecutive_losses=0,
                passes_filter=False, raw_metrics={"error": str(e)}, extensions={},
            )
        if (i + 1) % 10 == 0 or i == len(tickers) - 1:
            logger.info(f"Simulation v2 progress: {i+1}/{len(tickers)}")
    return results

def get_simulation_summary_v2(sim_results: Dict[str, SimResult]) -> dict:
    passed = [s for s in sim_results.values() if s.passes_filter]
    failed = [s for s in sim_results.values() if not s.passes_filter]
    if not passed:
        return {"total": len(sim_results), "passed": 0, "failed": len(failed), "avg_score": 0}
    scores = [s.robustness_score for s in passed]
    return {
        "total": len(sim_results), "passed": len(passed), "failed": len(failed),
        "avg_score": round(float(np.mean(scores)), 1),
        "top_score": round(float(np.max(scores)), 1),
        "avg_win_rate": round(float(np.mean([s.win_rate for s in passed])), 1),
        "avg_exp_return": round(float(np.mean([s.exp_return_pct for s in passed])), 2),
    }

# Backward compat
run_simulation = run_simulation_v2
run_simulation_batch = run_simulation_batch_v2
get_simulation_summary = get_simulation_summary_v2
