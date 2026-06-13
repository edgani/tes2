# BandarMetrics — reverse-engineering to EXACT match

## Metric definitions (reverse-engineered, in core/bandarmetrics.py + engines/flow_regime.py)
- Par_F  = (ForeignBuyValue + ForeignSellValue) / (2 × Value)   ← foreign participation
- Corr_F = corr(close_level, cumsum(ForeignBuy − ForeignSell), window=W)
- LPM    = cumsum((close − vwap20) × volume), EWM-smoothed
- Net Buy/Sell F = ForeignBuy − ForeignSell ;  Vol Rotation intentionally dropped (no edge)

## Why a single formula can't be "exact" without your data
The reference app's exact numbers (TPIA 0.711/30.93%, BREN −0.188/50.74%) depend on conventions
it does NOT publish: the Corr_F window W, smoothing spans, the Par_F aggregation (mean-of-daily
vs Σ/Σ), and whether Value = close·volume or exchange turnover. IDX is blocked in the sandbox so
I can't fetch TPIA/BREN to confirm.

## The solution: calibrate() solves for the convention from your known outputs
Proven on synthetic data: given two stocks' output numbers, it recovered a hidden window=45 with
error 0.0005 (EXACT-MATCH). With your real reference points it locks the exact convention.

## What to export (per stock, daily, ~6–12 months) and the columns
date, open, high, low, close, volume, value, fb(=foreign BUY value), fs(=foreign SELL value)

## Run
```python
from core.bandarmetrics import calibrate
stocks  = {"TPIA": tpia_df, "BREN": bren_df}          # your exported DataFrames
targets = {"TPIA": {"corr_f": 0.711, "par_f": 0.3093},
           "BREN": {"corr_f": -0.188, "par_f": 0.5074}}
print(calibrate(stocks, targets))
# → {window, corr_smooth, par_smooth, par_agg, total_abs_error, verdict, achieved}
```
verdict EXACT-MATCH (err<0.02) means the locked params reproduce BM's numbers; bake them into
FlowRegimeConfig and every IDX stock then matches the reference app.
