"""gcfis/run.py — end-to-end CLI runner (run on YOUR machine; has internet for real data).
Fetches OHLCV via yfinance, runs the GCFIS stack, prints master ranking + decision table.
FAILS LOUD if a data source is missing — never fabricates. IHSG broker flow via --broker-csv."""
from __future__ import annotations
import argparse, sys
import pandas as pd

def _fetch_yf(tickers, start):
    try:
        import yfinance as yf
    except ImportError:
        sys.exit("yfinance not installed. `pip install yfinance` (no fabricated data fallback).")
    data = yf.download(tickers, start=start, auto_adjust=True, progress=False)
    close = data["Close"] if "Close" in data else data
    return {t: close[t].dropna() for t in (close.columns if hasattr(close, "columns") else [tickers])}

def main():
    ap = argparse.ArgumentParser(description="GCFIS end-to-end runner")
    ap.add_argument("--tickers", nargs="+", required=True)
    ap.add_argument("--bench", default="SPY")
    ap.add_argument("--start", default="2023-01-01")
    ap.add_argument("--regime", default="chop",
                    choices=["risk_on", "risk_off", "transition_up", "transition_down", "chop"],
                    help="current regime (or wire adapter_v40.get_regime_posterior_from_v40)")
    ap.add_argument("--broker-csv", default=None, help="IHSG broker flow CSV (broker,agg_buy,pass_buy,agg_sell,pass_sell,is_foreign)")
    ap.add_argument("--broker-ticker", default=None)
    args = ap.parse_args()

    sys.path.insert(0, ".")
    from gcfis.orchestrator import run_gcfis

    allt = list(dict.fromkeys(args.tickers + [args.bench]))
    prices = _fetch_yf(allt, args.start)
    bench = prices.pop(args.bench, None)
    if bench is None:
        sys.exit(f"benchmark {args.bench} not fetched.")
    bf = None
    if args.broker_csv and args.broker_ticker:
        bf = {args.broker_ticker: pd.read_csv(args.broker_csv).to_dict("records")}

    out = run_gcfis({t: prices[t] for t in args.tickers if t in prices}, bench,
                    regime_posterior={args.regime: 1.0}, broker_flow_by_ticker=bf)
    fm = out["systemic"]["forward_macro"]
    print(f"\nForward Quad: {fm.get('forward_quad')} ({fm.get('quad_name')}) | "
          f"Fragility {out['systemic']['fragility'].get('fragility')} | "
          f"Shock {out['systemic']['shock'].get('shock_prob')}")
    print("\n=== MASTER LONG ===")
    for r in out["ranking"]["master_long"][:15]:
        print(f"  {r['ticker']:6} {r['action']:13} conv={r['conviction']:>5} | {r['reason']}")
    print("\n=== MASTER SHORT ===")
    for r in out["ranking"]["master_short"][:15]:
        print(f"  {r['ticker']:6} {r['action']:13} conv={r['conviction']:>5} | {r['reason']}")
    if out["leadlag"].get("edges"):
        print("\n=== LEAD-LAG (top) ===")
        for e in out["leadlag"]["edges"][:8]:
            print(f"  {e['leader']} -> {e['follower']}  lag={e['lag']}d  conf={e['confidence']}")
    print("\nRULE: only act where edge is validated on YOUR data (perm_p<0.05 AND DSR>=0.95). "
          "Size via gcfis.sizing.size_position (gated).")

if __name__ == "__main__":
    main()
