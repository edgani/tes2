"""engines/cftc_cot_scraper.py — CFTC Commitment of Traders Scraper v1.0

Fetches COT data from CFTC.gov (public, free):
  - Non-commercial (speculator) positioning
  - Commercial (hedger) positioning
  - Retail (non-reportable) positioning
  - Historical extremes and signals

Usage:
    from engines.cftc_cot_scraper import CFTCCOTScraper
    scraper = CFTCCOTScraper()

    # Get latest COT for EUR/USD
    eur_cot = scraper.get_cot("EUR/USD")
    print(f"Non-com net: {eur_cot['non_commercial']['net']}")

    # Get all COT signals
    signals = scraper.get_all_signals()

    # Get institutional flow summary
    summary = scraper.get_institutional_flow_summary()
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CFTC report URLs (legacy format — most widely used)
# Each exchange has its own report page
# ---------------------------------------------------------------------------
CFTC_LEGACY_URLS = {
    "CMX": "https://www.cftc.gov/dea/futures/deacmxsf.htm",   # Metals (Gold, Silver, Copper)
    "NYME": "https://www.cftc.gov/dea/futures/deanymesf.htm",  # Energy (Crude Oil, NatGas)
    "CME": "https://www.cftc.gov/dea/futures/deacmesf.htm",   # Currencies, Indices, Crypto, Rates
    "CBT": "https://www.cftc.gov/dea/futures/deacbtsf.htm",   # Treasuries, Agriculture
}

# Product CFTC codes we care about
PRODUCT_CODES: Dict[str, str] = {
    "EUR/USD": "099741",
    "GBP/USD": "096742",
    "JPY/USD": "097741",
    "CHF/USD": "092741",
    "AUD/USD": "232741",
    "CAD/USD": "090741",
    "NZD/USD": "112741",
    "MXN/USD": "095741",
    "BRL/USD": "102741",
    "GOLD": "088691",
    "SILVER": "084691",
    "COPPER": "085692",
    "PLATINUM": "076651",
    "CRUDE_OIL_WTI": "067651",
    "CRUDE_OIL_BRENT": "06765T",
    "GASOLINE_RBOB": "111659",
    "NATGAS": "023651",
    "SP500": "13874A",
    "SP500_CONSOLIDATED": "13874+",
    "NASDAQ": "209742",
    "NASDAQ_CONSOLIDATED": "20974+",
    "RUSSELL2000": "239742",
    "DJIA": "124603",
    "VIX": "1170E1",
    "BITCOIN": "133741",
    "BITCOIN_MICRO": "133742",
    "ETH": "146021",
    "ETH_MICRO": "146022",
    "XRP": "176740",
    "SOL": "177741",
    "UST_10Y": "043602",
    "UST_2Y": "042601",
    "UST_5Y": "044601",
    "UST_30Y": "020601",
    "SOFR_3M": "134741",
    "FEDFUNDS": "045601",
}

# Human-readable names for display
PRODUCT_NAMES: Dict[str, str] = {
    "099741": "EUR/USD",
    "096742": "GBP/USD",
    "097741": "JPY/USD",
    "092741": "CHF/USD",
    "232741": "AUD/USD",
    "090741": "CAD/USD",
    "112741": "NZD/USD",
    "095741": "MXN/USD",
    "102741": "BRL/USD",
    "088691": "GOLD",
    "084691": "SILVER",
    "085692": "COPPER",
    "076651": "PLATINUM",
    "067651": "CRUDE_OIL_WTI",
    "06765T": "CRUDE_OIL_BRENT",
    "111659": "GASOLINE_RBOB",
    "023651": "NATGAS",
    "13874A": "SP500",
    "13874+": "SP500_CONSOLIDATED",
    "209742": "NASDAQ",
    "20974+": "NASDAQ_CONSOLIDATED",
    "239742": "RUSSELL2000",
    "124603": "DJIA",
    "133741": "BITCOIN",
    "133742": "BITCOIN_MICRO",
    "146021": "ETH",
    "146022": "ETH_MICRO",
    "176740": "XRP",
    "177741": "SOL",
    "043602": "UST_10Y",
    "042601": "UST_2Y",
    "044601": "UST_5Y",
    "020601": "UST_30Y",
    "134741": "SOFR_3M",
    "045601": "FEDFUNDS",
}

# Reverse lookup: CFTC code -> product key
# (built at import time from PRODUCT_CODES)

# Percentile thresholds for extreme positioning
EXTREME_LONG_THRESHOLD = 90   # 90th percentile = extreme bullish
EXTREME_SHORT_THRESHOLD = 10  # 10th percentile = extreme bearish

# Historical net position baselines (approximate 5-year ranges for context)
# These serve as fallback when we don't have enough history
HISTORICAL_BASELINES: Dict[str, Dict[str, Tuple[int, int]]] = {
    # product: (min_net_5y, max_net_5y)
    "EUR/USD": {"non_commercial": (-150000, 150000), "commercial": (-400000, 400000)},
    "GBP/USD": {"non_commercial": (-120000, 50000), "commercial": (-200000, 300000)},
    "JPY/USD": {"non_commercial": (-250000, 50000), "commercial": (-200000, 400000)},
    "AUD/USD": {"non_commercial": (-100000, 150000), "commercial": (-300000, 200000)},
    "GOLD": {"non_commercial": (-100000, 300000), "commercial": (-400000, 100000)},
    "SILVER": {"non_commercial": (-50000, 80000), "commercial": (-100000, 50000)},
    "CRUDE_OIL_WTI": {"non_commercial": (-400000, 500000), "commercial": (-600000, 500000)},
    "SP500": {"non_commercial": (-500000, 200000), "commercial": (-1000000, 1000000)},
    "NASDAQ": {"non_commercial": (-100000, 50000), "commercial": (-200000, 200000)},
    "BITCOIN": {"non_commercial": (-5000, 15000), "commercial": (-5000, 5000)},
    "UST_10Y": {"non_commercial": (-1000000, 500000), "commercial": (-2000000, 3000000)},
}


@dataclass
class COTReport:
    """Single COT report for one product."""
    product: str           # e.g. "EUR/USD"
    cftc_code: str         # e.g. "099741"
    report_date: str       # YYYY-MM-DD
    exchange: str          # e.g. "CME"

    # Position data
    non_commercial_long: int = 0
    non_commercial_short: int = 0
    non_commercial_spreads: int = 0
    commercial_long: int = 0
    commercial_short: int = 0
    total_reportable_long: int = 0
    total_reportable_short: int = 0
    non_reportable_long: int = 0
    non_reportable_short: int = 0
    open_interest: int = 0

    # Weekly changes
    change_non_commercial_long: int = 0
    change_non_commercial_short: int = 0
    change_commercial_long: int = 0
    change_commercial_short: int = 0
    change_non_reportable_long: int = 0
    change_non_reportable_short: int = 0

    # Number of traders
    traders_non_commercial_long: int = 0
    traders_non_commercial_short: int = 0
    traders_commercial_long: int = 0
    traders_commercial_short: int = 0
    traders_total: int = 0

    @property
    def non_commercial_net(self) -> int:
        return self.non_commercial_long - self.non_commercial_short

    @property
    def commercial_net(self) -> int:
        return self.commercial_long - self.commercial_short

    @property
    def non_reportable_net(self) -> int:
        return self.non_reportable_long - self.non_reportable_short

    def to_dict(self) -> Dict:
        return {
            "product": self.product,
            "cftc_code": self.cftc_code,
            "date": self.report_date,
            "exchange": self.exchange,
            "open_interest": self.open_interest,
            "non_commercial": {
                "long": self.non_commercial_long,
                "short": self.non_commercial_short,
                "spreads": self.non_commercial_spreads,
                "net": self.non_commercial_net,
                "change_long": self.change_non_commercial_long,
                "change_short": self.change_non_commercial_short,
                "pct_oi": round(self.non_commercial_long / self.open_interest * 100, 1) if self.open_interest else 0.0,
            },
            "commercial": {
                "long": self.commercial_long,
                "short": self.commercial_short,
                "net": self.commercial_net,
                "change_long": self.change_commercial_long,
                "change_short": self.change_commercial_short,
            },
            "non_reportable": {
                "long": self.non_reportable_long,
                "short": self.non_reportable_short,
                "net": self.non_reportable_net,
                "change_long": self.change_non_reportable_long,
                "change_short": self.change_non_reportable_short,
            },
            "traders": {
                "non_commercial_long": self.traders_non_commercial_long,
                "non_commercial_short": self.traders_non_commercial_short,
                "commercial_long": self.traders_commercial_long,
                "commercial_short": self.traders_commercial_short,
                "total": self.traders_total,
            },
        }


class CFTCCOTScraper:
    """Scrape CFTC COT legacy reports from CFTC.gov (free, public, no login).

    Reports are published every Friday at 3:30 PM ET, covering positions as of
    the preceding Tuesday.  The data is in fixed-width text inside <pre> tags.
    """

    def __init__(self, delay: float = 1.0):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "MacroRegime/1.0 (Research/Data Analysis)"
        })
        self.delay = delay
        self._cache: Dict[str, COTReport] = {}
        self._cache_time: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_date(date_str: str) -> str:
        """Convert CFTC date format MM/DD/YY to YYYY-MM-DD."""
        try:
            # CFTC uses 2-digit year, e.g. 05/19/26
            dt = datetime.strptime(date_str.strip(), "%m/%d/%y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return date_str

    def _fetch_page(self, url: str) -> Optional[str]:
        """Fetch raw HTML from a CFTC page."""
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            time.sleep(self.delay)
            return resp.text
        except Exception as exc:
            logger.warning(f"Failed to fetch {url}: {exc}")
            return None

    @staticmethod
    def _extract_pre_text(html: str) -> str:
        """Extract the raw fixed-width text from the <pre> tag."""
        soup = BeautifulSoup(html, "html.parser")
        pre = soup.find("pre")
        if pre:
            return pre.get_text()
        # Fallback: return the whole text if no <pre>
        return soup.get_text()

    def _parse_report_page(self, html: str, exchange: str) -> Dict[str, COTReport]:
        """Parse one exchange page and return {cftc_code: COTReport}."""
        text = self._extract_pre_text(html)
        products: Dict[str, COTReport] = {}

        # Split text into product sections line-by-line
        # Each product starts with a header line containing "Code-XXXXXX"
        sections = self._split_into_product_sections(text)

        for section in sections:
            report = self._parse_product_section(section, exchange)
            if report and report.cftc_code:
                products[report.cftc_code] = report

        return products

    @staticmethod
    def _split_into_product_sections(text: str) -> List[str]:
        """Split CFTC report text into individual product sections.

        Each product section starts with a line containing "Code-XXXXXX"
        where X is a digit (optionally followed by a letter like 'A', '+', etc.)
        """
        lines = text.splitlines()
        sections: List[str] = []
        current: List[str] = []

        for line in lines:
            # Check if this line starts a new product
            if re.search(r'Code-\d{5,6}[A-Z+]?', line):
                # Save previous section if it has content
                if current:
                    sections.append('\n'.join(current))
                current = [line]
            else:
                current.append(line)

        # Don't forget the last section
        if current:
            sections.append('\n'.join(current))

        return sections

    def _parse_product_section(self, section: str, exchange: str) -> Optional[COTReport]:
        """Parse a single product section from the CFTC report."""
        lines = [ln.rstrip() for ln in section.splitlines()]
        if not lines:
            return None

        # Extract CFTC code from first line:  "... Code-099741" or "Code-13874+"
        # Codes are 5-6 digits, optionally followed by a letter (A, T) or +
        code_match = re.search(r'Code-(\d{5,6}[A-Z+]?)', lines[0])
        if not code_match:
            return None
        cftc_code = code_match.group(1)

        # Parse report date
        report_date = ""
        date_match = re.search(r'FUTURES ONLY POSITIONS AS OF\s+(\d{2}/\d{2}/\d{2})', section)
        if date_match:
            report_date = self._parse_date(date_match.group(1))

        # Look up product name
        product_name = PRODUCT_NAMES.get(cftc_code, cftc_code)

        # Extract Open Interest
        oi = 0
        oi_match = re.search(r'OPEN INTEREST:\s+([\d,]+)', section)
        if oi_match:
            oi = int(oi_match.group(1).replace(',', ''))

        # Find the COMMITMENTS line and the numeric line after it
        commitments: Dict[str, int] = {}
        changes: Dict[str, int] = {}

        for i, line in enumerate(lines):
            if line.strip() == "COMMITMENTS":
                if i + 1 < len(lines):
                    commitments = self._parse_data_line(lines[i + 1])
            if "CHANGES FROM" in line:
                if i + 1 < len(lines):
                    changes = self._parse_data_line(lines[i + 1])

        # Extract number of traders
        traders_nc_long = 0
        traders_nc_short = 0
        traders_comm_long = 0
        traders_comm_short = 0
        traders_total = 0

        for i, line in enumerate(lines):
            if "NUMBER OF TRADERS IN EACH CATEGORY" in line:
                # Next line has the numbers: "     87       53       33      139       96      238      171"
                if i + 1 < len(lines):
                    vals = self._parse_traders_line(lines[i + 1])
                    if len(vals) >= 7:
                        traders_nc_long, traders_nc_short, _spreads, \
                        traders_comm_long, traders_comm_short, _total1, _total2 = vals[:7]
                        traders_total = vals[6] if len(vals) > 6 else 0

        if not commitments:
            return None

        report = COTReport(
            product=product_name,
            cftc_code=cftc_code,
            report_date=report_date,
            exchange=exchange,
            non_commercial_long=commitments.get("nc_long", 0),
            non_commercial_short=commitments.get("nc_short", 0),
            non_commercial_spreads=commitments.get("nc_spreads", 0),
            commercial_long=commitments.get("comm_long", 0),
            commercial_short=commitments.get("comm_short", 0),
            total_reportable_long=commitments.get("total_long", 0),
            total_reportable_short=commitments.get("total_short", 0),
            non_reportable_long=commitments.get("nr_long", 0),
            non_reportable_short=commitments.get("nr_short", 0),
            open_interest=oi,
            change_non_commercial_long=changes.get("nc_long", 0),
            change_non_commercial_short=changes.get("nc_short", 0),
            change_commercial_long=changes.get("comm_long", 0),
            change_commercial_short=changes.get("comm_short", 0),
            change_non_reportable_long=changes.get("nr_long", 0),
            change_non_reportable_short=changes.get("nr_short", 0),
            traders_non_commercial_long=traders_nc_long,
            traders_non_commercial_short=traders_nc_short,
            traders_commercial_long=traders_comm_long,
            traders_commercial_short=traders_comm_short,
            traders_total=traders_total,
        )
        return report

    @staticmethod
    def _parse_data_line(line: str) -> Dict[str, int]:
        """Parse a numeric data line with 9 columns.

        CFTC legacy format has 9 numeric fields:
          NC Long | NC Short | NC Spreads | Comm Long | Comm Short | Total Long | Total Short | NR Long | NR Short
        """
        # Replace commas and handle parentheses for negative numbers
        cleaned = line.replace(',', '').replace('(', '-').replace(')', '')
        # Extract all numbers (including negative)
        numbers = re.findall(r'-?\d+', cleaned)
        if len(numbers) < 9:
            return {}
        try:
            vals = [int(n) for n in numbers[:9]]
            return {
                "nc_long": vals[0],
                "nc_short": vals[1],
                "nc_spreads": vals[2],
                "comm_long": vals[3],
                "comm_short": vals[4],
                "total_long": vals[5],
                "total_short": vals[6],
                "nr_long": vals[7],
                "nr_short": vals[8],
            }
        except (ValueError, IndexError):
            return {}

    @staticmethod
    def _parse_traders_line(line: str) -> List[int]:
        """Parse the traders count line."""
        cleaned = line.replace(',', '')
        numbers = re.findall(r'\d+', cleaned)
        return [int(n) for n in numbers]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_all_reports(self) -> Dict[str, COTReport]:
        """Fetch and parse COT reports from all exchanges.

        Returns a dict keyed by CFTC code with the latest report for each product.
        """
        all_reports: Dict[str, COTReport] = {}

        for exchange, url in CFTC_LEGACY_URLS.items():
            logger.info(f"Fetching COT data for {exchange}...")
            html = self._fetch_page(url)
            if html:
                reports = self._parse_report_page(html, exchange)
                all_reports.update(reports)
                logger.info(f"  {exchange}: parsed {len(reports)} products")
            else:
                logger.warning(f"  {exchange}: FAILED to fetch")

        self._cache = all_reports
        self._cache_time = datetime.now()
        return all_reports

    def get_cot(self, product: str) -> Optional[Dict]:
        """Get COT data for a specific product by name (e.g. 'EUR/USD') or CFTC code.

        Returns None if the product is not found.
        """
        # Refresh cache if stale (> 24 hours)
        if self._cache_time is None or (datetime.now() - self._cache_time) > timedelta(hours=24):
            self.fetch_all_reports()

        # Resolve product name to CFTC code
        cftc_code = PRODUCT_CODES.get(product, product)

        report = self._cache.get(cftc_code)
        if report is None:
            return None
        return report.to_dict()

    def get_signal(self, product: str) -> Optional[Dict]:
        """Generate a trading signal from COT positioning data.

        Logic (contrarian on non-commercial / speculator extremes):
          - Non-commercial net > 90th percentile of range → BEARISH (contrarian)
          - Non-commercial net < 10th percentile of range → BULLISH (contrarian)
          - Commercial net opposite to non-commercial → CONFIRM
          - Non-reportable (retail) usually wrong → fade retail

        Returns a dict with signal, retail sentiment, institutional extreme flag.
        """
        cot = self.get_cot(product)
        if cot is None:
            return None

        nc_net = cot["non_commercial"]["net"]
        comm_net = cot["commercial"]["net"]
        nr_net = cot["non_reportable"]["net"]
        oi = cot.get("open_interest", 1)

        # Get historical baselines for this product
        baselines = HISTORICAL_BASELINES.get(product, {})
        nc_range = baselines.get("non_commercial", (-abs(nc_net) * 2, abs(nc_net) * 2))
        nc_min, nc_max = nc_range

        # Normalize net position to percentile (0-100)
        range_span = nc_max - nc_min
        if range_span > 0:
            nc_percentile = max(0, min(100, (nc_net - nc_min) / range_span * 100))
        else:
            nc_percentile = 50.0

        # Determine signal (contrarian on non-commercial extremes)
        signal = "NEUTRAL"
        signal_strength = "MODERATE"

        if nc_percentile >= EXTREME_LONG_THRESHOLD:
            signal = "BEARISH"
            signal_strength = "EXTREME" if nc_percentile >= 95 else "STRONG"
        elif nc_percentile <= EXTREME_SHORT_THRESHOLD:
            signal = "BULLISH"
            signal_strength = "EXTREME" if nc_percentile <= 5 else "STRONG"
        elif nc_percentile >= 60:
            signal = "MILD_BEARISH"
            signal_strength = "MODERATE"
        elif nc_percentile <= 40:
            signal = "MILD_BULLISH"
            signal_strength = "MODERATE"

        # Commercial confirmation: commercial net opposite direction to speculators
        commercial_bias = "NEUTRAL"
        if abs(comm_net) > abs(nc_net) * 0.3:
            if (comm_net > 0 and nc_net < 0) or (comm_net < 0 and nc_net > 0):
                commercial_bias = "CONTRARIAN_CONFIRM"
            elif (comm_net > 0 and nc_net > 0) or (comm_net < 0 and nc_net < 0):
                commercial_bias = "CONTRARIAN_DIVERGE"

        # Retail sentiment: retail is usually wrong
        retail_sentiment = "NEUTRAL"
        if nr_net > 0:
            retail_sentiment = "CONTRARIAN_BEARISH"  # retail long = bearish for price
        elif nr_net < 0:
            retail_sentiment = "CONTRARIAN_BULLISH"  # retail short = bullish for price

        # Institutional extreme flag
        institutional_extreme = nc_percentile >= EXTREME_LONG_THRESHOLD or nc_percentile <= EXTREME_SHORT_THRESHOLD

        # Composite score (-100 to +100, positive = bullish)
        composite_score = 50 - nc_percentile  # contrarian: high spec long = negative score
        if commercial_bias == "CONTRARIAN_CONFIRM":
            composite_score *= 1.3  # Boost signal when commercials confirm
        composite_score = max(-100, min(100, composite_score))

        return {
            "product": product,
            "date": cot["date"],
            "signal": signal,
            "signal_strength": signal_strength,
            "composite_score": round(composite_score, 1),
            "non_commercial_percentile": round(nc_percentile, 1),
            "non_commercial_net": nc_net,
            "commercial_net": comm_net,
            "commercial_bias": commercial_bias,
            "retail_sentiment": retail_sentiment,
            "retail_net": nr_net,
            "institutional_extreme": institutional_extreme,
            "open_interest": oi,
            "traders_total": cot.get("traders", {}).get("total", 0),
        }

    def get_all_signals(self, products: Optional[List[str]] = None) -> Dict[str, Dict]:
        """Get COT signals for all (or specified) tracked products.

        Returns {product_name: signal_dict}
        """
        targets = products or list(PRODUCT_CODES.keys())
        results: Dict[str, Dict] = {}
        for product in targets:
            sig = self.get_signal(product)
            if sig:
                results[product] = sig
        return results

    def get_institutional_flow_summary(self) -> Dict:
        """Aggregate summary across major asset classes.

        Returns a high-level view of institutional positioning by sector:
          - USD sentiment (from currency futures)
          - Risk asset sentiment (equity indices)
          - Commodity sentiment (Gold, Oil)
          - Crypto sentiment
          - Treasury/Bond sentiment
        """
        signals = self.get_all_signals()

        def avg_score(products: List[str]) -> float:
            scores = [signals[p]["composite_score"] for p in products if p in signals]
            return round(sum(scores) / len(scores), 1) if scores else 0.0

        def sentiment_label(score: float) -> str:
            if score >= 30:
                return "BULLISH"
            elif score >= 10:
                return "MILD_BULLISH"
            elif score <= -30:
                return "BEARISH"
            elif score <= -10:
                return "MILD_BEARISH"
            return "NEUTRAL"

        # USD sentiment (contrarian on USD futures positioning)
        # Non-commercial long USD futures = commercial hedgers short USD = bearish for USD
        usd_pairs = ["EUR/USD", "GBP/USD", "JPY/USD", "AUD/USD", "CAD/USD", "CHF/USD"]
        usd_score = -avg_score(usd_pairs)  # invert: bearish EUR = bullish USD
        usd_sentiment = sentiment_label(usd_score)

        # Risk assets (equity indices)
        equity_products = ["SP500", "NASDAQ", "RUSSELL2000"]
        equity_score = avg_score(equity_products)
        equity_sentiment = sentiment_label(equity_score)

        # Commodities
        commodity_products = ["GOLD", "SILVER", "CRUDE_OIL_WTI", "COPPER"]
        commodity_score = avg_score(commodity_products)
        commodity_sentiment = sentiment_label(commodity_score)

        # Crypto
        crypto_products = ["BITCOIN", "ETH"]
        crypto_score = avg_score(crypto_products)
        crypto_sentiment = sentiment_label(crypto_score)

        # Treasuries (contrarian: speculators net short = bullish for bonds = yields fall)
        treasury_products = ["UST_10Y", "UST_2Y", "UST_5Y", "UST_30Y"]
        treasury_score = -avg_score(treasury_products)  # invert: spec short bonds = bullish bonds
        treasury_sentiment = sentiment_label(treasury_score)

        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "usd_sentiment": usd_sentiment,
            "usd_score": usd_score,
            "equity_sentiment": equity_sentiment,
            "equity_score": equity_score,
            "commodity_sentiment": commodity_sentiment,
            "commodity_score": commodity_score,
            "crypto_sentiment": crypto_sentiment,
            "crypto_score": crypto_score,
            "treasury_sentiment": treasury_sentiment,
            "treasury_score": treasury_score,
            "risk_on_off": "RISK_ON" if equity_score > 10 and usd_score < -10 else (
                "RISK_OFF" if equity_score < -10 and usd_score > 10 else "MIXED"
            ),
            "individual_signals": {
                k: {"signal": v["signal"], "score": v["composite_score"], "net": v["non_commercial_net"]}
                for k, v in signals.items()
            },
        }

    def get_crowded_trades(self) -> List[Dict]:
        """Identify the most crowded (extreme) trades right now.

        Returns products where non-commercial positioning is at extremes,
        sorted by how extreme the positioning is.
        """
        signals = self.get_all_signals()
        crowded = []
        for product, sig in signals.items():
            if sig["institutional_extreme"]:
                crowded.append({
                    "product": product,
                    "signal": sig["signal"],
                    "non_commercial_net": sig["non_commercial_net"],
                    "commercial_net": sig["commercial_net"],
                    "percentile": sig["non_commercial_percentile"],
                    "composite_score": sig["composite_score"],
                    "date": sig["date"],
                })
        # Sort by distance from 50th percentile
        crowded.sort(key=lambda x: abs(x["percentile"] - 50), reverse=True)
        return crowded


# ---------------------------------------------------------------------------
# Convenience module-level functions (stateless)
# ---------------------------------------------------------------------------

_scraper_instance: Optional[CFTCCOTScraper] = None


def _get_scraper() -> CFTCCOTScraper:
    global _scraper_instance
    if _scraper_instance is None:
        _scraper_instance = CFTCCOTScraper()
    return _scraper_instance


def get_cot(product: str) -> Optional[Dict]:
    """Module-level convenience: get COT data for a product."""
    return _get_scraper().get_cot(product)


def get_signal(product: str) -> Optional[Dict]:
    """Module-level convenience: get COT signal for a product."""
    return _get_scraper().get_signal(product)


def get_all_signals(products: Optional[List[str]] = None) -> Dict[str, Dict]:
    """Module-level convenience: get all COT signals."""
    return _get_scraper().get_all_signals(products)


def get_institutional_flow_summary() -> Dict:
    """Module-level convenience: get institutional flow summary."""
    return _get_scraper().get_institutional_flow_summary()


def get_crowded_trades() -> List[Dict]:
    """Module-level convenience: get crowded trades."""
    return _get_scraper().get_crowded_trades()


# ---------------------------------------------------------------------------
# __main__ quick test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scraper = CFTCCOTScraper()

    print("=" * 60)
    print("CFTC COT Scraper — Functional Test")
    print("=" * 60)

    reports = scraper.fetch_all_reports()
    print(f"\nFetched {len(reports)} total products from all exchanges")

    # Show a few key products
    for prod_key in ["EUR/USD", "GOLD", "SP500", "BITCOIN", "UST_10Y"]:
        code = PRODUCT_CODES.get(prod_key, prod_key)
        if code in reports:
            r = reports[code]
            print(f"\n{prod_key} ({r.cftc_code}) as of {r.report_date}:")
            print(f"  Non-Commercial Net: {r.non_commercial_net:+,}")
            print(f"  Commercial Net:     {r.commercial_net:+,}")
            print(f"  Non-Reportable Net: {r.non_reportable_net:+,}")
            print(f"  Open Interest:      {r.open_interest:,}")

    # Show signals
    print("\n" + "=" * 60)
    print("COT Signals")
    print("=" * 60)
    for prod_key in ["EUR/USD", "GOLD", "SP500", "BITCOIN"]:
        sig = scraper.get_signal(prod_key)
        if sig:
            print(f"\n{prod_key}: {sig['signal']} (score={sig['composite_score']}, "
                  f"pctile={sig['non_commercial_percentile']})")
            print(f"  NC net={sig['non_commercial_net']:,}, "
                  f"Comm net={sig['commercial_net']:,}, "
                  f"Retail={sig['retail_sentiment']}")

    # Summary
    print("\n" + "=" * 60)
    print("Institutional Flow Summary")
    print("=" * 60)
    summary = scraper.get_institutional_flow_summary()
    for key, val in summary.items():
        if key != "individual_signals":
            print(f"  {key}: {val}")
