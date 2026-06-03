#!/usr/bin/env python3
"""run_validation.py — ONE COMMAND automated weight validation on REAL data.

Run in your env (where yfinance + keys work):   python run_validation.py

What it does automatically (no manual judgment):
  1. Pulls price history for a representative multi-market universe.
  2. Walk-forward tests each tunable weight on OUT-OF-SAMPLE data.
  3. Prints + saves (data/validation_report.json) a verdict per weight:
        KEEP     = robust positive OOS edge (trust it)
        OVERFIT  = looked good in-sample, fails out-of-sample (DROP / re-fit)
        FRAGILE  = OOS performance swings on tiny parameter changes (risky)
        NEUTRAL  = parameter barely matters (safe to simplify / remove)
        WEAK     = no meaningful OOS edge

This validates the BACKTESTABLE weights (signal lookbacks / thresholds). The forward test
(ForwardTestLogger) runs separately + automatically inside the app each day — see app wiring.
NOTE: needs network for price history; that's why it runs in YOUR env, not the build sandbox.
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _fetch_prices(tickers):
    """Best-effort price fetch: app fetcher first, then yfinance."""
    # 1) try the app's own snapshot prices
    try:
        from orchestrator import build_snapshot
        snap = build_snapshot()
        px = snap.get("prices") or {}
        out = {t: px[t] for t in tickers if t in px}
        if len(out) >= max(2, len(tickers) // 2):
            return out
    except Exception as e:
        print(f"[info] app fetcher unavailable ({e}); trying yfinance")
    # 2) fallback: yfinance directly
    try:
        import yfinance as yf
        import pandas as pd
        data = yf.download(tickers, period="5y", progress=False)["Close"]
        if isinstance(data, pd.Series):
            data = data.to_frame()
        return {t: data[t].dropna() for t in data.columns}
    except Exception as e:
        print(f"[error] could not fetch prices: {e}")
        return {}


def momentum_signal(prices, p):
    """Representative backtestable signal: momentum over a lookback, with a strength gate.
    Stands in for the risk-range duration / phase-threshold family of weights."""
    lb = int(p["lookback"])
    thr = float(p.get("threshold", 0.0))
    m = prices.pct_change(lb)
    return (m > thr).astype(float) - (m < -thr).astype(float)


def main():
    from engines.validation_engine import auto_validate

    universe = ["SPY", "QQQ", "GLD", "USO", "TLT", "EURUSD=X", "BTC-USD", "BBCA.JK"]
    print(f"Fetching {len(universe)} tickers …")
    prices = _fetch_prices(universe)
    if not prices:
        print("No price data — run this in an env with network/yfinance.")
        return

    # weights to validate (the families I flagged as heuristic/unvalidated)
    grids = {
        "lookback": [3, 5, 10, 20, 40, 63],     # ~ risk-range TRADE/TREND duration
        "threshold": [0.0, 0.01, 0.02, 0.04, 0.08],  # ~ phase / signal strength cutoff
    }

    report = {}
    for t, s in prices.items():
        try:
            r = auto_validate(s, momentum_signal, {"lookback": 20, "threshold": 0.0}, grids)
            report[t] = r["summary"]
            print(f"\n{t}:")
            for verdict, params in r["summary"].items():
                if params:
                    print(f"   {verdict}: {params}")
        except Exception as e:
            print(f"   {t}: validation failed ({e})")

    # aggregate verdict per weight across the universe (majority)
    from collections import Counter
    agg = {}
    for w in grids:
        votes = Counter()
        for t, summ in report.items():
            for verdict, params in summ.items():
                if w in params:
                    votes[verdict] += 1
        if votes:
            agg[w] = votes.most_common(1)[0][0]
    print("\n=== AGGREGATE VERDICT (majority across universe) ===")
    for w, v in agg.items():
        print(f"   {w}: {v}")

    os.makedirs("data", exist_ok=True)
    with open("data/validation_report.json", "w") as f:
        json.dump({"per_ticker": report, "aggregate": agg}, f, indent=2)
    print("\nSaved → data/validation_report.json")


if __name__ == "__main__":
    main()
