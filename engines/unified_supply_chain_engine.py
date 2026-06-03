"""engines/cascade_engine.py — UNIVERSAL Second-Order Cascade Engine (Sprint 2)

Maps shock propagation across markets:
  - Commodity chains (Oil → Tankers → Refiners → Airlines)
  - Currency cascades (DXY → EM → Commodities)
  - Sector contagion (Banks → CRE → Insurance)
  - Tech bottlenecks (AI → Power → Optics → Materials)
  - Geopolitical (Iran → Oil → Tankers → Insurance)

Architecture:
  1. STATIC EDGES — Hand-coded high-confidence causal relationships (100+ edges)
  2. DYNAMIC EDGES — Auto-discovered via price clustering + news co-occurrence
  3. BFS PROPAGATION — Shock cascade with hop-decay
  4. REVERSE LOOKUP — Given any ticker, find upstream drivers

This works on ALL markets, not just bottlenecks.
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional, Tuple, Set
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────
# STATIC CAUSAL EDGES — Curated high-confidence relationships
# Format: (source_ticker, magnitude_threshold) → [(target, beta, lag_days)]
# ────────────────────────────────────────────────────────────────────────
STATIC_EDGES: Dict[str, List[Tuple[str, float, int]]] = {

    # ═════ OIL CASCADE (Edward's example) ═════
    "CL=F": [
        # First-order beneficiaries
        ("XLE", 1.10, 1), ("OIH", 1.30, 2), ("XOP", 1.40, 3),
        ("XOM", 0.85, 1), ("CVX", 0.85, 1), ("COP", 1.10, 2),
        # Tankers (Edward's example) — beta 1.5x, lag 5-7 days
        ("FRO", 1.50, 5), ("STNG", 1.40, 5), ("TNK", 1.30, 7),
        ("DHT", 1.25, 7), ("INSW", 1.20, 7), ("EURN", 1.30, 5),
        # Refiners (lag 7-14)
        ("VLO", 0.90, 10), ("MPC", 0.85, 10), ("PSX", 0.85, 10), ("PBF", 1.10, 10),
        # NEGATIVE — Airlines (oil = cost input)
        ("UAL", -0.80, 14), ("DAL", -0.75, 14), ("LUV", -0.70, 14), ("AAL", -0.85, 14),
        # NEGATIVE — Plastics (feedstock cost)
        ("LYB", -0.40, 21), ("DOW", -0.35, 21), ("WLK", -0.45, 21), ("EMN", -0.30, 21),
        # NEGATIVE — Consumer disc (gasoline drag on wallet)
        ("XLY", -0.20, 30), ("AMZN", -0.10, 30), ("WMT", -0.05, 30),
        # Macro: inflation push, bonds bearish
        ("TIP", 0.30, 7), ("TLT", -0.40, 14),
    ],

    # ═════ AI COMPUTE CASCADE ═════
    "NVDA": [
        # Power infra (data center demand)
        ("VST", 1.40, 7), ("CEG", 1.30, 7), ("ETN", 1.20, 14),
        ("VRT", 1.30, 7), ("GEV", 1.40, 10),
        # Optics
        ("COHR", 1.50, 5), ("LITE", 1.40, 5), ("GLW", 0.80, 14),
        ("POET", 1.80, 7), ("CIEN", 1.20, 14),
        # Materials
        ("MTRN", 1.30, 14), ("TROX", 0.90, 21),
        # Memory
        ("MU", 1.20, 7), ("WDC", 0.90, 14), ("STX", 0.80, 14),
        # Hyperscaler clients
        ("MSFT", 0.40, 14), ("AMZN", 0.35, 14), ("GOOGL", 0.40, 14), ("META", 0.45, 14),
        # Packaging
        ("AMKR", 1.30, 10), ("ASX", 1.20, 14), ("TSEM", 1.40, 14),
        # SiC/GaN
        ("ON", 0.90, 21), ("WOLF", 1.50, 21), ("STM", 0.70, 21),
        # ETF lift
        ("SMH", 0.85, 1), ("SOXX", 0.85, 1), ("XLK", 0.60, 3), ("QQQ", 0.50, 3),
    ],

    # ═════ DXY (USD STRENGTH) CASCADE ═════
    "DX-Y.NYB": [
        # EM equities — NEGATIVE
        ("EEM", -2.00, 5), ("VWO", -1.90, 5), ("EWZ", -2.20, 7),
        ("EWW", -2.30, 7), ("EIDO", -2.10, 7), ("FXI", -1.80, 7),
        ("INDA", -1.70, 14), ("EWY", -1.60, 7),
        # EM credit
        ("EMB", -1.40, 7), ("PCY", -1.30, 7), ("EMLC", -1.80, 7),
        # Precious metals (inverse correlation)
        ("GLD", -1.50, 3), ("SLV", -2.00, 5), ("GDX", -2.50, 5),
        ("GDXJ", -2.80, 7), ("SIL", -2.20, 7),
        # Commodities (priced in USD)
        ("CL=F", -0.80, 7), ("HG=F", -1.20, 7), ("DBA", -0.70, 14),
        # US Multinationals (FX translation drag)
        ("KO", -0.30, 30), ("MCD", -0.30, 30), ("PG", -0.25, 30),
        ("MSFT", -0.20, 30), ("AAPL", -0.25, 30),
        # Long bonds (USD safety bid mixed)
        ("TLT", -0.30, 7), ("IEF", -0.20, 7),
    ],

    # ═════ DGS10 (10Y YIELD) CASCADE ═════
    "DGS10": [
        # Duration
        ("TLT", -3.50, 1), ("IEF", -2.20, 1), ("LQD", -2.00, 3),
        # REITs (rate-sensitive)
        ("XLRE", -1.80, 3), ("VNO", -2.10, 5), ("BXP", -2.30, 5),
        ("SLG", -2.50, 7), ("O", -1.50, 5),
        # Growth (DCF discount)
        ("XLK", -1.20, 3), ("QQQ", -1.30, 3), ("ARKK", -2.50, 5),
        ("MAGS", -1.40, 3),
        # Financials (NIM benefit)
        ("XLF", 0.80, 7), ("KRE", 1.20, 7), ("KBE", 1.10, 7),
        # Insurance (book yield)
        ("LNC", 0.90, 14), ("PRU", 0.80, 14), ("MET", 0.70, 14),
    ],

    # ═════ BANKING / CREDIT CASCADE ═════
    "KRE": [  # Regional banks stress
        # CRE REITs (loan exposure)
        ("VNO", 0.80, 7), ("BXP", 0.85, 7), ("SLG", 1.20, 5),
        ("XLRE", 0.50, 5),
        # Insurance (regional bank securities)
        ("LNC", 0.50, 14), ("CINF", 0.40, 14),
        # Spillover
        ("XLF", 0.40, 3), ("BAC", 0.30, 3),
        # Defensive flight
        ("TLT", -0.30, 1), ("GLD", -0.20, 3),
    ],

    # ═════ GEOPOLITICAL — IRAN/HORMUZ ═════
    "iran_escalation": [
        ("CL=F", 1.20, 0), ("BZ=F", 1.30, 0),
        ("FRO", 1.80, 3), ("STNG", 1.60, 3),
        ("LMT", 0.80, 1), ("RTX", 0.70, 1), ("NOC", 0.60, 1), ("KTOS", 1.50, 1),
        ("ITA", 1.00, 1),
        ("GLD", 0.50, 1), ("UUP", 0.30, 1),
        ("UAL", -1.20, 7), ("DAL", -1.10, 7),
        ("EEM", -0.40, 5),
    ],

    # ═════ COPPER / INDUSTRIAL METALS ═════
    "HG=F": [
        ("FCX", 1.50, 3), ("SCCO", 1.40, 3), ("CPER", 1.10, 1),
        # AI compute proxy (copper for grid + data centers)
        ("VST", 0.60, 14), ("ETN", 0.50, 14),
        # Materials sector
        ("XLB", 0.70, 5),
        # China beta
        ("FXI", 0.50, 5),
    ],

    # ═════ NATURAL GAS CASCADE ═════
    "NG=F": [
        ("UNG", 1.10, 1), ("LNG", 1.30, 5), ("CHK", 1.40, 5),
        # Power utilities (gas-fired)
        ("VST", 0.80, 7), ("CEG", 0.70, 7),
        # Petchem (gas feedstock benefit when low)
        ("LYB", -0.40, 14), ("DOW", -0.30, 14),
    ],

    # ═════ AGRICULTURE CASCADE ═════
    "ZW=F": [  # Wheat
        ("WEAT", 1.10, 1), ("DBA", 0.40, 3),
        # Food cost inflation
        ("XLP", 0.10, 30), ("K", -0.20, 60), ("GIS", -0.20, 60),
        # EM food importers (negative)
        ("EGY", -0.30, 30),
    ],

    # ═════ BITCOIN CASCADE ═════
    "BTC-USD": [
        ("IBIT", 0.95, 1), ("FBTC", 0.95, 1), ("MSTR", 1.80, 1),
        # Miners (high beta)
        ("MARA", 1.50, 1), ("RIOT", 1.40, 1), ("CLSK", 1.30, 1),
        ("WGMI", 1.40, 1),
        # Crypto ecosystem
        ("COIN", 1.20, 1), ("HOOD", 0.80, 3),
        # Negative: dollar bid hurts crypto
        ("DX-Y.NYB", -0.30, 5),
        # Ethereum lag
        ("ETH-USD", 0.75, 3),
    ],

    # ═════ VIX SPIKE CASCADE ═════
    "^VIX": [
        # Risk-off
        ("SPY", -2.00, 1), ("QQQ", -2.50, 1), ("IWM", -3.00, 1),
        # Anti-beta safe havens
        ("TLT", 1.50, 1), ("GLD", 0.80, 1), ("UUP", 0.40, 1),
        ("BTAL", 1.80, 1),
        # Credit
        ("HYG", -1.20, 1), ("LQD", -0.50, 1),
        # Crypto risk-off
        ("BTC-USD", -1.50, 1), ("ETH-USD", -1.80, 1),
    ],

    # ═════ JPY CARRY UNWIND CASCADE ═════
    "USDJPY=X": [  # If JPY strengthens (USDJPY drops)
        # Japanese exporters benefit FROM weak JPY → reverse hurts
        ("EWJ", -0.40, 3), ("JPXN", -0.50, 3),
        # Risk assets historically vulnerable to JPY rallies
        ("SPY", -0.30, 5), ("QQQ", -0.50, 5),
        # Carry unwind → bond bid
        ("TLT", 0.50, 3),
    ],
}


# Bottleneck → beneficiary mapping (extends static edges with bottleneck thesis)
BOTTLENECK_CASCADES = {
    "ai_optics_shortage": {
        "primary": ["COHR", "LITE"],
        "secondary": ["GLW", "POET", "CIEN"],  # Adjacent optics
        "tertiary": ["MTRN", "TROX"],  # Substrate / materials
        "headwinds": ["INTC", "AMZN"],  # Customers facing margin pressure
    },
    "power_grid_shortage": {
        "primary": ["VST", "CEG", "GEV"],
        "secondary": ["ETN", "VRT", "EMR", "HUBB"],
        "tertiary": ["NEE", "DUK", "SO"],  # Utilities benefit indirectly
        "headwinds": ["NVDA"],  # Slows AI capex deployment
    },
    "tanker_shortage": {
        "primary": ["FRO", "STNG", "INSW"],
        "secondary": ["TNK", "DHT", "EURN"],
        "tertiary": ["KEX"],  # Inland tankers
        "headwinds": ["UAL", "DAL"],  # Fuel cost ripple
    },
    "uranium_supply": {
        "primary": ["URA", "CCJ"],
        "secondary": ["NXE", "DNN", "UUUU", "LEU"],
        "tertiary": ["CEG", "VST"],  # Nuclear utilities
    },
    "silver_squeeze": {
        "primary": ["SLV", "SILJ"],
        "secondary": ["SIL", "PAAS", "WPM"],
        "tertiary": ["GDX", "GDXJ"],  # Gold spillover
    },
}


# ────────────────────────────────────────────────────────────────────────
# DATACLASSES
# ────────────────────────────────────────────────────────────────────────

@dataclass
class CascadeImpact:
    target: str
    estimated_impact_pct: float
    lag_days: int
    confidence: float
    hop: int                  # 1=first-order, 2=second-order, etc.
    source: str               # Where impact came from
    chain: List[str]          # Causal chain ["CL=F", "OIH", "SLB"]


# ────────────────────────────────────────────────────────────────────────
# ENGINE
# ────────────────────────────────────────────────────────────────────────

class CascadeEngine:
    """
    Universal second-order shock propagation across all markets.
    """

    DECAY_PER_HOP = 0.65        # Each hop loses 35% magnitude
    MIN_IMPACT_TO_PROPAGATE = 0.005   # Stop propagation below 0.5%
    MAX_HOPS = 3

    def __init__(self, prices: Optional[Dict] = None, news: Optional[Dict] = None):
        self.prices = prices or {}
        self.news = news or {}
        self._dynamic_edges: Dict[str, List[Tuple[str, float, int]]] = {}
        self._build_reverse_index()

    def _build_reverse_index(self):
        """For reverse_lookup — who causes ticker X?"""
        self._upstream: Dict[str, List[Tuple[str, float, int]]] = defaultdict(list)
        for source, edges in STATIC_EDGES.items():
            for target, beta, lag in edges:
                self._upstream[target].append((source, beta, lag))

    # ═══════════════════════════════════════════════════════════════════
    # CORE: SHOCK PROPAGATION
    # ═══════════════════════════════════════════════════════════════════
    def propagate(self, shock_source: str, shock_magnitude: float,
                  max_hops: Optional[int] = None) -> List[CascadeImpact]:
        """
        Given a shock at source (e.g., 'CL=F' +5%), propagate through graph.
        Returns list of CascadeImpact sorted by absolute magnitude.

        Example:
          engine.propagate('CL=F', 0.05)  # Oil +5%
          → [
              CascadeImpact('XLE', +5.5%, 1day, conf 1.0, hop 1, chain=['CL=F','XLE']),
              CascadeImpact('FRO', +7.5%, 5days, conf 1.0, hop 1, chain=['CL=F','FRO']),
              CascadeImpact('UAL', -4.0%, 14days, conf 1.0, hop 1, chain=['CL=F','UAL']),
              CascadeImpact('PSX', +3.8%, 10days, conf 1.0, hop 1, chain=['CL=F','PSX']),
              ...
            ]
        """
        max_hops = max_hops or self.MAX_HOPS
        impacts: Dict[str, CascadeImpact] = {}

        # Initialize: source itself
        impacts[shock_source] = CascadeImpact(
            target=shock_source,
            estimated_impact_pct=shock_magnitude,
            lag_days=0,
            confidence=1.0,
            hop=0,
            source=shock_source,
            chain=[shock_source],
        )

        # BFS expansion
        for hop in range(1, max_hops + 1):
            current_layer = [t for t, ci in impacts.items() if ci.hop == hop - 1]
            for source_t in current_layer:
                source_impact = impacts[source_t]

                # Skip if impact too small to propagate further
                if abs(source_impact.estimated_impact_pct) < self.MIN_IMPACT_TO_PROPAGATE:
                    continue

                # Get downstream edges
                edges = self._get_edges(source_t)
                for target, beta, lag in edges:
                    new_magnitude = source_impact.estimated_impact_pct * beta * (self.DECAY_PER_HOP ** (hop - 1))

                    # Stop if too small
                    if abs(new_magnitude) < self.MIN_IMPACT_TO_PROPAGATE:
                        continue

                    new_chain = source_impact.chain + [target]
                    new_lag = source_impact.lag_days + lag
                    new_conf = source_impact.confidence * (0.85 ** (hop - 1))

                    # Keep best impact (largest magnitude)
                    if target not in impacts or abs(new_magnitude) > abs(impacts[target].estimated_impact_pct):
                        impacts[target] = CascadeImpact(
                            target=target,
                            estimated_impact_pct=new_magnitude,
                            lag_days=new_lag,
                            confidence=new_conf,
                            hop=hop,
                            source=shock_source,
                            chain=new_chain,
                        )

        # Sort by absolute magnitude, exclude source itself
        result = [v for k, v in impacts.items() if k != shock_source]
        result.sort(key=lambda x: abs(x.estimated_impact_pct), reverse=True)
        return result

    # ═══════════════════════════════════════════════════════════════════
    # REVERSE LOOKUP: "Why is X moving?"
    # ═══════════════════════════════════════════════════════════════════
    def reverse_lookup(self, target_ticker: str, max_depth: int = 2) -> List[Dict]:
        """
        Given a ticker, find all upstream drivers.
        Returns list of {source, beta, lag, depth}.
        """
        results = []
        visited = set()
        queue = [(target_ticker, 1, [target_ticker])]

        while queue:
            current, depth, chain = queue.pop(0)
            if depth > max_depth:
                continue
            for source, beta, lag in self._upstream.get(current, []):
                if source in visited:
                    continue
                visited.add(source)
                results.append({
                    "source": source,
                    "target": target_ticker,
                    "beta": beta,
                    "lag_days": lag,
                    "depth": depth,
                    "chain": chain + [source][::-1],
                })
                if depth < max_depth:
                    queue.append((source, depth + 1, chain + [source]))

        results.sort(key=lambda x: (abs(x["beta"]), -x["depth"]), reverse=True)
        return results

    # ═══════════════════════════════════════════════════════════════════
    # BOTTLENECK CASCADE (Edward's question: "ke yang lainnya?")
    # ═══════════════════════════════════════════════════════════════════
    def bottleneck_to_cascade(self, bottleneck_id: str,
                              intensity: float = 0.10) -> List[CascadeImpact]:
        """
        Given a bottleneck (e.g., 'tanker_shortage'), return full cascade.
        Maps bottleneck thesis to ticker-level shocks across all layers.
        """
        if bottleneck_id not in BOTTLENECK_CASCADES:
            return []

        b = BOTTLENECK_CASCADES[bottleneck_id]
        all_impacts: Dict[str, CascadeImpact] = {}

        # Primary tier — full intensity
        for t in b.get("primary", []):
            all_impacts[t] = CascadeImpact(
                target=t,
                estimated_impact_pct=intensity * 1.0,
                lag_days=3,
                confidence=0.90,
                hop=1,
                source=bottleneck_id,
                chain=[bottleneck_id, t],
            )
            # Propagate from each primary
            for impact in self.propagate(t, intensity * 1.0, max_hops=2)[:8]:
                if impact.target not in all_impacts or abs(impact.estimated_impact_pct) > abs(all_impacts[impact.target].estimated_impact_pct):
                    all_impacts[impact.target] = impact

        # Secondary tier — 60% intensity
        for t in b.get("secondary", []):
            if t not in all_impacts:
                all_impacts[t] = CascadeImpact(
                    target=t, estimated_impact_pct=intensity * 0.60,
                    lag_days=7, confidence=0.75, hop=1, source=bottleneck_id,
                    chain=[bottleneck_id, t],
                )

        # Tertiary tier — 35% intensity
        for t in b.get("tertiary", []):
            if t not in all_impacts:
                all_impacts[t] = CascadeImpact(
                    target=t, estimated_impact_pct=intensity * 0.35,
                    lag_days=14, confidence=0.55, hop=2, source=bottleneck_id,
                    chain=[bottleneck_id, t],
                )

        # Headwinds — negative impact
        for t in b.get("headwinds", []):
            all_impacts[t] = CascadeImpact(
                target=t, estimated_impact_pct=-intensity * 0.40,
                lag_days=21, confidence=0.60, hop=2, source=bottleneck_id,
                chain=[bottleneck_id, t],
            )

        result = list(all_impacts.values())
        result.sort(key=lambda x: abs(x.estimated_impact_pct), reverse=True)
        return result

    # ═══════════════════════════════════════════════════════════════════
    # DYNAMIC EDGE DISCOVERY (from price clusters) — WITH DISK CACHE v2
    # ═══════════════════════════════════════════════════════════════════
    _CACHE_DIR = None
    _CACHE_TTL_HOURS = 6.0  # Edges valid for 6 hours

    @classmethod
    def _get_cache_path(cls):
        from pathlib import Path
        if cls._CACHE_DIR is None:
            cls._CACHE_DIR = Path(".cache/cascade")
            cls._CACHE_DIR.mkdir(parents=True, exist_ok=True)
        return cls._CACHE_DIR / "dynamic_edges.pkl"

    def discover_dynamic_edges(self, lookback_days: int = 63,
                              min_corr: float = 0.60) -> Dict[str, List[Tuple[str, float, int]]]:
        """Discover new correlations not in STATIC_EDGES. Uses disk cache (6h TTL)."""
        # Try cache first
        try:
            import pickle, time as _t
            from pathlib import Path
            cache_path = self._get_cache_path()
            if cache_path.exists():
                age_hours = (_t.time() - cache_path.stat().st_mtime) / 3600
                if age_hours < self._CACHE_TTL_HOURS:
                    with open(cache_path, "rb") as f:
                        cached_edges = pickle.load(f)
                    self._dynamic_edges = cached_edges
                    logger.info(f"Cascade dynamic edges: {sum(len(v) for v in cached_edges.values())} loaded from cache ({age_hours:.1f}h old)")
                    return cached_edges
        except Exception as e:
            logger.debug(f"Cascade cache read failed: {e}")

        # Cache miss — compute fresh
        if not self.prices:
            return {}

        clean_prices = {}
        for t, s in self.prices.items():
            try:
                ser = pd.to_numeric(s, errors="coerce").dropna()
                if len(ser) >= lookback_days + 1:
                    clean_prices[t] = ser.tail(lookback_days + 1).pct_change().dropna()
            except Exception:
                continue

        if len(clean_prices) < 10:
            return {}

        df = pd.DataFrame(clean_prices)
        try:
            corr = df.corr()
        except Exception:
            return {}

        new_edges: Dict[str, List[Tuple[str, float, int]]] = defaultdict(list)
        for src in corr.index:
            for tgt in corr.columns:
                if src == tgt:
                    continue
                c = corr.loc[src, tgt]
                if not math.isfinite(c) or abs(c) < min_corr:
                    continue
                static = [e[0] for e in STATIC_EDGES.get(src, [])]
                if tgt in static:
                    continue
                new_edges[src].append((tgt, float(c) * 0.7, 5))

        self._dynamic_edges = dict(new_edges)

        # Save to cache
        try:
            import pickle
            with open(self._get_cache_path(), "wb") as f:
                pickle.dump(self._dynamic_edges, f)
        except Exception as e:
            logger.debug(f"Cascade cache save failed: {e}")

        logger.info(f"Cascade dynamic edges: {sum(len(v) for v in new_edges.values())} discovered (FRESH compute)")
        return self._dynamic_edges

    def _get_edges(self, ticker: str) -> List[Tuple[str, float, int]]:
        """Combine static + dynamic edges for a ticker."""
        return STATIC_EDGES.get(ticker, []) + self._dynamic_edges.get(ticker, [])


# ────────────────────────────────────────────────────────────────────────
# PUBLIC RUNNERS (orchestrator-friendly)
# ────────────────────────────────────────────────────────────────────────

def run_cascade_from_shock(prices: Dict, shock_source: str,
                           shock_magnitude: float = 0.05,
                           news: Optional[Dict] = None) -> Dict:
    """
    Main entry: given shock, return cascade analysis.
    Returns dict suitable for UI rendering.
    """
    engine = CascadeEngine(prices=prices, news=news)
    engine.discover_dynamic_edges(lookback_days=63)
    impacts = engine.propagate(shock_source, shock_magnitude)

    return {
        "shock_source": shock_source,
        "shock_magnitude": shock_magnitude,
        "total_impacts": len(impacts),
        "first_order": [
            {"target": i.target, "impact_pct": i.estimated_impact_pct,
             "lag_days": i.lag_days, "chain": i.chain}
            for i in impacts if i.hop == 1
        ][:20],
        "second_order": [
            {"target": i.target, "impact_pct": i.estimated_impact_pct,
             "lag_days": i.lag_days, "chain": i.chain}
            for i in impacts if i.hop == 2
        ][:15],
        "third_order": [
            {"target": i.target, "impact_pct": i.estimated_impact_pct,
             "lag_days": i.lag_days, "chain": i.chain}
            for i in impacts if i.hop == 3
        ][:10],
    }


def run_all_cascades(prices: Dict, news: Optional[Dict] = None,
                     active_shocks: Optional[Dict[str, float]] = None) -> Dict:
    """
    Run cascade analysis for all currently-active shocks.
    Auto-detects shocks from recent price moves if none provided.
    """
    engine = CascadeEngine(prices=prices, news=news)
    engine.discover_dynamic_edges(lookback_days=63)

    if active_shocks is None:
        active_shocks = _auto_detect_shocks(prices)

    all_cascades = {}
    for source, magnitude in active_shocks.items():
        all_cascades[source] = run_cascade_from_shock(prices, source, magnitude, news)

    return {
        "active_shocks": active_shocks,
        "cascades": all_cascades,
        "summary": f"{len(active_shocks)} active shocks, {sum(c['total_impacts'] for c in all_cascades.values())} total impacts",
    }


def _auto_detect_shocks(prices: Dict, threshold_5d: float = 0.05) -> Dict[str, float]:
    """Detect tickers that moved >threshold in last 5 days = active shocks."""
    shocks = {}
    key_signals = ["CL=F", "DX-Y.NYB", "DGS10", "^VIX", "BTC-USD", "HG=F", "NG=F", "GC=F"]
    for t in key_signals:
        s = prices.get(t)
        if s is None:
            continue
        try:
            ser = pd.to_numeric(s, errors="coerce").dropna()
            if len(ser) < 6:
                continue
            ret_5d = float(ser.iloc[-1] / ser.iloc[-6] - 1)
            if abs(ret_5d) >= threshold_5d:
                shocks[t] = ret_5d
        except Exception:
            continue
    return shocks


def reverse_lookup_ticker(prices: Dict, ticker: str, max_depth: int = 2) -> List[Dict]:
    """Convenience: why is ticker X moving?"""
    engine = CascadeEngine(prices=prices)
    return engine.reverse_lookup(ticker, max_depth)


def bottleneck_full_cascade(prices: Dict, bottleneck_id: str,
                            intensity: float = 0.10) -> Dict:
    """Convenience: bottleneck → all market impacts."""
    engine = CascadeEngine(prices=prices)
    impacts = engine.bottleneck_to_cascade(bottleneck_id, intensity)
    return {
        "bottleneck_id": bottleneck_id,
        "intensity": intensity,
        "impacts": [
            {"target": i.target, "impact_pct": i.estimated_impact_pct,
             "lag_days": i.lag_days, "hop": i.hop, "confidence": i.confidence,
             "chain": i.chain}
            for i in impacts
        ],
        "summary": f"{len(impacts)} impacted tickers across {max((i.hop for i in impacts), default=0)} hops",
    }

# ═══════════════════════════════════════════════════════════════════════════════
# BOTTLENECK & SUPPLY CHAIN (merged from bottleneck_discovery_v3, bottleneck_engine, supply_chain_graph)
# ═══════════════════════════════════════════════════════════════════════════════


# === FROM: bottleneck_discovery_v3.py ===
def run_bottleneck_discovery_v3(prices: Dict, fred: Dict, news_analysis: Dict) -> Dict:
    engine = BottleneckDiscoveryV3()
    return engine.run(prices, fred, news_analysis)



# === FROM: bottleneck_engine.py ===
class BottleneckEngine:
    def run(self, prices, volumes=None, quad_str="Q3", quad_mon="Q2",
            benchmark="SPY", asset_ranges=None, min_rs=-0.10, top_n=25):
        volumes = volumes or {}
        bench = prices.get(benchmark)
        qk = quad_str.upper()
        qk_mon = quad_mon.upper()
        regime_allows = {
            "Q1": {"structural": True, "squeeze": True, "commodity": False, "ihsg": True, "crypto": True},
            "Q2": {"structural": True, "squeeze": True, "commodity": True, "ihsg": True, "crypto": True},
            "Q3": {"structural": True, "squeeze": False, "commodity": True, "ihsg": True, "crypto": False},
            "Q4": {"structural": False, "squeeze": False, "commodity": False, "ihsg": False, "crypto": False}
        }.get(qk, {"structural": True})
        playbook = QUAD_ASSET_PERFORMANCE.get(quad_str, {})
        scored = []

        for ticker, close in prices.items():
            if ticker == benchmark:
                continue
            close = pd.to_numeric(close, errors="coerce").dropna()
            if len(close) < 30:
                continue
            sector = TICKER_SECTOR.get(ticker, "generic")
            prof = BOTTLENECK_PROFILES.get(sector, BOTTLENECK_PROFILES.get("generic", {"constraint": 0.5, "Q1": 0.5, "Q2": 0.5, "Q3": 0.5, "Q4": 0.5}))
            constraint = float(prof.get("constraint", 0.5))
            rf_str = float(prof.get(qk, 0.5))
            rf_mon = float(prof.get(qk_mon, 0.5))
            regime_fit = 0.65 * rf_str + 0.35 * rf_mon
            btn_type = "structural"
            rs3 = _rs(close, bench, 63) if bench is not None else None
            rs21 = _rs(close, bench, 21) if bench is not None else None
            if rs3 is not None and rs3 < min_rs:
                continue
            trd, acc_s, hh, hl = _trend(close, 63)[2], _acc(close, 63), _trend(close, 63)[0], _trend(close, 63)[1]
            px = float(close.iloc[-1])
            hi52 = float(close.tail(252).max()) if len(close) >= 252 else float(close.max())
            lo52 = float(close.tail(252).min()) if len(close) >= 252 else float(close.min())
            pct_from_hi = (px - hi52) / max(hi52, 1e-9)
            pct_from_lo = (px - lo52) / max(lo52, 1e-9)
            if trd == "uptrend":
                level = "level_2"
            elif trd == "range" and acc_s >= 0.60:
                level = "level_1"
            elif trd == "downtrend":
                level = "avoid"
            else:
                level = "watch"
            regime_trap = (qk in ("Q3", "Q4") and btn_type == "squeeze")
            score = (0.30 * constraint + 0.25 * regime_fit + 0.20 * (0.5 if trd == "uptrend" else 0.3) + 0.15 * (0.5 if rs3 and rs3 > 0 else 0.3) + 0.10 * acc_s)
            if level == "avoid":
                score *= 0.30
            if regime_trap:
                score *= 0.40
            score = float(np.clip(score, 0.0, 1.0))
            scored.append(dict(
                ticker=ticker, sector=sector, btn_type=btn_type, level=level,
                score=round(score, 3), constraint=round(constraint, 2),
                regime_fit=round(regime_fit, 2), trend=trd,
                acc=round(acc_s, 2), rs_3m=round(rs3, 4) if rs3 else None,
                px=round(px, 4), pct_from_hi=round(pct_from_hi, 3),
                pct_from_lo=round(pct_from_lo, 3), regime_trap=regime_trap,
                rationale=f"{sector}|{trd}|RS {rs3:.1%}" if rs3 else sector,
            ))

        scored.sort(key=lambda x: x["score"], reverse=True)

        return dict(
            all_candidates=scored[:top_n],
            level_1=[s for s in scored if s["level"] == "level_1" and not s["regime_trap"]][:top_n],
            level_2=[s for s in scored if s["level"] == "level_2" and not s["regime_trap"]][:top_n],
            watch=[s for s in scored if s["level"] == "watch"][:top_n],
            avoid=[s for s in scored if s["level"] == "avoid"][:8],
            regime_traps=[s for s in scored if s["regime_trap"]][:8],
            playbook=dict(structural=quad_str, monthly=quad_mon,
                         best=playbook.get("best", []), worst=playbook.get("worst", []),
                         sectors_overweight=playbook.get("sectors_overweight", []),
                         sectors_underweight=playbook.get("sectors_underweight", []),
                         style=playbook.get("style", ""), fx=playbook.get("fx", ""), bonds=playbook.get("bonds", "")),
            regime_filter=regime_allows,
            meta=dict(universe=len(prices) - 1, scored=len(scored)),
        )



# === FROM: supply_chain_graph_real.py ===
def run_supply_chain_analysis(prices: Optional[Dict] = None,
                             active_shocks: Optional[Dict[str, float]] = None) -> Dict:
    """Full supply chain graph analysis."""
    graph = SupplyChainGraph()
    graph.load_static_edges()
    if prices:
        graph.discover_dynamic_edges(prices)

    chokepoints = graph.identify_chokepoints(top_n=15)

    # Run forward propagation for each active shock
    propagation = {}
    if active_shocks:
        for src, mag in active_shocks.items():
            propagation[src] = graph.forward_propagate(src, mag)

    return {
        "ok": True,
        "summary": graph.summary(),
        "chokepoints": chokepoints,
        "propagation": propagation,
    }



def reverse_lookup(target: str, prices: Optional[Dict] = None) -> List[Dict]:
    """Given a ticker, find upstream supply chain causes."""
    graph = SupplyChainGraph()
    graph.load_static_edges()
    if prices:
        graph.discover_dynamic_edges(prices)
    return graph.reverse_propagate(target)


# Backward-compatible alias
supply_reverse = reverse_lookup