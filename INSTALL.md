# 🚀 MacroRegime Pro v2.5 — Sprint 10 — AUTONOMOUS NARRATIVE + 11 INVESTOR METHODOLOGIES

**Date:** May 17, 2026

## 🔥 Sprint 10 = Final unification of all engines into one correlated system

### Yang Edward minta — DELIVERED

| # | Edward's Request | v2.5 Status |
|---|---|---|
| 1 | Yves enhanced behavioral methodology | ✅ `methodology_pack.py`: 5 narrative-divergence frames + price/sentiment divergence detector |
| 2 | Soros reflexivity (boom-bust stages) | ✅ 5-stage playbook (Inception → Acceleration → Testing → Twilight → Reversal) with position size multiplier |
| 3 | Schadner vol risk + transition + **Black-Scholes decomp** | ✅ Transition risk score + BS decomposition (Diffusive / Jump premium / Transition signal) → recommends BUY_CONVEXITY or SELL_PREMIUM_WITH_TAIL_HEDGE |
| 4 | Druckenmiller liquidity-first | ✅ WALCL Fed balance sheet trend → liquidity-β per ticker (QQQ 1.5, BTC 2.5, MSTR 2.8, KRE fragile, etc) |
| 5 | Tier 1 Alpha (dealer gamma) | ✅ Mechanical regime: PINNING / AMPLIFICATION / TRANSITION + 0DTE proxy via VIX/RV |
| 6 | profplum99 (UOA flow + Risk Range context) | ✅ Accumulation / Distribution / Late Chasing / Hedging classification cross-referenced with composite |
| 7 | Citrini thematic | ✅ Already in thought_process_engine (kept inline) |
| 8 | All engines correlate as ONE system | ✅ `narrative_engine.py` pulls from ALL 17 engines → headline narrative + 3 scenarios |
| 9 | Autonomous narrative/scenario/bottleneck | ✅ 7 causal chains + 7 bottleneck patterns auto-detected per state |
| 10 | Re-audit tabs, merge correlated | ✅ 7 tabs → 5 consolidated tabs |
| 11 | Delete useless | ✅ Smart Money 13F holdings tab DELETED from dashboard |
| 12 | Visual upgrade | ✅ Top narrative card with bull/base/bear scenarios + active themes/bottlenecks |

## 🆕 Engines Built/Enhanced

### `engines/methodology_pack.py` — 6 evaluators in one (598 lines)
- **`evaluate_yves(ticker, prices, news_sentiment)`** — 5 narrative-divergence frames (bubble vs rotation, intel dead vs strategic, etc) + price/sentiment divergence
- **`evaluate_soros(stage, super_bubble_score)`** — Stage playbook with position size multiplier (Inception 0.5x → Acceleration 1.0x → Twilight 0.2x → Reversal -1.0x)
- **`evaluate_schadner(ticker, prices, vix, markov)`** — Transition risk + BS decomposition (NEW Edward-asked feature)
- **`evaluate_druckenmiller(ticker, fred)`** — Liquidity-β with WALCL trend (DRUCKENMILLER_LIQUIDITY_PLAYS dict)
- **`evaluate_tier1alpha(ticker, gamma_data, prices)`** — Dealer mechanical regime + 0DTE proxy
- **`evaluate_profplum99(ticker, gamma, greeks, risk_range)`** — UOA contextualization

### `engines/narrative_engine.py` — Autonomous synthesis (466 lines)
- **`CAUSAL_CHAINS` dict** — 7 cross-asset chains: fiscal_dominance, ai_capex_rotation, agentic_cpu_rotation, stagflation_real_asset, deflation_crash, credit_stress, behavioral_squeeze
- **`BOTTLENECK_PATTERNS` dict** — 7 bottleneck patterns: power_grid_5yr_waitlist, hbm_memory_supply, advanced_packaging_cowos, optical_photonics, uranium_nuclear, fiscal_dominance_real_asset, defense_rearmament
- **`generate_macro_narrative(snap)`** — THE single headline narrative (priority logic: CP alert > severe fiscal > Q3 stagflation > Q1 + rotation > Q4 > Soros twilight)
- **`generate_scenarios(snap)`** — Bull/Base/Bear scenarios with probabilities from Markov forecast_3m + ticker exposure + options play
- **`build_narrative(snap)`** — Master entry returning complete output

### Schadner BS-Decomposition (the new layer Edward asked about)

```python
schadner_bs_decomposition(rv_21, rv_60, rv_252, vix) → {
    "diffusive_baseline_pct": ...,    # Black-Scholes RV proxy
    "total_iv_implied_pct": ...,      # VIX-implied
    "jump_premium_pct": ...,          # Tail premium
    "transition_signal_pct": ...,    # Regime instability
    "recommended_structure": "BUY_CONVEXITY" | "SELL_PREMIUM_WITH_TAIL_HEDGE" | None,
}
```

**Why it matters**: When jump premium > 30% rich → BS underprices tails → Buy OTM convexity.
When jump premium < 10% + diffusive cheap → Sell iron condor + cheap OTM wing hedge.

## 📊 Dashboard Structure v2.5

### TOP: Autonomous Narrative Card (NEW)
```
[Macro Headline with emoji]
[Sub-narrative paragraph]

🟢 BULL ⭐ DOMINANT (75%)     🟡 BASE (20%)              🔴 BEAR (5%)
- Narrative                    - Narrative                - Narrative
- Long picks                   - Long picks               - Long picks
- Short picks                  - Short picks              - Short picks  
- Options play                 - Options play             - Options play

🎯 Position for BULL scenario — full action plan (expandable)
   Top Longs / Top Shorts / Options Play / Active Themes / Active Bottlenecks

3-col KPI: Chains Active | Bottlenecks Active | Behavioral Divergences

Tabs:
  🔗 Causal Chains (e.g., fiscal_dominance: 12mo, 4 longs)
  🚧 Bottlenecks (e.g., HBM Memory Supply: 2yr, 3 tickers)
  🎭 Behavioral Divergences (crowd vs flow mismatches)
```

### MIDDLE: 6 KPI metrics row (same as v2.3)

### BOTTOM: V2.5 Command Center — 5 CONSOLIDATED tabs

```
🎯 Regime Detection         (Markov V3 + GIP v10 + Discovery — merged)
🧠 Behavioral & Boom-Bust  (Yves + Soros + Divergences — merged)
🪙 Fiscal Dominance        (Bonds-XAU + UST Auction — merged)
⚡ Flow & Network          (Cascade + Capital Rotation + COATUE — merged)
🔬 Investor Lens (11 frameworks)  ★ NEW — sub-tabs for each methodology:
   🏗️ Leopold | 💱 COATUE | 📊 Karsan | 🧠 Yves | 🌀 Soros |
   ⚡ Schadner | 💧 Druckenmiller | 🎯 Tier1Alpha + profplum99
```

### REMOVED:
- ❌ 💼 Smart Money 13F (portfolio holdings — per Edward's instruction)

## 🚀 Install

```bash
cd /path/to/edgani/tes
git add . && git commit -m "Pre-v2.5 backup"
unzip ~/Downloads/macroregime_v2_5.zip
cp -r macroregime_FULL_v25/* .
git add . && git commit -m "v2.5 Sprint 10: methodology_pack + narrative_engine + dashboard consolidation" && git push
```

## 📋 Expected Build Log

```
INFO | V9 (Sprint 9) methodology engines: karsan=True spotgamma=True leopold=True coatue=True
INFO | Karsan: 3 squeeze, 5 sell-prem, 2 buy-conv
INFO | SpotGamma proxy scanner: ok
INFO | Leopold: 18 tickers matched, 3 asymmetry setups, 2 written-off recovering
INFO | COATUE: spread +85.2pp, 1 decay alerts
INFO | Narrative: '🟢 GOLDILOCKS + AI CAPITAL ROTATION VALIDATED' | Scenario: bull (62%) | Chains: 3 | Bottlenecks: 7
INFO | Orchestrator complete in ~80s
```

#process — Process output, manage risk accordingly. Deploy & verify.
