# Cleanup Manifest — v40 → v40_s46 (GCFIS)

Method: **import-graph reachability** from real entry points (app, orchestrator, validators, **and
Streamlit pages** — auto-discovered, not imported), with a corrected resolver that follows
`from pkg import submodule`. Every candidate cross-checked; ambiguous ones inspected **line-by-line**
(a name in a comment / local function / dict-key is NOT an import). Net: **19 dead engines removed,
all verified safe; zero dangling references.**

## DELETED — 19 superseded/duplicate/dead engines (verified unreferenced)
alpha_discovery_engine, bottleneck_map, chart_engine, cot_proxy, crypto_onchain,
druckenmiller_liquidity_engine, ihsg_broker, ihsg_specialist_v39 (2073 lines), market_card_renderer,
mqa_v17_engine, performance_optimizer, realtime_feed, trr_engine, unified_greeks_engine,
unified_macro_engine, unified_sizing_engine, unified_supply_chain_engine, universe_expansion (1072),
walkforward_backtest.
→ All recoverable from your original `macroregime_v40_s45.zip` if ever needed.

## SAFETY CATCH (why this wasn't blind)
First pass over-deleted: a resolver blind-spot (`from engines import X`) plus grep false-positives.
- `fx_commodity_driver_engine` — restored & KEPT: real `from engines import fx_commodity_driver_engine`
  in `rich_ticker_card.py`.
- `ihsg_broker`, `market_card_renderer`, `unified_greeks_engine` — initially restored, then re-deleted
  after inspecting the actual lines: only a local `_ihsg_broker_proxy_v2()` / dict-key `"ihsg_broker_proxy"`
  and **docstring mentions** — not imports. Confirmed dead.

## KEPT but FLAGGED — verify before any future deletion
- `engines/{barchart,laevitas,defillama}_scraper.py` — unwired but they are your **data scrapers** =
  the route to real options / on-chain data (closes the data gap). **Rewire, don't delete.**
- `config/narrative_universe.py` (18,644 lines) — reachable via pages; Ricky2212 knowledge base. Keep.
- `components/{market_panels,options_layer,ticker_card}.py`, `scrapers_local/local_data_scraper.py`,
  `config/autonomy_settings.py` — appear import-unreferenced but may be UI/runtime-loaded. **Not deleted.**

## STILL RECOMMENDED (needs your judgment — these are REACHABLE/live, so blind deletion breaks runtime)
Consolidate duplicate clusters to one each, rewire callers, then delete the rest:
`chain_reaction_engine`/`_v2`, the `walkforward_*` pair, `gex_engine`/`spotgamma_gex_engine`/`gamma_engine`,
`risk_range_engine`/`_v20`, and the `*_proxy` greeks (validate-or-cut per principle P4).
I did NOT auto-do these: they are imported by live code, so removing them without rewiring would break the app.
