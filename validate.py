"""
Module-20 VALIDATION HARNESS for the Dynamic Trader engine.

Run:  python validate.py

It measures the engine's PRICE cluster + TIME cluster + exact manual EOW against
known numbers. Two demos are included:
  1) a synthetic case whose APP target is computed BY HAND (proves the math),
  2) the exact manual-EOW reproduction.
Then a TEMPLATE you fill with a real Robert Miner chart (pivots + his printed
targets/dates) to measure match-rate. No network needed.
"""
import pandas as pd
from miner_dt import Pivot, validate_chart, print_validation, price_cluster_md


def P(idx, price, kind, day0="2024-01-01"):
    return Pivot(idx, pd.Timestamp(day0) + pd.Timedelta(days=idx), float(price), kind)


# ---------------------------------------------------------------------------
# 1) SYNTHETIC SELF-TEST — hand-computed APP so we can prove correctness
#    Most-recent LHL triple: L=120 (idx8) ... H=175 (idx15) ... L=140 (idx18)
#    APP 1.000 from L3:  140 + 1.000*(175-120) = 140 + 55 = 195   <- expect this
#    Time: highs at idx 5 and 15 -> cycle 10 -> 1.000 projection at idx 25
# ---------------------------------------------------------------------------
piv = [P(0, 100, "L"), P(5, 150, "H"), P(8, 120, "L"),
       P(15, 175, "H"), P(18, 140, "L")]

# sanity: print what the engine projects (up direction, ref = last low 140)
zones, _ = price_cluster_md(piv, piv, "up", 140.0)
print("engine up-zones:", [round(z["mid"], 2) for z in zones[:6]], "\n")

rep = validate_chart(
    name="SYNTHETIC LHL (hand-checked)",
    pivots=piv, direction="up", ref_price=140.0,
    expected_targets=[195.0],      # hand-computed APP 1.000
    expected_dates=[25],           # hand-computed H-H 1.000 projection bar
    tol_pct=0.5, tol_bars=2,
)
print_validation(rep)
print()

# ---------------------------------------------------------------------------
# 2) EXACT MANUAL EOW reproduction (no pivots-direction needed for the EOW part)
#    EOW-5 from W0,W1,W3,W4 = 6800, 7166.8, 7300, 7087  ->  zone 7432.06-7453.8
# ---------------------------------------------------------------------------
rep2 = validate_chart(
    name="EOW-5 exact (manual pivots)",
    pivots=[P(0, 6800, "L"), P(5, 7166.8, "H"), P(10, 7300, "H"), P(14, 7087, "L")],
    direction="up", ref_price=7087.0,
    expected_targets=[7453.8, 7432.06],   # the exact App%/ExtRet convergence
    expected_dates=[],                     # time not tested here
    eow_kind="5", eow_prices=[6800, 7166.8, 7300, 7087],
    tol_pct=0.5, tol_bars=2,
)
print_validation(rep2)
print()

# ---------------------------------------------------------------------------
# 3) TEMPLATE — paste a REAL Robert Miner chart here, then run.
#    From a chart screenshot read off:
#      - the pivots HE labelled (date + price + 'H'/'L'); set idx = bar number
#      - direction: 'up' if his target is ABOVE last close, else 'down'
#      - ref_price: the last close printed on the chart
#      - expected_targets: the price levels he printed (e.g. App% / Ret lines)
#      - expected_dates: bar-index of the date(s) he projected
#    Example skeleton (fill the real numbers, then uncomment):
#
# real = validate_chart(
#     name="GC J26 Daily 3/18 (Miner)",
#     pivots=[P(0, 5078.7, "H"), P(6, 4823.9, "L"), ...],
#     direction="down", ref_price=4823.9,
#     expected_targets=[4578.10, 4271.72],     # his "App% 1.618 / App% 1.000"
#     expected_dates=[],                        # bar idx of his projected reversal
#     tol_pct=0.5, tol_bars=2,
# )
# print_validation(real)

print("Fill section 3 with a real Miner chart to measure match-rate.")
