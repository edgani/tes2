"""
validate_lpm_calibration.py — calibrate LPM (and Intensity/Vol Rotation) against the
4 bandarmetrics.com reference tickers Edward captured on 2026-06-02.

WHY: I can't reach yfinance in my sandbox, so I can't fetch HUMI/BBCA/EURO/MSIN OHLCV to verify
my formula numerically. You CAN. Run this in your env and paste me the output table — I'll then
adjust the window / EMA span / scale so my LPM matches bandarmetrics to within a few %.

Run:  python validate_lpm_calibration.py
"""
import numpy as np
import pandas as pd
import yfinance as yf
from engines.bandarmetrics_engine import compute

# Bandarmetrics.com reference values (2026-06-02 close), from your screenshots:
REF = {
    "HUMI.JK": {"close": 136,   "vol": 59_896_200,  "lpm": -371_489_575.45,    "foreign_flow": -34_209_819_300,     "corr_f": 0.642, "par_f": 13.05},
    "BBCA.JK": {"close": 5825,  "vol": 346_305_200, "lpm": 412_091_862.26,     "foreign_flow": -51_893_858_020_000, "corr_f": 0.976, "par_f": 53.00},
    "EURO.JK": {"close": 1745,  "vol": 216_200,     "lpm": -1_240_757_343.90,  "foreign_flow": 47_468_760_000,      "corr_f": 0.933, "par_f": 13.14},
    "MSIN.JK": {"close": 370,   "vol": 61_125_200,  "lpm": -22_879_402.89,     "foreign_flow": 284_324_124_200,     "corr_f": 0.686, "par_f": 62.34},
}

# Try a few configs so we can see which window/EMA gets closest to the reference LPM.
CONFIGS = [
    {"lpm_smooth": 1,  "label": "raw ADL (no EMA)"},
    {"lpm_smooth": 20, "label": "EMA-20 ADL (current)"},
    {"lpm_smooth": 50, "label": "EMA-50 ADL"},
]


def fetch(ticker, period="2y"):
    df = yf.download(ticker, period=period, interval="1d", auto_adjust=False, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df[["Open", "High", "Low", "Close", "Volume"]].dropna()


def main():
    print(f"{'ticker':<10}{'config':<22}{'my LPM':>18}{'bandarmetrics LPM':>22}{'ratio(mine/ref)':>18}")
    print("-" * 90)
    for tk, ref in REF.items():
        try:
            df = fetch(tk)
        except Exception as e:
            print(f"{tk:<10} fetch failed: {e}")
            continue
        # sanity: does our last close/vol match the reference day?
        last_c, last_v = float(df['Close'].iloc[-1]), float(df['Volume'].iloc[-1])
        print(f"{tk}: last close={last_c:.0f} (ref {ref['close']}) · last vol={last_v:,.0f} (ref {ref['vol']:,})")
        for cfg in CONFIGS:
            r = compute(df, lpm_smooth=cfg["lpm_smooth"])
            mine = r["lpm"]
            ratio = (mine / ref["lpm"]) if ref["lpm"] else float("nan")
            print(f"{'':<10}{cfg['label']:<22}{mine:>18,.0f}{ref['lpm']:>22,.0f}{ratio:>18.3f}")
        print()
    print("PASTE this whole output back to me. I'll use the ratios to lock the exact window/scale.")
    print("NOTE: Foreign Flow / Corr F / Par F need IDX Type-F data (foreign buy/sell) — not in yfinance.")


if __name__ == "__main__":
    main()
