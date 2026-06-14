# MacroRegime War Room v40 — Redesigned Architecture

## Philosophy Shift
**From:** Data Terminal (show everything)  
**To:** Probabilistic Battlefield Awareness System (compress reality into actionable causal understanding)

## What Changed

### 1. Multi-Stage Filter Engine (Replaces Threshold Scoring)
```
STAGE 1: ELIMINATION        → liquidity, catalyst, confidence, persistence
STAGE 2: REGIME ALIGNMENT     → penalize misaligned, boost aligned
STAGE 3: COMPETITIVE RANKING  → top N BEST in class per market
STAGE 4: CONVICTION FILTER    → weak causal chain = eliminated
```
**Output:** Tier 1 (3-5 names), Tier 2 (5-10), Tier 3 (hidden)

### 2. Causal Ticker Cards (Replaces Signal Cards)
Every Tier 1 ticker now shows:
- **WHY NOW** — Asymmetric setup explanation
- **WHAT CHANGED** — Market structure delta
- **WHO IS TRAPPED** — Wrong-side positioning
- **WHO MUST BUY** — Forced buyers
- **WHAT IS MISPRICED** — Consensus gap
- **WHAT INVALIDATES** — Kill conditions

### 3. Regime Pressure Matrix (Replaces Flat Metrics)
7 variables × 4 horizons:
- Variables: liquidity, growth, inflation, volatility, credit, dollar, yields
- Horizons: structural, cyclical, tactical, short-term

### 4. Global Stress Engine (Replaces VIX Card)
5 stacked pressure towers:
- Liquidity Stress
- Systemic Fragility
- Positioning Crowding
- Crash Probability
- Contagion Probability

### 5. Bottleneck Map (Replaces Sector Lists)
Interactive dependency graph with chain reactions:
- AI Compute Buildout (NVDA → HBM → Power → Optics → CPO)
- Mideast Supply Shock (Oil → Tankers → Refining → Fertilizer → Defense)
- Indonesia Resources (Nickel → Palm Oil → Coal → Shipping)

### 6. Market Internals (6 Giant Panels)
- Breadth — Participation heatmap
- Leadership — RS treemap
- Credit — Spread pressure curve
- Volatility — Regime gauge
- Liquidity — Component breakdown
- Correlation — Rolling matrix

### 7. Execution Engine (Replaces Indicator Clutter)
- Market Structure Map (price + gamma + liquidity zones)
- Gamma walls
- Stop clusters
- Accumulation zones

## File Structure
```
macroregime_warroom/
├── app.py                      ← New router (7 tabs)
├── orchestrator.py             ← Multi-stage filter + tier system
├── pages_lib/
│   ├── __init__.py
│   └── warroom_pages.py        ← All 7 pages with redesigned UI
├── engines/
│   ├── __init__.py
│   └── warroom_engines.py      ← Filter, Confidence, Propagation, WhatChanged, CausalCard
└── README.md                   ← This file
```

## Integration with Legacy Engines

The new orchestrator is **backward compatible**. It still:
1. Imports `data.loader`, `data.fred_loader`
2. Runs `GIPEngine`, `RiskRangeEngine`, `MarketHealthEngine`
3. Loads all legacy engine outputs into the snapshot

But it **adds** new keys:
- `filtered_tickers` — Tier 1/2/3 output from MultiStageFilter
- `regime_pressures` — 7×4 heatmap data
- `global_stress` — 5-tower stress data
- `what_changed` — Delta detection
- `chain_reactions` — Bottleneck chains
- `leadlag` — Cross-asset lead/lag
- `causal_cards` — Causal explanations per ticker
- `confidence_scores` — Data quality + model agreement
- `propagation_network` — Nodes + edges for graph viz

## How to Deploy

### Option A: Drop-in Replacement (Recommended)
1. Backup your current `app.py` and `orchestrator.py`
2. Copy `app.py` and `orchestrator.py` from this package to your project root
3. Copy `pages_lib/warroom_pages.py` and `engines/warroom_engines.py` to your existing folders
4. Run `streamlit run app.py`

### Option B: Side-by-Side
1. Create a new folder `warroom/` in your project
2. Copy all files from this package into `warroom/`
3. Run `streamlit run warroom/app.py`

## UI/UX Rules Enforced

| Rule | Implementation |
|------|---------------|
| Theme | `#0B0E11` background, `#12161C` cards |
| Typography | Inter + Geist |
| Spacing | Section gap 32px, card gap 20px, inner padding 18px |
| Hierarchy | Regime = huge, Crash risk = huge, Opportunities = large, Raw data = hidden |
| No small widgets | Replaced with integrated heatmaps, treemaps, network graphs |
| No walls of text | One-sentence deltas + causal cards |
| No duplicated metrics | Single source of truth per metric |

## Next Steps

To complete the system, you still need to wire:
1. **Real Gamma Engine** — `gamma_data` with actual GEX/net gamma per ticker
2. **Real Options Data** — `options_data` for max pain, put/call walls
3. **Real News NLP** — `news_narratives` with sentiment + theme extraction
4. **Real Bottleneck Reference** — `bottleneck_reference.json` with consensus heatmap
5. **Real COT Data** — `cot_data` for positioning
6. **Real On-Chain** — `crypto_center` with whale signals, funding, unlocks

All integration points are marked with `# TODO: wire real engine` in the code.

## Key Design Decision: "Tickers Must Compete"

The old system used `if score > 70: show_stock()`. This is a retail screener.

The new system uses **competitive ranking** within each market:
- US Equities: max 12
- Crypto: max 8
- Commodities: max 6
- FX: max 5
- IHSG: max 10

This forces the system to say **"no"** to mediocre setups — the most important skill of an institutional filter.
