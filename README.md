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
