"""engines/barchart_scraper.py — Barchart Options Data Scraper v1.0

Scrapes real options data from Barchart.com to enrich GreeksProxy:
  - Gamma Exposure (GEX): flip point, call wall, put wall
  - Max Pain: per expiration
  - Expected Move: $ and % per expiration
  - Put/Call Ratio: volume and OI ratios
  - IV Term Structure: implied vol, historical vol, IV rank, IV percentile

Usage:
    from engines.barchart_scraper import BarchartScraper, BarchartOptionsData
    scraper = BarchartScraper(delay=1.0)
    data = scraper.scrape_ticker("AAPL")
    print(data.gamma_flip, data.call_wall, data.put_wall)

    # Batch scrape
    results = scraper.scrape_multi(["SPY", "QQQ", "AAPL"])
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
BASE_TICKER_URL = "https://www.barchart.com/stocks/quotes/{ticker}"

# Page path suffixes
GAMMA_EXPOSURE_PATH = "gamma-exposure"
MAX_PAIN_PATH = "max-pain-chart"
EXPECTED_MOVE_PATH = "expected-move"
PUT_CALL_RATIO_PATH = "put-call-ratios"
VOLATILITY_CHARTS_PATH = "volatility-charts"

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY = 2.0


@dataclass
class ExpectedMove:
    """Expected move for a single expiration."""
    expiration: str = ""
    dte: int = 0
    price: float = 0.0
    move: float = 0.0
    move_pct: float = 0.0
    upper_price: float = 0.0
    lower_price: float = 0.0
    total_oi: int = 0
    iv: float = 0.0


@dataclass
class PutCallRatio:
    """Put/Call ratio data for a single expiration."""
    expiration: str = ""
    dte: int = 0
    put_vol: int = 0
    call_vol: int = 0
    total_vol: int = 0
    put_call_vol_ratio: float = 0.0
    put_oi: int = 0
    call_oi: int = 0
    total_oi: int = 0
    put_call_oi_ratio: float = 0.0
    iv: float = 0.0


@dataclass
class MaxPainEntry:
    """Max pain price for a single expiration."""
    expiration: str = ""
    dte: int = 0
    max_pain_price: float = 0.0


@dataclass
class BarchartOptionsData:
    """Container for all scraped options data for a single ticker."""
    ticker: str = ""

    # Gamma exposure
    gamma_flip: Optional[float] = None
    call_wall: Optional[float] = None
    put_wall: Optional[float] = None

    # IV / HV metrics (common across pages)
    iv: Optional[float] = None
    hv: Optional[float] = None
    iv_rank: Optional[float] = None
    iv_percentile: Optional[float] = None

    # Max pain per expiration
    max_pain_entries: List[MaxPainEntry] = field(default_factory=list)

    # Put/Call ratios
    put_call_ratios: List[PutCallRatio] = field(default_factory=list)

    # Expected moves per expiration
    expected_moves: List[ExpectedMove] = field(default_factory=list)

    # Earnings history moves
    earnings_moves: List[Dict] = field(default_factory=list)
    avg_earnings_move: Optional[float] = None

    # Metadata
    latest_earnings: Optional[str] = None
    scraped_at: Optional[str] = None
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Serialize to plain dict for JSON/JSONL compatibility."""
        return {
            "ticker": self.ticker,
            "gamma_flip": self.gamma_flip,
            "call_wall": self.call_wall,
            "put_wall": self.put_wall,
            "iv": self.iv,
            "hv": self.hv,
            "iv_rank": self.iv_rank,
            "iv_percentile": self.iv_percentile,
            "max_pain": [
                {"expiration": e.expiration, "dte": e.dte, "max_pain_price": e.max_pain_price}
                for e in self.max_pain_entries
            ],
            "put_call_ratios": [
                {
                    "expiration": p.expiration,
                    "dte": p.dte,
                    "put_vol": p.put_vol,
                    "call_vol": p.call_vol,
                    "total_vol": p.total_vol,
                    "put_call_vol_ratio": p.put_call_vol_ratio,
                    "put_oi": p.put_oi,
                    "call_oi": p.call_oi,
                    "total_oi": p.total_oi,
                    "put_call_oi_ratio": p.put_call_oi_ratio,
                    "iv": p.iv,
                }
                for p in self.put_call_ratios
            ],
            "expected_moves": [
                {
                    "expiration": e.expiration,
                    "dte": e.dte,
                    "price": e.price,
                    "move": e.move,
                    "move_pct": e.move_pct,
                    "upper_price": e.upper_price,
                    "lower_price": e.lower_price,
                    "total_oi": e.total_oi,
                    "iv": e.iv,
                }
                for e in self.expected_moves
            ],
            "earnings_moves": self.earnings_moves,
            "avg_earnings_move": self.avg_earnings_move,
            "latest_earnings": self.latest_earnings,
            "scraped_at": self.scraped_at,
            "errors": self.errors,
        }


class BarchartScraper:
    """Scrape options data from Barchart.com with polite rate limiting.

    Args:
        delay: Seconds to sleep between requests (default 1.0).
    """

    def __init__(self, delay: float = 1.0):
        self.delay = delay
        try:
            import requests
            self._session = requests.Session()
            self._session.headers.update(
                {
                    "User-Agent": USER_AGENT,
                    "Accept": (
                        "text/html,application/xhtml+xml,application/xml;"
                        "q=0.9,image/webp,*/*;q=0.8"
                    ),
                    "Accept-Language": "en-US,en;q=0.5",
                    "Accept-Encoding": "gzip, deflate, br",
                    "DNT": "1",
                    "Connection": "keep-alive",
                }
            )
            self._has_requests = True
        except Exception:
            self._has_requests = False
            logger.warning("requests library not available; scraper will not function")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _url(self, ticker: str, path: str) -> str:
        """Build full Barchart URL for a ticker + page path."""
        return f"{BASE_TICKER_URL.format(ticker=ticker.upper())}/{path}"

    def _fetch(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch page with retry logic and return parsed BeautifulSoup.

        Returns None on failure (logs error).
        """
        if not self._has_requests:
            return None

        import requests

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self._session.get(url, timeout=15)
                if resp.status_code == 200:
                    return BeautifulSoup(resp.text, "html.parser")
                if resp.status_code == 404:
                    logger.debug(f"Page not found: {url}")
                    return None
                logger.debug(f"HTTP {resp.status_code} for {url} (attempt {attempt})")
            except requests.RequestException as exc:
                logger.debug(f"Request error for {url} (attempt {attempt}): {exc}")

            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

        return None

    def _sleep(self) -> None:
        """Polite delay between requests."""
        if self.delay > 0:
            time.sleep(self.delay)

    @staticmethod
    def _text_near(soup: BeautifulSoup, keyword: str) -> str:
        """Get concatenated text from elements containing *keyword*."""
        texts = []
        for elem in soup.find_all(string=re.compile(keyword, re.IGNORECASE)):
            texts.append(str(elem).strip())
        return " ".join(texts)

    @staticmethod
    def _extract_number(text: str, pattern: str) -> Optional[float]:
        """Extract first float matching regex *pattern* from *text*."""
        match = re.search(pattern, text)
        if match:
            try:
                return float(match.group(1).replace(",", ""))
            except (ValueError, IndexError):
                pass
        return None

    @staticmethod
    def _parse_table(soup: BeautifulSoup, table_class: str = "") -> List[Dict[str, str]]:
        """Parse an HTML table into list of row dicts.

        Looks for tables with class containing *table_class* or any table
        with <thead> and <tbody> structure.
        """
        rows: List[Dict[str, str]] = []

        # Try to find tables by class or structure
        if table_class:
            tables = soup.find_all("table", class_=re.compile(table_class, re.I))
        else:
            tables = soup.find_all("table")

        for table in tables:
            headers: List[str] = []
            thead = table.find("thead")
            if thead:
                headers = [th.get_text(strip=True) for th in thead.find_all("th")]
            else:
                # First row might be headers
                first_row = table.find("tr")
                if first_row:
                    headers = [
                        th.get_text(strip=True) for th in first_row.find_all(["th", "td"])
                    ]

            tbody = table.find("tbody")
            row_elements = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]

            for tr in row_elements:
                cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                if not cells or not any(cells):
                    continue
                row_dict: Dict[str, str] = {}
                for i, cell in enumerate(cells):
                    key = headers[i] if i < len(headers) else f"col_{i}"
                    row_dict[key] = cell
                if row_dict:
                    rows.append(row_dict)

        return rows

    @staticmethod
    def _safe_float(val: str) -> Optional[float]:
        """Parse a string to float, handling $, %, commas, and parens."""
        if not val or val == "-" or val == "N/A":
            return None
        cleaned = (
            val.replace("$", "")
            .replace("%", "")
            .replace(",", "")
            .replace("(", "-")
            .replace(")", "")
            .strip()
        )
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe_int(val: str) -> Optional[int]:
        """Parse a string to int, handling commas."""
        if not val or val == "-" or val == "N/A":
            return None
        cleaned = val.replace(",", "").replace("$", "").replace("%", "").strip()
        try:
            return int(float(cleaned))
        except (ValueError, TypeError):
            return None

    def _extract_iv_stats(self, soup: BeautifulSoup) -> Dict[str, Optional[float]]:
        """Extract IV, HV, IV Rank, IV Percentile from soup.

        These appear in a stats bar near the top of options pages:
            Implied Volatility: 148.57%
            Historic Volatility: 121.47%
            IV Rank: 24.07%
            IV Percentile: 80%
        """
        out: Dict[str, Optional[float]] = {
            "iv": None,
            "hv": None,
            "iv_rank": None,
            "iv_percentile": None,
        }

        # Strategy 1: Look for specific label→value patterns in page text
        page_text = soup.get_text(separator=" ", strip=True)

        patterns = {
            "iv": r"Implied\s*Volatility[:\s]+(\d+\.?\d*)",
            "hv": r"Historic\s*Volatility[:\s]+(\d+\.?\d*)",
            "iv_rank": r"IV\s*Rank[:\s]+(\d+\.?\d*)",
            "iv_percentile": r"IV\s*Percentile[:\s]+(\d+\.?\d*)",
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                try:
                    out[key] = float(match.group(1))
                except (ValueError, IndexError):
                    pass

        # Strategy 2: Look in <div> elements with class containing "volatility" etc.
        if not any(v is not None for v in out.values()):
            for div in soup.find_all("div"):
                text = div.get_text(strip=True)
                if "Implied Volatility" in text and out["iv"] is None:
                    out["iv"] = self._extract_number(text, r"Implied\s*Volatility[:\s]+(\d+\.?\d*)")
                if "Historic Volatility" in text and out["hv"] is None:
                    out["hv"] = self._extract_number(text, r"Historic\s*Volatility[:\s]+(\d+\.?\d*)")
                if "IV Rank" in text and out["iv_rank"] is None:
                    out["iv_rank"] = self._extract_number(text, r"IV\s*Rank[:\s]+(\d+\.?\d*)")
                if "IV Percentile" in text and out["iv_percentile"] is None:
                    out["iv_percentile"] = self._extract_number(text, r"IV\s*Percentile[:\s]+(\d+\.?\d*)")

        return out

    def _extract_latest_earnings(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract latest earnings date from page text."""
        text = soup.get_text(separator=" ", strip=True)
        match = re.search(r"Latest\s*Earnings[:\s]+(\d{2}/\d{2}/\d{2})", text, re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    # ── Page scrapers ─────────────────────────────────────────────────────────

    def scrape_gamma_exposure(self, ticker: str) -> Dict[str, Optional[float]]:
        """Scrape Gamma Exposure page for GEX flip point, call wall, put wall, IV/HV.

        Returns dict with keys: gamma_flip, call_wall, put_wall, iv, hv, iv_rank,
        iv_percentile.
        """
        soup = self._fetch(self._url(ticker, GAMMA_EXPOSURE_PATH))
        if soup is None:
            logger.warning(f"Failed to fetch gamma exposure for {ticker}")
            return {}

        out: Dict[str, Optional[float]] = {}
        page_text = soup.get_text(separator=" ", strip=True)

        # Gamma flip point: "{TICKER} gamma flip point is X.XX"
        flip_match = re.search(
            rf"{re.escape(ticker.upper())}\s+gamma\s*flip\s*point\s+is\s+([\d.]+)",
            page_text, re.IGNORECASE,
        )
        if not flip_match:
            # Fallback: looser pattern
            flip_match = re.search(
                r"gamma\s*flip\s*point\s+is\s+([\d.]+)", page_text, re.IGNORECASE
            )
        if flip_match:
            out["gamma_flip"] = float(flip_match.group(1))

        # Put wall: "{TICKER} put wall is X.XX"
        put_wall_match = re.search(
            rf"{re.escape(ticker.upper())}\s+put\s+wall\s+is\s+([\d.]+)",
            page_text, re.IGNORECASE,
        )
        if not put_wall_match:
            put_wall_match = re.search(
                r"put\s+wall\s+is\s+([\d.]+)", page_text, re.IGNORECASE
            )
        if put_wall_match:
            out["put_wall"] = float(put_wall_match.group(1))

        # Call wall: "{TICKER} call wall is X.XX"
        call_wall_match = re.search(
            rf"{re.escape(ticker.upper())}\s+call\s+wall\s+is\s+([\d.]+)",
            page_text, re.IGNORECASE,
        )
        if not call_wall_match:
            call_wall_match = re.search(
                r"call\s+wall\s+is\s+([\d.]+)", page_text, re.IGNORECASE
            )
        if call_wall_match:
            out["call_wall"] = float(call_wall_match.group(1))

        # IV / HV stats
        iv_stats = self._extract_iv_stats(soup)
        out.update(iv_stats)

        logger.info(
            f"{ticker} gamma-exposure: flip={out.get('gamma_flip')}, "
            f"call_wall={out.get('call_wall')}, put_wall={out.get('put_wall')}, "
            f"iv={out.get('iv')}%, hv={out.get('hv')}%"
        )
        return out

    def scrape_max_pain(self, ticker: str) -> List[MaxPainEntry]:
        """Scrape Max Pain & Vol Skew page for max pain price per expiration.

        Returns list of MaxPainEntry dataclasses.
        """
        soup = self._fetch(self._url(ticker, MAX_PAIN_PATH))
        if soup is None:
            logger.warning(f"Failed to fetch max pain for {ticker}")
            return []

        entries: List[MaxPainEntry] = []

        # Parse the table
        rows = self._parse_table(soup)

        # Max pain data may appear in a table or embedded in chart data
        # Look for table rows that have expiration + max pain info
        for row in rows:
            # Common column name variations
            exp = (
                row.get("Expiration Date", "")
                or row.get("Expiration", "")
                or row.get("Date", "")
                or ""
            )
            if not exp:
                continue

            dte = self._safe_int(
                row.get("DTE", "") or row.get("Days", "") or "0"
            ) or 0

            # Max pain price column names
            max_pain_raw = (
                row.get("Max Pain", "")
                or row.get("Max Pain Price", "")
                or ""
            )
            max_pain = self._safe_float(max_pain_raw)

            if max_pain is not None:
                entries.append(
                    MaxPainEntry(
                        expiration=exp,
                        dte=dte,
                        max_pain_price=max_pain,
                    )
                )

        # Fallback: if no table data, try to extract from page text
        if not entries:
            page_text = soup.get_text(separator=" ", strip=True)
            # Look for patterns like "max pain" near dollar values
            max_pain_matches = re.findall(
                r"max\s*pain.*?\$?([\d.]+)", page_text, re.IGNORECASE
            )
            for i, mp in enumerate(max_pain_matches[:4]):  # Limit to first few
                try:
                    entries.append(
                        MaxPainEntry(
                            expiration=f"exp_{i}",
                            dte=0,
                            max_pain_price=float(mp),
                        )
                    )
                except ValueError:
                    pass

        logger.info(f"{ticker} max-pain: {len(entries)} expiration(s) found")
        return entries

    def scrape_expected_move(self, ticker: str) -> Dict:
        """Scrape Expected Move page for expected move per expiration + earnings data.

        Returns dict with keys: expected_moves (List[ExpectedMove]),
        earnings_moves (List[Dict]), avg_earnings_move (float).
        """
        soup = self._fetch(self._url(ticker, EXPECTED_MOVE_PATH))
        if soup is None:
            logger.warning(f"Failed to fetch expected move for {ticker}")
            return {}

        out: Dict = {"expected_moves": [], "earnings_moves": [], "avg_earnings_move": None}

        # --- Earnings move history ---
        page_text = soup.get_text(separator=" ", strip=True)

        # Pattern: "06/25/25: -3.78%  08/14/25: -1.33%  11/14/25: -9.56%"
        earnings_pattern = r"(\d{2}/\d{2}/\d{2})\s*[:\-]\s*([\-]?\d+\.?\d*)%"
        for match in re.finditer(earnings_pattern, page_text):
            out["earnings_moves"].append({
                "date": match.group(1),
                "move_pct": float(match.group(2)),
            })

        # Average move
        avg_match = re.search(
            r"Average\s*Move[:\s]+([\-]?\d+\.?\d*)%", page_text, re.IGNORECASE
        )
        if avg_match:
            out["avg_earnings_move"] = float(avg_match.group(1))

        # --- Expected move table ---
        rows = self._parse_table(soup)

        for row in rows:
            exp = (
                row.get("Expiration Date", "")
                or row.get("Expiration", "")
                or ""
            )
            if not exp:
                continue

            dte = self._safe_int(row.get("DTE", "") or "0") or 0
            price = self._safe_float(row.get("Price~", "") or row.get("Price", "") or "")
            move = self._safe_float(row.get("Expected Move", "") or "")
            move_pct = self._safe_float(row.get("Expected Move%", "") or row.get("Expected Move %", "") or "")
            upper = self._safe_float(row.get("Upper Price", "") or "")
            lower = self._safe_float(row.get("Lower Price", "") or "")
            total_oi = self._safe_int(row.get("Total OI", "") or row.get("TotalOI", "") or "")
            iv = self._safe_float(row.get("Implied Volatility", "") or row.get("IV", "") or "")

            out["expected_moves"].append(
                ExpectedMove(
                    expiration=exp,
                    dte=dte,
                    price=price or 0.0,
                    move=move or 0.0,
                    move_pct=move_pct or 0.0,
                    upper_price=upper or 0.0,
                    lower_price=lower or 0.0,
                    total_oi=total_oi or 0,
                    iv=iv or 0.0,
                )
            )

        logger.info(
            f"{ticker} expected-move: {len(out['expected_moves'])} expiration(s), "
            f"earnings history: {len(out['earnings_moves'])} events"
        )
        return out

    def scrape_put_call_ratio(self, ticker: str) -> List[PutCallRatio]:
        """Scrape Put/Call Ratio page for P/C ratio per expiration.

        Returns list of PutCallRatio dataclasses.
        """
        soup = self._fetch(self._url(ticker, PUT_CALL_RATIO_PATH))
        if soup is None:
            logger.warning(f"Failed to fetch put/call ratio for {ticker}")
            return []

        entries: List[PutCallRatio] = []
        rows = self._parse_table(soup)

        for row in rows:
            exp = (
                row.get("Expiration Date", "")
                or row.get("Expiration", "")
                or ""
            )
            if not exp:
                continue

            dte = self._safe_int(row.get("DTE", "") or "0") or 0
            put_vol = self._safe_int(row.get("Put Vol", "") or "") or 0
            call_vol = self._safe_int(row.get("Call Vol", "") or "") or 0
            total_vol = self._safe_int(row.get("Total Vol", "") or "") or 0
            pc_vol = self._safe_float(row.get("Put/Call Vol", "") or row.get("Put/Call\tVol", "") or "")
            put_oi = self._safe_int(row.get("Put OI", "") or "") or 0
            call_oi = self._safe_int(row.get("Call OI", "") or "") or 0
            total_oi = self._safe_int(row.get("Total OI", "") or "") or 0
            pc_oi = self._safe_float(row.get("Put/Call OI", "") or row.get("Put/Call\tOI", "") or "")
            iv = self._safe_float(row.get("Implied Volatility", "") or "")

            entries.append(
                PutCallRatio(
                    expiration=exp,
                    dte=dte,
                    put_vol=put_vol,
                    call_vol=call_vol,
                    total_vol=total_vol,
                    put_call_vol_ratio=pc_vol or 0.0,
                    put_oi=put_oi,
                    call_oi=call_oi,
                    total_oi=total_oi,
                    put_call_oi_ratio=pc_oi or 0.0,
                    iv=iv or 0.0,
                )
            )

        logger.info(f"{ticker} put-call-ratio: {len(entries)} expiration(s)")
        return entries

    def scrape_iv_term_structure(self, ticker: str) -> Dict[str, Optional[float]]:
        """Scrape Volatility Charts page for IV term structure metadata.

        Returns dict with iv, hv, iv_rank, iv_percentile.
        """
        soup = self._fetch(self._url(ticker, VOLATILITY_CHARTS_PATH))
        if soup is None:
            logger.warning(f"Failed to fetch volatility charts for {ticker}")
            return {}

        return self._extract_iv_stats(soup)

    # ── Composite scraper ─────────────────────────────────────────────────────

    def scrape_ticker(self, ticker: str) -> BarchartOptionsData:
        """Scrape all options data pages for a single ticker.

        Combines gamma exposure, max pain, expected move, put/call ratio,
        and IV term structure into a single BarchartOptionsData object.

        Args:
            ticker: Stock ticker symbol (e.g. "AAPL", "SPY").

        Returns:
            BarchartOptionsData with all available fields populated.
        """
        from datetime import datetime, timezone

        result = BarchartOptionsData(ticker=ticker.upper())
        result.scraped_at = datetime.now(timezone.utc).isoformat()

        # 1) Gamma exposure (also gives us IV/HV)
        try:
            gamma_data = self.scrape_gamma_exposure(ticker)
            result.gamma_flip = gamma_data.get("gamma_flip")
            result.call_wall = gamma_data.get("call_wall")
            result.put_wall = gamma_data.get("put_wall")
            result.iv = gamma_data.get("iv")
            result.hv = gamma_data.get("hv")
            result.iv_rank = gamma_data.get("iv_rank")
            result.iv_percentile = gamma_data.get("iv_percentile")
        except Exception as exc:
            result.errors.append(f"gamma_exposure: {exc}")
            logger.warning(f"Error scraping gamma exposure for {ticker}: {exc}")

        self._sleep()

        # 2) Max pain
        try:
            result.max_pain_entries = self.scrape_max_pain(ticker)
        except Exception as exc:
            result.errors.append(f"max_pain: {exc}")
            logger.warning(f"Error scraping max pain for {ticker}: {exc}")

        self._sleep()

        # 3) Expected move
        try:
            em_data = self.scrape_expected_move(ticker)
            result.expected_moves = em_data.get("expected_moves", [])
            result.earnings_moves = em_data.get("earnings_moves", [])
            result.avg_earnings_move = em_data.get("avg_earnings_move")
        except Exception as exc:
            result.errors.append(f"expected_move: {exc}")
            logger.warning(f"Error scraping expected move for {ticker}: {exc}")

        self._sleep()

        # 4) Put/call ratio
        try:
            result.put_call_ratios = self.scrape_put_call_ratio(ticker)
        except Exception as exc:
            result.errors.append(f"put_call_ratio: {exc}")
            logger.warning(f"Error scraping put/call ratio for {ticker}: {exc}")

        self._sleep()

        # 5) Latest earnings date (extracted from any page; use gamma page)
        try:
            # Re-fetch gamma page or try to get from IV stats page
            soup = self._fetch(self._url(ticker, GAMMA_EXPOSURE_PATH))
            if soup:
                result.latest_earnings = self._extract_latest_earnings(soup)
        except Exception as exc:
            result.errors.append(f"latest_earnings: {exc}")

        self._sleep()

        logger.info(
            f"Barchart scrape complete for {ticker}: "
            f"gamma_flip={result.gamma_flip}, iv={result.iv}%, "
            f"expected_moves={len(result.expected_moves)}, "
            f"pc_ratios={len(result.put_call_ratios)}, "
            f"errors={len(result.errors)}"
        )
        return result

    def scrape_multi(
        self, tickers: List[str]
    ) -> Dict[str, BarchartOptionsData]:
        """Batch scrape multiple tickers with polite rate limiting.

        Args:
            tickers: List of ticker symbols.

        Returns:
            Dict mapping ticker → BarchartOptionsData.
        """
        results: Dict[str, BarchartOptionsData] = {}
        for i, ticker in enumerate(tickers):
            logger.info(f"[{i+1}/{len(tickers)}] Scraping {ticker} ...")
            data = self.scrape_ticker(ticker)
            results[ticker.upper()] = data
            if i < len(tickers) - 1:
                self._sleep()
        return results


# ── Convenience functions ────────────────────────────────────────────────────


def scrape_barchart_options(ticker: str, delay: float = 1.0) -> Dict:
    """One-shot function to scrape all Barchart options data for a ticker.

    Args:
        ticker: Stock ticker symbol.
        delay: Delay between requests in seconds.

    Returns:
        Plain dict (JSON-serializable) with all scraped data.
    """
    scraper = BarchartScraper(delay=delay)
    data = scraper.scrape_ticker(ticker)
    return data.to_dict()


def quick_gamma_scan(ticker: str) -> Dict[str, Optional[float]]:
    """Quick scan: gamma flip, walls, IV/HV only.

    Args:
        ticker: Stock ticker symbol.

    Returns:
        Dict with gamma_flip, call_wall, put_wall, iv, hv, iv_rank, iv_percentile.
    """
    scraper = BarchartScraper(delay=0.5)
    return scraper.scrape_gamma_exposure(ticker)


# ── Self-test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    test_ticker = sys.argv[1] if len(sys.argv) > 1 else "HIVE"

    print(f"\n=== BarchartScraper test: {test_ticker} ===\n")

    scraper = BarchartScraper(delay=1.0)

    # Quick gamma scan
    print("--- 1. Gamma Exposure ---")
    gamma = scraper.scrape_gamma_exposure(test_ticker)
    print(json.dumps(gamma, indent=2))

    time.sleep(1)

    # Expected move
    print("\n--- 2. Expected Move ---")
    em = scraper.scrape_expected_move(test_ticker)
    print(f"Expected moves: {len(em.get('expected_moves', []))} entries")
    for m in em.get("expected_moves", [])[:3]:
        print(f"  {m.expiration}: ${m.move} ({m.move_pct}%)")
    print(f"Earnings moves: {em.get('earnings_moves', [])}")
    print(f"Avg earnings move: {em.get('avg_earnings_move')}%")

    time.sleep(1)

    # Put/call ratio
    print("\n--- 3. Put/Call Ratio ---")
    pcr = scraper.scrape_put_call_ratio(test_ticker)
    print(f"P/C ratios: {len(pcr)} entries")
    for p in pcr[:3]:
        print(f"  {p.expiration}: vol_ratio={p.put_call_vol_ratio}, oi_ratio={p.put_call_oi_ratio}")

    time.sleep(1)

    # Max pain
    print("\n--- 4. Max Pain ---")
    mp = scraper.scrape_max_pain(test_ticker)
    print(f"Max pain entries: {len(mp)}")
    for m in mp[:3]:
        print(f"  {m.expiration}: ${m.max_pain_price}")

    time.sleep(1)

    # Full composite
    print("\n--- 5. Full Composite ---")
    full = scraper.scrape_ticker(test_ticker)
    print(json.dumps(full.to_dict(), indent=2, default=str))

    print("\n=== All tests passed ===")
