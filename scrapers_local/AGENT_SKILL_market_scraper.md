# Skill: MacroRegime Market Data Scraper

## Description
Given one or more ticker symbols, fetch options/GEX/OI/greeks data from barchart.com,
cmegroup.com, and laevitas.ch by driving a real browser, normalize the data to JSON,
and commit+push it to the GitHub repo so the MacroRegime dashboard can read it.
Trigger this skill when asked to "update market data", "scrape options for <ticker>",
or on the scheduled cron job.

## When to use
- Scheduled daily run (via the agent cron/heartbeat) to refresh data for the active watchlist.
- On-demand when a new ticker appears and needs options/OI data the free APIs lack.
- After market close (US ~4:15pm ET, crypto anytime) for freshest settled data.

## Inputs
- `tickers`: list of symbols, e.g. ["IBIT", "GLD", "USO", "NVDA"].
- `repo_path`: local clone of the dashboard repo (default: ~/macroregime).
- `output_file`: JSON to write (default: <repo_path>/scraped_market_data.json).

## Tools required
- browser (Playwright-backed) — render JS-heavy pages.
- file write — save JSON.
- shell — git add/commit/push.

## Procedure

### Step 1 — For each ticker, decide the source by asset class
- US stock / ETF (NVDA, IBIT, GLD, USO, SPY, QQQ) → **barchart**.
- Futures (crude, gold, silver, natgas, copper) → **cmegroup** (QuikStrike).
- Crypto (BTC, ETH) → **laevitas** (Deribit).

### Step 2 — Open the page in the browser and wait for render
- barchart options: `https://www.barchart.com/etfs-funds/quotes/{ticker}/options-overview`
  (also `/gamma-exposure`, `/max-pain-chart`, `/put-call-ratios`, `/volatility-greeks`).
- CME OI: `https://www.cmegroup.com/markets/{product}.html` then the QuikStrike OI profile tool.
- laevitas GEX: `https://app.laevitas.ch/dashboard/options/gex/{ASSET}/DERIBIT`
  and skew: `.../options/skew-bf/{ASSET}/DERIBIT`.
- Wait 3–5 seconds after load for JS/charts to render before reading the DOM.

### Step 3 — Extract the fields
For each page, pull and normalize into this schema (per ticker):
```json
{
  "ticker": "IBIT",
  "source": "barchart",
  "fetched_at": "ISO timestamp",
  "spot": 0.0,
  "net_gex": 0.0,
  "call_wall": 0.0,
  "put_wall": 0.0,
  "gamma_flip": 0.0,
  "max_pain": 0.0,
  "put_call_ratio": 0.0,
  "atm_iv": 0.0,
  "expected_move_pct": 0.0,
  "open_interest_by_strike": [{"strike": 0.0, "call_oi": 0, "put_oi": 0}]
}
```
If a field isn't present on the page, set it to null — do NOT invent values.

### Step 4 — Merge all tickers + write JSON
Write `{ "generated_at": "...", "data": { "<ticker>": {...}, ... } }` to `output_file`.

### Step 5 — Commit + push
```bash
cd {repo_path}
git add scraped_market_data.json
git commit -m "data: refresh scraped market data $(date -u +%Y-%m-%dT%H:%MZ)"
git push origin main
```

### Step 6 — Report
Send a short summary to the messaging channel: how many tickers succeeded, which failed, and the commit hash.

## Rate limiting & etiquette (MANDATORY)
- Wait **4–6 seconds between pages**. Never hammer a domain.
- Run at most **once or twice per day** per source for the full watchlist.
- This is personal-use data collection. Do not redistribute or resell.
- If a page returns 403 / Cloudflare challenge repeatedly, STOP that source and
  report it — likely the host IP is datacenter-blocked (see Notes).

## Notes / known constraints
- **IP matters most.** barchart/CME/laevitas block datacenter IPs. If Hermes runs on
  a cheap VPS, expect 403s even with a real browser. Run Hermes on a residential
  connection (home machine/mini-PC) OR route the browser through a residential proxy.
- CME QuikStrike uses session tokens; OI extraction may need an extra click into the
  tool and a longer wait. If it fails, fall back to yfinance ETF-proxy OI in the dashboard.
- laevitas is a single-page app — always wait for the chart canvas before scraping.
- Persist a small skill memory of which CSS selectors worked per site; re-check and
  self-update them if a scrape returns empty (sites change layout).

## Success criteria
- `scraped_market_data.json` updated with non-null GEX/walls/OI for the requested tickers.
- File committed and pushed; dashboard's `load_scraped_data()` reads it on next Rebuild.
