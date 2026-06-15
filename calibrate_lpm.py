"""
calibrate_lpm.py - lock LPM config against a BandarMetrics export. NO yfinance needed.

Export ~60+ daily rows for ONE liquid stock: date,Open,High,Low,Close,Volume,LPM  (CSV).
Run:  python calibrate_lpm.py your_export.csv

Tests scaling x mode(cumulative/windowed) x span. For each, fits  LPM_ref ~ a*model + b
(linear) on the post-burn-in region and ranks by R^2. Best R^2 = the formula; (a,b) = scale/anchor.
This is mode-agnostic: cumulative -> b is anchor offset (a~1); windowed -> a is scale (b~0).
"""
import sys
import numpy as np
import pandas as pd
from lpm import lpm as build_lpm

SCALINGS = ["volume", "value_close", "value_typical"]
CONFIGS = ([("cumulative", None, sp) for sp in (1, 10, 20, 30, 50)] +
           [("windowed", w, sp) for w in (20, 40, 60) for sp in (1, 10, 20)])


def _fit(ref, model):
    m = pd.concat([ref, model], axis=1).dropna()
    if len(m) < 8 or m.iloc[:, 1].std() == 0:
        return None
    x, y = m.iloc[:, 1].values, m.iloc[:, 0].values
    a, b = np.polyfit(x, y, 1)
    r2 = 1 - np.sum((y - (a * x + b)) ** 2) / (np.sum((y - y.mean()) ** 2) + 1e-12)
    return a, b, r2


def main(path):
    df = pd.read_csv(path)
    df = df.rename(columns={c: c.capitalize() for c in df.columns
                            if c.lower() in ("open", "high", "low", "close", "volume")})
    lpm_col = next((c for c in df.columns if c.lower() == "lpm"), None)
    if lpm_col is None or not {"Open", "High", "Low", "Close", "Volume"}.issubset(df.columns):
        print("ERROR: CSV needs Open,High,Low,Close,Volume,LPM"); return
    ref = pd.to_numeric(df[lpm_col], errors="coerce").reset_index(drop=True)
    rows = []
    for mode, win, sp in CONFIGS:
        model = build_lpm(df, span=sp, mode=mode, window=win or 40).reset_index(drop=True)
        burn = min(3 * sp + (win or 0), len(df) // 3)
        fit = _fit(ref.iloc[burn:].reset_index(drop=True), model.iloc[burn:].reset_index(drop=True))
        if fit:
            a, b, r2 = fit
            rows.append((f"{mode}{('/'+str(win)) if win else ''}", sp, r2, a, b))
    if not rows:
        print("Not enough rows after burn-in. Export >= 60 bars."); return
    rows.sort(key=lambda x: -x[2])
    print(f"{'mode':<16}{'span':>5}{'R^2':>9}{'scale_a':>14}{'offset_b':>18}")
    print("-" * 62)
    for nm, sp, r2, a, b in rows[:8]:
        print(f"{nm:<16}{sp:>5}{r2:>9.4f}{a:>14.4g}{b:>18,.0f}")
    b0 = rows[0]
    print(f"\nBEST: mode={b0[0]}, span={b0[1]}, R^2={b0[2]:.4f}  -> set in lpm.py")
    if b0[2] < 0.9:
        print("NOTE: best R^2 < 0.9 -> family may be incomplete (foreign Type-F component?). Send CSV.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python calibrate_lpm.py your_export.csv"); sys.exit(1)
    main(sys.argv[1])
