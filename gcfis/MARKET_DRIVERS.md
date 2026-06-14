# MARKET DRIVERS — surge-up / surge-down per market (researched June 2026)
Encoded in `gcfis/market_drivers.py` (sign / horizon ST·MT·LT / strength ★1-3 / series-to-wire).
Readings = robust-z of the CHANGE of each series (change-centric). No feed → shown as "wire feed", never fabricated.
Horizons: ST = days–weeks · MT = 1–6 months · LT = 6 months+.

## US EQUITIES
SURGE UP: Fed net-liquidity adds (ST★3) · earnings-revision breadth up (MT★3, institutions forced to chase) · GEX<0 in an uptrend (ST★3 amplifier) · ISM new orders turning (MT★2 leads EPS 1-2Q) · liquidity cycle (LT★2).
SURGE DOWN: HY-OAS widening (ST★3, the risk-off tell) · liquidity drain TGA/QT (ST★3) · real-10Y spike (MT★2 compresses multiples) · crowded long + revisions rolling (MT).
Key: price reacts to data **vs expectation/positioning**, not the absolute print.

## CRYPTO (BTC/ETH)
SURGE UP: spot-ETF inflow streaks (ST★3, most reliable 2026 driver, 0-2wk lead; ETFs ~6%+ of supply) · stablecoin mcap expanding (ST★2) · USD-sourced G4 liquidity accelerating (MT★3, 1-3mo lead — China-sourced M2 has blocked pathways) · dormant LTH supply (LT★2).
SURGE DOWN: ETF outflow streaks · dollar squeeze / DXY up (ST★2) · funding/leverage extremes flushing (ST★2) · real-yield spikes (MT★2).
2026 nuance: BTC decoupled from headline global-M2 (down 22% y/y vs liquidity +12%) — the SOURCE of liquidity matters; LTH avg entry (~$78k) acts as the reversal line.

## FX (DXY-complex / USDIDR)
SURGE (ccy UP): 2Y rate-differential repricing in its favor (ST★3) · real-rate differential (MT★3 anchor) · BoP/current-account improving (MT★2) · terms-of-trade tailwind (MT★2, IDR via CPO/coal/nickel).
SURGE DOWN: dollar-liquidity squeeze (USD up vs everything) · external-funding stress (IDR: Q1-26 BoP −$9.1bn, USDIDR 18,000 = the confidence line) · fiscal credibility erosion (LT★2). PPP = years-horizon mean reversion only (LT★1).

## GOLD
SURGE UP: real 10Y TIPS yield FALLING (ST★3 — THE anchor; ~$40-60/oz per 25bp) · DXY weakening (ST★2) · central-bank buying (MT★3: ~1,000t/yr 2022-25 vs ~200t prior decade; 2026 cooling on the surface — Q1 net reported tiny per JPM vs WGC 244t incl. unreported — EM bid intact) · Fed cut path (MT★2) · fiscal deficits 6-7% GDP / debasement + de-dollarization (LT★2).
SURGE DOWN: real-yield SPIKES (tighter-for-longer repricing = the May-26 dump to ~$4,450) · DELEVERAGING tape — liquidation sells the crowded winner ("sell what you can", gold/silver ratio rising = growth-fear tell) · geopolitical RESOLUTION removing the haven premium · CB-buying pace cooling.
Watch trio: 10Y TIPS real yield · FedWatch cut odds · Hormuz transit volumes.

## OIL (WTI/Brent)
SURGE UP: Hormuz/geopolitical supply shock (ST★3 — ~20% of global flows; 14+ mb/d shut in, >1bn bbl cumulative losses; THE dominant 2026 driver) · inventory DRAWS (ST★3: record global draws, 7 straight US weekly draws) · thinner spare capacity (MT★3: UAE OPEC exit cut buffer 3.8→2.5 mb/d → higher shock beta) · backwardation (MT★2) · demand growth ~1.4 mb/d (MT★2).
SURGE DOWN: Hormuz reopening (high-$80s Brent pricing on resolution vs $138 tail if fully shut) · OPEC+ supply adds · demand destruction · post-conflict surplus (EIA: builds 1.9-3.0 mb/d once flows restore → $70s-60s path 2027).

## IHSG (IDX)
SURGE UP: foreign net-flow persistence (ST★3 — THE swing factor; MSCI passive can move composite 1-2%/day) · rupiah stabilizing/strengthening (ST★3) · BI hike defending IDR (ST★2 — mechanically lifts index: banks ≈51% weight) · ratings outlook improving (MT★3) · commodity terms-of-trade CPO/coal/nickel (MT★2) · policy credibility returning (LT★2).
SURGE DOWN: foreign sell streaks (YTD-26 ≈ −Rp49T, ~2024's entire accumulation reversed) · rupiah breakdown loop (Rp18,000 record-weak = confidence test) · dollar squeeze/EM outflow · ratings-downgrade risk (rumor alone cratered the tape May-26) · BoP deficit (Q1 −$9.1bn).
Live proof of the matrix: BI surprise hike to 5.50% (Jun 9-10) → IHSG +7.5% snap rally + rupiah ~17,900 — exactly the ST drivers firing.

## CROSS-MARKET OVERLAY (overrides everything)
DELEVERAGING regime (cross_asset.py): margin-call tape sells ALL crowded winners regardless of their own drivers — gold down despite yields down, defer new longs. Driver signs are regime-CONDITIONAL, not constants.
