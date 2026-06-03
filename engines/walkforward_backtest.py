"""walkforward_backtest.py — REAL walkforward + Monte Carlo (NO random.uniform)

Replaces walkforward_backtest_engine.py stub. Anchored 60/40 train/test:
  - TRR/LRR signals: BUY at LRR, SELL at TRR
  - 5-day hold timeout, -3% stop loss
  - Score = hit_rate*0.35 + return*0.30 + sharpe*0.20 + (1-dd)*0.15
  - Monte Carlo: 100 bootstrap iterations
  - Gate: PASS if combined_score >= 55
"""
from __future__ import annotations
from typing import Dict, Optional, List
import numpy as np
import pandas as pd
import logging
logger = logging.getLogger(__name__)


def _trr_signals(prices: pd.Series, lookback: int = 63) -> pd.DataFrame:
    """Simplified TRR/LRR signal generation per bar."""
    s = pd.to_numeric(prices, errors="coerce").dropna()
    if len(s) < lookback + 5: return pd.DataFrame()
    log_ret = np.log(s / s.shift(1)).dropna()
    rv = log_ret.rolling(14).std() * np.sqrt(252)
    daily_vol = rv / np.sqrt(252)
    width = s * daily_vol * 2.75
    basis = s.shift(1)
    trr = basis + width * 0.7
    lrr = basis - width * 1.3  # asymmetric bull bias
    sig = pd.Series(0, index=s.index)
    sig[s <= lrr] = 1
    sig[s >= trr] = -1
    return pd.DataFrame({"px": s, "trr": trr, "lrr": lrr, "signal": sig}).dropna()


def _simulate_trades(df: pd.DataFrame, max_hold: int = 5, stop_loss: float = -0.03) -> List[Dict]:
    trades = []
    i = 0
    pxs = df["px"].values
    sigs = df["signal"].values
    while i < len(df) - 1:
        if sigs[i] == 1:
            entry = pxs[i]
            exit_idx = min(i + max_hold, len(df) - 1)
            sl_hit = False
            for j in range(i + 1, exit_idx + 1):
                ret = (pxs[j] - entry) / entry
                if ret <= stop_loss:
                    exit_idx = j; sl_hit = True; break
                if sigs[j] == -1:
                    exit_idx = j; break
            exit_px = pxs[exit_idx]
            ret = (exit_px - entry) / entry
            trades.append({"entry_idx": i, "exit_idx": exit_idx, "return": ret,
                          "hold": exit_idx - i, "sl_hit": sl_hit})
            i = exit_idx + 1
        else:
            i += 1
    return trades


def _stats(trades: List[Dict]) -> Dict:
    if not trades:
        return {"trade_count": 0, "hit_rate": 0, "avg_return": 0,
                "sharpe": 0, "max_dd": 0, "score": 0}
    rets = np.array([t["return"] for t in trades])
    hit_rate = float((rets > 0).mean())
    avg_ret = float(rets.mean())
    sharpe = float(rets.mean() / rets.std()) if rets.std() > 0 else 0.0
    cum = np.cumprod(1 + rets)
    peak = np.maximum.accumulate(cum)
    dd = float((cum / peak - 1).min())
    # Score (0-100)
    score = (
        hit_rate * 35 +
        np.clip(avg_ret * 1000, -30, 30) +
        np.clip(sharpe * 10, -20, 20) +
        (1 + dd) * 15  # dd is negative
    )
    return {"trade_count": len(trades), "hit_rate": round(hit_rate, 3),
            "avg_return": round(avg_ret, 4), "sharpe": round(sharpe, 2),
            "max_dd": round(dd, 4), "score": round(max(0, min(100, score)), 1)}


def walkforward_test(prices: pd.Series, train_pct: float = 0.6) -> Dict:
    sigs = _trr_signals(prices)
    if len(sigs) < 60:
        return {"ok": False, "reason": "insufficient_data"}
    split = int(len(sigs) * train_pct)
    train_trades = _simulate_trades(sigs.iloc[:split])
    test_trades = _simulate_trades(sigs.iloc[split:])
    return {"ok": True,
            "train": _stats(train_trades),
            "test": _stats(test_trades),
            "n_train": len(train_trades),
            "n_test": len(test_trades)}


def monte_carlo_bootstrap(prices: pd.Series, n_iter: int = 100) -> Dict:
    sigs = _trr_signals(prices)
    if len(sigs) < 60:
        return {"ok": False, "reason": "insufficient_data"}
    base_trades = _simulate_trades(sigs)
    if not base_trades:
        return {"ok": False, "reason": "no_trades"}
    base_rets = np.array([t["return"] for t in base_trades])
    rng = np.random.default_rng(seed=42)
    sharpes = []
    for _ in range(n_iter):
        sample = rng.choice(base_rets, size=len(base_rets), replace=True)
        if sample.std() > 0:
            sharpes.append(sample.mean() / sample.std())
    sharpes = np.array(sharpes)
    return {"ok": True,
            "median_sharpe": round(float(np.median(sharpes)), 3),
            "p5_sharpe": round(float(np.percentile(sharpes, 5)), 3),
            "p95_sharpe": round(float(np.percentile(sharpes, 95)), 3),
            "n_iter": n_iter,
            "base_trade_count": len(base_trades)}


def batch_gatekeeper(prices_dict: Dict[str, pd.Series], min_score: float = 55.0) -> Dict:
    """Run walkforward + MC on universe. Returns gate pass/fail per ticker."""
    results = {}
    for ticker, prices in (prices_dict or {}).items():
        try:
            wf = walkforward_test(prices)
            mc = monte_carlo_bootstrap(prices, n_iter=50)
            if not wf.get("ok"):
                results[ticker] = {"gate_pass": False, "reason": wf.get("reason"),
                                  "combined_gate_score": 0}
                continue
            test_score = wf["test"]["score"]
            mc_bonus = 10 if mc.get("ok") and mc["p5_sharpe"] > 0 else 0
            combined = test_score + mc_bonus
            results[ticker] = {
                "gate_pass": combined >= min_score,
                "combined_gate_score": round(combined, 1),
                "walkforward_test_score": test_score,
                "walkforward_train_score": wf["train"]["score"],
                "mc_p5_sharpe": mc.get("p5_sharpe", 0) if mc.get("ok") else None,
                "mc_median_sharpe": mc.get("median_sharpe", 0) if mc.get("ok") else None,
                "n_test_trades": wf["n_test"],
            }
        except Exception as e:
            logger.warning(f"WF failed for {ticker}: {e}")
            results[ticker] = {"gate_pass": False, "reason": f"error: {e}",
                              "combined_gate_score": 0}
    return results
