# Quad calc + ticker filter + ticker presentation — verification

## Quad (engines/forward_macro.py) — Hedgeye GIP, CORRECT
Market-implied growth/inflation composites, classified by RATE-OF-CHANGE (2nd-derivative):
GROC≥0&IROC<0→**Q1 Goldilocks** · ≥0&≥0→**Q2 Reflation** · <0&≥0→**Q3 Stagflation** · <0&<0→**Q4 Deflation**.
Verified in `test_all.py::t_l2`. Default weights are PRIORS; `fit_ridge()` re-fits on real next-period growth.

## Ticker FILTER (meta/regime_meta.py) — PRODUCT confluence (matches GCFIS spec)
Offensive score = **geometric mean** of the AVAILABLE offensive sub-scores (each ∈[0,1]):
`Theme × Bottleneck × Accumulation × Adoption-sweet-spot × Reflexivity`.
- AND-logic: a present-but-weak layer drags the score down (confluence required).
- Absent-data layers are EXCLUDED (not zeroed) — no penalty for data you don't have (honest).
- **Bottleneck now reaches the ticker**: `bottleneck_engine` emits a node→ticker map, each ticker
  inherits its supply-chain node's score (NVDA→GPU). Verified `t_bottleneck_map` + `t_full_contract_e2e`.
- **Reflexivity (B5)**: runaway loop detector (price×flow co-acceleration) feeds confluence. `t_reflexivity`.
A ticker reaches **master_long** only if: confluence·regime-tilt·(1−stress) ≥ 55, NOT distributing,
passes capacity (ADV), NOT cross-asset-deferred. **master_short** = distribution score
(exit_signal / crowded-rolling-over[crowd>85 & vel<0] / broker NET_DISTRIBUTION / COT-extreme).
Counter-regime: bullish quad + distribution → demote long / flip short.

## Ticker PRESENTATION (core/contracts.py + dashboard.card_html) — full GCFIS output contract
Each ticker carries the COMPLETE contract, rendered as a multi-panel card (not a one-liner):
- **Identity**: ticker, theme, subtheme
- **Scores**: meta, accumulation, theme, bottleneck, reflexivity, **liquidity, dealer, positioning**, confluence
- **Institutional**: adoption_stage, crowding, adoption_velocity, **revision, ownership_Δ, etf_flow** (surface when data supplied; also feed accumulation crowding)
- **Options** (real chain only, else "n/a" — never fabricated): call_wall, put_wall, GEX, gex_sign, **gamma, gamma_flip, vanna, charm**, is_real
- **Macro** (stamped per ticker): quad, liquidity_regime, fragility, shock_prob, cross_asset_regime
- **Entry**: type, gamma_regime, entry_px, stop, target, RR
- **Opportunity**: bear / base / bull / supercycle (vol-scaled price fan)
- **Conviction** + reason
Verified end-to-end in `test_all.py::t_full_contract_e2e` (asserts every panel populated + card renders all).
