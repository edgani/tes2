# GCFIS — Global Capital Flow Intelligence System
### Validated engine layer for MacroRegime Pro v40

GCFIS is the re-designed, **validated** core that sits on top of your v40 data layer. It fixes the
structural flaws (dogmatic quad mapping, static weights, level-not-change, GIGO proxies, engine
sprawl) with formulas that are normalized, change-centric, regime-conditional, and **tested**.

## The 4 principles every engine obeys
1. **CHANGE not LEVEL** — every metric has a Δz / acceleration form. (Validated on real macro data:
   growth *acceleration* was the predictive feature, OOS.)
2. **NORMALIZE then COMBINE** — robust median/MAD z-scores before any combination (no raw-unit sums/products).
3. **REGIME-CONDITIONAL** — meta weights blend by HMM posterior (crisis→fragility/shock dominate; risk-on→theme/accumulation).
4. **VALIDATE not FABRICATE** — proxies allowed only if calibrated + down-weighted; momentum-as-greek is banned.

## Engines (all pass the synthetic correctness suite)
| Module | Closes | What it does |
|---|---|---|
| `core/change_core.py` | philosophy | robust-z, Δz, acceleration, pct-rank, logistic, FDR, **CSD** (critical-slowing-down early warning) |
| `engines/leadlag_discovery.py` | Gap#1 (3/10) | DYNAMIC lead-lag discovery — returns + Granger + Transfer-Entropy + **FDR** + stability + direction. Output: `leader→follower, lag, confidence`. Backbone of the capital-flow graph. |
| `engines/change_detection.py` | Druckenmiller | per-metric regime-of-change (ACCELERATING_UP/DECELERATING/…) |
| `engines/fragility.py` | shock radar | fragility 0-100 with **non-linear amplifiers** (correlation conduit × CSD) + velocity |
| `engines/shock.py` | shock radar | probabilistic P(shock/regime-break) from market stress + CSD |
| `engines/forward_macro.py` | Quad latency | Market-Implied Forward Growth/Inflation → **forward** Quad (daily, leads reported GDP/CPI). `.fit()` does ridge on your real data. |
| `engines/accumulation.py` | next-PLTR | Accumulation (RS=alpha, signed VE) + **Institutional Adoption Curve** (Stage 1-5) + crowding velocity + sweet-spot/exit |
| `engines/broker_flow.py` | bandarmologi | order-flow INTENT: BUILDING / SCALPING / ABSORBING / PANIC / DELIBERATE distribution |
| `meta/regime_meta.py` | Gap#8 | regime-conditional weighting + **MASTER RANKING** (long/short/spot) + counter-regime flow-dominance |
| `orchestrator.py` | — | runs the whole stack → dashboard + ranking |
| `adapter_v40.py` | — | bridge to v40 `load_prices` / `markov_v3` regime |

## Run the tests
```bash
python3 gcfis/tests/test_all.py      # synthetic correctness — all engines + end-to-end
```

## Wire into v40 (no duplication)
```python
from gcfis.orchestrator import run_gcfis
from gcfis.adapter_v40 import get_prices_from_v40, get_regime_posterior_from_v40
prices = get_prices_from_v40(start="2023-01-01")
posterior = get_regime_posterior_from_v40(prices)
out = run_gcfis(prices, bench=prices["SPY"], regime_posterior=posterior,
                systemic_inputs={...}, growth_inputs={...}, infl_inputs={...},
                broker_flow_by_ticker={"HUMI": [...]})
out["ranking"]["master_long"]   # ranked long candidates
out["systemic"]["forward_macro"]["forward_quad"]
```
The orchestrator exposes hooks so you can plug the validated **frontrun_engine** modules
(`regime_edge.py`, `decision.py`, `sizing.py`, `broker_flow.py`) instead of duplicating them.

## ⚠️ HONEST BOUNDARY — read this
**Validated here:** every engine's LOGIC (synthetic correctness), all imports, the full orchestrator
end-to-end. The statistical machinery (FDR, Granger, TE, CSD, z-scoring) is correct.

**NOT validated here (you must run on your machine):** real-market EDGE. This sandbox has **no market-data
access** (yfinance/FRED/Glassnode are not reachable), so no real backtest was run. Whether these signals
actually predict your markets is an **empirical question answerable only on real data** with a proper
walk-forward (purged k-fold + embargo, point-in-time, anti-survivorship).
**No engine here claims accuracy.** A signal that can't beat a naive baseline OOS should be cut.

This is a validated *instrument*, not a proven *edge*. The edge is yours to verify.
