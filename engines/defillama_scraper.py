"""engines/defillama_scraper.py — DeFiLlama On-Chain Data Fetcher v1.0

Fetches on-chain metrics from DeFiLlama API:
  - TVL, TVL changes per chain
  - DEX volumes, fees
  - Stablecoin market caps
  - Yield opportunities
  - Active addresses

Usage:
    from engines.defillama_scraper import DeFiLlamaFetcher
    fetcher = DeFiLlamaFetcher()
    tvl_data = fetcher.get_chain_tvl("Ethereum")
    all_chains = fetcher.get_all_chains()
"""

import logging
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict

import requests

logger = logging.getLogger(__name__)

# DeFiLlama runs multiple sub-domains for different data sets.
BASE_API = "https://api.llama.fi"
BASE_STABLECOINS = "https://stablecoins.llama.fi"
BASE_YIELDS = "https://yields.llama.fi"


@dataclass
class ChainMetrics:
    """Aggregated on-chain metrics for a single blockchain."""

    name: str
    tvl: float = 0.0
    tvl_1d_change: float = 0.0
    tvl_7d_change: float = 0.0
    tvl_1m_change: float = 0.0
    dex_volume_24h: float = 0.0
    fees_24h: float = 0.0
    active_addresses: int = 0
    stablecoin_mcap: float = 0.0
    mcaptvl: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dict representation (JSON-serializable)."""
        return asdict(self)

    @property
    def tvl_change_score(self) -> float:
        """Composite TVL momentum score (weighted 1d/7d/1m)."""
        return (
            self.tvl_1d_change * 0.5
            + self.tvl_7d_change * 0.3
            + self.tvl_1m_change * 0.2
        )


class DeFiLlamaFetcher:
    """Fetch on-chain data from the public DeFiLlama API.

    All endpoints are free, require no API key, and return JSON.
    Built-in rate limiting (0.5 s between calls) and retry logic
    keep the scraper polite and resilient.
    """

    # DeFiLlama public API endpoints (relative to BASE_API)
    ENDPOINTS = {
        "chains": "/chains",
        "v2_chains": "/v2/chains",
        "dexs_overview": "/overview/dexs",
        "fees_overview": "/overview/fees",
        "protocols": "/protocols",
        "protocol_fees": "/summary/fees/{protocol}",
        "chain_tvl_history": "/v2/historicalChainTvl/{chain}",
    }

    # Sub-domain endpoints
    ENDPOINTS_STABLECOINS = {
        "stablecoins": "/stablecoins",
    }
    ENDPOINTS_YIELDS = {
        "pools": "/pools",
    }

    def __init__(self, delay: float = 0.5, max_retries: int = 3, timeout: int = 30):
        """Initialise the fetcher.

        Args:
            delay: Seconds to sleep between consecutive API calls.
            max_retries: Number of retries on transient errors.
            timeout: Request timeout in seconds.
        """
        self.delay = delay
        self.max_retries = max_retries
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "MacroRegime/1.0 (research bot)",
                "Accept": "application/json",
            }
        )
        self._last_call_ts: float = 0.0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        base_url: str = BASE_API,
    ) -> Optional[Any]:
        """GET *endpoint* (relative to *base_url*) with rate-limiting and retry.

        Returns the parsed JSON body, or *None* on failure.
        """
        url = f"{base_url}{endpoint}"
        self._rate_limit()

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                # Handle 429 Too Many Requests with exponential backoff
                if resp.status_code == 429:
                    sleep_backoff = (2 ** attempt) * self.delay
                    logger.warning(
                        "Rate limited on %s — sleeping %.1fs (attempt %d/%d)",
                        url,
                        sleep_backoff,
                        attempt,
                        self.max_retries,
                    )
                    time.sleep(sleep_backoff)
                    continue

                resp.raise_for_status()
                return resp.json()

            except requests.exceptions.RequestException as exc:
                logger.debug(
                    "Request error %s (attempt %d/%d): %s",
                    url,
                    attempt,
                    self.max_retries,
                    exc,
                )
                if attempt == self.max_retries:
                    logger.error("Failed after %d attempts: %s", self.max_retries, url)
                    return None
                time.sleep(self.delay * attempt)

        return None

    def _rate_limit(self) -> None:
        """Enforce the inter-request delay."""
        elapsed = time.time() - self._last_call_ts
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_call_ts = time.time()

    @staticmethod
    def _safe_float(value: Any) -> float:
        """Coerce *value* to float, returning 0.0 on failure."""
        try:
            return float(value) if value is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _safe_int(value: Any) -> int:
        """Coerce *value* to int, returning 0 on failure."""
        try:
            return int(value) if value is not None else 0
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _safe_pegged_usd(circulating: Any) -> float:
        """Extract peggedUSD value from a circulating dict.

        Handles formats like:
          {"peggedUSD": 123.45}
          {"current": {"peggedUSD": 123.45}}
        """
        if not isinstance(circulating, dict):
            return 0.0
        if "peggedUSD" in circulating:
            return DeFiLlamaFetcher._safe_float(circulating["peggedUSD"])
        if "current" in circulating and isinstance(circulating["current"], dict):
            return DeFiLlamaFetcher._safe_float(circulating["current"].get("peggedUSD"))
        return 0.0

    # ------------------------------------------------------------------
    # Public API — Chains & TVL
    # ------------------------------------------------------------------

    def get_all_chains(self, enrich_changes: bool = True, top_n: int = 20) -> List[ChainMetrics]:
        """Fetch all chain TVL data.

        Args:
            enrich_changes: If *True*, fetch historical data for the top *top_n*
                chains to compute 1d/7d/1m changes.
            top_n: Number of top chains to enrich with change data.

        Returns a list of ``ChainMetrics`` ordered by TVL descending.
        """
        data = self._get(self.ENDPOINTS["chains"])
        if not isinstance(data, list):
            logger.error("Unexpected /chains response type: %s", type(data).__name__)
            return []

        metrics: List[ChainMetrics] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name", "unknown")
            tvl = self._safe_float(entry.get("tvl"))
            mcaptvl = self._safe_float(entry.get("mcaptvl"))

            metrics.append(
                ChainMetrics(
                    name=name,
                    tvl=tvl,
                    mcaptvl=mcaptvl,
                )
            )

        metrics.sort(key=lambda x: x.tvl, reverse=True)

        # Enrich top N chains with historical change data
        if enrich_changes and metrics:
            for m in metrics[:top_n]:
                enriched = self.get_chain_tvl(m.name)
                if enriched is not None:
                    m.tvl_1d_change = enriched.tvl_1d_change
                    m.tvl_7d_change = enriched.tvl_7d_change
                    m.tvl_1m_change = enriched.tvl_1m_change

        return metrics

    def get_chain_tvl(self, chain_name: str) -> Optional[ChainMetrics]:
        """Fetch detailed TVL history for a specific *chain_name*.

        Returns a single ``ChainMetrics`` with the most recent point, or *None*.
        """
        endpoint = self.ENDPOINTS["chain_tvl_history"].format(chain=chain_name)
        data = self._get(endpoint)
        if not isinstance(data, list) or not data:
            return None

        # data is a list of {date, tvl} — take the most recent
        latest = data[-1]
        prev_day = data[-2] if len(data) > 1 else latest
        prev_week = data[-8] if len(data) > 7 else prev_day
        prev_month = data[-30] if len(data) > 29 else prev_week

        tvl_now = self._safe_float(latest.get("tvl"))
        tvl_prev_day = self._safe_float(prev_day.get("tvl"))
        tvl_prev_week = self._safe_float(prev_week.get("tvl"))
        tvl_prev_month = self._safe_float(prev_month.get("tvl"))

        change_1d = (
            ((tvl_now - tvl_prev_day) / tvl_prev_day * 100) if tvl_prev_day else 0.0
        )
        change_7d = (
            ((tvl_now - tvl_prev_week) / tvl_prev_week * 100) if tvl_prev_week else 0.0
        )
        change_1m = (
            ((tvl_now - tvl_prev_month) / tvl_prev_month * 100)
            if tvl_prev_month
            else 0.0
        )

        return ChainMetrics(
            name=chain_name,
            tvl=tvl_now,
            tvl_1d_change=change_1d,
            tvl_7d_change=change_7d,
            tvl_1m_change=change_1m,
        )

    # ------------------------------------------------------------------
    # Public API — DEX Volumes
    # ------------------------------------------------------------------

    def get_dex_volumes(
        self,
        chain_filter: Optional[List[str]] = None,
        top_n: int = 20,
    ) -> Dict[str, float]:
        """Fetch 24 h DEX volumes per chain.

        Args:
            chain_filter: Explicit list of chains to query. If *None*, the
                top *top_n* chains by TVL are used.
            top_n: Number of top-TVL chains to query when *chain_filter*
                is not provided.

        Returns ``{chain_name: volume_24h, ...}``.
        """
        # Determine which chains to query
        if chain_filter is None:
            chains_list = self._get(self.ENDPOINTS["v2_chains"])
            if isinstance(chains_list, list):
                chain_names = [
                    c.get("name", "")
                    for c in chains_list
                    if isinstance(c, dict) and c.get("name")
                ]
                chain_names.sort(
                    key=lambda n: next(
                        (c.get("tvl", 0) for c in chains_list if c.get("name") == n),
                        0,
                    ),
                    reverse=True,
                )
                chains_to_query = chain_names[:top_n]
            else:
                chains_to_query = [
                    "Ethereum",
                    "Solana",
                    "BSC",
                    "Base",
                    "Arbitrum",
                    "Avalanche",
                    "Polygon",
                    "Optimism",
                ]
        else:
            chains_to_query = chain_filter

        volumes: Dict[str, float] = {}
        for chain in chains_to_query:
            endpoint = f"/overview/dexs/{chain}"
            data = self._get(endpoint)
            if isinstance(data, dict):
                vol = self._safe_float(data.get("total24h"))
                if vol > 0:
                    volumes[chain] = vol

        return volumes

    def get_dex_summary(self) -> Dict[str, Any]:
        """Fetch high-level DEX overview including total volumes and trends.

        Returns a dict with ``total24h``, ``total7d``, ``change_1d``, etc.
        """
        data = self._get(self.ENDPOINTS["dexs_overview"])
        if not isinstance(data, dict):
            return {}

        return {
            "total24h": self._safe_float(data.get("total24h")),
            "total48hto24h": self._safe_float(data.get("total48hto24h")),
            "total7d": self._safe_float(data.get("total7d")),
            "total14dto7d": self._safe_float(data.get("total14dto7d")),
            "total30d": self._safe_float(data.get("total30d")),
            "total60dto30d": self._safe_float(data.get("total60dto30d")),
            "change_1d": self._safe_float(data.get("change_1d")),
            "change_7d": self._safe_float(data.get("change_7d")),
            "change_1m": self._safe_float(data.get("change_1m")),
            "protocols_count": len(data.get("protocols", [])),
        }

    # ------------------------------------------------------------------
    # Public API — Fees & Revenue
    # ------------------------------------------------------------------

    def get_fees_revenue(self) -> Dict[str, Dict[str, float]]:
        """Fetch 24 h fees and revenue per protocol.

        Returns ``{protocol: {"fees_24h": float, "revenue_24h": float}, ...}``.
        """
        data = self._get(self.ENDPOINTS["fees_overview"])
        if not isinstance(data, dict):
            logger.error("Unexpected /overview/fees response type")
            return {}

        protocols = data.get("protocols", [])
        if not isinstance(protocols, list):
            return {}

        result: Dict[str, Dict[str, float]] = {}
        for proto in protocols:
            if not isinstance(proto, dict):
                continue
            name = proto.get("name", "unknown")
            fees = self._safe_float(proto.get("total24h"))
            revenue = self._safe_float(proto.get("revenue24h"))
            result[name] = {"fees_24h": fees, "revenue_24h": revenue}

        return result

    def get_fees_summary(self) -> Dict[str, Any]:
        """Fetch high-level fees overview."""
        data = self._get(self.ENDPOINTS["fees_overview"])
        if not isinstance(data, dict):
            return {}

        return {
            "total24h": self._safe_float(data.get("total24h")),
            "total48hto24h": self._safe_float(data.get("total48hto24h")),
            "total7d": self._safe_float(data.get("total7d")),
            "total14dto7d": self._safe_float(data.get("total14dto7d")),
            "total30d": self._safe_float(data.get("total30d")),
            "total60dto30d": self._safe_float(data.get("total60dto30d")),
            "change_1d": self._safe_float(data.get("change_1d")),
            "change_7d": self._safe_float(data.get("change_7d")),
            "change_1m": self._safe_float(data.get("change_1m")),
            "protocols_count": len(data.get("protocols", [])),
        }

    def get_protocol_fees(self, protocol: str) -> Dict[str, Any]:
        """Fetch fee summary for a single protocol slug.

        Returns a dict with ``total24h``, ``total7d``, ``total30d``,
        or an empty dict on failure.
        """
        endpoint = self.ENDPOINTS["protocol_fees"].format(protocol=protocol)
        data = self._get(endpoint)
        if not isinstance(data, dict):
            return {}
        return {
            "protocol": protocol,
            "total24h": self._safe_float(data.get("total24h")),
            "total7d": self._safe_float(data.get("total7d")),
            "total30d": self._safe_float(data.get("total30d")),
        }

    # ------------------------------------------------------------------
    # Public API — Stablecoins
    # ------------------------------------------------------------------

    def get_stablecoins(self) -> Dict[str, Any]:
        """Fetch stablecoin market-cap data.

        Returns a dict with ``total_mcap``, ``chain_mcaps``, ``top_coins``,
        and flow indicators.
        """
        data = self._get(
            self.ENDPOINTS_STABLECOINS["stablecoins"],
            base_url=BASE_STABLECOINS,
        )
        if not isinstance(data, dict):
            logger.error("Unexpected stablecoins response type: %s", type(data).__name__)
            return {}

        assets = data.get("peggedAssets", [])
        if not isinstance(assets, list):
            return {}

        total_mcap = 0.0
        total_mcap_prev_day = 0.0
        total_mcap_prev_week = 0.0
        total_mcap_prev_month = 0.0
        chain_mcaps: Dict[str, float] = {}
        top_coins: List[Dict[str, Any]] = []

        for asset in assets:
            if not isinstance(asset, dict):
                continue

            # Current circulating mcap
            coin_mcap = self._safe_pegged_usd(asset.get("circulating"))
            if coin_mcap <= 0:
                continue

            total_mcap += coin_mcap
            total_mcap_prev_day += self._safe_pegged_usd(asset.get("circulatingPrevDay"))
            total_mcap_prev_week += self._safe_pegged_usd(asset.get("circulatingPrevWeek"))
            total_mcap_prev_month += self._safe_pegged_usd(asset.get("circulatingPrevMonth"))

            # Breakdown by chain
            chain_circ = asset.get("chainCirculating", {})
            if isinstance(chain_circ, dict):
                for ch, circ_data in chain_circ.items():
                    ch_mcap = self._safe_pegged_usd(circ_data)
                    if ch_mcap > 0:
                        chain_mcaps[ch] = chain_mcaps.get(ch, 0.0) + ch_mcap

            top_coins.append(
                {
                    "name": asset.get("name", "unknown"),
                    "symbol": asset.get("symbol", ""),
                    "mcap": round(coin_mcap, 2),
                    "peg_mechanism": asset.get("pegMechanism", ""),
                }
            )

        top_coins.sort(key=lambda x: x["mcap"], reverse=True)

        # Calculate flow changes
        change_1d = (
            ((total_mcap - total_mcap_prev_day) / total_mcap_prev_day * 100)
            if total_mcap_prev_day
            else 0.0
        )
        change_7d = (
            ((total_mcap - total_mcap_prev_week) / total_mcap_prev_week * 100)
            if total_mcap_prev_week
            else 0.0
        )
        change_1m = (
            ((total_mcap - total_mcap_prev_month) / total_mcap_prev_month * 100)
            if total_mcap_prev_month
            else 0.0
        )

        return {
            "total_mcap": round(total_mcap, 2),
            "change_1d_pct": round(change_1d, 4),
            "change_7d_pct": round(change_7d, 4),
            "change_1m_pct": round(change_1m, 4),
            "chain_mcaps": {k: round(v, 2) for k, v in sorted(chain_mcaps.items(), key=lambda x: x[1], reverse=True)},
            "top_coins": top_coins[:15],
            "count": len(assets),
        }

    # ------------------------------------------------------------------
    # Public API — Yields
    # ------------------------------------------------------------------

    def get_top_yields(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Fetch top yield pool opportunities.

        Returns a list of pool dicts sorted by APY descending.
        """
        data = self._get(
            self.ENDPOINTS_YIELDS["pools"],
            base_url=BASE_YIELDS,
        )
        if not isinstance(data, dict):
            logger.error("Unexpected /pools response type: %s", type(data).__name__)
            return []

        pools = data.get("data", [])
        if not isinstance(pools, list):
            return []

        results: List[Dict[str, Any]] = []
        for pool in pools[:limit]:
            if not isinstance(pool, dict):
                continue
            results.append(
                {
                    "pool_id": pool.get("pool", ""),
                    "chain": pool.get("chain", ""),
                    "project": pool.get("project", ""),
                    "symbol": pool.get("symbol", ""),
                    "apy": self._safe_float(pool.get("apy")),
                    "apy_base": self._safe_float(pool.get("apyBase")),
                    "apy_reward": self._safe_float(pool.get("apyReward")),
                    "apy_pct_1d": self._safe_float(pool.get("apyPct1D")),
                    "apy_pct_7d": self._safe_float(pool.get("apyPct7D")),
                    "tvl": self._safe_float(pool.get("tvlUsd")),
                    "stablecoin": pool.get("stablecoin", False),
                    "il_risk": pool.get("ilRisk", ""),
                }
            )

        results.sort(key=lambda x: x["apy"], reverse=True)
        return results[:limit]

    # ------------------------------------------------------------------
    # Aggregated / regime helpers
    # ------------------------------------------------------------------

    def get_crypto_liquidity_regime(self) -> Dict[str, Any]:
        """Aggregate on-chain metrics into a crypto liquidity regime signal.

        Returns a dict with:

        - **regime** — ``STRONG_INFLOW`` / ``MODERATE_INFLOW`` /
          ``NEUTRAL`` / ``OUTFLOW`` / ``CRISIS``
        - **top_chains_by_tvl_change** — top 5 chains by 1 d TVL change
        - **dex_volume_trend** — ``"rising"`` | ``"falling"`` | ``"stable"``
        - **stablecoin_flow** — ``"inflow"`` | ``"outflow"`` | ``"neutral"``
        - **confidence** — 0-100 score

        This is the primary signal used downstream for regime-based
        position sizing.
        """
        # Fetch data (top 20 chains enriched with historical changes)
        chains = self.get_all_chains(enrich_changes=True, top_n=20)
        dex_summary = self.get_dex_summary()
        stable_data = self.get_stablecoins()

        if not chains:
            return {
                "regime": "UNKNOWN",
                "top_chains_by_tvl_change": [],
                "dex_volume_trend": "unknown",
                "stablecoin_flow": "unknown",
                "confidence": 0,
            }

        # 1. TVL momentum — median 1 d % change across top 20 chains
        top20 = [c for c in chains[:20] if c.tvl > 0]
        if top20:
            median_1d = sorted(c.tvl_1d_change for c in top20)[len(top20) // 2]
            median_7d = sorted(c.tvl_7d_change for c in top20)[len(top20) // 2]
        else:
            median_1d = median_7d = 0.0

        # 2. DEX volume trend
        dex_change_1d = dex_summary.get("change_1d", 0.0)
        dex_trend = (
            "rising"
            if dex_change_1d > 2.0
            else "falling"
            if dex_change_1d < -2.0
            else "stable"
        )

        # 3. Stablecoin flow
        sc_change_1d = stable_data.get("change_1d_pct", 0.0)
        sc_flow = (
            "inflow"
            if sc_change_1d > 0.1
            else "outflow"
            if sc_change_1d < -0.1
            else "neutral"
        )

        # 4. Regime classification
        if median_1d > 5.0 and median_7d > 3.0:
            regime = "STRONG_INFLOW"
        elif median_1d > 1.0 or median_7d > 1.0:
            regime = "MODERATE_INFLOW"
        elif median_1d < -5.0 and median_7d < -3.0:
            regime = "CRISIS"
        elif median_1d < -1.0 or median_7d < -1.0:
            regime = "OUTFLOW"
        else:
            regime = "NEUTRAL"

        # 5. Confidence — based on data coverage
        coverage = min(len(top20) / 20.0 * 100, 100.0)
        confidence = int(coverage * 0.8 + 20) if top20 else 0

        # Top 5 chains by 1 d TVL change
        top_chains = sorted(top20, key=lambda x: x.tvl_1d_change, reverse=True)[:5]

        return {
            "regime": regime,
            "top_chains_by_tvl_change": [
                {
                    "name": c.name,
                    "tvl_1d_change_pct": round(c.tvl_1d_change, 2),
                    "tvl_7d_change_pct": round(c.tvl_7d_change, 2),
                    "tvl_usd": round(c.tvl, 2),
                }
                for c in top_chains
            ],
            "dex_volume_trend": dex_trend,
            "total_dex_volume_24h": round(dex_summary.get("total24h", 0), 2),
            "stablecoin_flow": sc_flow,
            "stablecoin_total_mcap": stable_data.get("total_mcap", 0),
            "median_tvl_1d_change_pct": round(median_1d, 2),
            "median_tvl_7d_change_pct": round(median_7d, 2),
            "confidence": confidence,
            "timestamp": int(time.time()),
        }

    def scrape_multi_chain(self, chain_names: List[str]) -> Dict[str, ChainMetrics]:
        """Batch-fetch metrics for multiple chains.

        Returns ``{chain_name: ChainMetrics, ...}``.  Missing chains are
        silently omitted.
        """
        result: Dict[str, ChainMetrics] = {}
        for name in chain_names:
            metric = self.get_chain_tvl(name)
            if metric is not None:
                result[name] = metric
        return result

    def get_full_snapshot(self) -> Dict[str, Any]:
        """Pull *all* data sources and return a unified snapshot.

        Useful for persisting a complete on-chain dataset in one call.
        """
        chains = self.get_all_chains(enrich_changes=True, top_n=20)
        dex_summary = self.get_dex_summary()
        fees_summary = self.get_fees_summary()
        stables = self.get_stablecoins()
        yields_top = self.get_top_yields(limit=20)
        regime = self.get_crypto_liquidity_regime()

        return {
            "chains": [c.to_dict() for c in chains],
            "dex_summary": dex_summary,
            "fees_summary": fees_summary,
            "stablecoins": stables,
            "top_yields": yields_top,
            "liquidity_regime": regime,
            "fetched_at": int(time.time()),
        }


# ---------------------------------------------------------------------------
# CLI quick-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    fetcher = DeFiLlamaFetcher()

    # 1. All chains TVL
    chains = fetcher.get_all_chains(enrich_changes=True, top_n=10)
    print(f"\n=== DeFiLlama On-Chain Data ===")
    print(f"Fetched {len(chains)} chains (top 10 enriched with changes)")
    if chains:
        top = chains[0]
        print(f"Top chain: {top.name} TVL=${top.tvl / 1e9:.2f}B")
        print(
            f"  1d: {top.tvl_1d_change:+.2f}% | 7d: {top.tvl_7d_change:+.2f}% | 1m: {top.tvl_1m_change:+.2f}%"
        )

    # 2. DEX volumes
    dex_summary = fetcher.get_dex_summary()
    print(f"\nDEX 24h volume: ${dex_summary.get('total24h', 0) / 1e6:.1f}M")
    print(f"DEX 1d change: {dex_summary.get('change_1d', 0):+.2f}%")

    # 3. Fees
    fees_summary = fetcher.get_fees_summary()
    print(f"Fees 24h: ${fees_summary.get('total24h', 0) / 1e6:.1f}M")

    # 4. Stablecoins
    stables = fetcher.get_stablecoins()
    print(f"\nStablecoin total mcap: ${stables.get('total_mcap', 0) / 1e9:.2f}B")
    print(f"Stablecoin 1d change: {stables.get('change_1d_pct', 0):+.4f}%")

    # 5. Top yields
    yields = fetcher.get_top_yields(limit=5)
    print(f"\nTop {len(yields)} yield pools:")
    for y in yields[:5]:
        print(f"  {y['project']} ({y['chain']}) — {y['symbol']} @ {y['apy']:.2f}% APY")

    # 6. Liquidity regime
    regime = fetcher.get_crypto_liquidity_regime()
    print(f"\n=== Crypto Liquidity Regime ===")
    print(f"Regime: {regime['regime']} (confidence: {regime['confidence']}%)")
    print(f"DEX trend: {regime['dex_volume_trend']}")
    print(f"Stablecoin flow: {regime['stablecoin_flow']}")
    print(f"Median TVL 1d change: {regime['median_tvl_1d_change_pct']:+.2f}%")
