"""settings.py — ALL parameters. Zero hardcoded thresholds in engines.

Hedgeye GIP: 30 monthly data points, 90 quarterly.
Everything flows from this file.

v3.1 Changes (surgical, preserving original engine constants):
- QUAD_ASSET_PERFORMANCE: rewritten to match Hedgeye ETF Pro Plus actual tickers
- Bitcoin: Q1/Q2/Q3 = IBIT long when Bullish TREND. Q4 = exit.
  Keith May 6 2026: "Bitcoin Is Back In The Book." Rule: "Any quad other than Q4,
  bitcoin should be your biggest digital asset position." Signal-dependent.
  DXY correlation -0.83 (15D): bearish USD = bullish BTC mechanics.
- TICKER_SECTOR + MARKET_CLASSIFICATION: added all missing Hedgeye ETFs
- BOTTLENECK_PROFILES: added housing, oil_services, steel, infrastructure, precious_metals_miners
- COMMODITIES: added SLX, GRID, GDX, GDXJ, SIL, SILJ, OIH, XOP
- DXY_CORRELATION_ASSETS: new — tracks Keith's key $USD correlations
- All original engine constants preserved: POLICY_WEIGHT_*, ISM_NEUTRAL, RR_*, COUNTRY_UNIVERSE format
"""
from __future__ import annotations
import os

LIVE_FETCH_ENABLED = True
FRED_CACHE_TTL_SECONDS = 3600

# ── API ───────────────────────────────────────────────────────────────────────
FRED_API_KEY: str = os.environ.get("FRED_API_KEY", "")

# ── Cache / storage ───────────────────────────────────────────────────────────
PRICE_HISTORY_DAYS: int = 756
FRED_HISTORY_MONTHS: int = 36
CACHE_TTL_SECONDS: int = 3600
SNAPSHOT_PATH: str = ".cache/snapshot.pkl"

# ── FRED series ───────────────────────────────────────────────────────────────
FRED_GROWTH_SERIES = {
    "INDPRO":  "Industrial Production",
    "RSAFS":   "Retail Sales",
    "PAYEMS":  "Nonfarm Payrolls",
    "UNRATE":  "Unemployment",
    "ICSA":    "Initial Claims",
    "HOUST":   "Housing Starts",
    "ISMNO":   "ISM Manufacturing"}
FRED_INFLATION_SERIES = {
    "CPIAUCSL": "CPI",
    "CPILFESL": "Core CPI",
    "PPIACO":   "PPI",
    "T5YIE":    "5yr Breakeven",
    "T10YIE":   "10yr Breakeven",
    "DFII10":   "10yr TIPS"}
FRED_POLICY_SERIES = {
    "FEDFUNDS": "Fed Funds",
    "DFF":      "Daily Fed Funds",
    "M2SL":     "M2 Money Supply"}

# ── GIP Weights (Hedgeye: RoC/momentum dominant) ─────────────────────────────
GROWTH_LEVEL_WEIGHTS = {
    "indpro_yoy": 0.22, "retail_yoy": 0.20, "payrolls_yoy": 0.18,
    "housing_yoy": 0.12, "ism_norm": 0.15, "unrate_inv": 0.07, "claims_inv": 0.06}
GROWTH_MOM_WEIGHTS = {
    "indpro_roc": 0.28, "retail_roc": 0.22, "payrolls_roc": 0.18,
    "ism_delta": 0.14, "unrate_delta": 0.10, "claims_delta": 0.08}
INFLATION_LEVEL_WEIGHTS = {
    "cpi_yoy": 0.28, "core_cpi_yoy": 0.24, "breakeven_5y": 0.18,
    "ppi_yoy": 0.14, "oil_3m": 0.10, "gold_3m": 0.06}
INFLATION_MOM_WEIGHTS = {
    "cpi_roc": 0.30, "core_cpi_roc": 0.26, "breakeven_delta": 0.18,
    "oil_1m": 0.14, "dxy_inv_1m": 0.12}
# PRESERVED from original — inflation-dominant for Q3 accuracy
STRUCTURAL_WEIGHTS = {
    "growth_level": 0.15,
    "growth_momentum": 0.30,
    "inflation_level": 0.20,
    "inflation_momentum": 0.35}
# PRESERVED from original — but inflation_level increased from 0.10 → 0.20
# Reason: original 0.10 causes Monthly to compute Q1 when CPI is still 2.5%+ YoY
# Even if inflation MOMENTUM is cooling, the LEVEL is still hot → Q2 not Q1
# Hedgeye May 2026 manual call = Monthly Q2. Model was computing Q1. Fix: raise inflation_level.
MONTHLY_WEIGHTS = {
    "growth_level": 0.10,
    "growth_momentum": 0.40,
    "inflation_level": 0.35,   # v9: naik dari 0.30 → level lebih dominan
    "inflation_momentum": 0.15, # v9: turun dari 0.20 → momentum lebih kecil
}
# ── CRITICAL: These were missing — caused ImportError in gip_engine.py ────────
POLICY_WEIGHT_STRUCTURAL: float = 0.12
POLICY_WEIGHT_MONTHLY: float    = 0.10
ISM_NEUTRAL: float              = 50.0

# ── Risk Range constants (PRESERVED from original) ────────────────────────────
RR_TRADE_LOOKBACK: int   = 15
RR_TREND_LOOKBACK: int   = 63
RR_TAIL_LOOKBACK: int    = 252
RR_TRADE_SIGMA: float    = 1.5
RR_TREND_SIGMA: float    = 2.0
RR_TAIL_SIGMA: float     = 2.8
RR_HURST_SCALE: float    = 1.0

# ── US Sectors & Factors ──────────────────────────────────────────────────────
US_SECTORS: dict = {
    "XLK":"Technology", "XLY":"Consumer Disc", "XLI":"Industrials", "XLF":"Financials",
    "XLE":"Energy", "XLB":"Materials", "XLV":"Healthcare", "XLP":"Consumer Staples",
    "XLU":"Utilities", "XLRE":"Real Estate", "XLC":"Communication"}
US_FACTORS: dict = {
    "SPY":"S&P500", "QQQ":"Nasdaq", "IWM":"Russell 2000", "DIA":"Dow Jones",
    "VTV":"Value", "VUG":"Growth", "USMV":"Min Vol", "HDV":"High Div",
    "RSP":"Equal Weight", "MTUM":"Momentum", "QUAL":"Quality", "SIZE":"Small-Mid"}

# ── Forex ─────────────────────────────────────────────────────────────────────
FOREX_PAIRS: dict = {
    "EURUSD=X":"EUR/USD", "GBPUSD=X":"GBP/USD", "USDJPY=X":"USD/JPY",
    "USDCHF=X":"USD/CHF", "USDCAD=X":"USD/CAD", "AUDUSD=X":"AUD/USD",
    "NZDUSD=X":"NZD/USD", "USDSEK=X":"USD/SEK", "USDNOK=X":"USD/NOK",
    "USDMXN=X":"USD/MXN", "USDBRL=X":"USD/BRL", "USDTRY=X":"USD/TRY",
    "USDZAR=X":"USD/ZAR", "USDIDR=X":"USD/IDR", "USDSGD=X":"USD/SGD",
    "USDINR=X":"USD/INR", "USDCNY=X":"USD/CNY", "USDKRW=X":"USD/KRW",
    "USDTHB=X":"USD/THB", "USDPHP=X":"USD/PHP", "USDMYR=X":"USD/MYR",
    "EURJPY=X":"EUR/JPY", "GBPJPY=X":"GBP/JPY", "AUDNZD=X":"AUD/NZD",
    "CADUSD=X":"CAD/USD (Oil proxy)", "DX-Y.NYB":"USD Index (DXY)"}

# ── Commodities ───────────────────────────────────────────────────────────────
COMMODITIES: dict = {
    # Precious Metals — Hedgeye core (SLV +143% since May 2025)
    "GC=F":"Gold Futures", "SI=F":"Silver Futures",
    "PL=F":"Platinum Futures", "PA=F":"Palladium Futures",
    "GLD":"Gold ETF", "SLV":"Silver ETF", "PPLT":"Platinum ETF",
    "GDX":"Gold Miners ETF", "GDXJ":"Junior Gold Miners ETF",
    "SIL":"Global Silver Miners ETF", "SILJ":"Junior Silver Miners ETF",
    "DUST":"Gold Miners Inverse 2x",
    # Energy (Hedgeye ETF Pro Plus confirmed)
    "CL=F":"WTI Crude Oil", "BZ=F":"Brent Crude", "NG=F":"Natural Gas",
    "RB=F":"RBOB Gasoline", "HO=F":"Heating Oil",
    "USO":"Oil ETF", "UNG":"Nat Gas ETF", "BNO":"Brent Oil ETF",
    "OIH":"Oil Services ETF", "XOP":"Oil & Gas E&P ETF",
    # Industrial Metals
    "HG=F":"Copper","CPER":"Copper ETF", "JJC":"iPath Copper",
    "SLX":"Steel ETF",
    # Infrastructure
    "GRID":"Smart Grid ETF",
    # Agriculture
    "ZW=F":"Wheat", "ZC=F":"Corn", "ZS=F":"Soybeans", "ZO=F":"Oats",
    "KC=F":"Coffee", "SB=F":"Sugar", "CT=F":"Cotton", "CC=F":"Cocoa",
    "DBA":"Agriculture ETF", "WEAT":"Wheat ETF", "CORN":"Corn ETF",# Nuclear
    "URA":"Uranium ETF", "CCJ":"Cameco"}

# ── Crypto ────────────────────────────────────────────────────────────────────
CRYPTO: dict = {
    "BTC-USD":"Bitcoin", "ETH-USD":"Ethereum", "BNB-USD":"BNB", "SOL-USD":"Solana",
    "XRP-USD":"Ripple", "ADA-USD":"Cardano", "AVAX-USD":"Avalanche",
    "DOT-USD":"Polkadot", "MATIC-USD":"Polygon", "LINK-USD":"Chainlink",
    "DOGE-USD":"Dogecoin", "LTC-USD":"Litecoin", "ATOM-USD":"Cosmos",
    "NEAR-USD":"NEAR", "APT-USD":"Aptos", "ARB-USD":"Arbitrum",
    "OP-USD":"Optimism", "SUI20947-USD":"Sui", "INJ-USD":"Injective", "SEI-USD":"SEI",
    "AAVE-USD":"Aave", "UNI7083-USD":"Uniswap", "MKR-USD":"Maker",
    "LDO-USD":"Lido DAO", "CRV-USD":"Curve", "COMP5692-USD":"Compound",
    "FET-USD":"Fetch.ai", "TAO22974-USD":"TAO/Bittensor", "RNDR-USD":"Render",
    "GRT6719-USD":"The Graph", "OCEAN-USD":"Ocean Protocol", "HNT-USD":"Helium",
    "ONDO-USD":"Ondo Finance", "POLYX-USD":"Polymesh",
    "TON11419-USD":"Toncoin", "TIA22861-USD":"Celestia", "PYTH-USD":"Pyth",
    "WIF-USD":"dogwifhat", "PEPE24478-USD":"Pepe", "BONK-USD":"Bonk", "FLOKI-USD":"Floki",
    # US-listed ETFs & proxies
    "IBIT":"iShares Bitcoin ETF", "FBTC":"Fidelity Bitcoin ETF", "ETHA":"iShares Ethereum ETF",
    "MSTR":"MicroStrategy",
    # Crypto equity proxies (direction = BTC TREND signal dependent)
    "MSTY":"YieldMax MSTR Option Income ETF",
    "BITS":"Global X Blockchain ETF",
    "BLOK":"Amplify Blockchain ETF",
    "WGMI":"Valkyrie Bitcoin Miners ETF"}

# ── IHSG / Indonesia ──────────────────────────────────────────────────────────
IHSG_UNIVERSE: dict = {
    "^JKSE":"IHSG Index", "EIDO":"Indonesia ETF (USD)",
    "BBCA.JK":"BCA", "BBRI.JK":"BRI", "BMRI.JK":"Mandiri", "BBNI.JK":"BNI",
    "BRIS.JK":"BSI", "BBTN.JK":"BTN", "BNGA.JK":"CIMB Niaga",
    "MEGA.JK":"Bank Mega", "NISP.JK":"OCBC",
    "ADRO.JK":"Adaro", "PTBA.JK":"Bukit Asam", "ITMG.JK":"ITMG",
    "HRUM.JK":"Harum", "INDY.JK":"Indika", "AADI.JK":"Aadi",
    "BUMI.JK":"Bumi Resources", "MEDC.JK":"Medco",
    "PGEO.JK":"Pertamina Geothermal", "AKRA.JK":"AKR", "UNTR.JK":"United Tractors",
    "INCO.JK":"Vale Indonesia", "MDKA.JK":"Merdeka", "ANTM.JK":"Antam",
    "TINS.JK":"Timah", "BRMS.JK":"Bumi Resources Min", "NCKL.JK":"Trimegah Bangun",
    "TLKM.JK":"Telkom", "EXCL.JK":"XL Axiata", "ISAT.JK":"Indosat",
    "JSMR.JK":"Jasa Marga", "PGAS.JK":"PGN",
    "WIKA.JK":"Wijaya Karya", "PTPP.JK":"PP Persero",
    "ICBP.JK":"Indofood CBP", "INDF.JK":"Indofood", "MYOR.JK":"Mayora",
    "KLBF.JK":"Kalbe", "SIDO.JK":"Sido Muncul",
    "ULTJ.JK":"Ultra Jaya", "CMRY.JK":"Cisarua",
    "AMRT.JK":"Alfamart", "ACES.JK":"Ace Hardware",
    "MAPI.JK":"Mitra Adiperkasa", "ERAA.JK":"Erajaya",
    "ASII.JK":"Astra", "CPIN.JK":"Charoen Pokphand", "JPFA.JK":"Japfa",
    "CTRA.JK":"Ciputra", "BSDE.JK":"BSD City",
    "PWON.JK":"Pakuwon", "SMRA.JK":"Summarecon",
    "HEAL.JK":"Hermina", "MIKA.JK":"Mika", "SILO.JK":"Siloam",
    "LSIP.JK":"London Sumatra", "AALI.JK":"Astra Agro",
    "SSMS.JK":"Sawit Sumbermas", "INKP.JK":"Indah Kiat",
    "TKIM.JK":"Tjiwi Kimia", "ESSA.JK":"Surya Esa",
    "WINS.JK":"Wintermar OSV", "LEAD.JK":"Logindo OSV",
    "SHIP.JK":"Sillo FPSO", "ELSA.JK":"Elnusa hulu",
    "SOCI.JK":"SOCI Mas tanker", "BULL.JK":"Bull Armada",
    "SMDR.JK":"Samudera Indo", "TMAS.JK":"Temas container",
    "DSNG.JK":"Dharma Satya", "TAPG.JK":"Triputra Agro",
    "SGRO.JK":"Sampoerna Agro",
    "BEST.JK":"Bekasi Fajar", "KIJA.JK":"Jababeka", "DMAS.JK":"Puradelta"}

# ── Bonds ─────────────────────────────────────────────────────────────────────
BONDS: dict = {
    "TLT":"20yr UST", "IEF":"7-10yr UST", "SHY":"1-3yr UST", "GOVT":"All UST",
    "TIP":"TIPS (inflation-linked)", "LTPZ":"Long TIPS",
    "LQD":"IG Corporate", "HYG":"HY Corporate", "JNK":"HY Bonds",
    "EMB":"EM USD Bonds", "PCY":"EM Local Bonds",
    "BND":"Total Bond", "AGG":"US Agg Bond"}

# ── Core macro proxy tickers ──────────────────────────────────────────────────
MACRO_PROXIES: dict = {
    "SPY":"S&P500", "QQQ":"Nasdaq", "IWM":"Russell 2k", "DIA":"Dow",
    "XLI":"Industrials", "XLY":"Consumer Disc", "XHB":"Homebuilders",
    "UUP":"USD ETF", "GLD":"Gold", "TLT":"Long Bond",
    "CL=F":"WTI Oil", "GC=F":"Gold Futures"}

# ── DXY Correlation Assets (Keith McCullough's key signal table) ──────────────
# Source: Keith tweets — "Key $USD Correlations* 15D"
# BTC/USD TRADE correlation = -0.90 (Apr 13); -0.83 (May 6)
# When DXY Bearish TREND → BTC Bullish TREND (inverse relationship)
# This is how Keith determines BTC long/short signal
DXY_CORRELATION_ASSETS: dict = {
    "SPX":        "SPY",      # -0.66 (15D)
    "BRENT Oil":  "BZ=F",     # +0.65 (15D) — oil positively correlated with weak USD
    "CRB Index":  "DBA",      # +0.59 (commodity basket proxy)
    "GOLD":       "GLD",      # +0.05 (15D) — relatively uncorrelated short-term
    "Bitcoin":    "BTC-USD",  # -0.83 (15D) — strongest inverse correlation
}
DXY_CORRELATION_WINDOW: int = 15  # Keith uses 15-day rolling correlation

# ══════════════════════════════════════════════════════════════════════════════
# QUAD ASSET PERFORMANCE — HEDGEYE ACTUAL (ETF Pro Plus aligned, May 2026)
# ══════════════════════════════════════════════════════════════════════════════
QUAD_ASSET_PERFORMANCE: dict = {

    # Q1: GOLDILOCKS — Growth↑ Inflation↓
    "Q1": {
        "best": [
            "XLK",   # Tech — #1 in Q1
            "XLY",   # Consumer Disc
            "XLI",   # Industrials
            "IWM",   # Small Caps (breadth confirmation)
            "QQQ",   # Nasdaq
            "RSP",   # Equal Weight
            "SLV",   # Silver — works in early Q1
            "GLD",   # Gold
            "JPXN",  # Japan — Goldilocks + Yen dynamics
            "EIS",   # Israel — geopolitical discount
            "GLIN",  # India — growth EM
            "ITA",   # Defense — secular
            "IBIT",  # Bitcoin — "Any quad other than Q4, biggest digital asset position"
        ],
        "worst": [
            "GLD",   # fades as growth accelerates
            "XLU",   # Utilities — bond proxy lags
            "XLP",   # Consumer Staples — defensive lags
            "TLT",   # Long Bonds — yields rise
            "XLV",   # Healthcare — defensive lags
        ],
        "style": "Growth, Small Cap, High Beta, Quality. Equal-weight RSP must confirm.",
        "fx": "USD moderate; AUD/NZD/CAD supportive; EM FX relief; JPY could strengthen.",
        "bonds": "Bearish — yields rise with growth. Short duration bias.",
        "sectors_overweight": ["XLK","XLY","XLI","XLF","IWM"],
        "sectors_underweight": ["XLU","XLP","XLV","TLT"],
        "monthly_adds": ["JPXN","EIS","ITA","GLIN","RSP"],
        "hedge": "BTAL (anti-beta).",
        "note": "Q1 = max risk-on. BTC works (Bullish TREND). Equal-weight breadth = confirmation signal."},

    # Q2: REFLATION / KNIFE FIGHTS — Growth↑ Inflation↑
    # KEY: Keith May 6 2026 — "Bitcoin Is Back In The Book" — LONG IBIT
    # BTC/USD 15D correlation = -0.83. USD Bearish TREND = BTC Bullish TREND.
    # MSTY/BITS/BLOK/WGMI = SHORT only when BTC Bearish TREND (Crash Mode). Covered May 2026.
    "Q2": {
        "best": [
            # Energy Offense
            "XLE",   # Energy Sector — core Q2 long
            "OIH",   # Oil Services — leverage to commodity prices
            "BNO",   # Brent Oil ETF
            "XOP",   # Oil & Gas E&P
            "DAR",   # Darling Ingredients — biofuel (added April 2026)
            "MTDR",  # Matador Resources — oil E&P (added April 2026)
            # Industrials
            "XLI",   # Top US equity long. +11.4% since Dec add.
            "XLB",   # Materials — commodity offense
            "CPER",  # Copper ETF
            "SLX",   # Steel ETF
            # Precious Metals (work in Q2 reflation)
            "SLV",   # Silver — +143% since May 2025. Monster performer.
            "GLD",   # Gold
            "PPLT",  # Platinum
            "GDX",   # Gold Miners
            "GDXJ",  # Junior Gold Miners
            # Housing (Long Duration Equity Proxy)
            "ITB",   # Home Construction — rate sensitivity play
            # Fixed Income (nuanced — add when 2s/10s/30s ALL bearish TREND)
            "TLT",   # ADDED when yield curve signals bearish TREND
            "LQD",   # IG Corporate
            # International (ETF Pro Plus confirmed)
            "JPXN",  # Japan — Goldilocks FX. +10.3% 1M, +37% Q1 2026.
            "EIS",   # Israel — geopolitical discount. +21.8% since add.
            "TUR",   # Turkey — Bullish TREND. +10.3% since add.
            "NORW",  # Norway — commodity FX + oil
            "EWZ",   # Brazil — commodity EM
            "EWW",   # Mexico — commodity FX + nearshoring
            "EIDO",  # Indonesia — commodity EM
            "GLIN",  # India — growth EM
            # Bitcoin (SIGNAL-DEPENDENT via DXY correlation)
            "IBIT",  # BTC via ETF — LONG when BTC Bullish TREND (confirmed May 6 2026)
                     # DXY Bearish TREND (-0.83 corr) = BTC Bullish TREND thesis
        ],
        "worst": [
            "XLU",   # Utilities — bond proxy, inflation headwind
            "XLP",   # Consumer Staples — defensive lags
            "HYG",   # High Yield — spreads widen
            "IWM",   # Small Caps — reduced to minimum
            # Crypto equity shorts (ONLY when BTC Bearish TREND — covered May 2026)
        ],
        "style": "Value, Cyclicals, Commodity, High Beta. International + Energy offense.",
        "fx": "Commodity FX: AUD, CAD, NOK, MXN, BRL. USD mixed (bearish TREND = BTC bid). IDR pressure.",
        "bonds": "Nuanced: short duration default. ADD TLT only when 2s/10s/30s all bearish TREND.",
        "sectors_overweight": ["XLI","XLE","XLB","ITB","OIH"],
        "sectors_underweight": ["XLU","XLP","HYG","IWM"],
        "monthly_adds": ["OIH","BNO","XOP","ITB","TLT","JPXN","EIS","TUR","DAR","MTDR","SLV","IBIT"],
        "monthly_removes": ["TXG","MPLX","GEL"],
        "hedge": "BTAL (anti-beta). DUST if metals overextended.",
        "sizing_note": "Start min. Scale gradually. Max 3% per name. IBIT = max 3%. IWM = minimum only.",
        "note": "Q2 KNIFE FIGHTS. BTC = LONG (Bullish TREND, DXY Bearish TREND). DXY/BTC corr -0.83."},

    # Q3: STAGFLATION — Growth↓ Inflation↑
    "Q3": {
        "best": [
            "SLV",   # Silver — #1. +143% since May 2025. Q3 safe haven + industrial.
            "GLD",   # Gold — McCullough: "single best asset allocation in Q3"
            "PPLT",  # Platinum
            "GDX",   # Gold Miners
            "GDXJ",  # Junior Gold Miners
            "SIL",   # Silver Miners
            "SILJ",  # Junior Silver Miners
            "XLV",   # Healthcare — Q3 best sector
            "XLP",   # Consumer Staples
            "XLU",   # Utilities
            "TLT",   # Long Duration — flight to quality
            "IEF",   # 7-10yr UST
            "LQD",   # IG Corporate — quality bid
            "ITA",   # Aerospace & Defense — secular
            "GRID",  # Smart Grid — secular defensive
            "EIDO",  # Indonesia — coal/nickel commodity EM
            "NORW",  # Norway — oil commodity EM
            "EWZ",   # Brazil — commodity EM
        ],
        "worst": [
            "XLK",   # Tech — #1 short. Stagflation destroys multiples.
            "MAGS",  # Mag7 proxy — concentrated short
            "XLY",   # Consumer Disc
            "IWM",   # Small Caps — credit sensitive
            "HYG",   # High Yield — spreads blow out
            "QQQ",   # Nasdaq
            "XLF",   # Financials
        ],
        "style": "Low Beta, Dividend Yield, Defensive Quality. Gold first, Silver second.",
        "fx": "USD bearish TREND (confirmed McCullough Apr 2026). Commodity FX mixed. EM: commodity exporters only.",
        "bonds": "TLT core hold. Flight to quality. Watch breakevens for Q4 signal.",
        "sectors_overweight": ["XLV","XLP","XLU","GLD","SLV","ITA"],
        "sectors_underweight": ["XLK","XLY","IWM","XLF","HYG"],
        "monthly_adds": ["SLV","GDX","GDXJ","SIL","ITA","GRID","TLT"],
        "hedge": "BTAL (anti-beta). DUST as metals volatility hedge.",
        "note": "CURRENT STRUCTURAL QUAD. SLV +143% — do not underweight. BTC: signal-dependent (exit if Bearish TREND). Monthly Q2 overlay adds tactical energy offense."},

    # Q4: DEFLATION — Growth↓ Inflation↓
    "Q4": {
        "best": [
            "TLT",   # Long Duration — maximum long
            "IEF",   # 7-10yr UST
            "GLD",   # Gold — deflation safe haven
            "SLV",   # Silver
            "XLV",   # Healthcare
            "XLP",   # Consumer Staples
            "XLU",   # Utilities
            "UUP",   # USD — flight to safety
            "BTAL",  # Anti-Beta — maximum hedge
        ],
        "worst": [
            "XLK",   # Tech — multiple compression
            "XLE",   # Energy — demand collapse
            "XLY",   # Consumer Disc
            "HYG",   # HY Credit — stress
            "IWM",   # Small Caps — highest credit risk
            "BTC-USD", # Bitcoin — Q4 is the exception. Keith: "Any quad OTHER than Q4."
            "IBIT",  # Bitcoin ETF — EXIT in Q4
        ],
        "style": "Min Volatility, Low Beta, Dividend, Quality. Capital preservation.",
        "fx": "USD very bullish. Commodity FX crushed. EM brutal.",
        "bonds": "Very bullish — deflationary collapse. Max long TLT/IEF.",
        "sectors_overweight": ["XLV","XLP","XLU","TLT","GLD"],
        "sectors_underweight": ["XLK","XLE","HYG","IWM","XLF"],
        "monthly_adds": ["TLT","IEF","GLD","BTAL","USMV"],
        "hedge": "BTAL maximum. DUST.",
        "note": "Q4 = most dangerous. ONLY quad where Bitcoin = EXIT. Cash + Bonds + Gold + Utilities."}}

# ── Bottleneck Profiles ───────────────────────────────────────────────────────
BOTTLENECK_PROFILES: dict = {
    "ai_compute":             {"constraint":0.90,"Q1":0.85,"Q2":0.70,"Q3":0.50,"Q4":0.30},
    "ai_networking":          {"constraint":0.85,"Q1":0.80,"Q2":0.75,"Q3":0.55,"Q4":0.35},
    "ai_optics":              {"constraint":0.92,"Q1":0.78,"Q2":0.72,"Q3":0.62,"Q4":0.40},
    "ai_power":               {"constraint":0.87,"Q1":0.70,"Q2":0.75,"Q3":0.65,"Q4":0.50},
    "ai_power_infra":         {"constraint":0.85,"Q1":0.65,"Q2":0.70,"Q3":0.70,"Q4":0.55},
    "ai_packaging":           {"constraint":0.80,"Q1":0.75,"Q2":0.70,"Q3":0.55,"Q4":0.35},
    "healthcare_eq":          {"constraint":0.80,"Q1":0.65,"Q2":0.55,"Q3":0.85,"Q4":0.80},
    "pharma":                 {"constraint":0.82,"Q1":0.60,"Q2":0.50,"Q3":0.80,"Q4":0.75},
    "defense":                {"constraint":0.82,"Q1":0.55,"Q2":0.65,"Q3":0.78,"Q4":0.62},
    "utilities":              {"constraint":0.75,"Q1":0.50,"Q2":0.45,"Q3":0.82,"Q4":0.86},
    "water":                  {"constraint":0.80,"Q1":0.55,"Q2":0.50,"Q3":0.85,"Q4":0.86},
    "precious_metals":        {"constraint":0.72,"Q1":0.70,"Q2":0.68,"Q3":0.88,"Q4":0.82},
    "precious_metals_miners": {"constraint":0.80,"Q1":0.65,"Q2":0.70,"Q3":0.85,"Q4":0.78},
    "energy_infra":           {"constraint":0.75,"Q1":0.55,"Q2":0.88,"Q3":0.75,"Q4":0.30},
    "oil_services":           {"constraint":0.78,"Q1":0.60,"Q2":0.90,"Q3":0.65,"Q4":0.25},
    "uranium":                {"constraint":0.85,"Q1":0.70,"Q2":0.80,"Q3":0.65,"Q4":0.50},
    "steel":                  {"constraint":0.70,"Q1":0.65,"Q2":0.82,"Q3":0.55,"Q4":0.25},
    "coal":                   {"constraint":0.60,"Q1":0.50,"Q2":0.80,"Q3":0.55,"Q4":0.25},
    "nickel":                 {"constraint":0.70,"Q1":0.60,"Q2":0.82,"Q3":0.55,"Q4":0.30},
    "cpo_palm":               {"constraint":0.65,"Q1":0.55,"Q2":0.75,"Q3":0.60,"Q4":0.30},
    "housing":                {"constraint":0.68,"Q1":0.72,"Q2":0.78,"Q3":0.45,"Q4":0.35},
    "infrastructure":         {"constraint":0.75,"Q1":0.70,"Q2":0.72,"Q3":0.68,"Q4":0.55},
    "staples":                {"constraint":0.55,"Q1":0.45,"Q2":0.40,"Q3":0.78,"Q4":0.82},
    "sic_gan":                {"constraint":0.88,"Q1":0.70,"Q2":0.75,"Q3":0.65,"Q4":0.45},
    "osv_offshore":           {"constraint":0.82,"Q1":0.55,"Q2":0.80,"Q3":0.72,"Q4":0.30},
    "tanker_shipping":        {"constraint":0.75,"Q1":0.50,"Q2":0.82,"Q3":0.65,"Q4":0.25},
    "depin_ai":               {"constraint":0.70,"Q1":0.75,"Q2":0.65,"Q3":0.55,"Q4":0.30},
    "generic":                {"constraint":0.50,"Q1":0.50,"Q2":0.50,"Q3":0.50,"Q4":0.50}}

# ── Ticker → Sector (used by BottleneckEngine + Leaderboard) ─────────────────
TICKER_SECTOR: dict = {
    # US Sectors/Factors
    "SPY":"generic","QQQ":"ai_compute","IWM":"generic","DIA":"generic","RSP":"generic",
    "XLK":"ai_compute","XLY":"generic","XLI":"energy_infra","XLF":"generic",
    "XLE":"energy_infra","XLB":"generic","XLV":"healthcare_eq","XLP":"staples",
    "XLU":"utilities","XLRE":"housing","XLC":"generic","XHB":"housing",
    "VTV":"generic","VUG":"generic","USMV":"generic","HDV":"generic",
    "MTUM":"generic","QUAL":"generic","SIZE":"generic",
    # Hedgeye ETF Pro Plus confirmed tickers
    "OIH":"oil_services","BNO":"energy_infra","XOP":"energy_infra",
    "ITB":"housing","ITA":"defense","BTAL":"generic","DUST":"precious_metals",
    "JPXN":"generic","EIS":"generic","TUR":"generic","NORW":"generic",
    "EWZ":"generic","EWW":"generic","EIDO":"generic","GLIN":"generic",
    "UAE":"generic","INDA":"generic","EWT":"generic","EWS":"generic",
    "GLD":"precious_metals","SLV":"precious_metals","PPLT":"precious_metals",
    "GDX":"precious_metals_miners","GDXJ":"precious_metals_miners",
    "SIL":"precious_metals_miners","SILJ":"precious_metals_miners",
    "AEM":"precious_metals_miners","WPM":"precious_metals_miners",
    "FNV":"precious_metals_miners","RGLD":"precious_metals_miners",
    "SLX":"steel","CPER":"generic","GRID":"infrastructure",
    "DAR":"energy_infra","MTDR":"energy_infra",
    "ULS":"generic","BRBR":"staples",
    "MSTY":"generic","BITS":"generic","BLOK":"generic","WGMI":"generic","MAGS":"ai_compute",
    "IBIT":"generic","FBTC":"generic","ETHA":"generic",
    # AI/Tech
    "NVDA":"ai_compute","AMD":"ai_compute","AVGO":"ai_compute",
    "TSM":"ai_compute","INTC":"ai_compute","ALAB":"ai_compute",
    "CRDO":"ai_networking","MRVL":"ai_compute","ANET":"ai_networking",
    "SMCI":"ai_compute","LITE":"ai_optics","COHR":"ai_optics",
    "CIEN":"ai_optics","POET":"ai_optics","VIAV":"ai_optics","GLW":"ai_optics",
    "ON":"sic_gan","WOLF":"sic_gan","STM":"sic_gan","MPWR":"ai_power",
    "VST":"ai_power_infra","CEG":"ai_power_infra","ETN":"ai_power_infra",
    "NRG":"ai_power_infra","GEV":"ai_power_infra","EMR":"ai_power_infra","VRT":"ai_power_infra",
    "AMKR":"ai_packaging","ASX":"ai_packaging","TSEM":"ai_packaging",
    "MKSI":"ai_optics","RMBS":"ai_compute","QCOM":"ai_compute","MU":"ai_compute",
    "APH":"ai_networking","MCHP":"ai_compute","ENTG":"ai_compute",
    "KLIC":"ai_packaging","UCTT":"ai_packaging","CAMT":"ai_compute",
    # Defense
    "PLTR":"defense","AXON":"defense","SAIC":"defense","BWXT":"defense",
    "LMT":"defense","RTX":"defense","NOC":"defense","GD":"defense","KTOS":"defense",
    "HII":"defense","LDOS":"defense","BAH":"defense",
    # Healthcare
    "LLY":"pharma","MRNA":"pharma","REGN":"pharma","BMY":"pharma","PFE":"pharma",
    "JNJ":"pharma","ABBV":"pharma","MRK":"pharma","AZN":"pharma","NVO":"pharma",
    "ISRG":"healthcare_eq","ABT":"healthcare_eq","BSX":"healthcare_eq",
    "MDT":"healthcare_eq","EW":"healthcare_eq","SYK":"healthcare_eq",
    "ZBH":"healthcare_eq","DXCM":"healthcare_eq","PODD":"healthcare_eq","RMD":"healthcare_eq",
    # Utilities
    "NEE":"utilities","DUK":"utilities","D":"utilities","SO":"utilities",
    "AEP":"utilities","EXC":"utilities","SRE":"utilities","PEG":"utilities","ED":"utilities",
    "AWK":"water","WTRG":"water","CWT":"water",
    # Staples
    "PG":"staples","KO":"staples","PEP":"staples","WMT":"staples","COST":"staples",
    "PM":"staples","MO":"staples","GIS":"staples","K":"staples","HSY":"staples","MDLZ":"staples",
    # Industrials
    "HUBB":"infrastructure","NVT":"ai_power_infra","AYI":"infrastructure",
    "AMETEK":"infrastructure","ROP":"infrastructure",
    # Uranium
    "URA":"uranium","CCJ":"uranium","NXE":"uranium","UUUU":"uranium",
    "LEU":"uranium","DNN":"uranium","URG":"uranium",
    # Energy
    "XOM":"energy_infra","CVX":"energy_infra","COP":"energy_infra","SLB":"oil_services",
    "HAL":"oil_services","BKR":"oil_services",
    "OXY":"energy_infra","MPC":"energy_infra","VLO":"energy_infra","PSX":"energy_infra","KMI":"energy_infra",
    # Financials
    "JPM":"generic","BAC":"generic","GS":"generic","MS":"generic",
    "BLK":"generic","V":"generic","MA":"generic","SCHW":"generic",
    # Precious metals stocks
    "NEM":"precious_metals_miners","GFI":"precious_metals_miners",
    # Crypto
    "TAO22974-USD":"depin_ai","RNDR-USD":"depin_ai",
    "FET-USD":"depin_ai","OCEAN-USD":"depin_ai","GRT6719-USD":"depin_ai","HNT-USD":"depin_ai",
    "MSTR":"generic",
    # Forex
    "EURUSD=X":"generic","GBPUSD=X":"generic","USDJPY=X":"generic","USDCHF=X":"generic",
    "USDCAD=X":"generic","AUDUSD=X":"generic","NZDUSD=X":"generic","USDSEK=X":"generic","USDNOK=X":"generic",
    "USDMXN=X":"generic","USDBRL=X":"generic","USDTRY=X":"generic","USDZAR=X":"generic",
    "USDIDR=X":"generic","USDSGD=X":"generic","USDINR=X":"generic","USDCNY=X":"generic","USDKRW=X":"generic",
    "USDTHB=X":"generic","USDPHP=X":"generic","USDMYR=X":"generic",
    "EURJPY=X":"generic","GBPJPY=X":"generic","AUDNZD=X":"generic","CADUSD=X":"generic",
    "DX-Y.NYB":"generic",
    # Commodities
    "GC=F":"precious_metals","SI=F":"precious_metals","PL=F":"precious_metals","PA=F":"precious_metals",
    "CL=F":"energy_infra","BZ=F":"energy_infra","NG=F":"energy_infra",
    "RB=F":"energy_infra","HO=F":"energy_infra",
    "USO":"energy_infra","UNG":"energy_infra","BNO":"energy_infra",
    "HG=F":"generic","CPER":"generic","JJC":"generic",
    "SLX":"steel",
    "ZW=F":"staples","ZC=F":"staples","ZS=F":"staples","ZO=F":"staples",
    "KC=F":"staples","SB=F":"staples","CT=F":"staples","CC=F":"staples",
    "DBA":"staples","WEAT":"staples","CORN":"staples"}

# ── Market Classification ─────────────────────────────────────────────────────
MARKET_CLASSIFICATION: dict = {
    # US Equity
    "SPY":"us_equity","QQQ":"us_equity","IWM":"us_equity","DIA":"us_equity","RSP":"us_equity",
    "XLK":"us_equity","XLY":"us_equity","XLI":"us_equity","XLF":"us_equity",
    "XLE":"us_equity","XLB":"us_equity","XLV":"us_equity","XLP":"us_equity",
    "XLU":"us_equity","XLRE":"us_equity","XLC":"us_equity","XHB":"us_equity",
    "VTV":"us_equity","VUG":"us_equity","USMV":"us_equity","HDV":"us_equity",
    "MTUM":"us_equity","QUAL":"us_equity","SIZE":"us_equity",
    # ETF Pro Plus tickers
    "OIH":"us_equity","BNO":"commodity","XOP":"us_equity","ITB":"us_equity",
    "ITA":"us_equity","BTAL":"us_equity","DUST":"us_equity",
    "JPXN":"us_equity","EIS":"us_equity","TUR":"us_equity","NORW":"us_equity",
    "EWZ":"us_equity","EWW":"us_equity","EIDO":"us_equity","GLIN":"us_equity",
    "UAE":"us_equity","INDA":"us_equity","EWT":"us_equity","EWS":"us_equity",
    "GLD":"commodity","SLV":"commodity","PPLT":"commodity",
    "GDX":"us_equity","GDXJ":"us_equity","SIL":"us_equity","SILJ":"us_equity",
    "SLX":"us_equity","CPER":"commodity","GRID":"us_equity",
    "DAR":"us_equity","MTDR":"us_equity",
    "ULS":"us_equity","BRBR":"us_equity",
    "MSTY":"us_equity","BITS":"us_equity","BLOK":"us_equity","WGMI":"us_equity","MAGS":"us_equity",
    "IBIT":"us_equity","FBTC":"us_equity","ETHA":"us_equity","MSTR":"us_equity",
    # AI/Tech/Defense/Health/Energy singles
    "NVDA":"us_equity","AMD":"us_equity","AVGO":"us_equity","TSM":"us_equity","INTC":"us_equity",
    "ALAB":"us_equity","CRDO":"us_equity","MRVL":"us_equity","ANET":"us_equity","SMCI":"us_equity",
    "LITE":"us_equity","COHR":"us_equity","CIEN":"us_equity","POET":"us_equity","VIAV":"us_equity","GLW":"us_equity",
    "ON":"us_equity","WOLF":"us_equity","STM":"us_equity","MPWR":"us_equity",
    "VST":"us_equity","CEG":"us_equity","ETN":"us_equity","NRG":"us_equity",
    "GEV":"us_equity","EMR":"us_equity","VRT":"us_equity",
    "AMKR":"us_equity","ASX":"us_equity","TSEM":"us_equity",
    "LLY":"us_equity","MRNA":"us_equity","REGN":"us_equity","BMY":"us_equity","PFE":"us_equity",
    "JNJ":"us_equity","ABBV":"us_equity","MRK":"us_equity","AZN":"us_equity","NVO":"us_equity",
    "ISRG":"us_equity","ABT":"us_equity","BSX":"us_equity","MDT":"us_equity","EW":"us_equity","SYK":"us_equity",
    "ZBH":"us_equity","DXCM":"us_equity","PODD":"us_equity","RMD":"us_equity",
    "LMT":"us_equity","RTX":"us_equity","NOC":"us_equity","GD":"us_equity","KTOS":"us_equity",
    "HII":"us_equity","LDOS":"us_equity","BAH":"us_equity","PLTR":"us_equity","AXON":"us_equity",
    "SAIC":"us_equity","BWXT":"us_equity",
    "NEE":"us_equity","DUK":"us_equity","D":"us_equity","SO":"us_equity",
    "AEP":"us_equity","EXC":"us_equity","SRE":"us_equity","PEG":"us_equity","ED":"us_equity",
    "AWK":"us_equity","WTRG":"us_equity","CWT":"us_equity",
    "PG":"us_equity","KO":"us_equity","PEP":"us_equity","WMT":"us_equity","COST":"us_equity",
    "PM":"us_equity","MO":"us_equity","GIS":"us_equity","K":"us_equity","HSY":"us_equity","MDLZ":"us_equity",
    "AEM":"us_equity","WPM":"us_equity","FNV":"us_equity","RGLD":"us_equity","NEM":"us_equity","GFI":"us_equity",
    "URA":"us_equity","CCJ":"us_equity","NXE":"us_equity","UUUU":"us_equity",
    "LEU":"us_equity","DNN":"us_equity","URG":"us_equity",
    "XOM":"us_equity","CVX":"us_equity","COP":"us_equity","SLB":"us_equity",
    "OXY":"us_equity","MPC":"us_equity","VLO":"us_equity","PSX":"us_equity","KMI":"us_equity",
    "JPM":"us_equity","BAC":"us_equity","GS":"us_equity","MS":"us_equity",
    "BLK":"us_equity","V":"us_equity","MA":"us_equity","SCHW":"us_equity",
    "HUBB":"us_equity","NVT":"us_equity","AYI":"us_equity","AMETEK":"us_equity","ROP":"us_equity",
    # Forex
    "EURUSD=X":"forex","GBPUSD=X":"forex","USDJPY=X":"forex","USDCHF=X":"forex",
    "USDCAD=X":"forex","AUDUSD=X":"forex","NZDUSD=X":"forex","USDSEK=X":"forex","USDNOK=X":"forex",
    "USDMXN=X":"forex","USDBRL=X":"forex","USDTRY=X":"forex","USDZAR=X":"forex",
    "USDIDR=X":"forex","USDSGD=X":"forex","USDINR=X":"forex","USDCNY=X":"forex","USDKRW=X":"forex",
    "USDTHB=X":"forex","USDPHP=X":"forex","USDMYR=X":"forex",
    "EURJPY=X":"forex","GBPJPY=X":"forex","AUDNZD=X":"forex","CADUSD=X":"forex","DX-Y.NYB":"forex",
    # Commodities
    "GC=F":"commodity","SI=F":"commodity","PL=F":"commodity","PA=F":"commodity",
    "CL=F":"commodity","BZ=F":"commodity","NG=F":"commodity","RB=F":"commodity","HO=F":"commodity",
    "USO":"commodity","UNG":"commodity",
    "HG=F":"commodity","CPER":"commodity","JJC":"commodity",
    "ZW=F":"commodity","ZC=F":"commodity","ZS=F":"commodity","ZO=F":"commodity",
    "KC=F":"commodity","SB=F":"commodity","CT=F":"commodity","CC=F":"commodity",
    "DBA":"commodity","WEAT":"commodity","CORN":"commodity","SLX":"commodity",
    # Crypto
    "BTC-USD":"crypto","ETH-USD":"crypto","BNB-USD":"crypto","SOL-USD":"crypto",
    "XRP-USD":"crypto","ADA-USD":"crypto","AVAX-USD":"crypto","DOT-USD":"crypto",
    "MATIC-USD":"crypto","LINK-USD":"crypto","DOGE-USD":"crypto","LTC-USD":"crypto",
    "ATOM-USD":"crypto","NEAR-USD":"crypto","APT-USD":"crypto","ARB-USD":"crypto",
    "OP-USD":"crypto","SUI20947-USD":"crypto","INJ-USD":"crypto","SEI-USD":"crypto",
    "AAVE-USD":"crypto","UNI7083-USD":"crypto","MKR-USD":"crypto","LDO-USD":"crypto",
    "FET-USD":"crypto","TAO22974-USD":"crypto","RNDR-USD":"crypto","GRT6719-USD":"crypto",
    "OCEAN-USD":"crypto","HNT-USD":"crypto","ONDO-USD":"crypto","POLYX-USD":"crypto",
    "TON11419-USD":"crypto","TIA22861-USD":"crypto","PYTH-USD":"crypto",
    "WIF-USD":"crypto","PEPE24478-USD":"crypto","BONK-USD":"crypto","FLOKI-USD":"crypto",
    # IHSG
    "^JKSE":"ihsg","EIDO":"ihsg",
    "BBCA.JK":"ihsg","BBRI.JK":"ihsg","BMRI.JK":"ihsg","BBNI.JK":"ihsg",
    "BRIS.JK":"ihsg","BBTN.JK":"ihsg","BNGA.JK":"ihsg","MEGA.JK":"ihsg","NISP.JK":"ihsg",
    "ADRO.JK":"ihsg","PTBA.JK":"ihsg","ITMG.JK":"ihsg","HRUM.JK":"ihsg",
    "INDY.JK":"ihsg","AADI.JK":"ihsg","BUMI.JK":"ihsg",
    "MEDC.JK":"ihsg","PGEO.JK":"ihsg","AKRA.JK":"ihsg","UNTR.JK":"ihsg",
    "INCO.JK":"ihsg","MDKA.JK":"ihsg","ANTM.JK":"ihsg","TINS.JK":"ihsg",
    "BRMS.JK":"ihsg","NCKL.JK":"ihsg",
    "TLKM.JK":"ihsg","EXCL.JK":"ihsg","ISAT.JK":"ihsg","JSMR.JK":"ihsg",
    "PGAS.JK":"ihsg","WIKA.JK":"ihsg","PTPP.JK":"ihsg",
    "ICBP.JK":"ihsg","INDF.JK":"ihsg","MYOR.JK":"ihsg","KLBF.JK":"ihsg",
    "SIDO.JK":"ihsg","ULTJ.JK":"ihsg","CMRY.JK":"ihsg",
    "AMRT.JK":"ihsg","ACES.JK":"ihsg","MAPI.JK":"ihsg","ERAA.JK":"ihsg",
    "ASII.JK":"ihsg","CPIN.JK":"ihsg","JPFA.JK":"ihsg",
    "CTRA.JK":"ihsg","BSDE.JK":"ihsg","PWON.JK":"ihsg","SMRA.JK":"ihsg",
    "HEAL.JK":"ihsg","MIKA.JK":"ihsg","SILO.JK":"ihsg",
    "LSIP.JK":"ihsg","AALI.JK":"ihsg","SSMS.JK":"ihsg","INKP.JK":"ihsg",
    "TKIM.JK":"ihsg","ESSA.JK":"ihsg",
    "WINS.JK":"ihsg","LEAD.JK":"ihsg","SHIP.JK":"ihsg","ELSA.JK":"ihsg",
    "SOCI.JK":"ihsg","BULL.JK":"ihsg","SMDR.JK":"ihsg","TMAS.JK":"ihsg",
    "DSNG.JK":"ihsg","TAPG.JK":"ihsg","SGRO.JK":"ihsg",
    "BEST.JK":"ihsg","KIJA.JK":"ihsg","DMAS.JK":"ihsg"}

# ── Quad → Market Direction ───────────────────────────────────────────────────
# crypto: "long" = BTC/IBIT when Bullish TREND signal
# Keith rule: "Any quad other than Q4, bitcoin = biggest digital asset position"
QUAD_MARKET_DIRECTION: dict = {
    "Q1": {"us_equity":"long","forex":"neutral","commodity":"neutral","crypto":"long","ihsg":"long"},
    "Q2": {"us_equity":"long","forex":"long","commodity":"long","crypto":"long","ihsg":"long"},
    "Q3": {"us_equity":"short","forex":"short","commodity":"long","crypto":"neutral","ihsg":"short"},
    "Q4": {"us_equity":"short","forex":"short","commodity":"short","crypto":"short","ihsg":"short"}}

# ── EM Recovery Signals ───────────────────────────────────────────────────────
EM_RECOVERY_SIGNALS: dict = {
    "Q3→Q2": {
        "trigger": "Monthly Q2 inside Structural Q3 = EM commodity exporters early recovery",
        "best": ["EIDO","EWW","EWZ","EWC","NORW","EWA","USDMXN=X","USDBRL=X","AUDUSD=X"],
        "rationale": "Q2 monthly = commodity bid + growth rebound. EM commodity exporters lead.",
        "confidence": 0.55},
    "Q4→Q1": {
        "trigger": "Deflation → Goldilocks = MAX EM recovery setup",
        "best": ["EIDO","INDA","EWZ","EWW","EEM","VWO","USDMXN=X","USDBRL=X","USDZAR=X"],
        "rationale": "Q4→Q1 = growth re-acceleration + Fed easing. EM equities historically +25-40% in first 6M of Q1.",
        "confidence": 0.85},
    "Q3→Q1": {
        "trigger": "Direct stagflation → goldilocks = EM selective recovery",
        "best": ["INDA","EIDO","EWS","EWT"],
        "rationale": "Rare direct transition. Only high-quality EM recover.",
        "confidence": 0.35},
    "Q3→Q3": {
        "trigger": "Stagflation persistence = EM headwind continues",
        "best": [],
        "rationale": "EM non-commodity exporters under pressure. Defensive EM (India) only.",
        "confidence": 0.70}}

# ── Country Universe (50+ countries, PRESERVED original format) ───────────────
# Format: (etf, region, inflation_sensitivity, growth_sensitivity)
COUNTRY_UNIVERSE: dict = {
    "USA":         ("SPY",   "americas", 0.20, 1.00),
    "Mexico":      ("EWW",   "americas", 0.40, 0.85),
    "Canada":      ("EWC",   "americas", 0.55, 0.80),
    "Argentina":   ("ARGT",  "americas", 0.35, 0.90),
    "Brazil":      ("EWZ",   "americas", 0.65, 0.75),
    "Chile":       ("ECH",   "americas", 0.60, 0.75),
    "Colombia":    ("GXG",   "americas", 0.65, 0.70),
    "Peru":        ("EPU",   "americas", 0.60, 0.70),
    "Hong_Kong":   ("EWH",   "asia",     0.15, 0.95),
    "Japan":       ("EWJ",   "asia",     0.20, 0.80),  # EWJ for global quad; JPXN for ETF Pro
    "Korea":       ("EWY",   "asia",     0.30, 0.75),
    "Taiwan":      ("EWT",   "asia",     0.15, 0.70),
    "China":       ("MCHI",  "asia",     0.30, 0.65),
    "India":       ("INDA",  "asia",     0.25, 0.70),
    "Indonesia":   ("EIDO",  "asia",     0.70, 0.55),
    "Australia":   ("EWA",   "asia",     0.65, 0.70),
    "Vietnam":     ("VNM",   "asia",     0.40, 0.65),
    "Thailand":    ("THD",   "asia",     0.45, 0.65),
    "Malaysia":    ("EWM",   "asia",     0.50, 0.65),
    "Singapore":   ("EWS",   "asia",     0.25, 0.80),
    "Germany":     ("EWG",   "europe",   0.35, 0.70),
    "UK":          ("EWU",   "europe",   0.30, 0.75),
    "France":      ("EWQ",   "europe",   0.30, 0.70),
    "Switzerland": ("EWL",   "europe",   0.20, 0.75),
    "Norway":      ("NORW",  "europe",   0.75, 0.80),
    "Sweden":      ("EWD",   "europe",   0.35, 0.75),
    "Poland":      ("EPOL",  "europe",   0.40, 0.65),
    "Turkey":      ("TUR",   "europe",   0.35, 0.60),  # Hedgeye ETF Pro Plus long
    "Italy":       ("EWI",   "europe",   0.30, 0.70),
    "Spain":       ("EWP",   "europe",   0.30, 0.70),
    "Israel":      ("EIS",   "mideast",  0.20, 0.80),  # Hedgeye ETF Pro Plus long (+21.8%)
    "UAE":         ("UAE",   "mideast",  0.80, 0.65),  # Added March 2026
    "Saudi":       ("KSA",   "mideast",  0.85, 0.65),
    "Qatar":       ("QAT",   "mideast",  0.80, 0.65),
    "South_Africa":("EZA",   "em",       0.55, 0.65),
    "Nigeria":     ("NGE",   "em",       0.70, 0.60),
    "Egypt":       ("EGPT",  "em",       0.45, 0.60),
    "New_Zealand": ("ENZL",  "asia",     0.30, 0.70),
    "Philippines": ("EPHE",  "asia",     0.50, 0.60),
    "Denmark":     ("EDEN",  "europe",   0.25, 0.75),
    "Netherlands": ("EWN",   "europe",   0.30, 0.70),
    "Ireland":     ("EIRL",  "europe",   0.25, 0.75),
    "Finland":     ("EFNL",  "europe",   0.30, 0.70),
    "Greece":      ("GREK",  "europe",   0.50, 0.60),
    "Hungary":     ("FLHU",  "europe",   0.40, 0.60),
    "Czech":       ("FLCZ",  "europe",   0.35, 0.65),
    "Pakistan":    ("PAK",   "em",       0.60, 0.55),
    "Sri_Lanka":   ("SLXB",  "em",       0.55, 0.50)}

# ── US Sector Buckets ─────────────────────────────────────────────────────────
US_BUCKETS: dict = {
    "Growth":         ["QQQ","VUG","AAPL","MSFT","NVDA","AMZN","META","GOOGL","NFLX","NOW","CRM","SNOW"],
    "Quality":        ["QUAL","LLY","UNH","COST","WMT","PG","KO","PEP","V","MA"],
    "Defensives":     ["XLP","XLU","XLV","WMT","KO","PEP","PG","JNJ","MRK","ABBV"],
    "Semis":          ["NVDA","AMD","AVGO","AMAT","MU","QCOM","TXN","INTC","KLAC","LRCX"],
    "Energy":         ["XLE","OIH","XOP","BNO","XOM","CVX","COP","SLB","HAL","OXY","DAR","MTDR"],
    "Industrials":    ["XLI","CAT","DE","GE","LMT","NOC","RTX","UNP","CSX","NSC","BA"],
    "Financials":     ["XLF","JPM","BAC","GS","MS","BLK","V","MA","SCHW"],
    "AI_Infra":       ["NVDA","ETN","VST","VRT","GEV","LITE","COHR","ON"],
    "PreciousMetals": ["GLD","SLV","PPLT","GDX","GDXJ","SIL","SILJ","AEM","WPM","FNV"],
    "International":  ["JPXN","EIS","TUR","NORW","EWZ","EWW","EIDO","GLIN","UAE"],
    "Housing":        ["ITB","XHB","DHI","LEN","PHM","NVR"],
    "Bitcoin":        ["IBIT","FBTC","MSTR","BTC-USD"]}
IHSG_BUCKETS: dict = {
    "Banks":           ["BBCA.JK","BBRI.JK","BMRI.JK","BBNI.JK","BRIS.JK","BBTN.JK"],
    "Coal_Energy":     ["AADI.JK","ADRO.JK","PTBA.JK","ITMG.JK","HRUM.JK","INDY.JK","BUMI.JK"],
    "Metals":          ["ANTM.JK","INCO.JK","MDKA.JK","TINS.JK","BRMS.JK","NCKL.JK"],
    "Telco_Infra":     ["TLKM.JK","EXCL.JK","ISAT.JK","JSMR.JK","PGAS.JK","UNTR.JK"],
    "Consumer_Def":    ["ICBP.JK","INDF.JK","MYOR.JK","KLBF.JK","SIDO.JK","ULTJ.JK"],
    "Consumer_Cyc":    ["AMRT.JK","ACES.JK","MAPI.JK","ERAA.JK","ASII.JK","CPIN.JK","JPFA.JK"],
    "Property_Health": ["CTRA.JK","BSDE.JK","PWON.JK","SMRA.JK","HEAL.JK","MIKA.JK","SILO.JK"],
    "CPO_Agri":        ["AALI.JK","LSIP.JK","SSMS.JK","INKP.JK","TKIM.JK","ESSA.JK","DSNG.JK","TAPG.JK","SGRO.JK"],
    "OSV_Hulu":        ["WINS.JK","LEAD.JK","SHIP.JK","ELSA.JK","MEDC.JK","ESSA.JK"],
    "Tanker_Ship":     ["SOCI.JK","BULL.JK","SMDR.JK","TMAS.JK"]}
FX_BUCKETS: dict = {
    "Majors":       ["EURUSD=X","GBPUSD=X","AUDUSD=X","NZDUSD=X","USDJPY=X","USDCHF=X","USDCAD=X"],
    "EM_FX":        ["USDMXN=X","USDBRL=X","USDTRY=X","USDZAR=X","USDIDR=X","USDINR=X","USDSGD=X"],
    "Commodity_FX": ["AUDUSD=X","USDCAD=X","USDNOK=X"]}
COMMODITY_BUCKETS: dict = {
    "Precious":      ["GC=F","SI=F","PL=F","PA=F","GLD","SLV"],
    "Miners":        ["GDX","GDXJ","SIL","SILJ"],
    "Energy":        ["CL=F","BZ=F","NG=F","RB=F","HO=F","USO","BNO","OIH","XOP"],
    "Industrial":    ["HG=F","CPER","SLX"],
    "Agri_Softs":    ["ZC=F","ZW=F","ZS=F","KC=F","SB=F","CT=F","CC=F","DBA","WEAT","CORN"],
    "Nuclear":       ["URA","CCJ","NXE"]}
CRYPTO_BUCKETS: dict = {
    "Majors":        ["BTC-USD","ETH-USD","SOL-USD","BNB-USD","XRP-USD"],
    "L1_L2":         ["ADA-USD","AVAX-USD","ATOM-USD","NEAR-USD","APT-USD","ARB-USD","OP-USD","MATIC-USD"],
    "DeFi":          ["AAVE-USD","UNI7083-USD","MKR-USD","LDO-USD","CRV-USD","COMP5692-USD"],
    "AI_Data":       ["FET-USD","TAO22974-USD","RNDR-USD","GRT6719-USD","OCEAN-USD"],
    "RWA_Infra":     ["ONDO-USD","POLYX-USD","LINK-USD","INJ-USD","SEI-USD","TIA22861-USD","PYTH-USD"],
    "High_Beta":     ["DOGE-USD","WIF-USD","PEPE24478-USD","BONK-USD","FLOKI-USD"],
    "ETFs":          ["IBIT","FBTC","ETHA"],
    "BTC_Proxies":   ["MSTR","MSTY","BITS","BLOK","WGMI"],  # direction = BTC TREND signal
}

# MAG7 for breadth/concentration analysis
MAG7 = ["AAPL","MSFT","NVDA","AMZN","META","GOOGL","TSLA"]

# NOTE: LIVE_FETCH_ENABLED and FRED_CACHE_TTL_SECONDS already defined at top of file.
# Duplicates removed to prevent redefinition warnings.