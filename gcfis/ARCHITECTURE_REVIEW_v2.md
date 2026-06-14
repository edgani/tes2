# GCFIS Architecture Review v2 — critical re-read (post-s51)

**Verdict:** the GCFIS conceptual architecture is correct and implemented. A from-scratch
re-design would be value-DESTRUCTIVE churn (re-creates the "two parallel versions" debt). The
architecture is not wrong — it was INCOMPLETE in 4 structural places. This pass closes the two
that are implementable + validatable now; the other two need real data and are specced, not faked.

## The 4 structural gaps found

| # | Gap | Status |
|---|-----|--------|
| 1 | **Lead-lag graph was decorative.** `leadlag_discovery` was computed but only *reported* — it never drove selection, despite being the specced "moat" (rotation-prediction). | ✅ **FIXED (s52)** |
| 2 | **Regime posterior is a quad→lookup, not a fitted HMM.** | ✅ **FIXED (s53)** — real Gaussian HMM (`regime_hmm.py`, hmmlearn, runtime-fit on bench/breadth/VIX, graceful fallback) |
| 3 | **Bottleneck has no migration tracking.** | ✅ **FIXED (s53)** — `run_bottleneck_migration` ranks nodes by Δtightness → emerging/fading; wired into orchestrator output |
| 4 | **No portfolio-level construction.** Top-N longs could be one correlated bet, sized as N. | ✅ **FIXED (s52)** |

## What was built

### #1 — Rotation engine (`engines/rotation.py`) — the moat goes live
- Discovered lead-lag edges (leader→follower, lag, confidence) now feed `run_rotation`.
- When a LEADER fires (recent lag-window return z ≥ threshold), its FOLLOWERS are flagged "primed":
  `{leader, lag, days_since_fire, window, strength}`. Strength = fired_z × confidence.
- `regime_meta` applies a conviction boost (≤18) to a primed follower in a risk-on tilt, and can
  promote it across the BUILD threshold. Reason string explains the rotation.
- Wired BEFORE asset selection (was computed after → couldn't influence ranking).
- Honest limit: this is *predictive* lead-lag, not mechanistic causation; fragile if the latent
  driver regime shifts (why the stability filter + regime-conditioning matter).
- `leadlag_cfg` passthrough added so granger_lags/maxlag can be tuned to the relationships you expect.

### #4 — Portfolio guard (`engines/portfolio.py`)
- Greedy-clusters the long book by return correlation (ρ≥0.6 default).
- Reports **effective number of independent bets** (= #clusters), flags concentration, and emits an
  **alloc multiplier** (1/cluster_size) so a correlated cluster isn't oversized.
- Surfaces in the dashboard as a portfolio warning + per-card `size×` factor.

## Visibility fix (s53) — why it 'felt like nothing changed'
The GCFIS work lived in a parallel package + one side tab whose adapter fed only PRICES, so every
advanced panel showed `n/a` and the existing tabs were untouched. s53 fixes that: the adapter now
harvests the data v40 already computes (volumes, breadth, VIX, GEX/walls, quads) and fits a real HMM
regime at runtime → the 🧭 tab populates; and a compact GCFIS confluence section is folded into Alpha
Center (guarded). v40's GEX is proxy → shown labelled `GEX·proxy`, never laundered as a real chain.

## (historical) what was deferred — now done
- **#2 real HMM regime:** the State Layer should be a Gaussian HMM fitted on the daily feature vector
  (forward-growth, NetLiq Δ, credit-z, vol-z, breadth-z, x-asset-corr). Fitting on synthetic data
  proves nothing; this needs your real feeds. The hook (`regime_posterior`) is already the seam — swap
  the quad-lookup for the fitted HMM posterior and nothing downstream changes.
- **#3 bottleneck migration:** rank nodes by Δ(tightness) to surface the *next* winner. Needs a
  time-series of node scarcity/pricing-power; the per-node scoring is already there to feed it.

## Validation
`tests/test_all.py` — 22 tests. New: `t_rotation`, `t_portfolio`, `t_rotation_portfolio_e2e`
(leadlag discovers LEADER→FOLLOWER → rotation primes FOLLOWER → wired into ranking; portfolio attaches).
As always: validated = LOGIC on synthetic + statistical machinery; NOT validated = real-market edge
(no live data in sandbox).
