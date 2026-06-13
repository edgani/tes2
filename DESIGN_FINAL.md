# MacroRegime — FINAL DESIGN (definitive)

This is the contract the build follows. It merges **v40s60's visuals** + **every ChatGPT audit (docs 11/12/15/16 + UI blueprint)** + improvements where both fell short. Honest status tags throughout: ✅ built in v2 · 🟡 partial · 🔴 not built · 🔒 seam (needs paid/auth feed).

---

## 0. Design philosophy
War-room, not Bloomberg. In 5 seconds the screen answers: *what changed, what's fragile, what's silently accumulating, where is bottleneck pressure, what's the best asymmetric trade, why now.* Visual-first with concise explanation text (not walls). One screen = one primary message. Hierarchy: **what matters now → why → what benefits/breaks → how to execute → raw drilldown**.

---

## 1. DATA ARCHITECTURE (the thing that must never silently fail)
Every number carries provenance: **REAL / PROXY / SEAM**. The banner shows counts; nothing proxy is ever shown as real.

| Source | What | Status | Load path |
|---|---|---|---|
| Yahoo chart API | OHLCV universe (prices) | ✅ | `core/live_data.py` (Stooq fallback) |
| FRED (no key) | NetLiq, HY/IG OAS credit, real yield, curve, VIX | ✅ (cache-failure bug fixed, 30s) | `core/data_layer.py` |
| Yahoo ^VIX/^VIX3M | VIX term structure | ✅ | data_layer |
| IDX GetStockSummary | Type-F foreign flow (FB/FS) → BM | ✅ parser, 🔒 live (IDX blocks non-ID/cloud IPs sometimes) | `core/typef_idx.py` |
| Options chain | GEX/Vanna/Charm (real Black-Scholes) | ✅ engine, 🔒 chain feed (FlashAlpha paid / Deribit free for crypto) | `engines/dealer.py` |
| ETF/MF flow, earnings-revision, dark-pool, on-chain, full-constituent breadth | — | 🔒 | declared seams |

**Resilience rules (non-negotiable):** never cache a failed fetch; per-series graceful fallback; a manual "Reload live data" button; if a feed is down, label SEAM and degrade — never blank-screen, never fabricate.

---

## 2. FRAMEWORK / THINKER INTEGRATION (keep what's useful)
| Thinker | Contribution | Where it plugs in | Status |
|---|---|---|---|
| **Soros** | Reflexivity: price→flow→narrative→price; runaway = price AND flow accelerating | `engines/reflexivity.py` → ticker causal stack + exit guard | ✅ |
| **Citrini** | Bottleneck / hidden second-order winners (AI→HBM→foundry→power→cooling→uranium) | `engines/bottleneck_engine.py` → Bottleneck Map tab | 🟡 **upgrade to real network** (currently boolean) |
| **Leopold / Aschenbrenner** | AI-capex super-cycle / situational awareness (NVDA/SMH/power/datacenter/optical) | NEW `engines/ai_capex.py` → US-market DNA + theme regime | 🔴 **build** (ChatGPT flaw #8) |
| **Hedgeye** | GIP 2×2 quad (growth×inflation RoC), Risk Range, TRADE/TREND/TAIL | `engines/forward_macro.py` + `core/visuals.quad_map` | ✅ visual + market-implied quad |
| **Bandarmologi (Ricky/Om Salim)** | Foreign flow, LPM, Corr_F/Par_F, broker concentration, nominee/UBO | `engines/flow_regime.py` + `core/bandarmetrics.py` (calibratable to exact-match) | ✅ formula, 🔒 live IDX |
| **Yves** | *Not found in codebase.* If this is Yves Lamoureux (contrarian/sentiment) or another, tell me the framework and I'll encode it — I won't fake an attribution. | — | ❓ need spec |

Options/greeks are first-class: **GEX>0 → dealers long gamma → mean-reversion regime; GEX<0 → short gamma → momentum/crash-accelerant.** Gamma flip level + Vanna + Charm feed Execution + crash detection.

---

## 3. THE 7 TABS (final, merged structure)

### Tab 1 — COMMAND CENTER ✅(visual hero done) 🟡(what-changed pending)
*What is changing in the world right now?*
- **Hero left (62%):** Hedgeye 2×2 quad heatmap — live position from GROC/IROC, structural/monthly/global markers + transition arrow. ✅
- **Hero right (38%):** Risk = stacked **stress bars** (credit / liquidity / VIX-term / breadth) + big Shock & Crash metrics, color-coded, with provenance per bar. ✅
- **What Changed Today** 🔴: timeline cards — gamma flip, credit widening, breadth deterioration, accumulation shift, narrative acceleration (daily-delta engine vs stored snapshot).
- **Cross-asset consistency** 🟡: mini network — if semis/credit/transports disagree with index → warning.

### Tab 2 — OPPORTUNITY RADAR 🟡
*Best asymmetric trades.*
- **Opportunity cluster map** 🔴: bubble matrix — X=crowding, Y=fundamental pressure, size=reflexivity, color=regime alignment.
- **Ticker cards** ✅(basic) → 🟡 upgrade to full causal-stack card (§6), 2-column, not tables.

### Tab 3 — BOTTLENECK MAP 🔴 (most unique edge — Citrini)
Fullscreen interactive dependency network. Nodes = commodities/sectors/suppliers/power/semis; size = demand acceleration; color = constrained(red)/accumulation(cyan)/beneficiary(green)/emerging(yellow). Click → supply elasticity, inventories, lead times, utilization, beneficiaries/victims.

### Tab 4 — FLOW & POSITIONING 🟡 (front-running)
- **Accumulation heatmap** 🟡: rows=markets, cols=accumulation/dealer-gamma/foreign-flow/dark-pool/OI/funding/whale/crowding.
- **Market-specific panels:** US=gamma/vanna/charm/ETF-conc (🔒 chain); Crypto=exchange reserves/stablecoin/whale/funding/liquidation (🔒 on-chain); IHSG=LPM/DTE/Corr_F/broker-entropy/participation/intensity (✅ formula, 🔒 live).

### Tab 5 — MARKET INTERNALS 🟡 (crash vs healthy)
Market health bar + 6-panel grid: breadth(heatmap) / credit(spread curve ✅) / liquidity(NetLiq ✅) / volatility(regime bands) / correlation(matrix) / leadership(RS tree). Breadth needs constituents 🟡.

### Tab 6 — EXECUTION ENGINE 🟡
Market structure (gamma walls 🔒 / liquidity zones / vol compression / stop clusters). Main chart = price + key levels + gamma + accumulation zones ONLY. Execution playbooks: breakout / squeeze / mean-reversion / continuation / capitulation-reversal, each with conditions + invalidation + (eventually) historical win-rate.

### Tab 7 — RESEARCH LAB ✅
Walk-forward, feature importance, correlation decay, Monte-Carlo, the validation gates (DSR≥0.95 + perm p<0.05 else NOISE), and the honest open-calibration list.

---

## 4. TICKER FILTERING BY MARKET (each market has its own DNA)
A name is evaluated by its market's dominant variables, NOT one universal rule:

| Market | Dominant DNA | Primary long trigger | Primary short/avoid trigger |
|---|---|---|---|
| **US equities** | gamma · breadth · credit · semis-RS · AI-capex | positive alpha-RS + accumulation stage (≤ Institutional) + GEX context + not exit-signal | distribution + breadth/credit deterioration + GEX<0 waterfall |
| **Crypto** | liquidity · reflexivity · funding · stablecoin | spot accumulation + reflexive uptrend not yet euphoric + funding reset | reflexive blow-off (runaway) + funding extreme + OI unwind |
| **FX** | rate differentials · DXY · carry · funding | differential + carry tailwind aligned | carry-unwind / dollar-funding stress |
| **Commodities** | inventory · term-structure · positioning | backwardation + inventory draw + positioning not crowded | demand destruction + contango + positioning unwind |
| **IHSG** | foreign flow · LPM · Corr_F · broker entropy · participation | foreign accumulation (Corr_F up) + LPM rising + low broker entropy (concentration) | distribution + foreign exit + LPM rollover (long-only book: avoid, don't short) |

---

## 5. TICKER APPEARANCE CRITERIA (the quality gate — quality > quantity, no padding)
A ticker is shown ONLY if ALL hold (else it stays WATCH and is not listed):
1. **Direction confirmed** — sign agreement between trend(60d), alpha-RS, and flow/accumulation (fixes the direction-blind bug).
2. **≥2 independent supporting reasons** from different engines (e.g. RS + adoption-stage + surge), not one signal echoed.
3. **Regime-permitted** — hard override: if systemic credit stress > 85 → long signals disabled (ChatGPT flaw #1). If regime contradicts (e.g. ACCUMULATION in DELEVERAGING liquidation day) → gated.
4. **Valid execution** — entry/stop/target present and **RR ≥ 1.5** (the current ATR-stop RR<1 bug is fixed by wiring `entry.py`).
5. **Positive EV** at the blended conviction probability.
6. **Not late-stage exhausted** — RETAIL_MANIA + exit_signal blocks a fresh long (don't chase the top).
7. **Confidence floor** — if all inputs are proxy/seam, it's labeled low-confidence and de-ranked, never shown as high-conviction.

If <N clear the bar, show <N. Never fabricate fills to hit a number.

---

## 6. TICKER CARD CONTENT (causal decomposition, not "good stock")
Each card answers: **why now · why this · why not others · what breaks it · who's trapped · who must buy.**
- **Header:** ticker · direction · conviction · timeframe (all large).
- **Causal stack (horizontal pressure bars):** macro · liquidity · bottleneck · accumulation · positioning · narrative · reflexivity.
- **Propagation:** the chain (e.g. AI demand → HBM shortage → foundry → power).
- **Execution:** entry · invalidation · liquidity zones · gamma wall · RR · volatility state.
- **Mini chart (right, no spaghetti):** price + RS + accumulation + gamma levels only.

---

## 7. FORMULAS & WEIGHTS (honest provenance — priors until validated)
- **GIP quad:** growth/inflation = robust-z composites of market inputs (copper/gold, SOX-RS, HY-OAS-inv, small-cap, curve | breakeven, commodities, real-yield-inv). Quad from sign(GROC)×sign(IROC). ✅ Weights = priors; `.fit()` ridge on real next-period growth on your machine.
- **NetLiq** = WALCL/1000 − WTREGEN − RRPONTSYD ($bn). ✅ REAL.
- **Shock** = 0.34·credit + 0.30·liquidity + 0.20·VIX-term + 0.16·breadth → crash-type FLUSH/CYCLICAL/SYSTEMIC; confidence = #REAL inputs. ✅
- **Dealer:** signed GEX/Vanna/Charm from Black-Scholes over the chain; gamma_flip = strike where net gamma crosses 0. ✅ engine, 🔒 chain.
- **BM:** Par_F=(FB+FS)/(2·Value); Corr_F=corr(close, cumΣ(FB−FS), W); LPM=cumΣ((close−vwap)·vol). ✅ `calibrate()` solves W/smoothing/aggregation to **exact-match** your TPIA 0.711/30.93% & BREN −0.188/50.74% once you export the data.
- **Dynamic weighting (ChatGPT flaw #2/#3)** 🔴: weight profiles per regime — QE-meltup→{gamma,liquidity,momentum}; banking-crisis→{credit,funding,liquidity}; commodity-shock→{inventory,shipping,curve}. Replaces static `_W`.
- **Conviction blend:** 0.30·meta + 0.25·confluence + 0.15·flow + 0.10·horizon + 0.10·responseQ + 0.10·crowd, direction-aware. Prior.

---

## 8. HONEST BUILD STATUS & WHAT I NEED FROM YOU
**Built & working (v2):** Yahoo price loader, FRED macro+credit (robust), VIX-term, full 34-engine library, BM + calibration harness, Hedgeye quad visual, shock engine, quality-gated picks, 7-tab shell with visual Command Center.
**Top build queue (priority order):** (1) ✅ DONE entry.py RR≥1.5; (2) dynamic regime weighting + hard credit override; (3) **AI-capex engine (Leopold)**; (4) real **bottleneck network (Citrini)**; (5) full causal-stack ticker card; (6) what-changed daily-delta; (7) opportunity bubble map; (8) cross-asset consistency; (9) breadth via constituents.
**Needs you / external:** options chain feed (FlashAlpha) for live GEX; TPIA/BREN export to lock BM exact-match; the **Yves** framework spec; confirm IDX Type-F resolves on your deploy.
**Never faked:** ETF flow, earnings-revision, dark-pool, on-chain — declared seams until you wire a feed.
