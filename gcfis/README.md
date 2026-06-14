# GCFIS — Global Capital Flow Intelligence System
### Full 13-layer validated engine layer for MacroRegime Pro v40

## 4 principles every engine obeys
1. **CHANGE not LEVEL** (Δz / acceleration everywhere). 2. **NORMALIZE then COMBINE** (robust median/MAD z).
3. **REGIME-CONDITIONAL** (meta weights blend by HMM posterior). 4. **VALIDATE not FABRICATE** (no chain → dealer returns `unknown`, never fakes greeks).

## Full GCFIS 13-layer coverage (all pass `tests/test_all.py`)
| Layer | Module | What it does |
|---|---|---|
| L1 Fragility | `engines/fragility.py` | 0-100 + non-linear amplifiers (corr conduit × CSD) + velocity |
| L2 Macro/Quad | `engines/forward_macro.py` | Market-Implied Forward Growth/Inflation → **forward** Quad (leads GDP/CPI) |
| L3 Liquidity | `engines/liquidity.py` | NetLiq = FedBS−TGA−RRP (correct signs); expanding vs zero-baseline; dominance flag |
| L4 Flow | `engines/flow.py` | capital rotation — who's gaining/losing relative strength (rotating in/out) |
| L5 Theme | `engines/theme.py` | Theme = 0.4·ΔEarnRev + 0.3·CohortRS + 0.2·ΔFlow + 0.1·Narrative |
| L6 Bottleneck | `engines/bottleneck_engine.py` | **geometric mean** of normalized factors (+ PricingPower) — any-zero-kills; node ranking |
| L7 Accumulation | `engines/accumulation.py` | RS=alpha, signed VE, + Institutional **Adoption Curve** (Stage 1-5) + crowding velocity + sweet-spot/exit |
| L8 Dealer | `engines/dealer.py` | **real signed GEX/Vanna** (Black-Scholes from chain); GEX>0=mean-rev, GEX<0=momentum; walls + gamma-flip |
| L9 Positioning | `engines/positioning.py` | COT (Williams) index, OI ROC (Δz), crowding, extreme-long/short |
| L10 Crypto | `engines/crypto.py` | post-ETF weighted: ETF flow+funding+CME basis+perp OI dominant; on-chain regime-gated |
| L11 Lead-Lag | `engines/leadlag_discovery.py` | DYNAMIC discovery: returns+Granger+Transfer-Entropy+**FDR**+stability → `leader→follower, lag, conf` |
| L12 Asset Selection | `meta/regime_meta.py` | regime-conditional **confluence** (accum+theme+flow) + **master ranking** + capacity filter + counter-regime flow-dominance |
| L13 **Entry** | `engines/entry.py` | Entry = 0.25Trend+0.25Mom+0.20Dealer+0.15Liq+0.15Structure → **Breakout/Pullback/Continuation/Mean-Reversion**, **gamma-aware** (wrong-regime entries flagged INVALID) + risk-range stop/target/RR |
| — change core | `core/change_core.py` | robust-z, Δz, acceleration, FDR, CSD; `core/contracts.py` typed per-ticker output |
| — sizing | `sizing.py` | fractional-Kelly × vol-target × VIX-bucket × drawdown — **gated** (no edge → 0) |
| — backtest | `backtest.py` | walk-forward honest metrics: cross-sectional IC + permutation, Wilson CI (non-overlap), Deflated Sharpe |
| — orchestrator/adapter/run | `orchestrator.py`, `adapter_v40.py`, `run.py` | wires all 13 → full per-ticker contract + master ranking; CLI for your machine |

## Gamma-aware entry (the fix)
- **GEX < 0 (momentum regime):** Breakout / Continuation valid (dealers amplify).
- **GEX > 0 (mean-reversion regime):** Pullback / Mean-Reversion valid; **breakout flagged INVALID** ("dealers fade — likely to fail").
- Every entry returns stop, target, R/R; R/R below threshold → invalid.
- Counter-regime: bullish quad but smart-money distributing → flips to short / stand-aside.

## Run
```bash
python3 gcfis/tests/test_all.py     # 13 layers + entry + e2e — all pass
python3 -m gcfis.run --tickers NVDA PLTR --bench SPY --regime risk_on   # on your machine (yfinance)
```

## ⚠️ HONEST BOUNDARY
**Validated:** every layer's LOGIC (synthetic correctness) + the statistical machinery on **real** S&P data
(`VALIDATION_REAL.md`: harness has power — momentum perm_p 0.007 vs random 0.192; no-look-ahead; honestly strict).
**You must run:** real-market EDGE on YOUR universe (small-caps + broker flow, IHSG, crypto on-chain) — sandbox
has no live data. Dealer/positioning/crypto/theme layers need their data feeds wired (they return `unknown`
when absent, never fabricate). Hard rule: **perm_p<0.05 AND DSR≥0.95, or NOISE.**

---
## v48 additions
- **`engines/cross_asset.py`** — Cross-Asset Coherence: reads the whole tape together, classifies regime
  (DELEVERAGING / STAGFLATION_SCARE / DEFLATION_GROWTH_SCARE / GROWTH_ON / MONETARY_EASING / MIXED) and
  flags divergences (e.g. *gold↓ while nominal yields↓ = haven bid in bonds, not gold → real-yield/liquidation
  override, NOT monetary easing*). Validated against the real June-2026 gold tape → DELEVERAGING.
- **`engines/narrative.py`** — composes the logical WHY for every ticker (which layers fired + macro + entry plan).
  **No recommendation without a reason.**
- **Entry defer-gate** — in DELEVERAGING/DEFLATION_SCARE, new longs are auto-moved to `deferred_longs`
  ("data good but price falling" guard — don't catch the liquidation knife).
- **`dashboard.py`** — one reusable `render_gcfis_dashboard(out)` you call from ANY tab (Market, Alpha Center):
  systemic radar (quad / cross-asset / fragility / shock / liquidity) + master long/short/spot/deferred with
  Alpha-Center badges (✅ ALPHA-READY / 🟡 WAIT-ENTRY / 🔶 WARMING / 🔻 SHORT / 👁 WATCH / ⏸ DEFER) + reason + entry.
- See `QUAD_AND_FILTER.md` for the verified quad mapping + ticker-filter conditions.

---
## v50 additions — closes the ticker filter + presentation gaps
- **PRODUCT confluence** (`meta/regime_meta.py`): ranking = geometric mean of theme×bottleneck×
  accumulation×adoption×reflexivity (AND-logic), replacing the additive 3-layer sum.
- **Bottleneck node→ticker** (`bottleneck_engine.py`): tickers inherit their supply-chain node's
  bottleneck score — bottleneck alpha finally reaches asset selection.
- **Reflexivity engine (B5)** (`engines/reflexivity.py`): runaway-loop detector (price×flow
  co-acceleration); `runaway` flag = monster-move signature.
- **Full per-ticker output contract** (`core/contracts.py`): Options panel, Macro stamp, Risk,
  **Opportunity scenarios (bear/base/bull/supercycle)**, Institutional, subtheme.
- **Multi-panel card** (`dashboard.card_html`): renders the whole contract, not one line.
- All in `tests/test_all.py` (19 tests incl. `t_reflexivity`, `t_bottleneck_map`, `t_full_contract_e2e`).
