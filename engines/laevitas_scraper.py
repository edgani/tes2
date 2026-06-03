"""engines/laevitas_scraper.py — Laevitas Crypto Options Scraper v1.0

Scrapes crypto options data from Laevitas.ch:
  - GEX (Gamma Exposure) by strike
  - Volatility term structure
  - Skew & Butterfly
  - Volume & Open Interest
  - Options Flows
  - Option Chain with Greeks

Usage:
    from engines.laevitas_scraper import LaevitasScraper
    scraper = LaevitasScraper()

    # GEX data
    gex = scraper.get_gex("BTC", "DERIBIT")

    # Volatility data
    vol = scraper.get_volatility("BTC", "DERIBIT")

    # Skew & Butterfly
    skew = scraper.get_skew_bf("BTC", "DERIBIT")

    # Volume & OI
    vol_oi = scraper.get_volume_oi("BTC", "DERIBIT")

    # Flows
    flows = scraper.get_flows("BTC", "DERIBIT")

API Key (optional):
    If you have a Laevitas API key, provide it for direct API access:
    scraper = LaevitasScraper(api_key="your-api-key")

    The API v2 uses x402 pay-per-request or API key auth.
    Without a key, the scraper falls back to public web page parsing.
"""

from __future__ import annotations

import json
import logging
import re
import time
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlencode, urljoin

try:
    import requests
    from bs4 import BeautifulSoup
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False
    warnings.warn(
        "requests and beautifulsoup4 are required. "
        "Install: pip install requests beautifulsoup4 lxml"
    )

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL_APP = "https://app.laevitas.ch"
BASE_URL_API_V1 = "https://api.laevitas.ch"
BASE_URL_API_V2 = "https://apiv2.laevitas.ch"

DEFAULT_EXCHANGE = "DERIBIT"
DEFAULT_CURRENCIES = ["BTC", "ETH"]
SUPPORTED_EXCHANGES = ["DERIBIT", "OKX", "BINANCE", "BYBIT"]

# Rate limiting: max 1 request per second
MIN_REQUEST_INTERVAL = 1.0

# Request timeout
REQUEST_TIMEOUT = 30

# Chart data extraction patterns
CHART_PATTERN = re.compile(
    r"new_layout[.]assets[.]options_([a-z_]+)[.]([A-Za-z_]+)"
)

# Page paths for each tab
PAGE_PATHS = {
    "gex": "/assets/options/gex/{currency}/{exchange}",
    "volatility": "/assets/options/volatility/{currency}/{exchange}",
    "skew_bf": "/assets/options/skew-bf/{currency}/{exchange}",
    "volume_oi": "/assets/options/activity/{currency}/{exchange}/volume-oi",
    "flows": "/assets/options/activity/{currency}/{exchange}/flows",
    "option_chain": "/assets/options/{currency}/{exchange}/option-chain",
    "overview": "/assets/options/overview/{currency}",
}

# V1 API analytics endpoints (requires API key)
V1_ANALYTICS_ENDPOINTS = {
    "gex_all": "/analytics/options/gex_date_all/{market}/{currency}",
    "gex_by_maturity": "/analytics/options/gex_date/{market}/{currency}/{maturity}",
    "atm_iv_ts": "/analytics/options/atm_iv_ts/{market}/{currency}",
    "maturities": "/analytics/options/maturities/{market}/{currency}",
    "oi_expiry": "/analytics/options/oi_expiry/{market}/{currency}",
    "oi_strike_all": "/analytics/options/oi_strike_all/{market}/{currency}",
    "oi_type": "/analytics/options/oi_type/{market}/{currency}",
    "oi_strike": "/analytics/options/oi_strike/{market}/{currency}/{maturity}",
    "v_strike_all": "/analytics/options/v_strike_all/{market}/{currency}",
    "v_expiry": "/analytics/options/v_expiry/{market}/{currency}",
    "volume_buy_sell_all": "/analytics/options/volume_buy_sell_all/{market}/{currency}",
    "volume_buy_sell": "/analytics/options/volume_buy_sell/{market}/{currency}/{maturity}",
    "top_traded": "/analytics/options/top_traded_option/{market}/{currency}",
    "top_instrument_oi_change": "/analytics/options/top_instrument_oi_change/{market}/{currency}/{hours}",
    "oi_net_change": "/analytics/options/oi_net_change_all/{market}/{currency}/{hours}",
    "iv_strike": "/analytics/options/iv_strike/{market}/{currency}/{strike}",
}

# V2 API endpoints (requires API key or x402 payment)
V2_ENDPOINTS = {
    "catalog": "/api/v1/options/catalog",
    "metadata": "/api/v1/options/metadata",
    "ohlcvt": "/api/v1/options/ohlcvt",
    "vol_surface_expiry": "/api/v1/options/vol-surface/by-expiry",
    "vol_surface_tenor": "/api/v1/options/vol-surface/by-tenor",
    "vol_surface_time": "/api/v1/options/vol-surface/by-time",
    "volatility": "/api/v1/options/volatility",
    "flow": "/api/v1/options/flow",
    "open_interest": "/api/v1/options/open-interest",
    "volume": "/api/v1/options/volume",
    "trades_summary": "/api/v1/options/trades/summary",
    "snapshot": "/api/v1/options/snapshot",
    "realized_vol": "/api/v1/analytics/realized-volatility",
}


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class GEXData:
    """Gamma Exposure data by strike."""
    currency: str
    exchange: str
    timestamp: Optional[str] = None
    spot_price: Optional[float] = None
    gamma_by_strike: List[Dict[str, Any]] = field(default_factory=list)
    gex_term_structure: List[Dict[str, Any]] = field(default_factory=list)
    gamma_exposure_index: Optional[Dict[str, Any]] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "currency": self.currency,
            "exchange": self.exchange,
            "timestamp": self.timestamp,
            "spot_price": self.spot_price,
            "gamma_by_strike": self.gamma_by_strike,
            "gex_term_structure": self.gex_term_structure,
            "gamma_exposure_index": self.gamma_exposure_index,
        }


@dataclass
class VolatilityData:
    """Volatility data: term structure, ATM IV, IV-RV."""
    currency: str
    exchange: str
    timestamp: Optional[str] = None
    term_structure: List[Dict[str, Any]] = field(default_factory=list)
    atm_iv_by_tenor: List[Dict[str, Any]] = field(default_factory=list)
    iv_rv_spread: Optional[Dict[str, Any]] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "currency": self.currency,
            "exchange": self.exchange,
            "timestamp": self.timestamp,
            "term_structure": self.term_structure,
            "atm_iv_by_tenor": self.atm_iv_by_tenor,
            "iv_rv_spread": self.iv_rv_spread,
        }


@dataclass
class SkewBFData:
    """Skew & Butterfly data."""
    currency: str
    exchange: str
    timestamp: Optional[str] = None
    skew_25d: List[Dict[str, Any]] = field(default_factory=list)
    butterfly_25d: List[Dict[str, Any]] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "currency": self.currency,
            "exchange": self.exchange,
            "timestamp": self.timestamp,
            "skew_25d": self.skew_25d,
            "butterfly_25d": self.butterfly_25d,
        }


@dataclass
class VolumeOIData:
    """Volume and Open Interest data."""
    currency: str
    exchange: str
    timestamp: Optional[str] = None
    volume_by_expiry: List[Dict[str, Any]] = field(default_factory=list)
    oi_by_expiry: List[Dict[str, Any]] = field(default_factory=list)
    volume_by_strike: List[Dict[str, Any]] = field(default_factory=list)
    oi_by_strike: List[Dict[str, Any]] = field(default_factory=list)
    total_24h_volume: Optional[Dict[str, Any]] = None
    total_oi: Optional[Dict[str, Any]] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "currency": self.currency,
            "exchange": self.exchange,
            "timestamp": self.timestamp,
            "volume_by_expiry": self.volume_by_expiry,
            "oi_by_expiry": self.oi_by_expiry,
            "volume_by_strike": self.volume_by_strike,
            "oi_by_strike": self.oi_by_strike,
            "total_24h_volume": self.total_24h_volume,
            "total_oi": self.total_oi,
        }


@dataclass
class FlowsData:
    """Options flow data: buy/sell pressure."""
    currency: str
    exchange: str
    timestamp: Optional[str] = None
    buy_sell_volume: List[Dict[str, Any]] = field(default_factory=list)
    oi_change: List[Dict[str, Any]] = field(default_factory=list)
    top_instrument_oi_change: List[Dict[str, Any]] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "currency": self.currency,
            "exchange": self.exchange,
            "timestamp": self.timestamp,
            "buy_sell_volume": self.buy_sell_volume,
            "oi_change": self.oi_change,
            "top_instrument_oi_change": self.top_instrument_oi_change,
        }


# ---------------------------------------------------------------------------
# Main Scraper Class
# ---------------------------------------------------------------------------

class LaevitasScraper:
    """
    Laevitas Crypto Options Scraper.

    Scrapes options analytics data from Laevitas.ch public web pages.
    Falls back to HTML parsing since the API requires authentication.

    Args:
        api_key: Optional Laevitas API key for direct API access.
        use_api_v2: If True and api_key is provided, use API v2 endpoints.
        rate_limit: Minimum seconds between requests (default: 1.0).
        timeout: Request timeout in seconds (default: 30).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        use_api_v2: bool = False,
        rate_limit: float = MIN_REQUEST_INTERVAL,
        timeout: float = REQUEST_TIMEOUT,
    ) -> None:
        if not REQUESTS_OK:
            raise ImportError(
                "requests and beautifulsoup4 are required. "
                "Install: pip install requests beautifulsoup4 lxml"
            )

        self.api_key = api_key
        self.use_api_v2 = use_api_v2 and api_key is not None
        self.rate_limit = rate_limit
        self.timeout = timeout
        self._last_request_time: float = 0.0

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",  # No brotli — avoids decompression issues
            "DNT": "1",
            "Connection": "keep-alive",
        })

        if self.api_key:
            self.session.headers["X-API-Key"] = self.api_key
            logger.info("API key configured — using direct API access")
        else:
            # Set referer for web scraping mode
            self.session.headers["Referer"] = BASE_URL_APP + "/"
            logger.info("No API key — using public web page scraping")

    # --- Internal helpers ------------------------------------------------

    def _enforce_rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self._last_request_time = time.time()

    def _get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        as_json: bool = False,
    ) -> Union[requests.Response, Dict[str, Any], None]:
        """
        Make a GET request with rate limiting and error handling.

        Returns:
            Response object, parsed JSON dict, or None on failure.
        """
        self._enforce_rate_limit()
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            if resp.status_code == 200:
                if as_json:
                    return resp.json()
                return resp
            elif resp.status_code == 402:
                logger.warning("Payment required (402) — API needs auth: %s", url)
            elif resp.status_code == 400:
                err = resp.json() if resp.text else {}
                if "Api Key is Required" in str(err.get("message", "")):
                    logger.warning("API key required: %s", url)
                else:
                    logger.warning("Bad request (400) %s: %s", url, err)
            else:
                logger.warning("HTTP %d for %s", resp.status_code, url)
        except requests.exceptions.Timeout:
            logger.error("Timeout fetching %s", url)
        except requests.exceptions.ConnectionError:
            logger.error("Connection error for %s", url)
        except Exception as exc:
            logger.error("Error fetching %s: %s", url, exc)
        return None

    def _get_page_soup(
        self, currency: str, exchange: str, tab: str
    ) -> Optional[BeautifulSoup]:
        """
        Fetch and parse a Laevitas options page.

        Args:
            currency: Crypto asset (BTC, ETH, etc.).
            exchange: Exchange name (DERIBIT, OKX, etc.).
            tab: Tab name (gex, volatility, skew_bf, volume_oi, flows).

        Returns:
            BeautifulSoup object or None on failure.
        """
        path = PAGE_PATHS.get(tab, "").format(
            currency=currency, exchange=exchange
        )
        if not path:
            logger.error("Unknown tab: %s", tab)
            return None

        url = f"{BASE_URL_APP}{path}"
        resp = self._get(url)
        if resp is None:
            return None
        return BeautifulSoup(resp.text, "lxml")

    def _extract_spot_price(self, soup: BeautifulSoup) -> Optional[float]:
        """Extract spot price from page header."""
        try:
            # Look for price in the ticker bar
            price_elem = soup.find("div", string=re.compile(r"\$[\d,.]+[KM]?"))
            if price_elem:
                text = price_elem.get_text(strip=True)
                match = re.search(r"\$([\d,.]+)", text)
                if match:
                    price_str = match.group(1).replace(",", "")
                    if "K" in price_str:
                        return float(price_str.replace("K", "")) * 1000
                    return float(price_str)
        except Exception:
            pass
        return None

    def _extract_chart_descriptions(
        self, soup: BeautifulSoup
    ) -> Dict[str, str]:
        """Extract chart descriptions and metadata from the page."""
        descriptions = {}
        try:
            # Find all chart description paragraphs
            desc_elems = soup.find_all("p")
            for elem in desc_elems:
                text = elem.get_text(strip=True)
                if len(text) > 50 and any(
                    kw in text.lower()
                    for kw in ["gamma", "volatility", "skew", "butterfly",
                               "exposure", "open interest", "volume", "flow"]
                ):
                    # Try to identify the chart type
                    if "gamma" in text.lower() or "gex" in text.lower():
                        descriptions.setdefault("gex", []).append(text)
                    elif "volatility" in text.lower() or "iv" in text.lower():
                        descriptions.setdefault("volatility", []).append(text)
                    elif "skew" in text.lower():
                        descriptions.setdefault("skew", []).append(text)
                    elif "butterfly" in text.lower():
                        descriptions.setdefault("butterfly", []).append(text)
                    elif "open interest" in text.lower():
                        descriptions.setdefault("oi", []).append(text)
                    elif "volume" in text.lower():
                        descriptions.setdefault("volume", []).append(text)
                    elif "flow" in text.lower():
                        descriptions.setdefault("flows", []).append(text)
        except Exception as exc:
            logger.debug("Error extracting descriptions: %s", exc)
        return descriptions

    def _extract_chart_metadata(
        self, soup: BeautifulSoup
    ) -> List[Dict[str, Any]]:
        """
        Extract chart metadata (title, type, axes, data ranges) from page.
        """
        charts = []
        try:
            # Find all elements that look like chart containers
            chart_headers = soup.find_all(
                ["h3", "h4", "span"],
                string=re.compile(
                    r"(Gamma|GEX|Skew|Butterfly|ATM IV|Term Structure|"
                    r"Volume|Open Interest|Buy/Sell|Flow)",
                    re.IGNORECASE,
                ),
            )
            for header in chart_headers:
                text = header.get_text(strip=True)
                if text and len(text) < 100:
                    charts.append({
                        "title": text,
                        "tag": header.name,
                    })
        except Exception as exc:
            logger.debug("Error extracting chart metadata: %s", exc)
        return charts

    # --- Public API: GEX ------------------------------------------------

    def get_gex(
        self,
        currency: str = "BTC",
        exchange: str = DEFAULT_EXCHANGE,
    ) -> Optional[GEXData]:
        """
        Fetch Gamma Exposure (GEX) data.

        Args:
            currency: Crypto asset (BTC, ETH).
            exchange: Exchange (DERIBIT, OKX, BINANCE).

        Returns:
            GEXData object or None on failure.
        """
        # Try API v1 if key is available
        if self.api_key and not self.use_api_v2:
            result = self._get_gex_api_v1(currency, exchange)
            if result:
                return result

        # Try API v2 if key is available
        if self.use_api_v2:
            result = self._get_gex_api_v2(currency, exchange)
            if result:
                return result

        # Fall back to web scraping
        return self._get_gex_scrape(currency, exchange)

    def _get_gex_api_v1(
        self, currency: str, exchange: str
    ) -> Optional[GEXData]:
        """Fetch GEX via V1 API (requires API key)."""
        url = f"{BASE_URL_API_V1}/analytics/options/gex_date_all/{exchange}/{currency}"
        data = self._get(url, params={"date": datetime.now(timezone.utc).strftime("%Y-%m-%d")}, as_json=True)
        if data and isinstance(data, dict) and "status" not in data:
            return GEXData(
                currency=currency,
                exchange=exchange,
                timestamp=datetime.now(timezone.utc).isoformat(),
                gamma_by_strike=data if isinstance(data, list) else [data],
                raw=data if isinstance(data, dict) else {},
            )
        return None

    def _get_gex_api_v2(
        self, currency: str, exchange: str
    ) -> Optional[GEXData]:
        """Fetch GEX via V2 API (requires API key or x402)."""
        # V2 does not have a direct GEX endpoint, use vol-surface
        url = f"{BASE_URL_API_V2}/api/v1/options/vol-surface/by-expiry"
        data = self._get(
            url,
            params={"exchange": exchange.lower(), "currency": currency},
            as_json=True,
        )
        if data and isinstance(data, dict):
            return GEXData(
                currency=currency,
                exchange=exchange,
                timestamp=datetime.now(timezone.utc).isoformat(),
                gamma_by_strike=data.get("data", []),
                raw=data,
            )
        return None

    def _get_gex_scrape(
        self, currency: str, exchange: str
    ) -> Optional[GEXData]:
        """Scrape GEX data from the public page."""
        soup = self._get_page_soup(currency, exchange, "gex")
        if soup is None:
            return None

        spot_price = self._extract_spot_price(soup)
        descriptions = self._extract_chart_descriptions(soup)
        chart_meta = self._extract_chart_metadata(soup)

        gamma_by_strike = []
        gex_term_structure = []
        gamma_index = None

        try:
            # Parse the GEX description for metadata
            gex_desc = " ".join(descriptions.get("gex", []))

            # Look for strike and gamma values in the page text
            page_text = soup.get_text()

            # Try to find gamma exposure values by strike
            # Pattern: numbers followed by K (strike levels) and their gamma
            strike_gamma = re.findall(
                r"(\d+K?)\s*[—-]\s*([\d.-]+)", page_text
            )
            for strike, gamma in strike_gamma:
                gamma_by_strike.append({
                    "strike": strike,
                    "gamma": float(gamma) if gamma.replace(".", "").replace("-", "").isdigit() else None,
                })

            # Extract GEX term structure data from chart text
            term_structure_text = re.search(
                r"GEX Term Structure[^\n]*\n([^\n]+)", page_text
            )
            if term_structure_text:
                gex_term_structure.append({
                    "description": term_structure_text.group(1).strip()
                })

        except Exception as exc:
            logger.debug("Error parsing GEX data: %s", exc)

        return GEXData(
            currency=currency,
            exchange=exchange,
            timestamp=datetime.now(timezone.utc).isoformat(),
            spot_price=spot_price,
            gamma_by_strike=gamma_by_strike,
            gex_term_structure=gex_term_structure,
            gamma_exposure_index={
                "description": (
                    "Gamma Exposure Index shows gamma exposure vs index price. "
                    "Positive GEX = price magnet (support/resistance). "
                    "Negative GEX = volatility expansion zone."
                ),
                "charts": chart_meta,
            },
            raw={
                "descriptions": descriptions,
                "chart_metadata": chart_meta,
                "page_title": soup.title.string if soup.title else None,
            },
        )

    # --- Public API: Volatility -------------------------------------------

    def get_volatility(
        self,
        currency: str = "BTC",
        exchange: str = DEFAULT_EXCHANGE,
    ) -> Optional[VolatilityData]:
        """
        Fetch volatility data (term structure, ATM IV, IV-RV spread).

        Args:
            currency: Crypto asset (BTC, ETH).
            exchange: Exchange (DERIBIT, OKX, BINANCE).

        Returns:
            VolatilityData object or None on failure.
        """
        if self.api_key and not self.use_api_v2:
            result = self._get_vol_api_v1(currency, exchange)
            if result:
                return result

        if self.use_api_v2:
            result = self._get_vol_api_v2(currency, exchange)
            if result:
                return result

        return self._get_vol_scrape(currency, exchange)

    def _get_vol_api_v1(
        self, currency: str, exchange: str
    ) -> Optional[VolatilityData]:
        """Fetch volatility via V1 API."""
        url = f"{BASE_URL_API_V1}/analytics/options/atm_iv_ts/{exchange}/{currency}"
        data = self._get(
            url,
            params={
                "start_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "end_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            },
            as_json=True,
        )
        if data and isinstance(data, dict) and "status" not in data:
            return VolatilityData(
                currency=currency,
                exchange=exchange,
                timestamp=datetime.now(timezone.utc).isoformat(),
                term_structure=data if isinstance(data, list) else [data],
                raw=data if isinstance(data, dict) else {},
            )
        return None

    def _get_vol_api_v2(
        self, currency: str, exchange: str
    ) -> Optional[VolatilityData]:
        """Fetch volatility via V2 API."""
        url = f"{BASE_URL_API_V2}/api/v1/options/vol-surface/by-expiry"
        data = self._get(
            url,
            params={"exchange": exchange.lower(), "currency": currency},
            as_json=True,
        )
        if data and isinstance(data, dict):
            term_structure = []
            for item in data.get("data", []):
                term_structure.append({
                    "expiry": item.get("expiry"),
                    "atm_iv": item.get("atm_iv"),
                    "skew_25d": item.get("skew_25d"),
                    "butterfly_25d": item.get("butterfly_25d"),
                })
            return VolatilityData(
                currency=currency,
                exchange=exchange,
                timestamp=datetime.now(timezone.utc).isoformat(),
                term_structure=term_structure,
                raw=data,
            )
        return None

    def _get_vol_scrape(
        self, currency: str, exchange: str
    ) -> Optional[VolatilityData]:
        """Scrape volatility data from public page."""
        soup = self._get_page_soup(currency, exchange, "volatility")
        if soup is None:
            return None

        descriptions = self._extract_chart_descriptions(soup)
        chart_meta = self._extract_chart_metadata(soup)
        term_structure = []
        atm_iv = []

        try:
            # Parse term structure from description
            vol_desc = " ".join(descriptions.get("volatility", []))

            # Extract ATM IV values from chart metadata
            for chart in chart_meta:
                title = chart.get("title", "")
                if "ATM" in title or "atm" in title:
                    atm_iv.append({"title": title})
                elif "term" in title.lower() or "structure" in title.lower():
                    term_structure.append({"title": title})

            # Add IV-RV description if available
            iv_rv = None
            if vol_desc:
                iv_rv = {
                    "description": vol_desc,
                    "note": (
                        "Positive IV-RV spread = IV > RV (options expensive). "
                        "Negative IV-RV spread = IV < RV (options cheap)."
                    ),
                }

        except Exception as exc:
            logger.debug("Error parsing volatility data: %s", exc)

        return VolatilityData(
            currency=currency,
            exchange=exchange,
            timestamp=datetime.now(timezone.utc).isoformat(),
            term_structure=term_structure,
            atm_iv_by_tenor=atm_iv,
            iv_rv_spread=iv_rv,
            raw={
                "descriptions": descriptions,
                "chart_metadata": chart_meta,
            },
        )

    # --- Public API: Skew & BF --------------------------------------------

    def get_skew_bf(
        self,
        currency: str = "BTC",
        exchange: str = DEFAULT_EXCHANGE,
    ) -> Optional[SkewBFData]:
        """
        Fetch Skew & Butterfly data.

        Args:
            currency: Crypto asset (BTC, ETH).
            exchange: Exchange (DERIBIT, OKX, BINANCE).

        Returns:
            SkewBFData object or None on failure.
        """
        if self.use_api_v2:
            result = self._get_skew_api_v2(currency, exchange)
            if result:
                return result
        return self._get_skew_scrape(currency, exchange)

    def _get_skew_api_v2(
        self, currency: str, exchange: str
    ) -> Optional[SkewBFData]:
        """Fetch skew/butterfly via V2 API."""
        url = f"{BASE_URL_API_V2}/api/v1/options/vol-surface/by-expiry"
        data = self._get(
            url,
            params={"exchange": exchange.lower(), "currency": currency},
            as_json=True,
        )
        if data and isinstance(data, dict):
            skew_data = []
            bf_data = []
            for item in data.get("data", []):
                skew_data.append({
                    "expiry": item.get("expiry"),
                    "skew_25d": item.get("skew_25d"),
                })
                bf_data.append({
                    "expiry": item.get("expiry"),
                    "butterfly_25d": item.get("butterfly_25d"),
                })
            return SkewBFData(
                currency=currency,
                exchange=exchange,
                timestamp=datetime.now(timezone.utc).isoformat(),
                skew_25d=skew_data,
                butterfly_25d=bf_data,
                raw=data,
            )
        return None

    def _get_skew_scrape(
        self, currency: str, exchange: str
    ) -> Optional[SkewBFData]:
        """Scrape skew & butterfly data from public page."""
        soup = self._get_page_soup(currency, exchange, "skew_bf")
        if soup is None:
            return None

        descriptions = self._extract_chart_descriptions(soup)
        chart_meta = self._extract_chart_metadata(soup)

        skew_data = []
        bf_data = []

        try:
            skew_desc = descriptions.get("skew", [])
            bf_desc = descriptions.get("butterfly", [])

            # Parse skew values from chart metadata
            for chart in chart_meta:
                title = chart.get("title", "")
                if "skew" in title.lower():
                    skew_data.append({"label": title})
                elif "butterfly" in title.lower() or "bf" in title.lower():
                    bf_data.append({"label": title})

        except Exception as exc:
            logger.debug("Error parsing skew data: %s", exc)

        return SkewBFData(
            currency=currency,
            exchange=exchange,
            timestamp=datetime.now(timezone.utc).isoformat(),
            skew_25d=skew_data or [{"note": "; ".join(descriptions.get("skew", []))}],
            butterfly_25d=bf_data or [{"note": "; ".join(descriptions.get("butterfly", []))}],
            raw={
                "descriptions": descriptions,
                "chart_metadata": chart_meta,
                "skew_formula": (
                    "Normalized Skew = (IV_25d Put - IV_25d Call) / IV_ATM"
                ),
                "butterfly_formula": (
                    "Butterfly Spread = IV_25d Call + IV_25d Put - 2 * IV_ATM"
                ),
            },
        )

    # --- Public API: Volume & OI ------------------------------------------

    def get_volume_oi(
        self,
        currency: str = "BTC",
        exchange: str = DEFAULT_EXCHANGE,
    ) -> Optional[VolumeOIData]:
        """
        Fetch Volume and Open Interest data.

        Args:
            currency: Crypto asset (BTC, ETH).
            exchange: Exchange (DERIBIT, OKX, BINANCE).

        Returns:
            VolumeOIData object or None on failure.
        """
        if self.api_key and not self.use_api_v2:
            result = self._get_vol_oi_api_v1(currency, exchange)
            if result:
                return result

        if self.use_api_v2:
            result = self._get_vol_oi_api_v2(currency, exchange)
            if result:
                return result

        return self._get_vol_oi_scrape(currency, exchange)

    def _get_vol_oi_api_v1(
        self, currency: str, exchange: str
    ) -> Optional[VolumeOIData]:
        """Fetch volume/OI via V1 API."""
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        endpoints = {
            "oi_strike": f"{BASE_URL_API_V1}/analytics/options/oi_strike_all/{exchange}/{currency}",
            "v_strike": f"{BASE_URL_API_V1}/analytics/options/v_strike_all/{exchange}/{currency}",
            "oi_expiry": f"{BASE_URL_API_V1}/analytics/options/oi_expiry/{exchange}/{currency}",
            "v_expiry": f"{BASE_URL_API_V1}/analytics/options/v_expiry/{exchange}/{currency}",
        }

        results = {}
        for key, url in endpoints.items():
            data = self._get(url, params={"date": date_str}, as_json=True)
            if data and isinstance(data, dict) and "status" not in data:
                results[key] = data

        if results:
            return VolumeOIData(
                currency=currency,
                exchange=exchange,
                timestamp=datetime.now(timezone.utc).isoformat(),
                oi_by_strike=results.get("oi_strike", []),
                volume_by_strike=results.get("v_strike", []),
                oi_by_expiry=results.get("oi_expiry", []),
                volume_by_expiry=results.get("v_expiry", []),
                raw=results,
            )
        return None

    def _get_vol_oi_api_v2(
        self, currency: str, exchange: str
    ) -> Optional[VolumeOIData]:
        """Fetch volume/OI via V2 API."""
        oi_url = f"{BASE_URL_API_V2}/api/v1/options/open-interest"
        vol_url = f"{BASE_URL_API_V2}/api/v1/options/volume"

        oi_data = self._get(
            oi_url,
            params={"exchange": exchange.lower(), "currency": currency},
            as_json=True,
        )
        vol_data = self._get(
            vol_url,
            params={"exchange": exchange.lower(), "currency": currency},
            as_json=True,
        )

        if oi_data or vol_data:
            return VolumeOIData(
                currency=currency,
                exchange=exchange,
                timestamp=datetime.now(timezone.utc).isoformat(),
                oi_by_expiry=oi_data.get("data", []) if isinstance(oi_data, dict) else [],
                volume_by_expiry=vol_data.get("data", []) if isinstance(vol_data, dict) else [],
                raw={"oi": oi_data, "volume": vol_data},
            )
        return None

    def _get_vol_oi_scrape(
        self, currency: str, exchange: str
    ) -> Optional[VolumeOIData]:
        """Scrape volume/OI data from public page."""
        soup = self._get_page_soup(currency, exchange, "volume_oi")
        if soup is None:
            return None

        descriptions = self._extract_chart_descriptions(soup)
        chart_meta = self._extract_chart_metadata(soup)

        return VolumeOIData(
            currency=currency,
            exchange=exchange,
            timestamp=datetime.now(timezone.utc).isoformat(),
            volume_by_strike=[],
            oi_by_strike=[],
            total_24h_volume={
                "note": "24h volume data from Laevitas options page",
                "available_charts": [
                    c["title"] for c in chart_meta
                    if "volume" in c.get("title", "").lower()
                ],
            },
            total_oi={
                "note": "Open interest data from Laevitas options page",
                "available_charts": [
                    c["title"] for c in chart_meta
                    if "open interest" in c.get("title", "").lower()
                ],
            },
            raw={
                "descriptions": descriptions,
                "chart_metadata": chart_meta,
            },
        )

    # --- Public API: Flows ------------------------------------------------

    def get_flows(
        self,
        currency: str = "BTC",
        exchange: str = DEFAULT_EXCHANGE,
    ) -> Optional[FlowsData]:
        """
        Fetch options flow data (buy/sell pressure).

        Args:
            currency: Crypto asset (BTC, ETH).
            exchange: Exchange (DERIBIT, OKX, BINANCE).

        Returns:
            FlowsData object or None on failure.
        """
        if self.use_api_v2:
            result = self._get_flows_api_v2(currency, exchange)
            if result:
                return result

        if self.api_key:
            result = self._get_flows_api_v1(currency, exchange)
            if result:
                return result

        return self._get_flows_scrape(currency, exchange)

    def _get_flows_api_v1(
        self, currency: str, exchange: str
    ) -> Optional[FlowsData]:
        """Fetch flows via V1 API."""
        url = (
            f"{BASE_URL_API_V1}/analytics/options/volume_buy_sell_all/"
            f"{exchange}/{currency}"
        )
        data = self._get(
            url,
            params={"date": datetime.now(timezone.utc).strftime("%Y-%m-%d")},
            as_json=True,
        )
        if data and isinstance(data, dict) and "status" not in data:
            return FlowsData(
                currency=currency,
                exchange=exchange,
                timestamp=datetime.now(timezone.utc).isoformat(),
                buy_sell_volume=data if isinstance(data, list) else [data],
                raw=data if isinstance(data, dict) else {},
            )
        return None

    def _get_flows_api_v2(
        self, currency: str, exchange: str
    ) -> Optional[FlowsData]:
        """Fetch flows via V2 API."""
        url = f"{BASE_URL_API_V2}/api/v1/options/flow"
        data = self._get(
            url,
            params={"exchange": exchange.lower(), "currency": currency},
            as_json=True,
        )
        if data and isinstance(data, dict):
            return FlowsData(
                currency=currency,
                exchange=exchange,
                timestamp=datetime.now(timezone.utc).isoformat(),
                buy_sell_volume=data.get("data", []),
                raw=data,
            )
        return None

    def _get_flows_scrape(
        self, currency: str, exchange: str
    ) -> Optional[FlowsData]:
        """Scrape flow data from public page."""
        soup = self._get_page_soup(currency, exchange, "flows")
        if soup is None:
            return None

        descriptions = self._extract_chart_descriptions(soup)
        chart_meta = self._extract_chart_metadata(soup)

        buy_sell = []
        oi_change = []
        top_inst = []

        try:
            flow_desc = descriptions.get("flows", [])

            for chart in chart_meta:
                title = chart.get("title", "")
                if "buy" in title.lower() or "sell" in title.lower():
                    buy_sell.append({"label": title})
                elif "oi change" in title.lower() or "open interest" in title.lower():
                    oi_change.append({"label": title})
                elif "top instrument" in title.lower():
                    top_inst.append({"label": title})

        except Exception as exc:
            logger.debug("Error parsing flow data: %s", exc)

        return FlowsData(
            currency=currency,
            exchange=exchange,
            timestamp=datetime.now(timezone.utc).isoformat(),
            buy_sell_volume=buy_sell,
            oi_change=oi_change,
            top_instrument_oi_change=top_inst,
            raw={
                "descriptions": descriptions,
                "chart_metadata": chart_meta,
                "flow_note": (
                    "Green bars = Call buying / Put selling (bullish). "
                    "Red bars = Put buying / Call selling (bearish)."
                ),
            },
        )

    # --- Utility methods --------------------------------------------------

    def get_all_data(
        self,
        currency: str = "BTC",
        exchange: str = DEFAULT_EXCHANGE,
    ) -> Dict[str, Any]:
        """
        Fetch all available options data for a currency/exchange pair.

        Args:
            currency: Crypto asset (BTC, ETH).
            exchange: Exchange (DERIBIT, OKX, BINANCE).

        Returns:
            Dictionary with all data types. Values may be None on failure.
        """
        logger.info("Fetching all data for %s/%s", currency, exchange)
        return {
            "currency": currency,
            "exchange": exchange,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "gex": self.get_gex(currency, exchange),
            "volatility": self.get_volatility(currency, exchange),
            "skew_bf": self.get_skew_bf(currency, exchange),
            "volume_oi": self.get_volume_oi(currency, exchange),
            "flows": self.get_flows(currency, exchange),
        }

    def get_supported_exchanges(self) -> List[str]:
        """Return list of supported exchanges."""
        return list(SUPPORTED_EXCHANGES)

    def get_page_url(
        self, currency: str, exchange: str, tab: str
    ) -> Optional[str]:
        """
        Get the public page URL for a given tab.

        Args:
            currency: Crypto asset.
            exchange: Exchange name.
            tab: Tab name (gex, volatility, skew_bf, volume_oi, flows).

        Returns:
            Full URL or None if tab is unknown.
        """
        path = PAGE_PATHS.get(tab, "").format(
            currency=currency, exchange=exchange
        )
        if path:
            return f"{BASE_URL_APP}{path}"
        return None

    def health_check(self) -> bool:
        """
        Check if Laevitas web app is accessible.

        Returns:
            True if accessible, False otherwise.
        """
        try:
            self._enforce_rate_limit()
            resp = self.session.get(BASE_URL_APP, timeout=self.timeout)
            return resp.status_code == 200
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Standalone execution
# ---------------------------------------------------------------------------

def main():
    """Demo: fetch and print all available data."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )

    scraper = LaevitasScraper()

    # Health check
    if not scraper.health_check():
        logger.error("Laevitas is not accessible")
        return

    logger.info("Laevitas scraper initialized — fetching BTC/DERIBIT data")

    # Fetch all data
    all_data = scraper.get_all_data("BTC", "DERIBIT")

    # Print summary
    print("\n" + "=" * 60)
    print("LAEVITAS OPTIONS DATA SUMMARY")
    print("=" * 60)
    print(f"Currency : {all_data['currency']}")
    print(f"Exchange : {all_data['exchange']}")
    print(f"Timestamp: {all_data['timestamp']}")
    print()

    for key, value in all_data.items():
        if key in ("currency", "exchange", "timestamp"):
            continue
        status = "OK" if value is not None else "FAILED"
        print(f"  {key:15s}: {status}")

    print()
    print("Page URLs:")
    for tab in PAGE_PATHS:
        url = scraper.get_page_url("BTC", "DERIBIT", tab)
        if url:
            print(f"  {tab:15s}: {url}")

    # Save to JSON
    output_file = "/mnt/agents/output/macroregime/engines/laevitas_data_sample.json"
    serializable = {}
    for k, v in all_data.items():
        if hasattr(v, "to_dict"):
            serializable[k] = v.to_dict()
        else:
            serializable[k] = v

    with open(output_file, "w") as f:
        json.dump(serializable, f, indent=2, default=str)
    print(f"\nSample data saved to: {output_file}")


if __name__ == "__main__":
    main()
