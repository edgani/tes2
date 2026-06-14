# BandarMetrics — REDESIGNED (verdict tiers applied, engines/flow_regime.py)

## Tier verdict → what shipped
| BM metric | Edge | Decision |
|---|---|---|
| Foreign Correlation (Corr_F) | HIGH — who drives price (foreign vs local operator) | **KEPT** — level-corr(Close, cumΣFN, 60), regime TAG |
| Foreign Participation (Par_F) | HIGH — liquidity regime gate | **KEPT** — (FB+FS)/(2·V), EMA20 |
| EFD = Corr_F × Par_F | composite single driver | **BUILT** |
| LPM | conditional only (BBCA: LPM +519M while price −40%) | **KEPT, GATED** — valid iff slope>0 ∧ ADV20/63>1 ∧ breadth>0; otherwise "garis cantik" |
| Intensity | trigger-only, direction-less | **KEPT** as trigger (z>1.5), sign from regime |
| DTE | theory ok, data weak from OHLCV | **SKIP** — BRAIN mark-out P&L is the superior inventory proxy |
| Vol Rotation | forward-edge ≈ 0 (green all the way down −40%) | **DROPPED** |
| AvgCost standalone | AVWAP proxy | **DROPPED** |
| Net Buy/Sell F | redundant derivative of FN | **DROPPED** |

## The regime law (validated vs 2025: IHSG 24× ATH on −Rp17.34T foreign net sell)
DomesticNet = −ForeignNet. "Follow asing" is a REGIME, not a law:
- Par_F < 0.20 → **OPERATOR** (ignore foreign) · Corr_F > +0.30 → **FOREIGN_LED** (follow foreign)
- Corr_F < −0.30 → **DOMESTIC_LED** (foreign is the EXIT LIQUIDITY — do not fade domestic markup)
- else → **DECOUPLED** (low conviction, cut size)
Scores: FOREIGN_LED 100·tanh(3.0·fgn_p) · DOMESTIC_LED 100·tanh(0.9·lpm_p+0.7·breadth) (NO foreign term)
· OPERATOR 100·tanh(0.9·lpm_p+0.5·tanh(int)) · DECOUPLED 40·tanh(0.5·fgn_p+0.5·lpm_p).
Weights = PRIORS — walk-forward (DSR + permutation p) before trusting. Needs Type-F (fb/fs) feed:
pass `typef_by_ticker={tkr: df[close,high,low,open,volume,fb,fs]}` to run_gcfis.

## Wiring
idx ticker + Type-F present → a["bm"] readout; flow01 override = 0.5 + score/200·conf (replaces OHLCV
proxy in the market-weighted confluence); decision-stack why_now/who's-trapped speak BM regimes;
card shows BM chips (regime/EFD/ParF/CorrF/LPM±valid). Tests: t_bm_flow_regime + t_bm_idx_wiring_e2e.
