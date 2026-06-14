# MacroRegime War Room — BUILD STATUS

**Status: all 5 tabs now render** from computable signals (price/volume + FRED +
verified Risk Range / asymmetric engines). Feed-gated enrichments (GEX, on-chain, COT,
fundamentals, credit spreads) are absent and flagged — never fabricated. Not financial advice.

## ✅ Done & verified
1. **GCFIS brain** (`gcfis/`) — 13-layer engine; synthetic suite passes (`gcfis/tests/test_all.py` → 33 OK); weights normalized + labelled priors.
2. **Risk Range engine** (`gcfis/engines/risk_range_hedgeye.py`) — MQA v25.1 port, Hedgeye-faithful (TRADE 15d / TREND 63d / TAIL 756d, single ATR14, auto-tune, vol-state, Amihud, anti-wiggle, formation, RTA, response-zone). Verified on real AAPL.
3. **Asymmetric / Moonshot engine** (`gcfis/engines/asymmetric_discovery.py` + `gcfis/data/moonshot_universe.py`) — structural screen for hidden bottleneck names, honest tier base rates + failure modes. Verified.
4. **Compute bridge** (`warroom/engine_bridge.py`) — per-ticker signals (RS, momentum, crowding, reflexivity), formation-gated trade plans (entry/stop/T1/T2/R-R), breadth/leadership, Risk Range signal backtest. Verified on real + synthetic data.
5. **War Room** (`warroom/app.py`) — all 5 tabs live & smoke-tested with data:
   - **Command Center** — Risk Range measured across the universe, "X of N signaling", breadth health, NetLiq, per-market tables.
   - **Opportunity & Execution** — crowding × RS bubble map + trade cards (Risk Range band, causal mini-stack, entry/stop/target/R-R, RTA).
   - **Bottleneck & Moonshot** — ranked hidden bottleneck candidates by domain + failure modes.
   - **Market State** — breadth health, per-market breadth, RS leadership, NetLiq.
   - **Research Lab** — Risk Range dip-buy diagnostic + the acceptance gate (perm_p<0.05 AND DSR≥0.95 else NOISE).

## 🚧 Remaining — feed-gated enrichments (absent, flagged, NOT faked)
- Live **market-cap / valuation / coverage** → sharpens & de-ties the Moonshot ranking.
- **GEX / greeks** (US gamma walls on the band), **on-chain / funding** (crypto), **COT**, **IDX broker-level Type-F**, **credit spreads** (HY/IG OAS).
- **Propagation network graph** + tier-multiplier ladder + node detail sidebar.
- Full **DSR + permutation** backtest wiring (`gcfis/engines/backtest.py`) + Monte Carlo in Research Lab.

## ▶ How to run
```bash
pip install -r warroom/requirements.txt
streamlit run warroom/app.py
```
No API key (yfinance OHLCV + FRED fredgraph). In a sandbox without market data, tabs show
the degraded/empty state by design; Moonshot Radar renders from structural priors regardless.

## ⚠ Honesty
- Engine **logic/math is verified**; **edge is NOT** — weights are priors. Validate OOS in the Research Lab.
- Moonshot Radar = **structural screen, not a return forecast**. Tier-4/5 = lottery; most go to zero.
- Risk Range backtest in the lab is a **diagnostic** (overlapping, no costs, in-sample), not the acceptance gate.
- Not financial advice.
