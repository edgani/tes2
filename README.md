# MacroRegime v2 — clean, data-first rebuild

**Why v2:** v40 was a polished dashboard on OHLCV *proxies* → garbage tickers, with sprawling/empty tabs.
v2 puts a REAL data layer first (provenance on every number), then a 7-tab causal structure populated by a real engine pipeline.

## Run
Deploy to Streamlit Cloud → point at `app.py`. Live feeds (FRED credit/NetLiq, VIX term, IDX Type-F)
resolve only on Cloud. In the sandbox it runs a **labeled DEMO universe** so every tab shows real
engine output; swap in your universe + the feeds flip provenance to REAL.

## What's real now (free, no key): FRED NetLiq, **HY/IG OAS credit**, real yield, curve, VIX; VIX term; IDX Type-F.
## Seams (paid/auth, never faked): options GEX/Vanna · ETF flow · earnings revision · dark pool · on-chain · full-constituent breadth.

## HONEST open items (see Research Lab tab)
1. **flow_type is direction-blind** — reads volume expansion as DISTRIBUTION on strong uptrends
   (NVDA +33% → NEUTRAL, never ACCUMULATION). This is the #1 reason "next PLTR" isn't caught yet.
   It's a logic gap, not a data gap. Verdicts are directionally gated so it can't emit a wrong-side call.
2. breadth + forward-growth need index constituents (free, computable on Cloud).
3. paid seams above.

## Tabs (ChatGPT structure) — all populated from the pipeline
Mission Control (shock + crash + FINAL DESK) · Regime & Liquidity (FRED macro + internals) ·
Narratives & Bottlenecks · Market Intelligence (per-market state tables) · Ticker Intelligence
(thesis/positioning/execution) · Portfolio & Risk · Research Lab (validation gates + open items).

## s-rebuild update: validated v40 engine library RESTORED into v2
Earlier I wrongly dropped most engines doing a literal "from 0". Now v2 carries the full validated
set (31 engines + regime_meta/decision_stack/contracts), import-resolved to the flat layout.
The per-ticker verdict now uses accumulation (RS + adoption stage + crowding + velocity) and
reflexivity — so flow_type's direction-blindness is fixed: it's one input, not the sole judge.
Demo proof: PLTR/XLU → LONG (real RS + institutional stage); NVDA/BTC correctly HELD (retail-mania
+ exit_signal = don't chase top). Open flaw logged: ATR-based stops sometimes give RR<1 — sizing/
target engine (entry.py) to be wired next. Engines mapped to ChatGPT audit in the chat.

## salvage audit + BandarMetrics (this pass)
- Confirmed: all 34 v40 engines/meta/core ARE in v2 (not thrown away). What was missing = the rich
  UI layer; now restored: components/ (rich_ticker_card, market_panels, mini_viz, options_layer,
  ticker_card, causal_map) — all compile clean in v2.
- BandarMetrics: core/bandarmetrics.py + calibrate() harness reverse-engineers BM's exact convention
  from your reference numbers. See BANDARMETRICS_REVERSE_ENGINEERING.md. Proven on synthetic
  (recovered hidden window exactly). Final exact-match needs your TPIA/BREN export (IDX blocked here).

## live-data fix (root cause of permanent "DEMO universe")
- core/live_data.py ADDED: fetches real OHLCV via Yahoo chart endpoint (Stooq fallback). The app
  never had a live price loader — that's why it always showed DEMO. Now it tries LIVE first;
  demo is a labeled fallback only.
- FRED fixed: no longer caches failures (a cold-start timeout used to poison the whole session),
  timeout 20→30s, '🔄 Reload live data' button to force refetch.
- Sandbox blocks Yahoo/FRED so it still shows DEMO HERE; on Streamlit Cloud the banner flips to
  "🟢 LIVE — N/12 loaded" and engines run on real prices + FRED credit/NetLiq turns REAL.
- Verify on deploy: top banner says LIVE (not DEMO) and FINAL DESK shows your real tickers.
  If FRED still times out, click Reload (the failure is no longer cached).

## build-queue executed (this pass) — 5 items shipped + tested
1. ✅ entry.py wired → execution RR ENFORCED ≥1.5 (structure-based stop/target). The RR<1 bug is gone;
   gate now filters (demo: 3/12 clear, PLTR RR 4.99 / USDJPY 2.55 / XLU 9.74).
2. ✅ Hard regime override + dynamic weighting (core/regime_policy.py) — systemic credit (REAL, >0.85)
   → LONGS_DISABLED banner + long picks suppressed. Weight profile per regime replaces static _W.
3. ✅ AI-capex engine (core/../engines/ai_capex.py — Leopold) — compute/power/infra RS → 0-100 cycle
   score + phase. Demo: 73.9 ACCELERATION, compute leading, power lagging (narrow leadership flagged).
4. ✅ Bottleneck NETWORK (core/supply_chain.py — Citrini) — AI dependency graph, pressure = tightness ×
   centrality, surfaces the HIDDEN winner (demo: power). Rendered in Narratives & Bottlenecks tab.
5. ✅ What-changed daily-delta (core/what_changed.py) — quad shift / shock jump / crash-type / new-dropped
   picks / crowding. Rendered as delta cards on Command Center.

Tests: 5/5 groups pass. DEPLOY NOTE: set Streamlit Cloud Main file path = macroregime_v2/app.py + Reboot,
else changes won't show (this was likely why "nothing changed").

## quad fix + Hedgeye reality check (this pass)
- Researched Hedgeye's ACTUAL current state: Q1→Q3 transition early 2026; now **Quad 3 Stagflation**
  (Q2/Q3 2026, oil-shock driven), → Quad 4 in November; gold #1. Source: Hedgeye insights Mar–Apr 2026.
- Quad engine rewritten to Hedgeye's REAL structure: **Quarterly (climate, 63d RoC) + Monthly (weather,
  21d RoC)** — two genuine horizons, not 3 identical fakes.
- Visual fixed: active quadrant highlighted (border + brighter fill + ● badge), markers clamped in-bounds
  (the off-screen/behind-axis bug is gone), Quarterly solid + Monthly hollow at real positions.
- **Hedgeye reference shown on Command Center with a divergence flag.** Our quad is MARKET-IMPLIED (RoC of
  growth/inflation proxies); Hedgeye's is a GDP/CPI economic nowcast — they can diverge, and the app now
  shows both so you're never misled. Market-implied vs Hedgeye calibration is an open item (needs your real
  data + ideally the GDP/CPI nowcast inputs to align the proxy).
