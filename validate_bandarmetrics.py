#!/usr/bin/env python3
"""validate_bandarmetrics.py — walk-forward test: does the bandarmetrics v2 signal predict forward returns?

This is the ACCURACY GATE. The engine's phase/score are heuristics until proven against real
forward returns. Run this in YOUR environment (needs network for yfinance OHLCV).

What it does (NO lookahead — proper walk-forward):
  for each ticker, for each date T (stepped):
    1. compute the bandarmetrics signal using ONLY data up to T  (df.iloc[:T])
    2. measure the forward N-day return  close[T+N]/close[T] - 1
  then aggregate by signal bucket (divergence regime + score tier):
    • average forward return per bucket
    • hit rate (% positive) per bucket
    • Spearman/Pearson correlation between score and forward return
    • a verdict: is BULLISH_DIV / high-score actually better than BEARISH_DIV / low-score?

Usage:
    python validate_bandarmetrics.py                      # default IHSG sample
    python validate_bandarmetrics.py BBCA.JK BBRI.JK ...  # custom tickers
    python validate_bandarmetrics.py --fwd 20 --step 5 --days 1000

Output: prints a summary table + writes data/bandarmetrics_validation.json
"""
import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="*", help="tickers (default: IHSG sample)")
    ap.add_argument("--fwd", type=int, default=20, help="forward return horizon in days (default 20)")
    ap.add_argument("--step", type=int, default=5, help="walk-forward step in days (default 5)")
    ap.add_argument("--days", type=int, default=1000, help="history days to fetch (default 1000)")
    ap.add_argument("--min-bars", type=int, default=120, help="min bars before first signal (default 120)")
    args = ap.parse_args()

    tickers = args.tickers or [
        "BBCA.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "ASII.JK", "ANTM.JK",
        "MDKA.JK", "ADRO.JK", "GOTO.JK", "BUVA.JK", "HRUM.JK", "DAAZ.JK",
    ]

    import numpy as np
    import pandas as pd
    try:
        from data.loader import load_ohlcv
    except Exception as e:
        print(f"ERROR importing loader: {e}"); sys.exit(1)
    from engines import bandarmetrics_engine as bm

    print(f"Fetching OHLCV for {len(tickers)} tickers ({args.days}d)… (needs network)")
    ohlcv = load_ohlcv(tickers, days=args.days)
    if not ohlcv:
        print("No OHLCV returned — check network / tickers."); sys.exit(1)
    print(f"Got {len(ohlcv)} tickers with data.\n")

    rows = []  # (ticker, date, divergence, score, phase, cmf, fwd_ret)
    for t, df in ohlcv.items():
        if df is None or len(df) < args.min_bars + args.fwd + 10:
            continue
        closes = pd.to_numeric(df["Close"], errors="coerce")
        n = len(df)
        for T in range(args.min_bars, n - args.fwd, args.step):
            sub = df.iloc[:T]
            r = bm.compute(sub)
            if not r:
                continue
            c0 = float(closes.iloc[T - 1]); cN = float(closes.iloc[T - 1 + args.fwd])
            if not (np.isfinite(c0) and np.isfinite(cN) and c0 > 0):
                continue
            rows.append({
                "ticker": t, "div": r["divergence"], "score": r["score"],
                "phase": r["phase"], "cmf": r["cmf"], "fwd_ret": cN / c0 - 1.0,
            })

    if not rows:
        print("No signal/return pairs computed."); sys.exit(1)
    data = pd.DataFrame(rows)
    print(f"Computed {len(data)} signal→forward-return pairs (fwd={args.fwd}d, step={args.step}d).\n")

    def _bucket_stats(g):
        return pd.Series({
            "n": len(g),
            "avg_fwd_ret_%": round(g["fwd_ret"].mean() * 100, 2),
            "median_%": round(g["fwd_ret"].median() * 100, 2),
            "hit_rate_%": round((g["fwd_ret"] > 0).mean() * 100, 1),
        })

    print("══ By divergence regime ══")
    by_div = data.groupby("div").apply(_bucket_stats).sort_values("avg_fwd_ret_%", ascending=False)
    print(by_div.to_string(), "\n")

    print("══ By score tier ══")
    data["score_tier"] = pd.cut(data["score"], [0, 35, 50, 65, 80, 100],
                                labels=["0-35", "35-50", "50-65", "65-80", "80-100"])
    by_tier = data.groupby("score_tier", observed=True).apply(_bucket_stats)
    print(by_tier.to_string(), "\n")

    print("══ By phase ══")
    by_phase = data.groupby("phase").apply(_bucket_stats).sort_values("avg_fwd_ret_%", ascending=False)
    print(by_phase.to_string(), "\n")

    # correlations
    pear = data["score"].corr(data["fwd_ret"])
    spear = data["score"].corr(data["fwd_ret"], method="spearman")
    cmf_corr = data["cmf"].corr(data["fwd_ret"])

    # verdict: does the signal separate winners from losers?
    bull = data[data["div"] == "BULLISH_DIV"]["fwd_ret"].mean()
    bear = data[data["div"] == "BEARISH_DIV"]["fwd_ret"].mean()
    hi = data[data["score"] >= 65]["fwd_ret"].mean()
    lo = data[data["score"] <= 35]["fwd_ret"].mean()
    edge_div = (bull - bear) * 100 if (not np.isnan(bull) and not np.isnan(bear)) else None
    edge_score = (hi - lo) * 100 if (not np.isnan(hi) and not np.isnan(lo)) else None

    print("══ Correlations (signal vs forward return) ══")
    print(f"  Pearson(score, fwd)   = {pear:+.3f}")
    print(f"  Spearman(score, fwd)  = {spear:+.3f}")
    print(f"  Pearson(CMF, fwd)     = {cmf_corr:+.3f}\n")

    print("══ VERDICT ══")
    if edge_div is not None:
        print(f"  BULLISH_DIV avg fwd − BEARISH_DIV avg fwd = {edge_div:+.2f}pp "
              f"({'signal has edge ✓' if edge_div > 0.5 else 'weak/no edge ✗'})")
    if edge_score is not None:
        print(f"  score≥65 avg fwd − score≤35 avg fwd       = {edge_score:+.2f}pp "
              f"({'score tiers work ✓' if edge_score > 0.5 else 'score tiers weak ✗'})")
    print(f"  monotonic score→return = {'roughly yes' if spear > 0.05 else 'no'} "
          f"(Spearman {spear:+.3f})")
    print("\n  ⚠️ This is OHLCV-only. Real edge needs IDX broker/foreign data. Treat as a sanity check,\n"
          "     not proof. If edges are negative/zero, the heuristic thresholds need rework (or the\n"
          "     signal genuinely doesn't predict returns on this universe/horizon).")

    out = {
        "params": {"fwd": args.fwd, "step": args.step, "days": args.days,
                   "tickers": list(ohlcv.keys()), "n_pairs": len(data)},
        "by_divergence": json.loads(by_div.reset_index().to_json(orient="records")),
        "by_score_tier": json.loads(by_tier.reset_index().to_json(orient="records")),
        "by_phase": json.loads(by_phase.reset_index().to_json(orient="records")),
        "correlations": {"pearson_score": round(float(pear), 3),
                         "spearman_score": round(float(spear), 3),
                         "pearson_cmf": round(float(cmf_corr), 3)},
        "edges_pp": {"divergence": edge_div, "score": edge_score},
    }
    outp = Path(__file__).resolve().parent / "data" / "bandarmetrics_validation.json"
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(out, indent=2))
    print(f"\n✓ Wrote {outp}")


if __name__ == "__main__":
    main()
