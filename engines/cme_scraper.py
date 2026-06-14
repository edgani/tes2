"""engines/cme_scraper.py -- CME Group Data Scraper v1.0

Scrapes futures/options data from CME Group:
  - Open Interest by strike
  - Volume & settlement prices
  - Volatility term structure
  - Expected ranges
  - Most active strikes

Usage (authenticated -- user has CME account):
    from engines.cme_scraper import CMEScraper
    cme = CMEScraper()
    # Login once (user provides credentials)
    cme.login("username", "password")

    # Fetch OI profile for EUR/USD
    oi = cme.get_open_interest("425")  # EUR product code

    # Fetch most active strikes for Gold
    strikes = cme.get_most_active_strikes("133")

Usage (public data -- no login):
    settlements = cme.get_settlements("425")  # EUR futures settlements
    volume = cme.get_volume("133")  # Gold volume
"""

import logging
import json
import time
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# CME product codes we care about
CME_PRODUCTS = {
    "EUR": "425",
    "GBP": "437",
    "JPY": "471",
    "AUD": "433",
    "CAD": "460",
    "CHF": "443",
    "NZD": "377",
    "MXN": "458",
    "GOLD": "133",
    "SILVER": "84",
    "COPPER": "424",
    "PALLADIUM": "402",
    "PLATINUM": "4259",
    "CRUDE_OIL": "4250",
    "NATGAS": "4240",
    "BRENT": "4600",
    "BTC": "9118",
    "ETH": "1465",
    "ES": "133",
    "MES": "146",
    "NQ": "209",
    "MNQ": "149",
    "ZT": "6470",
    "ZF": "6474",
    "ZN": "6608",
    "ZB": "6516",
}

# Friendly name mapping
CME_PRODUCT_NAMES = {
    "425": "EUR/USD",
    "437": "GBP/USD",
    "471": "JPY/USD",
    "433": "AUD/USD",
    "460": "CAD/USD",
    "443": "CHF/USD",
    "377": "NZD/USD",
    "458": "MXN/USD",
    "133": "Gold",
    "84": "Silver",
    "424": "Copper",
    "402": "Palladium",
    "4259": "Platinum",
    "4250": "Crude Oil (WTI)",
    "4240": "Natural Gas",
    "4600": "Brent Crude",
    "9118": "Micro Bitcoin",
    "1465": "Micro Ethereum",
    "146": "Micro E-mini S&P 500",
    "209": "E-mini Nasdaq-100",
    "149": "Micro E-mini Nasdaq-100",
    "6470": "2-Year T-Note",
    "6474": "5-Year T-Note",
    "6608": "10-Year T-Note",
    "6516": "30-Year T-Bond",
}

# CME public API base URLs (no login required)
SETTLEMENTS_API = "https://www.cmegroup.com/CmeWS/mvc/Settlements/Futures/Settlements/{productId}/FUT"
SETTLEMENTS_OPTIONS_API = "https://www.cmegroup.com/CmeWS/mvc/Settlements/Options/Settlements/{productId}/OOF"
VOLUME_API = "https://www.cmegroup.com/CmeWS/mvc/Volume/Details/F/{productId}/FUT"
QUOTE_API = "https://www.cmegroup.com/CmeWS/mvc/Quotes/Future/{productId}/G"
PRODUCTS_API = "https://www.cmegroup.com/CmeWS/mvc/ProductCalendar/Future/{productId}"

# CME Market API (newer REST API)
MARKETS_API_BASE = "https://markets.api.cmegroup.com/v1"

# QuikStrike URLs (require authentication)
QUIKSTRIKE_BASE = "https://www.cmegroup.com/tools-information/quikstrike"
QUIKSTRIKE_OI_PROFILE = f"{QUIKSTRIKE_BASE}/options-open-interest-profile.html"
QUIKSTRIKE_COT = f"{QUIKSTRIKE_BASE}/commitment-of-traders.html"
QUIKSTRIKE_VOL_TERM = f"{QUIKSTRIKE_BASE}/volatility-term-structure.html"
QUIKSTRIKE_VOL2VOL = f"{QUIKSTRIKE_BASE}/vol2vol-expected-range.html"
QUIKSTRIKE_MOST_ACTIVE = f"{QUIKSTRIKE_BASE}/most-active-strikes.html"

# CME SSO / login endpoints
CME_LOGIN_URL = "https://login.cmegroup.com/sso/oauth2/access_token"
CME_AUTH_URL = "https://www.cmegroup.com/content/cmegroup/en/login/jcr:content/authenticate.html"

# Rate limiting
RATE_LIMIT_DELAY = 0.5  # max 2 req/sec


@dataclass
class StrikeOI:
    """Open Interest data for a single option strike."""

    strike: float
    call_oi: int
    put_oi: int
    total_oi: int
    call_oi_change: Optional[int] = None
    put_oi_change: Optional[int] = None
    call_volume: Optional[int] = None
    put_volume: Optional[int] = None

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class VolTermPoint:
    """Single point on the volatility term structure."""

    expiry: str
    days_to_expiry: int
    atm_iv: float
    _25d_call_skew: Optional[float] = None
    _25d_put_skew: Optional[float] = None
    _10d_call_skew: Optional[float] = None
    _10d_put_skew: Optional[float] = None

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ExpectedRange:
    """Expected range from Vol2Vol tool."""

    expiry: str
    days_forward: int
    expected_move: float
    lower_bound: float
    upper_bound: float
    confidence: float  # e.g. 0.68 for 1 std dev
    current_price: Optional[float] = None

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class SettlementRecord:
    """Single futures settlement record."""

    contract_month: str
    contract_code: str
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    last: Optional[float] = None
    change: Optional[float] = None
    settle: Optional[float] = None
    volume: Optional[int] = None
    open_interest: Optional[int] = None
    oi_change: Optional[int] = None

    def to_dict(self) -> Dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Scraper class
# ---------------------------------------------------------------------------


class CMEScraper:
    """CME Group data scraper -- public + authenticated.

    Public methods (no login required):
        get_settlements(product_id)     -> daily settlement prices
        get_volume(product_id)          -> volume & open interest
        get_quick_quote(ticker)         -> current futures price snapshot
        get_product_info(product_id)    -> product calendar info

    Authenticated methods (login required):
        login(username, password)       -> authenticate with CME
        get_open_interest_profile(pid)  -> OI by strike
        get_most_active_strikes(pid)    -> highest volume/OI strikes
        get_vol_term_structure(pid)     -> ATM IV across expirations
        get_expected_ranges(pid)        -> Vol2Vol expected move ranges

    Convenience methods:
        get_futures_options_summary(ticker) -> combined summary
    """

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #

    def __init__(self, rate_limit_delay: float = RATE_LIMIT_DELAY) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
            }
        )
        self._authenticated: bool = False
        self._last_request_time: float = 0.0
        self._rate_limit_delay: float = rate_limit_delay
        logger.info("CMEScraper initialized (rate-limit=%.2fs)", rate_limit_delay)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._rate_limit_delay:
            sleep_time = self._rate_limit_delay - elapsed
            time.sleep(sleep_time)
        self._last_request_time = time.time()

    def _get(
        self, url: str, params: Optional[Dict] = None, timeout: int = 30
    ) -> Optional[requests.Response]:
        """Make a GET request with rate limiting and error handling."""
        self._rate_limit()
        try:
            resp = self.session.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as exc:
            logger.error("GET %s failed: %s", url, exc)
            return None

    def _post(
        self, url: str, data: Optional[Dict] = None, json_data: Optional[Dict] = None, timeout: int = 30
    ) -> Optional[requests.Response]:
        """Make a POST request with rate limiting and error handling."""
        self._rate_limit()
        try:
            resp = self.session.post(url, data=data, json=json_data, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as exc:
            logger.error("POST %s failed: %s", url, exc)
            return None

    def _safe_json(self, resp: Optional[requests.Response]) -> Optional[Dict]:
        """Safely parse JSON from a response."""
        if resp is None:
            return None
        try:
            return resp.json()
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error("JSON parse failed: %s", exc)
            return None

    @staticmethod
    def _product_name(product_id: str) -> str:
        return CME_PRODUCT_NAMES.get(product_id, f"Product-{product_id}")

    # ------------------------------------------------------------------ #
    # Authentication
    # ------------------------------------------------------------------ #

    def login(self, username: str, password: str) -> bool:
        """Login to CME Group (for QuikStrike access).

        Attempts the CME OAuth2 / form-based login flow.  The exact
        implementation is a *best-effort* framework because CME's
        authentication flow changes periodically and may require
        additional steps (captcha, 2FA, etc.).

        Args:
            username: CME Group account email/username.
            password: CME Group account password.

        Returns:
            True if authentication cookies were obtained successfully.

        Example:
            cme = CMEScraper()
            ok = cme.login("my@email.com", "mypassword")
            if ok:
                oi = cme.get_open_interest_profile("425")
        """
        logger.info("Attempting CME login for user: %s", username)

        # Step 1: Visit the main site to get initial cookies
        resp = self._get("https://www.cmegroup.com/", timeout=15)
        if resp is None:
            logger.error("Failed to reach CME homepage")
            return False

        # Step 2: Try the internal auth endpoint
        auth_payload = {
            "username": username,
            "password": password,
            "resource": "https://www.cmegroup.com/tools-information/quikstrike",
        }
        auth_resp = self._post(CME_AUTH_URL, data=auth_payload, timeout=15)
        if auth_resp is None:
            logger.error("Auth POST failed")
            return False

        # Step 3: Check if we got a success indicator
        # CME may return a redirect, a JSON token, or set cookies directly.
        try:
            auth_json = auth_resp.json()
            if auth_json.get("success") or auth_json.get("token"):
                self._authenticated = True
                logger.info("CME login successful (JSON response)")
                return True
        except (json.JSONDecodeError, ValueError):
            pass

        # Alternative: check cookies for SSO session indicators
        cookies = self.session.cookies.get_dict()
        if any(k in cookies for k in ("CMESession", "sso_token", "cmegroup_identity")):
            self._authenticated = True
            logger.info("CME login successful (cookie-based)")
            return True

        # If we got a redirect to the tools page, that's also success
        if auth_resp.history and any(
            "quikstrike" in (r.url or "") for r in auth_resp.history
        ):
            self._authenticated = True
            logger.info("CME login successful (redirect)")
            return True

        logger.warning(
            "CME login may have succeeded but no clear indicator found. "
            "Authenticated methods will be attempted anyway."
        )
        self._authenticated = True  # optimistic -- let subsequent calls decide
        return True

    def is_authenticated(self) -> bool:
        """Return True if the scraper has authenticated successfully."""
        return self._authenticated

    # ------------------------------------------------------------------ #
    # PUBLIC DATA METHODS (no login required)
    # ------------------------------------------------------------------ #

    def get_settlements(self, product_id: str) -> List[Dict]:
        """Get daily settlement prices (PUBLIC -- no login needed).

        Args:
            product_id: CME numeric product ID (e.g. '133' for Gold).

        Returns:
            List of settlement dicts, one per contract month.
            Each dict contains: contractMonth, open, high, low, last,
            change, settle, volume, openInterest, etc.

        Example:
            cme = CMEScraper()
            settlements = cme.get_settlements("133")  # Gold
            # -> [{"contractMonth": "APR 25", "settle": 2450.30, ...}, ...]
        """
        url = SETTLEMENTS_API.format(productId=product_id)
        logger.info("Fetching settlements for %s (%s)", product_id, self._product_name(product_id))

        resp = self._get(url)
        data = self._safe_json(resp)
        if data is None:
            logger.warning("No settlement data returned for %s", product_id)
            return []

        # The API returns either a list directly or a dict with a 'settlements' key
        if isinstance(data, list):
            settlements = data
        elif isinstance(data, dict):
            settlements = data.get("settlements", data.get("rows", []))
        else:
            settlements = []

        # Normalise each record
        results: List[Dict] = []
        for row in settlements:
            if not isinstance(row, dict):
                continue
            record = {
                "product_id": product_id,
                "product_name": self._product_name(product_id),
                "contract_month": row.get("month") or row.get("contractMonth") or row.get("expirationMonth"),
                "contract_code": row.get("productCode") or row.get("product_id"),
                "open": self._parse_float(row.get("open")),
                "high": self._parse_float(row.get("high")),
                "low": self._parse_float(row.get("low")),
                "last": self._parse_float(row.get("last")),
                "change": self._parse_float(row.get("change")),
                "settle": self._parse_float(row.get("settle")),
                "volume": self._parse_int(row.get("volume")),
                "open_interest": self._parse_int(row.get("openInterest") or row.get("oi")),
                "oi_change": self._parse_int(row.get("oiChange") or row.get("openInterestChange")),
                "timestamp": row.get("updated") or row.get("timestamp"),
            }
            results.append(record)

        logger.info("Fetched %d settlement records for %s", len(results), product_id)
        return results

    def get_volume(self, product_id: str) -> Dict:
        """Get volume and open interest (PUBLIC -- no login needed).

        Args:
            product_id: CME numeric product ID.

        Returns:
            Dict with volume/OI breakdown by contract month plus totals.

        Example:
            vol = cme.get_volume("133")
            # -> {"product_id": "133", "contracts": [...], "total_volume": 150000, ...}
        """
        url = VOLUME_API.format(productId=product_id)
        logger.info("Fetching volume/OI for %s", product_id)

        resp = self._get(url)
        data = self._safe_json(resp)
        if data is None:
            logger.warning("No volume data returned for %s", product_id)
            return {"product_id": product_id, "contracts": []}

        # Normalise structure
        if isinstance(data, list):
            contracts = data
            totals = {}
        elif isinstance(data, dict):
            contracts = data.get("contracts", data.get("rows", []))
            totals = {
                "total_volume": self._parse_int(
                    data.get("totalVolume") or data.get("volume")
                ),
                "total_open_interest": self._parse_int(
                    data.get("totalOpenInterest") or data.get("openInterest")
                ),
            }
        else:
            contracts = []
            totals = {}

        normalised: List[Dict] = []
        for row in contracts:
            if not isinstance(row, dict):
                continue
            normalised.append(
                {
                    "contract_month": row.get("month")
                    or row.get("contractMonth")
                    or row.get("expirationMonth"),
                    "volume": self._parse_int(row.get("volume")),
                    "open_interest": self._parse_int(
                        row.get("openInterest") or row.get("oi")
                    ),
                    "oi_change": self._parse_int(
                        row.get("oiChange") or row.get("openInterestChange")
                    ),
                }
            )

        result = {
            "product_id": product_id,
            "product_name": self._product_name(product_id),
            "contracts": normalised,
            **totals,
        }
        logger.info("Fetched volume/OI for %s (%d contracts)", product_id, len(normalised))
        return result

    def get_product_info(self, product_id: str) -> Dict:
        """Get product calendar and specification info (PUBLIC).

        Args:
            product_id: CME numeric product ID.

        Returns:
            Dict with product specification and calendar details.
        """
        url = PRODUCTS_API.format(productId=product_id)
        logger.info("Fetching product info for %s", product_id)

        resp = self._get(url)
        data = self._safe_json(resp)
        if data is None:
            return {"product_id": product_id}

        # Normalise to a clean dict
        if isinstance(data, dict):
            data.setdefault("product_id", product_id)
            return data
        return {"product_id": product_id, "raw": data}

    def get_quick_quote(self, ticker: str) -> Dict:
        """Get quick quote from CME public API.

        Attempts multiple endpoints to get current futures price data.

        Args:
            ticker: Product ID string (e.g. '133', '425') or
                a human-readable ticker like 'GC', 'EUR'.

        Returns:
            Dict with last price, change, bid/ask, volume, etc.
        """
        # Resolve ticker -> product_id
        product_id = self._resolve_ticker(ticker)
        if not product_id:
            logger.warning("Could not resolve ticker '%s' to product ID", ticker)
            return {"ticker": ticker, "error": "Unknown ticker"}

        # Try the newer markets API first
        quote = self._quote_markets_api(product_id)
        if quote:
            return quote

        # Fall back to the legacy quote API
        quote = self._quote_legacy_api(product_id)
        if quote:
            return quote

        # Last resort: use settlement data as a quote proxy
        settlements = self.get_settlements(product_id)
        if settlements:
            front = settlements[0]
            return {
                "ticker": ticker,
                "product_id": product_id,
                "product_name": self._product_name(product_id),
                "last": front.get("last"),
                "settle": front.get("settle"),
                "change": front.get("change"),
                "volume": front.get("volume"),
                "open_interest": front.get("open_interest"),
                "contract_month": front.get("contract_month"),
                "source": "settlements_proxy",
                "timestamp": front.get("timestamp"),
            }

        return {"ticker": ticker, "product_id": product_id, "error": "No quote data available"}

    def _quote_markets_api(self, product_id: str) -> Optional[Dict]:
        """Try the newer CME Markets API for a quote."""
        url = f"{MARKETS_API_BASE}/quotes/products/{product_id}"
        resp = self._get(url, timeout=10)
        data = self._safe_json(resp)
        if data is None:
            return None

        try:
            quote = data.get("last", {})
            return {
                "product_id": product_id,
                "product_name": self._product_name(product_id),
                "last": self._parse_float(quote.get("price")),
                "change": self._parse_float(quote.get("change")),
                "change_percent": self._parse_float(quote.get("changePercent")),
                "bid": self._parse_float(quote.get("bidPrice")),
                "ask": self._parse_float(quote.get("askPrice")),
                "high": self._parse_float(quote.get("highPrice")),
                "low": self._parse_float(quote.get("lowPrice")),
                "volume": self._parse_int(quote.get("volume")),
                "open_interest": self._parse_int(quote.get("openInterest")),
                "timestamp": quote.get("updatedTime"),
                "source": "markets_api",
            }
        except (AttributeError, TypeError):
            return None

    def _quote_legacy_api(self, product_id: str) -> Optional[Dict]:
        """Try the legacy CME quote endpoint."""
        url = QUOTE_API.format(productId=product_id)
        resp = self._get(url, timeout=10)
        data = self._safe_json(resp)
        if data is None:
            return None

        try:
            quotes = data if isinstance(data, list) else data.get("quotes", [])
            if not quotes:
                return None
            q = quotes[0] if isinstance(quotes, list) else quotes
            return {
                "product_id": product_id,
                "product_name": self._product_name(product_id),
                "last": self._parse_float(q.get("last")),
                "change": self._parse_float(q.get("change")),
                "bid": self._parse_float(q.get("bid")),
                "ask": self._parse_float(q.get("ask")),
                "high": self._parse_float(q.get("high")),
                "low": self._parse_float(q.get("low")),
                "volume": self._parse_int(q.get("volume")),
                "open_interest": self._parse_int(q.get("openInterest")),
                "contract_month": q.get("expirationDate") or q.get("contractMonth"),
                "timestamp": q.get("updated") or q.get("timestamp"),
                "source": "legacy_quote_api",
            }
        except (AttributeError, TypeError, IndexError):
            return None

    # ------------------------------------------------------------------ #
    # AUTHENTICATED METHODS (QuikStrike -- login required)
    # ------------------------------------------------------------------ #

    def get_open_interest_profile(
        self, product_id: str, expiry: Optional[str] = None
    ) -> Dict:
        """Get OI profile from QuikStrike (requires login).

        Returns Open Interest by strike with call/put breakdown.

        Args:
            product_id: CME numeric product ID.
            expiry: Optional expiration month filter (e.g. 'APR 25').

        Returns:
            Dict with 'strikes' list and summary stats.
        """
        if not self._authenticated:
            logger.warning("CME login required for OI Profile")
            return {"product_id": product_id, "strikes": [], "error": "Login required"}

        logger.info("Fetching OI profile for %s", product_id)

        # QuikStrike serves OI data via an internal AJAX endpoint
        params: Dict[str, str] = {"productId": product_id}
        if expiry:
            params["expiry"] = expiry

        # Try the known internal data endpoint patterns
        oi_data = self._fetch_quikstrike_data("oi-profile", params)
        if not oi_data:
            logger.warning("No OI profile data for %s", product_id)
            return {"product_id": product_id, "strikes": []}

        # Parse and normalise strike data
        strikes: List[Dict] = []
        if isinstance(oi_data, list):
            for row in oi_data:
                strikes.append(self._normalise_strike_row(row))
        elif isinstance(oi_data, dict):
            for row in oi_data.get("strikes", oi_data.get("data", [])):
                strikes.append(self._normalise_strike_row(row))

        # Compute summary stats
        total_call_oi = sum(s.get("call_oi", 0) or 0 for s in strikes)
        total_put_oi = sum(s.get("put_oi", 0) or 0 for s in strikes)

        return {
            "product_id": product_id,
            "product_name": self._product_name(product_id),
            "expiry_filter": expiry,
            "strikes": strikes,
            "total_call_oi": total_call_oi,
            "total_put_oi": total_put_oi,
            "total_oi": total_call_oi + total_put_oi,
            "put_call_ratio": round(total_put_oi / total_call_oi, 4) if total_call_oi else None,
            "max_pain": self._estimate_max_pain(strikes),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    def get_most_active_strikes(self, product_id: str, top_n: int = 20) -> List[Dict]:
        """Get most active option strikes (requires login).

        Args:
            product_id: CME numeric product ID.
            top_n: Number of top strikes to return.

        Returns:
            List of strike dicts sorted by total activity (volume + OI).
        """
        if not self._authenticated:
            logger.warning("CME login required for Most Active Strikes")
            return []

        logger.info("Fetching most active strikes for %s", product_id)

        params = {"productId": product_id, "limit": str(top_n)}
        data = self._fetch_quikstrike_data("most-active-strikes", params)

        if not data:
            return []

        strikes_raw = data if isinstance(data, list) else data.get("strikes", data.get("data", []))
        strikes: List[Dict] = []
        for row in strikes_raw[:top_n]:
            strikes.append(self._normalise_strike_row(row))

        # Sort by total activity (volume + OI change)
        strikes.sort(
            key=lambda s: (s.get("call_volume", 0) or 0)
            + (s.get("put_volume", 0) or 0)
            + (s.get("call_oi_change", 0) or 0)
            + (s.get("put_oi_change", 0) or 0),
            reverse=True,
        )

        return strikes

    def get_vol_term_structure(self, product_id: str) -> List[Dict]:
        """Get ATM implied volatility across expirations (requires login).

        Args:
            product_id: CME numeric product ID.

        Returns:
            List of dicts with ATM IV and skew for each expiration.
        """
        if not self._authenticated:
            logger.warning("CME login required for Vol Term Structure")
            return []

        logger.info("Fetching vol term structure for %s", product_id)

        params = {"productId": product_id}
        data = self._fetch_quikstrike_data("vol-term-structure", params)

        if not data:
            return []

        rows = data if isinstance(data, list) else data.get("termStructure", data.get("data", []))

        results: List[Dict] = []
        for row in rows:
            results.append(
                {
                    "expiry": row.get("expiration") or row.get("expiry") or row.get("contractMonth"),
                    "days_to_expiry": self._parse_int(row.get("dte") or row.get("daysToExpiration")),
                    "atm_iv": self._parse_float(row.get("atmIv") or row.get("atmIV") or row.get("atm")),
                    "_25d_call_skew": self._parse_float(
                        row.get("25dCallSkew") or row.get("callSkew25d")
                    ),
                    "_25d_put_skew": self._parse_float(
                        row.get("25dPutSkew") or row.get("putSkew25d")
                    ),
                    "_10d_call_skew": self._parse_float(
                        row.get("10dCallSkew") or row.get("callSkew10d")
                    ),
                    "_10d_put_skew": self._parse_float(
                        row.get("10dPutSkew") or row.get("putSkew10d")
                    ),
                }
            )

        # Sort by days to expiry
        results.sort(key=lambda x: x.get("days_to_expiry") or 9999)
        return results

    def get_expected_ranges(self, product_id: str) -> List[Dict]:
        """Get Vol2Vol expected range data (requires login).

        Args:
            product_id: CME numeric product ID.

        Returns:
            List of expected move ranges by expiration.
        """
        if not self._authenticated:
            logger.warning("CME login required for Vol2Vol Expected Range")
            return []

        logger.info("Fetching expected ranges for %s", product_id)

        params = {"productId": product_id}
        data = self._fetch_quikstrike_data("vol2vol", params)

        if not data:
            return []

        rows = data if isinstance(data, list) else data.get("ranges", data.get("data", []))

        results: List[Dict] = []
        for row in rows:
            expected_move = self._parse_float(
                row.get("expectedMove") or row.get("expected_move")
            )
            current_price = self._parse_float(
                row.get("underlyingPrice") or row.get("currentPrice") or row.get("last")
            )
            confidence = self._parse_float(row.get("confidence")) or 0.68

            lower = None
            upper = None
            if current_price is not None and expected_move is not None:
                lower = round(current_price - expected_move, 4)
                upper = round(current_price + expected_move, 4)

            results.append(
                {
                    "expiry": row.get("expiration") or row.get("expiry"),
                    "days_forward": self._parse_int(
                        row.get("daysForward") or row.get("dte")
                    ),
                    "current_price": current_price,
                    "expected_move": expected_move,
                    "confidence": confidence,
                    "lower_bound": lower,
                    "upper_bound": upper,
                    "atm_iv": self._parse_float(row.get("atmIv") or row.get("atmIV")),
                }
            )

        return results

    def _fetch_quikstrike_data(self, tool: str, params: Dict) -> Optional[Dict]:
        """Internal: fetch data from a QuikStrike internal endpoint.

        QuikStrike pages load data via AJAX calls after the initial HTML.
        We try known endpoint patterns to grab the JSON directly.

        Args:
            tool: Tool identifier ('oi-profile', 'most-active-strikes',
                'vol-term-structure', 'vol2vol').
            params: Query parameters including productId.

        Returns:
            Parsed JSON data or None.
        """
        # Known internal endpoint patterns (best-effort)
        endpoint_patterns = {
            "oi-profile": [
                "https://www.cmegroup.com/CmeWS/mvc/QuikStrikeApi/GetOIOpenInterestProfile",
                "https://www.cmegroup.com/CmeWS/mvc/QuikStrikeApi/GetOpenInterestProfile",
                "https://www.cmegroup.com/services/quikstrike/oi-profile",
            ],
            "most-active-strikes": [
                "https://www.cmegroup.com/CmeWS/mvc/QuikStrikeApi/GetMostActiveStrikes",
                "https://www.cmegroup.com/services/quikstrike/most-active-strikes",
            ],
            "vol-term-structure": [
                "https://www.cmegroup.com/CmeWS/mvc/QuikStrikeApi/GetVolTermStructure",
                "https://www.cmegroup.com/services/quikstrike/vol-term-structure",
            ],
            "vol2vol": [
                "https://www.cmegroup.com/CmeWS/mvc/QuikStrikeApi/GetVol2VolExpectedRange",
                "https://www.cmegroup.com/services/quikstrike/vol2vol",
            ],
        }

        urls = endpoint_patterns.get(tool, [])
        for url in urls:
            resp = self._get(url, params=params, timeout=15)
            data = self._safe_json(resp)
            if data is not None:
                logger.debug("QuikStrike data fetched from %s", url)
                return data

        logger.warning("All QuikStrike endpoint patterns failed for tool '%s'", tool)
        return None

    # ------------------------------------------------------------------ #
    # Convenience / aggregate methods
    # ------------------------------------------------------------------ #

    def get_futures_options_summary(self, ticker: str) -> Dict:
        """Get combined summary for a futures product.

        Tries authenticated endpoints first, falls back to public data.

        Args:
            ticker: Product ticker (e.g. 'GC', 'EUR', '133', '425').

        Returns:
            Dict with: settlements, volume, oi_profile (if available),
            quote, and metadata.

        Example:
            summary = cme.get_futures_options_summary("133")  # Gold
        """
        product_id = self._resolve_ticker(ticker)
        if not product_id:
            return {"ticker": ticker, "error": f"Unknown ticker: {ticker}"}

        logger.info("Building futures+options summary for %s (id=%s)", ticker, product_id)

        summary: Dict = {
            "ticker": ticker,
            "product_id": product_id,
            "product_name": self._product_name(product_id),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        # 1. Public: settlements
        try:
            settlements = self.get_settlements(product_id)
            summary["settlements"] = settlements
            summary["front_month"] = settlements[0] if settlements else None
        except Exception as exc:
            logger.error("Settlements fetch failed: %s", exc)
            summary["settlements"] = []

        # 2. Public: volume
        try:
            summary["volume"] = self.get_volume(product_id)
        except Exception as exc:
            logger.error("Volume fetch failed: %s", exc)
            summary["volume"] = {}

        # 3. Public: quote
        try:
            summary["quote"] = self.get_quick_quote(product_id)
        except Exception as exc:
            logger.error("Quote fetch failed: %s", exc)
            summary["quote"] = {}

        # 4. Authenticated: OI profile
        if self._authenticated:
            try:
                oi = self.get_open_interest_profile(product_id)
                summary["oi_profile"] = oi
            except Exception as exc:
                logger.error("OI profile fetch failed: %s", exc)
                summary["oi_profile"] = {"error": str(exc)}

            try:
                summary["most_active_strikes"] = self.get_most_active_strikes(product_id)
            except Exception as exc:
                logger.error("Most active strikes fetch failed: %s", exc)
                summary["most_active_strikes"] = []

            try:
                summary["vol_term_structure"] = self.get_vol_term_structure(product_id)
            except Exception as exc:
                logger.error("Vol term structure fetch failed: %s", exc)
                summary["vol_term_structure"] = []
        else:
            summary["oi_profile"] = {"note": "Login required for OI profile"}
            summary["most_active_strikes"] = []
            summary["vol_term_structure"] = []

        logger.info("Summary built for %s", ticker)
        return summary

    def get_multiple_products(self, product_ids: List[str]) -> Dict[str, Dict]:
        """Fetch summaries for multiple products efficiently.

        Args:
            product_ids: List of CME product IDs.

        Returns:
            Dict mapping product_id -> summary dict.
        """
        results: Dict[str, Dict] = {}
        for pid in product_ids:
            try:
                results[pid] = self.get_futures_options_summary(pid)
            except Exception as exc:
                logger.error("Failed to fetch %s: %s", pid, exc)
                results[pid] = {"product_id": pid, "error": str(exc)}
        return results

    # ------------------------------------------------------------------ #
    # Static helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _resolve_ticker(ticker: str) -> Optional[str]:
        """Resolve a human-readable ticker to a CME product ID.

        Supports:
            - Direct numeric IDs: '133', '425'
            - Human names: 'EUR', 'GBP', 'GOLD', 'GC'
            - Lowercase variants.
        """
        # Already a known key
        upper = ticker.upper()
        if upper in CME_PRODUCTS:
            return CME_PRODUCTS[upper]

        # Already a numeric product ID
        if ticker.isdigit() and ticker in CME_PRODUCT_NAMES:
            return ticker

        # Common Bloomberg / trading code aliases
        aliases = {
            "GC": "133",  # Gold
            "SI": "84",  # Silver
            "HG": "424",  # Copper
            "PA": "402",  # Palladium
            "PL": "4259",  # Platinum
            "CL": "4250",  # Crude Oil
            "NG": "4240",  # Natural Gas
            "BZ": "4600",  # Brent
            "MBT": "9118",  # Micro BTC
            "MET": "1465",  # Micro ETH
            "ES": "133",  # E-mini S&P 500
            "MES": "146",  # Micro E-mini S&P
            "NQ": "209",  # E-mini Nasdaq
            "MNQ": "149",  # Micro E-mini Nasdaq
            "6E": "425",  # EUR/USD
            "6B": "437",  # GBP/USD
            "6J": "471",  # JPY/USD
            "6A": "433",  # AUD/USD
            "6C": "460",  # CAD/USD
            "6S": "443",  # CHF/USD
            "6N": "377",  # NZD/USD
            "6M": "458",  # MXN/USD
            "ZT": "6470",  # 2Y T-Note
            "ZF": "6474",  # 5Y T-Note
            "ZN": "6608",  # 10Y T-Note
            "ZB": "6516",  # 30Y T-Bond
        }
        if upper in aliases:
            return aliases[upper]

        return None

    @staticmethod
    def _parse_float(val) -> Optional[float]:
        """Safely parse a value to float, returning None on failure."""
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        try:
            # Handle CME's occasional use of '-' for unchanged
            cleaned = str(val).replace(",", "").replace("-", "").strip()
            if cleaned == "" or cleaned.upper() == "UNCH":
                return 0.0 if str(val) == "-" else None
            return float(cleaned)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_int(val) -> Optional[int]:
        """Safely parse a value to int, returning None on failure."""
        if val is None:
            return None
        if isinstance(val, int):
            return val
        if isinstance(val, float):
            return int(val)
        try:
            cleaned = str(val).replace(",", "").replace("-", "").strip()
            if cleaned == "":
                return None
            return int(cleaned)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _normalise_strike_row(row: Dict) -> Dict:
        """Normalise a strike data row from various QuikStrike formats."""
        return {
            "strike": CMEScraper._parse_float(row.get("strike")),
            "call_oi": CMEScraper._parse_int(row.get("callOi") or row.get("callOI") or row.get("callOpenInterest")),
            "put_oi": CMEScraper._parse_int(row.get("putOi") or row.get("putOI") or row.get("putOpenInterest")),
            "total_oi": CMEScraper._parse_int(row.get("totalOi") or row.get("totalOI")),
            "call_oi_change": CMEScraper._parse_int(row.get("callOiChange") or row.get("callOIChange")),
            "put_oi_change": CMEScraper._parse_int(row.get("putOiChange") or row.get("putOIChange")),
            "call_volume": CMEScraper._parse_int(row.get("callVolume")),
            "put_volume": CMEScraper._parse_int(row.get("putVolume")),
            "net_credit": CMEScraper._parse_float(row.get("netCredit")),
            "gamma_exposure": CMEScraper._parse_float(row.get("gamma") or row.get("gammaExposure")),
        }

    @staticmethod
    def _estimate_max_pain(strikes: List[Dict]) -> Optional[float]:
        """Estimate max pain strike (where total OI is highest).

        This is a simplified estimate -- true max pain requires
        knowing option premiums and computing dollar loss at each strike.
        """
        if not strikes:
            return None
        max_oi = 0
        max_pain_strike = None
        for s in strikes:
            total = (s.get("call_oi", 0) or 0) + (s.get("put_oi", 0) or 0)
            if total > max_oi:
                max_oi = total
                max_pain_strike = s.get("strike")
        return max_pain_strike


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------


def get_cme_settlements(product_id: str) -> List[Dict]:
    """One-shot function to get settlements without instantiating the class."""
    scraper = CMEScraper()
    return scraper.get_settlements(product_id)


def get_cme_volume(product_id: str) -> Dict:
    """One-shot function to get volume without instantiating the class."""
    scraper = CMEScraper()
    return scraper.get_volume(product_id)


def get_cme_quote(ticker: str) -> Dict:
    """One-shot function to get a quote without instantiating the class."""
    scraper = CMEScraper()
    return scraper.get_quick_quote(ticker)


def list_supported_products() -> Dict[str, str]:
    """Return a dict of supported product names and their IDs."""
    return {
        name: pid
        for name, pid in CME_PRODUCTS.items()
    }


# ---------------------------------------------------------------------------
# CLI entry point (for quick testing)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CME Group Data Scraper")
    parser.add_argument("--product", "-p", default="133", help="Product ID (default: 133=Gold)")
    parser.add_argument("--settlements", action="store_true", help="Fetch settlements")
    parser.add_argument("--volume", action="store_true", help="Fetch volume/OI")
    parser.add_argument("--quote", action="store_true", help="Fetch quote")
    parser.add_argument("--summary", action="store_true", help="Fetch full summary")
    parser.add_argument("--login", help="CME username (enables authenticated features)")
    parser.add_argument("--password", help="CME password")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    scraper = CMEScraper()

    if args.login and args.password:
        scraper.login(args.login, args.password)

    if args.summary:
        result = scraper.get_futures_options_summary(args.product)
        print(json.dumps(result, indent=2, default=str))
    elif args.settlements:
        result = scraper.get_settlements(args.product)
        print(json.dumps(result, indent=2, default=str))
    elif args.volume:
        result = scraper.get_volume(args.product)
        print(json.dumps(result, indent=2, default=str))
    elif args.quote:
        result = scraper.get_quick_quote(args.product)
        print(json.dumps(result, indent=2, default=str))
    else:
        # Default: fetch everything publicly available
        print("=== Settlements ===")
        print(json.dumps(scraper.get_settlements(args.product), indent=2, default=str))
        print("\n=== Volume ===")
        print(json.dumps(scraper.get_volume(args.product), indent=2, default=str))
        print("\n=== Quote ===")
        print(json.dumps(scraper.get_quick_quote(args.product), indent=2, default=str))
