# MacroRegime War Room — BUILD STATUS

**Status: WORK IN PROGRESS — this is NOT the final version.** It is a verified
foundation + a runnable Command Center MVP. Tabs 2/4/5 are stubs, and live
fundamental feeds are not wired yet. Nothing here is financial advice.

---

## ✅ Done & verified

1. **GCFIS brain** (`gcfis/`) — 13-layer engine, cross-asset, final desk, crash/bottom,
   surge. Full synthetic correctness suite passes (`python3 gcfis/tests/test_all.py` → 33 OK).
   Composite weights normalized (sum=1.0) and labelled priors.
2. **Risk Range engine** (`gcfis/engines/risk_range_hedgeye.py`) — Python port of MQA v25.1,
   faithful to Hedgeye's published structure (TRADE 15d / TREND 63d / TAIL 756d, single ATR14,
   per-ticker auto-tune, vol-state, Amihud, anti-wiggle, formation, RTA, response-zone).
   Verified on real AAPL daily data.
3. **Asymmetric / Moonshot engine** (`gcfis/engines/asymmetric_discovery.py` +
   `gcfis/data/moonshot_universe.py`) — structural screen for hidden bottleneck names
   (centrality + early adoption + reflexivity + under-coverage + valuation + room-to-run),
   with honest tier base rates and failure modes. Verified (ordering logic + full universe).
4. **War room shell** (`warroom/app.py`) — 5-tab Streamlit app.
   - **Command Center**: measures Risk Range across the whole multi-market universe,
     surfaces only the few signaling names (quality-over-quantity, "X of N signaling"),
     per-market aware, FRED NetLiq header.
   - **Bottleneck Map → Moonshot Radar**: ranked hidden/indirect bottleneck candidates by domain.

## 🚧 Not built yet (stubs)

- **Opportunity & Execution** — bubble map + ticker cards (causal stack + Risk Range band + RTA + playbook + entry/stop/target/qty).
- **Market State** — internals (breadth/credit/liquidity/vol/correlation/leadership) + flow/positioning, per-market selector.
- **Research Lab** — walk-forward IC + permutation p + Deflated Sharpe + Monte Carlo + acceptance gate.
- **Live feeds**: market-cap / valuation / coverage (sharpens & de-ties the Moonshot ranking),
  GEX/greeks (US), on-chain/funding (crypto), COT, IDX broker-level. The Moonshot Radar runs on
  structural priors until these are wired (fundamentals shown neutral — never fabricated).
- **Propagation network graph** + tier-multiplier ladder + node detail sidebar.

## ▶ How to run

```bash
pip install -r warroom/requirements.txt
streamlit run warroom/app.py
```

Runs on deploy with **no API key** (yfinance OHLCV + FRED fredgraph). In a sandboxed
environment without outbound market data, Command Center shows the empty/degraded state
(by design) while the Moonshot Radar still renders from structural priors.

## ⚠ Honesty notes

- Engine **logic/math is verified**; **edge is NOT** — weights are documented priors,
  not proven optimal. Validate out-of-sample in the Research Lab (acceptance gate:
  `perm_p < 0.05 AND DSR ≥ 0.95, else NOISE`).
- Moonshot Radar is a **structural research screen, not a return forecast**. Higher upside
  tier = lower base rate; tier-4/5 micro-caps are lottery tickets and most go to zero.
- Not financial advice.

## Next build order

1. Wire live cap/valuation/coverage feed → re-rank Moonshot Radar.
2. Propagation network graph + tier ladder (Bottleneck Map).
3. Opportunity & Execution (ticker cards + Risk Range band + RTA).
4. Market State (flow + internals).
5. Research Lab (OOS validation harness).
