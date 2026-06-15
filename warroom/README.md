# MacroRegime War Room — complete app (7 tabs, per FINAL_REDESIGN_SPEC)

A **decision war room**, not a data terminal. Competitive ranking (3-5 conviction, not 60),
hierarchy by importance, causal cards, propagation graph, market-specific flow. Computable
signals (price/volume + FRED) drive it; paid feeds (gamma/on-chain/COT) are shown **locked,
never faked**. Not financial advice.

## Run
```bash
pip install -r requirements.txt
streamlit run app.py
```
No API key (yfinance + FRED). In a sandbox without market data, tabs show the degraded state
by design; deploy to Streamlit Cloud for live data.

## What's wired (verified end-to-end)
- `competitive_ranking_engine.py` — multi-stage competition: eliminate → regime-weighted
  geometric-mean score → hard penalties → per-market caps + global tiers (T1 3-5 / T2 5-10 / hidden).
- `bridge.py` — computes signals from price/volume → maps to `TickerCandidate` pillars →
  runs the ranking → tiers. Plus regime read, breadth, leadership, propagation chains.
- `risk_range_hedgeye.py` — Hedgeye Risk Range (MQA v25.1 port) for bands/entries.
- `moonshot_universe.py` — bottleneck centrality + the asymmetric/moonshot seed names.
- `app.py` — 7 tabs:
  1. Command Center — Regime Pressure Matrix + Global Stress Engine (towers) + what-changed + active chains
  2. Opportunity Radar — bubble cluster + Tier-1 causal cards (why now / what changed / mispriced / invalidation)
  3. Bottleneck Map — propagation chains (event→bottleneck→2nd order→loser) + Moonshot Radar
  4. Flow & Positioning — market-specific (computable now + locked feed panels per market)
  5. Market Internals — 6 panels (breadth/leadership/credit/volatility/liquidity/correlation)
  6. Execution Engine — Risk Range bands + entry/stop/target for Tier-1 (no indicator clutter)
  7. Research Lab — acceptance gate (perm_p<0.05 AND DSR≥0.95 else NOISE)

## Honest status
- Engine **logic is verified**; **edge is NOT** — pillars are computable proxies + priors. Validate OOS in Research Lab.
- Feed-gated panels (gamma/vanna/charm, on-chain/funding/liquidation, COT, HY OAS, correlation matrix, propagation node intensity) are **locked, not fabricated**.
- "What changed" shows biggest RS shifts now; true day-over-day deltas need prior-session state (next).
- Moonshot Radar = structural screen, not a return forecast. Tier-4/5 mostly go to zero.
