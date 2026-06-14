# MacroRegime Pro — Deep A–Z Re-Audit Report

Scope: all 116 .py files (~61k LOC). Method: AST scan (every file, mechanically) for
bug classes + cross-engine convention/import/cohesion analysis + deep reads of the
integration core (orchestrator import graph, engine APIs, COT/OI render path).

Honest scope note: an AST + convention sweep mechanically touches every file; it does
NOT equal a human line-by-line read of 61k lines. Runtime behavior of the Streamlit app
(import-time wiring, live data) was NOT executed here — it needs a boot in your env.

---

## ✅ VERIFIED HEALTHY
- 0 syntax errors across all 116 files (`compileall` clean).
- 0 mutable default arguments, 0 `== None` comparisons.
- orchestrator does NOT contain divergent inline copies of engine logic. The apparent
  "duplicate compute_*()" functions are the `try: import real / except: def stub`
  fallback pattern — orchestrator imports the real engine and only stubs on failure.
  (So the system is modular, not a hidden monolith.)
- Quad sign mapping, risk-range key contract, sizing playbooks: consistent.

## ✅ FIXED THIS SESSION (correctness — verified by smoke test)
S0–S3 (prior): risk-range main path → v20.3b (was legacy ATR), GEX scaling+sign aligned,
charm = real Greek, vanna = real skew proxy, GIP proxy gate, VIX buckets 9-19/20-29/29+,
6% position envelope, in-sample calibration disclosed, monthly-quad weights flagged.

Re-audit additions:
- **gex_engine walls (regression I introduced in S0-b)** — after flipping equity sign,
  single-stock books go all-negative which made call_wall/flip_level degenerate. Fixed:
  walls are now POSITION-ANCHORED (call wall above spot, put wall below) + flip falls back
  to the strike nearest spot. Robust for both index (mixed-sign) and equity (all-negative).
- **COT forex polarity (real bug)** — CFTC FX futures are quoted USD-per-foreign, so spec
  NET LONG = bullish the FOREIGN currency. For USD-BASE pairs (USDJPY/USDCAD/USDCHF) that
  is BEARISH the pair. The old alignment compared raw net to a pair bias directly → INVERTED
  for USD-base pairs. Fixed via `_cot_pair_polarity()`; USDJPY JPY-long now correctly flags
  divergence vs a long-USDJPY bias. (DXY/UUP and foreign-base pairs unaffected.)
- **OI heatmap proxy scale (real bug)** — futures use an ETF proxy (GC=F→GLD), but GLD ≈
  1/10 of gold's price, so absolute $ wall levels were ~10× off next to the underlying.
  Fixed: when a proxy is used, walls are shown as % from proxy spot (percentages transfer
  cleanly to the underlying). Direct (same-domain) options still show absolute $.

## ✅ ELEVATION BUILT (not yet wired — see below)
- `engines/confluence_scorer.py` — regime-aware multi-engine scorer with HARD-VETO
  multiplicative gating. score_ticker() + rank_universe(). Tested. NOT yet called by any
  page (confirmed by audit: it is in the "dead engines / imported nowhere" list).

---

## ⚠️ SYSTEMIC DEBT (this is what stops the system being "1 kesatuan")

### D1 — 21 advertised features silently DISABLED (missing modules)
`from engines.X import ...` where `engines/X.py` does NOT exist. All are guarded by
try/except → they don't crash, they fall back to stubs ("…unavailable"). So the feature
is permanently off and the UI quietly shows a placeholder. Missing modules:
vix_bucket_engine, vanna_charm_flows, bottleneck_engine, odte_monitor, conviction_sizing,
news_nlp_engine_v3, odte_enhanced, bottleneck_discovery_v3, supply_chain_graph_real,
ust_auction_tracker, ihsg_specialist_v38, walkforward_backtest_engine, curated_picks_engine,
+ 8 in integrator_guide (walkforward_engine, signal_decay_engine, reflexivity_coefficient,
anti_fragility_engine, fractional_kelly_engine, bayesian_fusion_engine, duration_hmm_engine,
cri_v2_engine).
Remediation: per module decide REBUILD / REMOVE-import / POINT-to-existing.

### D2 — IHSG specialist version/API mismatch (high priority — your core market)
orchestrator imports `ihsg_specialist_v38` (missing) → stub. `ihsg_specialist_v39.py`
EXISTS but is imported nowhere, AND its API differs: v39 exposes `analyze_broker_flow()`
and `analyze_concentration()`, not the `.analyze()` orchestrator calls. So a naive import
swap would AttributeError / silently fail differently. Needs an adapter + call-site update
+ runtime test (v39 also wants IHSG_DATA_PATH data files present).

### D3 — 14 dead engine files (imported nowhere) = cruft
alpha_discovery_engine, bottleneck_map, cot_proxy, crypto_onchain,
druckenmiller_liquidity_engine, ihsg_broker, ihsg_specialist_v39, mqa_v17_engine,
trr_engine (a 3rd risk-range engine), unified_macro_engine, unified_sizing_engine,
unified_supply_chain_engine, walkforward_backtest, confluence_scorer (new, pending wire).
Remediation: delete or wire. Low risk but should be a deliberate decision per file.

### D4 — 127 `except: pass` silent swallows
Mostly legitimate numerical/optional-data guards (not individual bugs), but in aggregate
they make engine failures invisible. Recommendation: in the snapshot-feeding engines,
swap the most load-bearing ones to `except Exception as e: logger.debug(...)` so a failed
engine is visible rather than silently empty.

---

## 🚀 PRIORITIZED ELEVATION PROGRAM (next level, done RIGHT = incremental + runtime-tested)
1. WIRE confluence_scorer into market pages + Alpha Center (rank_universe over the
   per-ticker engine outputs already in the snapshot). Makes the cohesion layer real.
2. Alpha Center static→dynamic: keep curated thesis, add live confluence scoring/ranking.
3. Quad-conditional sector rotation per market (Q3→energy/coal in IHSG, Q1→banks/tech).
4. Resolve D2 (IHSG v39 adapter) — high value for your primary market.
5. Triage D1 (21 disabled features): rebuild the ones you actually use, remove the rest.
6. theme-maturity/crowding score + mechanical forced-selling estimator + dealer-sign
   INFERENCE (stop assuming dealer sign; infer from intraday price-vs-gamma).

Each item is independently shippable and should be runtime-verified in your Streamlit env.
