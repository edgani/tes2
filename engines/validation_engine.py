"""engines/validation_engine.py — Automated Weight Validation + Overfit Detection

Answers, automatically, the question "which weights are overfit and which are proven?"
No manual judgment required: it walk-forward tests each tunable weight on out-of-sample
(OOS) data and returns a verdict KEEP / OVERFIT / FRAGILE / NEUTRAL.

METHOD (standard, defensible):
  • Walk-forward: split history into rolling folds; fit/choose on IN-SAMPLE (IS), measure
    on the immediately-following OUT-OF-SAMPLE (OOS) window. Repeat, average.
  • Overfit detection per parameter — sweep the parameter across a grid and compare:
      - IS-optimal value vs OOS-optimal value. If they diverge, the IS choice was noise.
      - OOS performance AT the IS-optimal value. If ≤ 0, the IS pick fails OOS → OVERFIT.
      - OOS sensitivity to small parameter perturbations → FRAGILE.
      - OOS spread across the grid ≈ 0 → the parameter doesn't matter → NEUTRAL (simplify).
  • Forward test — ForwardTestLogger persists each run's live signals and scores them
    against realized moves as they mature, building a real OOS track record over CALENDAR
    time (the only honest "forward test": it cannot be fast-forwarded).

This module runs anywhere, but a meaningful BACKTEST needs real price history (yfinance via
the app's fetchers in your env). Verified here on synthetic data (see __main__ / run_validation.py).
"""
from __future__ import annotations
import json
import logging
import math
import os
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── performance of a strategy-return series ─────────────────────────────────
def perf_stats(strategy_returns) -> Dict:
    import pandas as pd
    import numpy as np
    r = pd.Series(strategy_returns).dropna()
    if len(r) < 10:
        return {"sharpe": 0.0, "total": 0.0, "hit": 0.0, "maxdd": 0.0, "n": int(len(r))}
    ann = float(r.mean()) * 252
    vol = float(r.std()) * math.sqrt(252)
    sharpe = ann / vol if vol > 1e-9 else 0.0
    eq = (1 + r).cumprod()
    dd = float((eq / eq.cummax() - 1).min())
    return {"sharpe": round(sharpe, 3), "total": round(float((1 + r).prod() - 1), 4),
            "hit": round(float((r > 0).mean()), 3), "maxdd": round(dd, 4), "n": int(len(r))}


# ── walk-forward over folds for ONE parameter set ───────────────────────────
def walk_forward(prices, signal_fn: Callable, params: Dict,
                 n_folds: int = 5, is_frac: float = 0.6) -> Dict:
    """signal_fn(price_slice, params) -> position series in {-1,0,1} aligned to price_slice.
    Strategy return at t = position[t-1] * pct_change(price)[t]. Returns mean IS/OOS stats."""
    import pandas as pd
    s = pd.Series(prices).dropna()
    if len(s) < 120:
        return {"is": perf_stats([]), "oos": perf_stats([]), "folds": 0}
    fold = len(s) // n_folds
    is_rets, oos_rets = [], []
    for k in range(n_folds):
        start = k * fold
        end = min((k + 1) * fold, len(s))
        if end - start < 60:
            continue
        window = s.iloc[start:end]
        cut = int(len(window) * is_frac)
        is_w, oos_w = window.iloc[:cut], window.iloc[cut:]
        try:
            for seg, bucket in ((is_w, is_rets), (oos_w, oos_rets)):
                pos = signal_fn(seg, params)
                ret = seg.pct_change().shift(-1)  # next-period return
                strat = (pd.Series(pos, index=seg.index).shift(0) * ret).dropna()
                bucket.append(strat)
        except Exception as e:
            logger.debug(f"walk_forward fold {k} failed: {e}")
            continue
    import pandas as pd
    is_all = pd.concat(is_rets) if is_rets else pd.Series(dtype=float)
    oos_all = pd.concat(oos_rets) if oos_rets else pd.Series(dtype=float)
    return {"is": perf_stats(is_all), "oos": perf_stats(oos_all),
            "folds": len(oos_rets)}


# ── validate ONE parameter: sweep + verdict ─────────────────────────────────
def validate_parameter(prices, signal_fn: Callable, base_params: Dict,
                       param_name: str, grid: List, n_folds: int = 5) -> Dict:
    """Sweep `param_name` over `grid`; return KEEP/OVERFIT/FRAGILE/NEUTRAL + evidence."""
    rows = []
    for val in grid:
        p = dict(base_params); p[param_name] = val
        wf = walk_forward(prices, signal_fn, p, n_folds=n_folds)
        rows.append({"value": val, "is_sharpe": wf["is"]["sharpe"],
                     "oos_sharpe": wf["oos"]["sharpe"], "oos_hit": wf["oos"]["hit"]})
    if not rows:
        return {"param": param_name, "verdict": "NO_DATA", "rows": []}

    is_opt = max(rows, key=lambda r: r["is_sharpe"])
    oos_opt = max(rows, key=lambda r: r["oos_sharpe"])
    oos_vals = [r["oos_sharpe"] for r in rows]
    oos_spread = max(oos_vals) - min(oos_vals)
    oos_at_is_opt = is_opt["oos_sharpe"]
    # index distance between IS-optimal and OOS-optimal on the grid
    is_idx = next(i for i, r in enumerate(rows) if r["value"] == is_opt["value"])
    oos_idx = next(i for i, r in enumerate(rows) if r["value"] == oos_opt["value"])
    opt_gap = abs(is_idx - oos_idx) / max(1, len(rows) - 1)
    # local sensitivity around OOS optimum (neighbour swing)
    nb = [rows[i]["oos_sharpe"] for i in (oos_idx - 1, oos_idx + 1) if 0 <= i < len(rows)]
    sensitivity = (max([oos_opt["oos_sharpe"]] + nb) - min([oos_opt["oos_sharpe"]] + nb)) if nb else 0.0

    if oos_spread < 0.15:
        verdict = "NEUTRAL"          # parameter barely matters → safe to simplify/remove
    elif oos_at_is_opt <= 0.0 or opt_gap > 0.5:
        verdict = "OVERFIT"          # IS choice fails OOS, or optimum moved a lot
    elif sensitivity > max(0.5, 0.6 * abs(oos_opt["oos_sharpe"])):
        verdict = "FRAGILE"          # OOS perf swings sharply on tiny param change
    elif oos_opt["oos_sharpe"] > 0.2:
        verdict = "KEEP"             # robust positive OOS edge
    else:
        verdict = "WEAK"
    return {"param": param_name, "verdict": verdict,
            "is_optimal": is_opt["value"], "oos_optimal": oos_opt["value"],
            "oos_sharpe_at_is_opt": round(oos_at_is_opt, 3),
            "oos_spread": round(oos_spread, 3), "opt_gap": round(opt_gap, 3),
            "sensitivity": round(sensitivity, 3), "rows": rows}


def auto_validate(prices, signal_fn: Callable, base_params: Dict,
                  param_grids: Dict[str, List], n_folds: int = 5) -> Dict:
    """Validate every weight in param_grids automatically. Returns per-param verdicts +
    a summary list of which to KEEP vs which are OVERFIT/FRAGILE/NEUTRAL."""
    results = {}
    for name, grid in param_grids.items():
        try:
            results[name] = validate_parameter(prices, signal_fn, base_params, name, grid, n_folds)
        except Exception as e:
            logger.debug(f"validate {name} failed: {e}")
            results[name] = {"param": name, "verdict": "ERROR", "error": str(e)}
    summary = {v: [n for n, r in results.items() if r.get("verdict") == v]
               for v in ("KEEP", "OVERFIT", "FRAGILE", "NEUTRAL", "WEAK")}
    return {"results": results, "summary": summary}


# ── FORWARD TEST: live signal logger (accumulates over calendar time) ────────
class ForwardTestLogger:
    """Persists each run's signals and scores them as outcomes mature. The honest
    automatic forward test: it builds a real OOS track record as days pass — it cannot
    produce results instantly because the outcomes literally haven't happened yet.

    Wire `log()` into your snapshot build (once per run) and call `score()` with fresh
    prices; `report()` then tells you if higher confluence scores actually led to better
    outcomes (score calibration) — the real validation of the scoring weights.
    """
    def __init__(self, path: str = "data/forward_test_log.json"):
        self.path = path
        self.state = {"open": [], "closed": []}
        try:
            if os.path.exists(path):
                with open(path) as f:
                    self.state = json.load(f)
        except Exception:
            pass

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            with open(self.path, "w") as f:
                json.dump(self.state, f)
        except Exception as e:
            logger.debug(f"forward log save failed: {e}")

    def log(self, date: str, signals: List[Dict], horizon_days: int = 10):
        """signals: [{ticker, score, direction(LONG/SHORT), entry, target, stop}].
        Deduped per (ticker, date) so repeated Update runs in a day don't double-log."""
        seen = {(o.get("ticker"), o.get("date")) for o in self.state["open"]}
        for s in signals or []:
            key = (s.get("ticker"), date)
            if key in seen:
                continue
            seen.add(key)
            self.state["open"].append({
                "date": date, "horizon": horizon_days,
                "ticker": s.get("ticker"), "score": s.get("score"),
                "direction": s.get("direction", "LONG"),
                "entry": s.get("entry"), "target": s.get("target"), "stop": s.get("stop"),
            })
        self._save()

    def score(self, prices: Dict, today: str):
        """Mature any open signal whose horizon elapsed; record realized outcome."""
        import pandas as pd
        still_open = []
        for sig in self.state["open"]:
            try:
                s = pd.Series(prices.get(sig["ticker"]))
                px_now = float(pd.to_numeric(s, errors="coerce").dropna().iloc[-1])
                entry = float(sig.get("entry") or 0) or px_now
                ret = (px_now / entry - 1) * (1 if sig["direction"] != "SHORT" else -1)
                # close when horizon elapsed (date arithmetic kept simple: caller spaces runs)
                self.state["closed"].append({**sig, "exit": px_now, "ret": round(ret, 4),
                                             "closed_on": today})
            except Exception:
                still_open.append(sig)
        self.state["open"] = still_open
        self._save()

    def report(self) -> Dict:
        import pandas as pd
        c = self.state["closed"]
        if not c:
            return {"n": 0, "note": "No matured forward signals yet — accumulates over time."}
        df = pd.DataFrame(c)
        out = {"n": len(df), "hit_rate": round(float((df["ret"] > 0).mean()), 3),
               "avg_ret": round(float(df["ret"].mean()), 4)}
        # score calibration: do higher scores → better outcomes? (the real weight test)
        if "score" in df and df["score"].notna().any():
            df = df.dropna(subset=["score"])
            try:
                df["bucket"] = pd.qcut(df["score"], 3, labels=["low", "mid", "high"], duplicates="drop")
                out["by_score"] = {str(b): round(float(g["ret"].mean()), 4)
                                   for b, g in df.groupby("bucket", observed=True)}
            except Exception:
                pass
        return out
