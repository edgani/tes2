# MacroRegime v2 — clean, data-first rebuild

**Why v2:** v40 was a polished dashboard running on OHLCV *proxies* → garbage tickers. v2 puts a
REAL data layer first, tags every number REAL/PROXY/SEAM, then builds the 7-tab causal structure on top.

## Run
Deploy to Streamlit Cloud, point it at `app.py`. Live feeds (FRED credit/NetLiq, VIX term, IDX Type-F)
resolve **only** on Cloud — this is by design. Locally you will see PROXY/SEAM labels (the honest state).

## What's REAL now (free, no API key)
- FRED: NetLiq (FedBS−TGA−RRP), **HY & IG OAS credit spreads**, 10y real yield, 10y-2y curve, VIX spot
- VIX term structure (^VIX/^VIX3M) — panic-transition signal
- IDX Type-F foreign flow (ForeignBuy/Sell) for .JK names

## Declared SEAMS (need paid/auth feeds — never faked)
options GEX/Vanna/Charm · ETF/MF flow · earnings-revision diffusion · dark-pool prints · on-chain (SOPR/MVRV) · full-constituent breadth

## Build order (this pass = step 1)
1. ✅ Data layer + shock engine (credit/liquidity/VIX-term, crash-type classifier) — REAL, fixture-tested
2. Market-state classifier per market DNA (reuses validated engines)
3. 7-tab visuals: causal map, FINAL DESK, per-market pages, ticker thesis page
4. Wire breadth (constituents) + forward-growth index
