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
