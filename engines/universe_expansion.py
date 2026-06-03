"""engines/universe_expansion.py — Dynamic Ticker Universe Manager v1.0

Manages dynamic ticker lists for all markets:
  - US Stocks: S&P 500, NASDAQ 100, Russell 2000, + custom additions
  - IHSG: IDX 30, LQ 45, + all listed .JK stocks
  - Crypto: top 100 by market cap
  - Forex: major + minor + exotic pairs
  - Commodities: futures contracts

Lazy loading: tickers fetched on-demand, cached, refreshed periodically.

Usage:
    from engines.universe_expansion import UniverseManager
    um = UniverseManager()

    # Get US stocks (lazy — only fetch when called)
    sp500 = um.get_us_stocks("sp500")  # ~503 tickers

    # Add custom ticker
    um.add_ticker("AAPL", "us_equity")
    um.add_ticker("BBCA.JK", "ihsg")

    # Get IHSG all
    ihsg_all = um.get_ihsg_stocks("all")  # ~900 tickers

    # Get combined for a market page
    all_tickers = um.get_market_tickers("us_equity")  # ~4000 tickers
"""

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Set

import pandas as pd
import requests
import yfinance as yf

logger = logging.getLogger(__name__)

CACHE_DIR = "data/universe_cache"
CACHE_TTL = 86400  # 24 hours

# ── S&P 500 (~503 tickers + recent additions) ───────────────────────────
SP500_TICKERS = [
    "A",
    "AAL",
    "AAP",
    "AAPL",
    "ABBV",
    "ABNB",
    "ABT",
    "ACGL",
    "ACN",
    "ADBE",
    "ADI",
    "ADM",
    "ADP",
    "ADSK",
    "AEE",
    "AEP",
    "AES",
    "AFL",
    "AIG",
    "AIZ",
    "AJG",
    "AKAM",
    "ALB",
    "ALGN",
    "ALK",
    "ALL",
    "ALLE",
    "AMAT",
    "AMCR",
    "AMD",
    "AME",
    "AMGN",
    "AMP",
    "AMT",
    "AMZN",
    "ANET",
    "AON",
    "AOS",
    "APA",
    "APD",
    "APH",
    "APO",
    "APTV",
    "ARE",
    "ARES",
    "ATO",
    "AVB",
    "AVGO",
    "AVY",
    "AWK",
    "AXP",
    "AZO",
    "AZPN",
    "BA",
    "BAC",
    "BALL",
    "BAX",
    "BBWI",
    "BBY",
    "BDX",
    "BEN",
    "BF.B",
    "BG",
    "BIIB",
    "BKNG",
    "BKR",
    "BLDR",
    "BLK",
    "BMY",
    "BNY",
    "BR",
    "BRK.B",
    "BRO",
    "BSX",
    "BX",
    "BXP",
    "C",
    "CAG",
    "CAH",
    "CARR",
    "CASY",
    "CAT",
    "CB",
    "CBOE",
    "CBRE",
    "CCI",
    "CCL",
    "CDAY",
    "CDNS",
    "CDW",
    "CEG",
    "CF",
    "CFG",
    "CHD",
    "CHRW",
    "CHTR",
    "CI",
    "CIEN",
    "CINF",
    "CL",
    "CLX",
    "CMA",
    "CMCSA",
    "CME",
    "CMG",
    "CMI",
    "CMS",
    "CNC",
    "CNP",
    "COF",
    "COO",
    "COP",
    "COR",
    "COST",
    "CPAY",
    "CPB",
    "CPRT",
    "CPT",
    "CRH",
    "CRL",
    "CRM",
    "CRWD",
    "CSCO",
    "CSGP",
    "CSX",
    "CTAS",
    "CTLT",
    "CTRA",
    "CTSH",
    "CTVA",
    "CVNA",
    "CVS",
    "CVX",
    "D",
    "DAL",
    "DASH",
    "DD",
    "DDOG",
    "DE",
    "DECK",
    "DELL",
    "DG",
    "DGX",
    "DHI",
    "DHR",
    "DIS",
    "DLR",
    "DLTR",
    "DOC",
    "DOV",
    "DOW",
    "DPZ",
    "DRI",
    "DTE",
    "DUK",
    "DVA",
    "DVN",
    "DXCM",
    "EA",
    "EBAY",
    "ECL",
    "ED",
    "EFX",
    "EG",
    "EIX",
    "EL",
    "ELV",
    "EME",
    "EMN",
    "EMR",
    "EOG",
    "EPAM",
    "EQIX",
    "EQR",
    "EQT",
    "ERIE",
    "ES",
    "ESS",
    "ETN",
    "ETR",
    "EVRG",
    "EW",
    "EXC",
    "EXE",
    "EXPD",
    "EXPE",
    "EXR",
    "F",
    "FANG",
    "FAST",
    "FCX",
    "FDS",
    "FDX",
    "FE",
    "FFIV",
    "FI",
    "FICO",
    "FITB",
    "FLT",
    "FOX",
    "FOXA",
    "FRT",
    "FSLR",
    "FTNT",
    "FTV",
    "GD",
    "GE",
    "GEHC",
    "GEN",
    "GEV",
    "GFS",
    "GILD",
    "GIS",
    "GL",
    "GLW",
    "GM",
    "GNRC",
    "GOOG",
    "GOOGL",
    "GPC",
    "GPN",
    "GRMN",
    "GS",
    "GWW",
    "H",
    "HAL",
    "HAS",
    "HBAN",
    "HCA",
    "HD",
    "HIG",
    "HII",
    "HLT",
    "HOLX",
    "HON",
    "HPE",
    "HPQ",
    "HRL",
    "HSIC",
    "HST",
    "HSY",
    "HUBB",
    "HUM",
    "HWM",
    "IBKR",
    "IBM",
    "ICE",
    "IDXX",
    "IEX",
    "IFF",
    "ILMN",
    "INCY",
    "INTC",
    "INTU",
    "IP",
    "IPG",
    "IQV",
    "IR",
    "IRM",
    "ISRG",
    "IT",
    "ITW",
    "IVZ",
    "J",
    "JBHT",
    "JBL",
    "JCI",
    "JKHY",
    "JNJ",
    "JNPR",
    "JPM",
    "K",
    "KDP",
    "KEY",
    "KEYS",
    "KHC",
    "KIM",
    "KKR",
    "KLAC",
    "KMB",
    "KMI",
    "KMX",
    "KO",
    "KR",
    "KVUE",
    "L",
    "LDOS",
    "LEN",
    "LH",
    "LHX",
    "LIN",
    "LITE",
    "LKQ",
    "LLY",
    "LMT",
    "LNT",
    "LOW",
    "LRCX",
    "LULU",
    "LUV",
    "LVS",
    "LYB",
    "LYV",
    "M",
    "MA",
    "MAA",
    "MAR",
    "MAS",
    "MCD",
    "MCHP",
    "MCK",
    "MCO",
    "MDLZ",
    "MDT",
    "MET",
    "META",
    "MGM",
    "MHK",
    "MKC",
    "MLM",
    "MMC",
    "MMM",
    "MNST",
    "MO",
    "MOH",
    "MOS",
    "MPC",
    "MPWR",
    "MRK",
    "MRNA",
    "MRO",
    "MS",
    "MSCI",
    "MSFT",
    "MSI",
    "MTB",
    "MTCH",
    "MTD",
    "MU",
    "NCLH",
    "NDAQ",
    "NDSN",
    "NEE",
    "NEM",
    "NFLX",
    "NI",
    "NKE",
    "NOC",
    "NOW",
    "NRG",
    "NSC",
    "NTAP",
    "NTRS",
    "NUE",
    "NVDA",
    "NVR",
    "NXPI",
    "O",
    "ODFL",
    "OKE",
    "OMC",
    "ON",
    "ORCL",
    "ORLY",
    "OTIS",
    "OXY",
    "PANW",
    "PAYC",
    "PAYX",
    "PCAR",
    "PCG",
    "PEG",
    "PEP",
    "PFE",
    "PFG",
    "PG",
    "PGR",
    "PH",
    "PHM",
    "PKG",
    "PLD",
    "PLTR",
    "PM",
    "PNC",
    "PNR",
    "PNW",
    "PODD",
    "POOL",
    "PPG",
    "PPL",
    "PRU",
    "PSA",
    "PSKY",
    "PSX",
    "PTC",
    "PWR",
    "PXD",
    "PYPL",
    "Q",
    "QCOM",
    "RCL",
    "REG",
    "REGN",
    "RF",
    "RHI",
    "RJF",
    "RL",
    "RMD",
    "ROK",
    "ROL",
    "ROP",
    "ROST",
    "RRC",
    "RSG",
    "RTX",
    "RVTY",
    "SBAC",
    "SBUX",
    "SCHW",
    "SHW",
    "SJM",
    "SLB",
    "SMCI",
    "SNA",
    "SNDK",
    "SNPS",
    "SO",
    "SOLV",
    "SPG",
    "SPGI",
    "SRE",
    "STE",
    "STLD",
    "STT",
    "STX",
    "STZ",
    "SW",
    "SWK",
    "SWKS",
    "SYF",
    "SYK",
    "SYY",
    "T",
    "TAP",
    "TDG",
    "TDY",
    "TECH",
    "TEL",
    "TER",
    "TFC",
    "TGT",
    "TJX",
    "TKO",
    "TMO",
    "TMUS",
    "TPR",
    "TRGP",
    "TRMB",
    "TROW",
    "TRV",
    "TSCO",
    "TSLA",
    "TSN",
    "TT",
    "TTWO",
    "TXN",
    "TXT",
    "TYL",
    "UAL",
    "UBER",
    "UDR",
    "UHS",
    "ULTA",
    "UNH",
    "UNP",
    "UPS",
    "URI",
    "USB",
    "V",
    "VFC",
    "VICI",
    "VLO",
    "VLTO",
    "VMC",
    "VRSK",
    "VRSN",
    "VRTX",
    "VST",
    "VTR",
    "VTRS",
    "VZ",
    "WAB",
    "WAT",
    "WBD",
    "WDAY",
    "WDC",
    "WEC",
    "WELL",
    "WFC",
    "WHR",
    "WM",
    "WMB",
    "WMT",
    "WRB",
    "WRK",
    "WST",
    "WTW",
    "WY",
    "WYNN",
    "XEL",
    "XOM",
    "YUM",
    "ZBH",
    "ZBRA",
    "ZTS"
]

# ── NASDAQ 100 (101 tickers) ───────────────────────────
NASDAQ100_TICKERS = [
    "AAPL",
    "ABNB",
    "ADBE",
    "ADI",
    "ADP",
    "ADSK",
    "AEP",
    "ALGN",
    "AMAT",
    "AMD",
    "AMGN",
    "AMZN",
    "ANSS",
    "APP",
    "ARM",
    "AVGO",
    "AXON",
    "AZN",
    "BIIB",
    "BKR",
    "CCEP",
    "CDNS",
    "CDW",
    "CEG",
    "CHTR",
    "CMCSA",
    "COIN",
    "COST",
    "CPRT",
    "CRWD",
    "CSCO",
    "CSGP",
    "CSX",
    "CTAS",
    "DASH",
    "DDOG",
    "DXCM",
    "EA",
    "EXC",
    "FANG",
    "FAST",
    "FTNT",
    "GEHC",
    "GFS",
    "GILD",
    "GOOG",
    "GOOGL",
    "HON",
    "IDXX",
    "ILMN",
    "INTC",
    "INTU",
    "ISRG",
    "KDP",
    "KHC",
    "KLAC",
    "LIN",
    "LRCX",
    "LULU",
    "MAR",
    "MCHP",
    "MDB",
    "MDLZ",
    "MELI",
    "META",
    "MNST",
    "MRNA",
    "MRVL",
    "MSFT",
    "MU",
    "NFLX",
    "NVDA",
    "NXPI",
    "ODFL",
    "ON",
    "ORLY",
    "PANW",
    "PAYX",
    "PCAR",
    "PDD",
    "PEP",
    "PLTR",
    "PYPL",
    "QCOM",
    "REGN",
    "ROP",
    "ROST",
    "SBUX",
    "SNPS",
    "TEAM",
    "TMUS",
    "TSLA",
    "TTD",
    "TTWO",
    "TXN",
    "VRSK",
    "VRTX",
    "WBD",
    "WDAY",
    "XEL",
    "ZS"
]

# ── IHSG IDX30 (30 stocks) ─────────────────────────────
IHSG_IDX30 = [
    "ASII.JK",
    "BBCA.JK",
    "BBRI.JK",
    "BBNI.JK",
    "BMRI.JK",
    "UNVR.JK",
    "TLKM.JK",
    "PGAS.JK",
    "PTBA.JK",
    "KLBF.JK",
    "INDF.JK",
    "CPIN.JK",
    "SMGR.JK",
    "GGRM.JK",
    "MNCN.JK",
    "WSKT.JK",
    "JPFA.JK",
    "JSMR.JK",
    "LPPF.JK",
    "EXCL.JK",
    "ANTM.JK",
    "ADRO.JK",
    "MEDC.JK",
    "ITMG.JK",
    "BRMS.JK",
    "HRUM.JK",
    "DOID.JK",
    "TINS.JK",
    "INCO.JK",
    "AALI.JK"
]

# ── IHSG LQ45 (45 stocks = IDX30 + 15) ───────────────
IHSG_LQ45 = [
    "ASII.JK",
    "BBCA.JK",
    "BBRI.JK",
    "BBNI.JK",
    "BMRI.JK",
    "UNVR.JK",
    "TLKM.JK",
    "PGAS.JK",
    "PTBA.JK",
    "KLBF.JK",
    "INDF.JK",
    "CPIN.JK",
    "SMGR.JK",
    "GGRM.JK",
    "MNCN.JK",
    "WSKT.JK",
    "JPFA.JK",
    "JSMR.JK",
    "LPPF.JK",
    "EXCL.JK",
    "ANTM.JK",
    "ADRO.JK",
    "MEDC.JK",
    "ITMG.JK",
    "BRMS.JK",
    "HRUM.JK",
    "DOID.JK",
    "TINS.JK",
    "INCO.JK",
    "AALI.JK",
    "BSDE.JK",
    "LSIP.JK",
    "PWON.JK",
    "SMRA.JK",
    "BBTN.JK",
    "BJBR.JK",
    "BJTM.JK",
    "BRPT.JK",
    "TPIA.JK",
    "ERAA.JK",
    "AKRA.JK",
    "MIKA.JK",
    "SILO.JK",
    "HEAL.JK",
    "SCMA.JK"
]


@dataclass
class TickerInfo:
    """Metadata for a single ticker."""

    symbol: str
    name: str = ""
    market_type: str = "us_equity"  # us_equity, ihsg, crypto, forex, commodity
    sector: str = ""
    industry: str = ""
    market_cap: float = 0.0
    added_date: str = ""
    source: str = "manual"  # manual, sp500, nasdaq100, idx30, discovery

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "market_type": self.market_type,
            "sector": self.sector,
            "industry": self.industry,
            "market_cap": self.market_cap,
            "added_date": self.added_date,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TickerInfo":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class UniverseManager:
    """Dynamic ticker universe with lazy loading and caching."""

    def __init__(self, cache_dir: str = CACHE_DIR):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self._custom_tickers: Dict[str, TickerInfo] = {}
        self._load_custom_tickers()

    # ── US Stocks ───────────────────────────────────────

    def get_sp500(self) -> List[str]:
        """Get S&P 500 tickers. Uses cached list or fetches from Wikipedia."""
        cache_file = os.path.join(self.cache_dir, "sp500.json")
        if self._is_cache_valid(cache_file):
            return self._load_cache(cache_file)
        try:
            url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
            tables = pd.read_html(url)
            tickers = tables[0]["Symbol"].tolist()
            self._save_cache(cache_file, tickers)
            logger.info(f"S&P 500 fetched from Wikipedia: {len(tickers)} tickers")
            return tickers
        except Exception as e:
            logger.warning(f"Failed to fetch S&P 500 from Wikipedia: {e}")
            return SP500_TICKERS  # fallback

    def get_nasdaq100(self) -> List[str]:
        """Get NASDAQ 100 tickers."""
        cache_file = os.path.join(self.cache_dir, "nasdaq100.json")
        if self._is_cache_valid(cache_file):
            return self._load_cache(cache_file)
        try:
            url = "https://en.wikipedia.org/wiki/NASDAQ-100"
            tables = pd.read_html(url)
            tickers = tables[1]["Ticker"].tolist()
            self._save_cache(cache_file, tickers)
            logger.info(f"NASDAQ 100 fetched from Wikipedia: {len(tickers)} tickers")
            return tickers
        except Exception as e:
            logger.warning(f"Failed to fetch NASDAQ 100 from Wikipedia: {e}")
            return NASDAQ100_TICKERS

    def get_russell2000(self) -> List[str]:
        """Get Russell 2000 tickers (top 200 dari ~2000)."""
        cache_file = os.path.join(self.cache_dir, "russell2000.json")
        if self._is_cache_valid(cache_file):
            return self._load_cache(cache_file)
        logger.info("Russell 2000: returning empty list (use add_ticker)")
        return []

    def get_all_us_stocks(self) -> List[str]:
        """Get all US stocks (S&P 500 + NASDAQ 100 + Russell 2000)."""
        sp500 = set(self.get_sp500())
        nasdaq = set(self.get_nasdaq100())
        russell = set(self.get_russell2000())
        return sorted(sp500 | nasdaq | russell)

    def get_us_stocks(self, index: str = "sp500") -> List[str]:
        """Get US stocks by index name."""
        if index == "sp500":
            return self.get_sp500()
        elif index == "nasdaq100":
            return self.get_nasdaq100()
        elif index == "russell2000":
            return self.get_russell2000()
        elif index == "all":
            return self.get_all_us_stocks()
        return []

    # ── IHSG ────────────────────────────────────────────────

    def get_idx30(self) -> List[str]:
        """Get IDX 30 constituent tickers."""
        return IHSG_IDX30

    def get_lq45(self) -> List[str]:
        """Get LQ 45 constituent tickers."""
        return IHSG_LQ45

    def get_ihsg_stocks(self, index: str = "all") -> List[str]:
        """Get IHSG stocks by index name."""
        if index == "idx30":
            return self.get_idx30()
        elif index == "lq45":
            return self.get_lq45()
        elif index == "all":
            return self.get_all_ihsg()
        return []

    def get_all_ihsg(self) -> List[str]:
        """Get ALL listed IHSG stocks (~900 tickers).

        Strategy:
        1. Try fetch from IDX website
        2. Fallback to composite of known indices + custom additions
        3. Cache result
        """
        cache_file = os.path.join(self.cache_dir, "all_ihsg.json")
        if self._is_cache_valid(cache_file):
            return self._load_cache(cache_file)

        # Try fetch from IDX
        try:
            url = "https://www.idx.co.id/umbraco/Surface/Helper/GetTickerList"
            resp = requests.get(url, timeout=15)
            data = resp.json()
            tickers = [f"{t['ticker']}.JK" for t in data]
            if tickers:
                self._save_cache(cache_file, tickers)
                logger.info(f"IHSG all fetched from IDX: {len(tickers)} tickers")
                return tickers
        except Exception as e:
            logger.warning(f"Failed to fetch IHSG from IDX: {e}")

        # Fallback: combine all known + custom
        all_ihsg = set(IHSG_IDX30) | set(IHSG_LQ45)
        for t in self._custom_tickers.values():
            if t.market_type == "ihsg":
                all_ihsg.add(t.symbol)
        return sorted(all_ihsg)

    # ── Crypto ───────────────────────────────────────────

    def get_top_crypto(self, limit: int = 100) -> List[str]:
        """Get top cryptocurrencies by market cap."""
        cache_file = os.path.join(self.cache_dir, f"crypto_top{limit}.json")
        if self._is_cache_valid(cache_file):
            return self._load_cache(cache_file)
        try:
            url = "https://api.coingecko.com/api/v3/coins/markets"
            params = {
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": limit,
                "page": 1,
            }
            resp = requests.get(url, params=params, timeout=15)
            data = resp.json()
            tickers = [f"{d['symbol'].upper()}-USD" for d in data]
            self._save_cache(cache_file, tickers)
            logger.info(f"Crypto top {limit} fetched: {len(tickers)} tickers")
            return tickers
        except Exception as e:
            logger.warning(f"Failed to fetch crypto: {e}")
            return [
                "BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD", "XRP-USD",
                "ADA-USD", "AVAX-USD", "DOGE-USD", "DOT-USD", "MATIC-USD",
                "LINK-USD", "LTC-USD", "BCH-USD", "XLM-USD", "UNI-USD",
                "ETC-USD", "FIL-USD", "ARB-USD", "OP-USD", "NEAR-USD",
            ]

    # ── Custom Ticker Management ─────────────────────────────

    def add_ticker(self, symbol: str, market_type: str, name: str = "") -> None:
        """Add a custom ticker to the universe."""
        self._custom_tickers[symbol] = TickerInfo(
            symbol=symbol,
            name=name,
            market_type=market_type,
            added_date=datetime.now().isoformat(),
            source="manual",
        )
        self._save_custom_tickers()
        logger.info(f"Added ticker: {symbol} ({market_type})")

    def remove_ticker(self, symbol: str) -> None:
        """Remove a custom ticker."""
        if symbol in self._custom_tickers:
            del self._custom_tickers[symbol]
            self._save_custom_tickers()
            logger.info(f"Removed ticker: {symbol}")

    def list_custom_tickers(self) -> List[TickerInfo]:
        """List all custom tickers."""
        return list(self._custom_tickers.values())

    # ── Market Aggregator ─────────────────────────────────

    def get_market_tickers(self, market_type: str) -> List[str]:
        """Get all tickers for a market."""
        if market_type == "us_equity":
            return self.get_all_us_stocks()
        elif market_type == "ihsg":
            return self.get_all_ihsg()
        elif market_type == "crypto":
            return self.get_top_crypto(100)
        elif market_type == "forex":
            return self.get_forex_pairs()
        elif market_type == "commodity":
            return self.get_commodity_tickers()
        return []

    def get_forex_pairs(self) -> List[str]:
        """Major + minor + exotic forex pairs (Yahoo Finance format)."""
        majors = [
            "EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCHF=X",
            "AUDUSD=X", "USDCAD=X", "NZDUSD=X",
        ]
        minors = [
            "EURGBP=X", "EURJPY=X", "GBPJPY=X", "EURCHF=X",
            "EURAUD=X", "GBPAUD=X", "CADJPY=X", "CHFJPY=X",
        ]
        exotics = [
            "USDMXN=X", "USDSGD=X", "USDZAR=X", "USDCNH=X",
            "USDTRY=X", "USDSEK=X", "USDNOK=X", "USDDKK=X",
        ]
        return majors + minors + exotics

    def get_commodity_tickers(self) -> List[str]:
        """Commodity futures tickers (Yahoo Finance format)."""
        return [
            "GC=F",   # Gold
            "SI=F",   # Silver
            "CL=F",   # Crude Oil (WTI)
            "BZ=F",   # Brent Oil
            "NG=F",   # Natural Gas
            "HG=F",   # Copper
            "PL=F",   # Platinum
            "PA=F",   # Palladium
            "ZC=F",   # Corn
            "ZW=F",   # Wheat
            "ZS=F",   # Soybeans
            "KC=F",   # Coffee
            "CT=F",   # Cotton
            "CC=F",   # Cocoa
            "SB=F",   # Sugar
            "LB=F",   # Lumber
        ]

    # ── Discovery ──────────────────────────────────────────

    def discover_us_tickers(self, query: str) -> List[dict]:
        """Search for US ticker symbols using Yahoo Finance search."""
        try:
            ticker = yf.Ticker(query)
            info = ticker.info
            if info and "symbol" in info:
                return [{
                    "symbol": info.get("symbol"),
                    "name": info.get("longName", ""),
                    "sector": info.get("sector", ""),
                }]
        except Exception:
            pass
        return []

    # ── Cache Helpers ────────────────────────────────────────

    def _is_cache_valid(self, path: str) -> bool:
        if not os.path.exists(path):
            return False
        age = time.time() - os.path.getmtime(path)
        return age < CACHE_TTL

    def _load_cache(self, path: str) -> List[str]:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_cache(self, path: str, data: List[str]) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _load_custom_tickers(self) -> None:
        path = os.path.join(self.cache_dir, "custom_tickers.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._custom_tickers = {
                        k: TickerInfo.from_dict(v) for k, v in data.items()
                    }
            except Exception as e:
                logger.warning(f"Failed to load custom tickers: {e}")
                self._custom_tickers = {}

    def _save_custom_tickers(self) -> None:
        path = os.path.join(self.cache_dir, "custom_tickers.json")
        with open(path, "w", encoding="utf-8") as f:
            data = {k: v.to_dict() for k, v in self._custom_tickers.items()}
            json.dump(data, f, indent=2)

    def clear_cache(self) -> None:
        """Clear all cached ticker lists."""
        for fname in os.listdir(self.cache_dir):
            if fname.endswith(".json") and fname != "custom_tickers.json":
                os.remove(os.path.join(self.cache_dir, fname))
        logger.info("Cache cleared")
