# Quad calc + ticker filter — verification

## Quad (engines/forward_macro.py) — Hedgeye GIP, CORRECT
Market-implied growth/inflation composites, classified by RATE-OF-CHANGE (2nd-derivative), not level:
| GROC | IROC | Quad |
|---|---|---|
| ≥0 | <0 | **Q1 Goldilocks** (growth↑ inflation↓) |
| ≥0 | ≥0 | **Q2 Reflation** (growth↑ inflation↑) |
| <0 | ≥0 | **Q3 Stagflation** (growth↓ inflation↑) |
| <0 | <0 | **Q4 Deflation** (growth↓ inflation↓) |
Matches Hedgeye's 2×2 exactly. Verified in `test_all.py::t_l2` (g↑/i↓ → Q1).
Default factor weights are PRIORS; `fit_ridge()` re-fits on real next-period growth on your machine.

## Ticker filter (meta/regime_meta.py) — multi-condition, CORRECT
A ticker reaches **master_long** only if ALL hold:
1. confluence `0.45·accumulation + 0.35·theme + 0.20·smart-money` clears bull threshold (≥55)
2. regime tilt supports longs (`W_long` from HMM posterior), scaled down by systemic stress
3. NOT distributing (no exit_signal / broker NET_DISTRIBUTION / COT-extreme-long)
4. passes capacity (ADV ≥ min_adv) — illiquid → STAND_ASIDE
5. NOT cross-asset deferred (DELEVERAGING/DEFLATION_SCARE → moved to deferred_longs)

Counter-regime: bullish quad + distribution → demote long, flip short.
**master_short**: bear confluence OR stress-driven. **master_spot**: uncrowded Stage 2→3 sweet-spot.
Every row carries a `reason` string (narrative.py) — no recommendation without a logical why.
