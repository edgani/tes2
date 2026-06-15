# War Room v2 — new-design front-end on your VERIFIED tes2 engines

## What this is
A new-design Streamlit front-end (verdict-first, conviction-focused) that **reuses the engines
already in your `edgani/tes2` repo** instead of rebuilding them. 6/7 target engines smoke-tested
PASS on synthetic data; the full `compute()` pipeline runs end-to-end with zero errors.

## Run it
```bash
git clone https://github.com/edgani/tes2 && cd tes2
pip install -r warroom/requirements.txt        # streamlit, pandas, numpy, yfinance, scipy, sklearn, statsmodels, hmmlearn
cp /path/to/warroom_v2.py /path/to/lpm.py .     # drop these two in the repo ROOT
cp -r /path/to/.streamlit .                      # dark theme
streamlit run warroom_v2.py
```
yfinance live in your env; no feed → deterministic SYNTHETIC fallback (flagged in UI).

## What's wired (verified PASS)
| Tab | Engine used | Gives |
|---|---|---|
| Command Center | `warroom.bridge.build` + `risk_range_hedgeye` | Quad verdict, drivers, breadth, conviction w/ Hedgeye TRADE/TREND/TAIL band |
| Alpha Center | `warroom.bridge` ranking + `thought_process_engine` | competitive funnel, causal cards + matched frameworks per name |
| Bottleneck & Moonshot | `leopold_methodology` + `asymmetric_discovery` | Aschenbrenner OOM scaling, bottleneck layers, hidden-name screen |

## Analyst frameworks → engines (they were already built — now surfaced)
- **Citrini** (bottleneck migration) → `thought_process_engine.evaluate_citrini` + `bottleneck_discovery_v3` + `supply_chain_graph_real`
- **Leopold Aschenbrenner** (OOM / compute scaling, atoms>bits) → `leopold_methodology` (Layer1_Power … Layer4_PhotonsMemory)
- **Yves Lamoureux** (behavioral extremes) → `yves_engine` + `methodology_pack.evaluate_yves` + `aaii_scraper`
- **Soros** (reflexivity / boom-bust) → `boombust_engine` + `reflexivity_engine` + `methodology_pack.evaluate_soros`
- **Druckenmiller** (liquidity-first) → `methodology_pack.evaluate_druckenmiller` + `liquidity.py` (NetLiq)
- **Coatue** (shortage economy) → `coatue_methodology`
- **Keith McCullough / Hedgeye** → `keith_signal_sync` + `risk_range_hedgeye` + `gip_engine`
- **Cem Karsan** (vanna/charm/vol) → `cem_karsan_universal` + `karsan_vol_scanner` + `vanna_charm_flows`
All are orchestrated by `engines/thought_process_engine.analyze_multi` (already wired into Alpha Center).

## LPM fix (replaces the buggy volume-based one)
- `lpm.py` — value-based `CLV × Volume × Price`, + windowed mode. Matches the repo's own
  `BANDARMETRICS_REVERSE_ENGINEERING.md` derivation.
- `calibrate_lpm.py` — feed it a 60-row BandarMetrics export (date,OHLC,Volume,LPM); it locks
  `{scaling, span, cumulative vs windowed}` by R². Then point `engines/bandarmetrics_engine` at it.

## Honesty
Engine math is verified; **edge is not** — weights are priors, validate OOS in the Research Lab.
Moonshot = structural screen, not a forecast. Not financial advice.

## Next (not yet in v2)
- IDX tab (BandarMetrics + `flow_regime` + fixed LPM), Crypto tab (`crypto.py` + on-chain), FX tab (`fx_carry_engine`).
- Fix `gcfis/orchestrator.run_gcfis` input shape (wants 1-D series) to swap in the full 13-layer.
- Propagation graph (`components/causal_map.py` + `supply_chain_graph_real`) for the Bottleneck tab.
