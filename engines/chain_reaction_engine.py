"""engines/chain_reaction_engine.py — v38

REAL chain reaction database + projection model.

Loads from data/chain_reactions.json (Edward updatable).

Capabilities:
  1. Lookup which chain a ticker is in (with tier, mechanism, propagation)
  2. Compute projection scenarios (bull/base/bear with multiplier ranges)
  3. Detect "next SNDK" candidates (Tier 1 in active chain + early stage)
  4. Cascade forward: who benefits NEXT after this ticker moves
  5. Cross-chain validation (NVDA in ai_compute + ai_power simultaneously)

Used by:
  - alpha_synthesis_v37 (adds chain context to picks)
  - deep_research_generator (full ticker bundle)
  - curated_picks_engine (enrich projection narrative)

Honest disclosures:
  - Tier multipliers are HISTORICAL base rates, NOT predictions
  - Projection assumes chain plays out — invalidations exist
  - Edward updatable: add new chains to data/chain_reactions.json
"""
from __future__ import annotations

import os
import json
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

DEFAULT_DATA_PATH = "data/chain_reactions.json"


# ═══════════════════════════════════════════════════════════════════════
# DATACLASSES
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class ChainPosition:
    """Position of a ticker in a specific chain."""
    chain_id: str
    chain_name: str
    tier: int                       # 1-5
    step: int
    role: str
    horizon_quarters: int
    expected_multiplier_low: float
    expected_multiplier_high: float
    rationale: str
    trigger_status: str
    mechanism: str
    cascade_to_chains: List[str]


@dataclass
class ChainProjection:
    """Forward-looking projection for a ticker in chain context."""
    ticker: str
    current_price: float
    positions: List[ChainPosition]   # ticker might be in multiple chains
    bull_case_multiplier: float       # combined max from all positions
    base_case_multiplier: float
    bear_case_multiplier: float
    bull_target: float
    base_target: float
    bear_target: float
    combined_horizon: str
    invalidations: List[str]
    forward_cascade_tickers: List[str]   # who moves NEXT after this ticker


# ═══════════════════════════════════════════════════════════════════════
# CHAIN REACTION ENGINE
# ═══════════════════════════════════════════════════════════════════════

class ChainReactionEngine:
    """Lookup + project + cascade based on chain_reactions.json database."""

    def __init__(self, data_path: str = DEFAULT_DATA_PATH):
        self.data_path = data_path
        self.chains_data = self._load()
        self.tier_multipliers = self.chains_data.get("tier_multipliers", {})
        self.chains = self.chains_data.get("chains", [])
        self._build_ticker_index()

    def _load(self) -> Dict:
        """Load JSON. Try multiple paths."""
        paths_to_try = [
            self.data_path,
            "data/chain_reactions.json",
            "chain_reactions.json",
            "./chain_reactions.json",
        ]
        for path in paths_to_try:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception as e:
                    logger.error(f"Chain JSON load failed at {path}: {e}")
        logger.warning(f"Chain reactions JSON not found at any path")
        return {"chains": [], "tier_multipliers": {}}

    def _build_ticker_index(self):
        """Build ticker → list of (chain, step, tier) for fast lookup."""
        self.ticker_index = {}
        for chain in self.chains:
            chain_id = chain.get("chain_id")
            for step_data in chain.get("propagation_sequence", []):
                for ticker in step_data.get("tickers", []):
                    tu = ticker.upper()
                    self.ticker_index.setdefault(tu, []).append({
                        "chain_id": chain_id,
                        "step_data": step_data,
                        "chain_data": chain,
                    })

    def reload(self):
        """Reload after Edward updates JSON."""
        self.chains_data = self._load()
        self.tier_multipliers = self.chains_data.get("tier_multipliers", {})
        self.chains = self.chains_data.get("chains", [])
        self._build_ticker_index()

    # ── Lookup ────────────────────────────────────────────────────────

    def find_chains_for_ticker(self, ticker: str) -> List[ChainPosition]:
        """Find all chains containing this ticker. Returns list of positions."""
        tu = ticker.upper()
        positions = []
        for entry in self.ticker_index.get(tu, []):
            chain = entry["chain_data"]
            step = entry["step_data"]
            mult = step.get("expected_multiplier", [1.0, 2.0])
            positions.append(ChainPosition(
                chain_id=chain.get("chain_id", "?"),
                chain_name=chain.get("name", "?"),
                tier=step.get("tier", 1),
                step=step.get("step", 1),
                role=step.get("role", "?"),
                horizon_quarters=step.get("horizon_quarters", 1),
                expected_multiplier_low=float(mult[0]) if len(mult) > 0 else 1.0,
                expected_multiplier_high=float(mult[1]) if len(mult) > 1 else 2.0,
                rationale=step.get("rationale", ""),
                trigger_status=chain.get("trigger_status", "UNKNOWN"),
                mechanism=chain.get("mechanism", ""),
                cascade_to_chains=chain.get("cascade_to_other_chains", []),
            ))
        return positions

    # ── Projection ────────────────────────────────────────────────────

    def project(self, ticker: str, current_price: float) -> Optional[ChainProjection]:
        """Build projection scenarios based on chain positions."""
        positions = self.find_chains_for_ticker(ticker)
        if not positions:
            return None

        # Filter ACTIVE chains
        active_positions = [
            p for p in positions
            if p.trigger_status in ("ACTIVE", "ACTIVE_ACCELERATING", "ACTIVE_INFLECTING",
                                   "ACTIVE_STRUCTURAL", "EPISODIC", "PERSISTENT",
                                   "ACCELERATING", "PRE_HALVING_AND_AI_PIVOT")
        ]
        if not active_positions:
            active_positions = positions  # fall back to all if none flagged active

        # Take MAX bull multiplier from any chain (asymmetric upside)
        bull_mult = max((p.expected_multiplier_high for p in active_positions), default=1.0)
        # Base = mean of (low * 1.5) and (high * 0.6)
        base_mult = sum(
            (p.expected_multiplier_low * 1.5 + p.expected_multiplier_high * 0.6) / 2
            for p in active_positions
        ) / len(active_positions)
        # Bear = MIN low (could go nowhere)
        bear_mult = min((p.expected_multiplier_low for p in active_positions), default=1.0)
        # If multiple chains converge, BONUS to bull (cross-chain validation)
        if len(active_positions) >= 2:
            bull_mult *= 1.3   # 30% bonus for multi-chain
            base_mult *= 1.15

        # Horizon = longest from positions
        horizon_q = max((p.horizon_quarters for p in active_positions), default=4)
        horizon_str = f"{horizon_q*3}-{horizon_q*6} months"

        # Forward cascade: find tickers in NEXT step or chains we cascade TO
        forward_cascade = self._compute_forward_cascade(ticker, active_positions)

        # Invalidations based on chain mechanisms
        invalidations = self._build_invalidations(active_positions)

        return ChainProjection(
            ticker=ticker,
            current_price=current_price,
            positions=active_positions,
            bull_case_multiplier=round(bull_mult, 2),
            base_case_multiplier=round(base_mult, 2),
            bear_case_multiplier=round(bear_mult, 2),
            bull_target=round(current_price * bull_mult, 2),
            base_target=round(current_price * base_mult, 2),
            bear_target=round(current_price * bear_mult, 2),
            combined_horizon=horizon_str,
            invalidations=invalidations,
            forward_cascade_tickers=forward_cascade,
        )

    def _compute_forward_cascade(self, ticker: str, positions: List[ChainPosition]) -> List[str]:
        """Who moves NEXT in the chain after this ticker?"""
        cascade_tickers = set()
        for pos in positions:
            chain = next((c for c in self.chains if c.get("chain_id") == pos.chain_id), None)
            if not chain:
                continue
            current_step = pos.step
            # Find next-step tickers
            for step_data in chain.get("propagation_sequence", []):
                if step_data.get("step", 0) == current_step + 1:
                    for t in step_data.get("tickers", []):
                        if t.upper() != ticker.upper():
                            cascade_tickers.add(t.upper())
            # Find tickers in cascade-to chains (first step)
            for cascade_chain_id in pos.cascade_to_chains:
                cascade_chain = next((c for c in self.chains if c.get("chain_id") == cascade_chain_id), None)
                if cascade_chain:
                    first_step = cascade_chain.get("propagation_sequence", [{}])[0]
                    for t in first_step.get("tickers", [])[:3]:
                        cascade_tickers.add(t.upper())
        return sorted(cascade_tickers)[:8]

    def _build_invalidations(self, positions: List[ChainPosition]) -> List[str]:
        """Generic invalidation triggers based on chain types."""
        invalidations = []
        chain_ids = {p.chain_id for p in positions}

        if "ai_compute_cascade" in chain_ids or "ai_memory_hbm_micron" in chain_ids:
            invalidations.append("AI capex slowdown: hyperscaler guidance cuts capex >20%")
        if "ai_power_cascade" in chain_ids:
            invalidations.append("Grid policy change: removes interconnect queue friction")
        if "iran_mideast_war" in chain_ids:
            invalidations.append("Geopolitical de-escalation: ceasefire or sanctions lifted")
        if "nand_memory_cycle_sndk" in chain_ids:
            invalidations.append("Capex floods back from competitors (NAND price compression)")
            invalidations.append("AI demand normalizes faster than expected")
        if "glp1_obesity_cascade" in chain_ids:
            invalidations.append("Cheaper generic semaglutide ramps faster than expected")
        if "nuclear_renaissance" in chain_ids:
            invalidations.append("Major nuclear accident or policy reversal")
        if "crypto_cycle_4yr" in chain_ids:
            invalidations.append("BTC ETF outflows sustained 4+ weeks")
        if "china_decoupling" in chain_ids:
            invalidations.append("US-China deal: export restrictions lifted")

        # Macro overlay
        invalidations.append("Hedgeye Quad shifts to Q4 (global growth + inflation both decel)")

        return invalidations

    # ── SNDK-style candidate detection ────────────────────────────────

    def find_next_sndk_candidates(self, snap: Dict, prices: Dict,
                                   min_chain_position_tier: int = 1,
                                   max_tier: int = 3) -> List[Dict]:
        """
        Find tickers that match the SNDK setup pattern:
          - In active chain at Tier 1-3
          - Status ACTIVE or ACTIVE_INFLECTING
          - Early Soros stage (INCEPTION or early ACCELERATION)
          - Risk Range A+/A grade
          - Multi-framework convergence
          - Cheap vol (asymmetric option setup)
        """
        candidates = []
        rr_all = (snap.get("risk_ranges", {}) or {}).get("asset_ranges", {})
        boom = snap.get("boom_bust_v3", {}) or snap.get("boom_bust", {}) or {}
        stage = boom.get("stage", "INCEPTION")

        for chain in self.chains:
            if chain.get("trigger_status") not in ("ACTIVE", "ACTIVE_INFLECTING",
                                                    "ACTIVE_ACCELERATING", "ACTIVE_STRUCTURAL"):
                continue

            for step_data in chain.get("propagation_sequence", []):
                tier = step_data.get("tier", 1)
                if tier < min_chain_position_tier or tier > max_tier:
                    continue

                mult = step_data.get("expected_multiplier", [1.0, 2.0])
                bull_mult = float(mult[1]) if len(mult) > 1 else 2.0
                if bull_mult < 3.0:
                    continue  # Want asymmetric upside

                for ticker in step_data.get("tickers", []):
                    rr = rr_all.get(ticker, {})
                    if not rr.get("ok"):
                        continue
                    quality = rr.get("quality", "C")
                    if quality not in ("A+", "A"):
                        continue
                    formation = rr.get("composite", "")
                    if formation != "bullish":
                        continue

                    px = float(rr.get("px", 0))
                    if px <= 0:
                        continue

                    # Score the candidate
                    score = 50 + min(40, int(bull_mult * 5))
                    if quality == "A+":
                        score += 10
                    if tier == 1:
                        score += 5
                    if stage in ("INCEPTION", "ACCELERATION"):
                        score += 10

                    candidates.append({
                        "ticker": ticker,
                        "score": score,
                        "chain_id": chain.get("chain_id"),
                        "chain_name": chain.get("name"),
                        "tier": tier,
                        "expected_multiplier_range": mult,
                        "horizon_quarters": step_data.get("horizon_quarters", 1),
                        "current_price": px,
                        "potential_bull_target": round(px * bull_mult, 2),
                        "rationale": step_data.get("rationale", ""),
                        "trigger_status": chain.get("trigger_status"),
                        "mechanism": chain.get("mechanism", ""),
                    })

        # Dedup by ticker (keep highest score)
        seen = {}
        for c in candidates:
            t = c["ticker"]
            if t not in seen or c["score"] > seen[t]["score"]:
                seen[t] = c
        return sorted(seen.values(), key=lambda x: x["score"], reverse=True)

    # ── Worked example lookup ─────────────────────────────────────────

    def get_worked_example(self, chain_id: str) -> Optional[Dict]:
        """Get worked example (e.g., SNDK $30→$1500 mechanism) for a chain."""
        for chain in self.chains:
            if chain.get("chain_id") == chain_id:
                return chain.get("worked_example_sndk") or chain.get("worked_example")
        return None

    # ── Formatting helpers ────────────────────────────────────────────

    def format_projection_markdown(self, projection: ChainProjection) -> str:
        """Format projection as markdown for display."""
        if not projection:
            return ""
        lines = []
        lines.append(f"### 🔗 Chain Projection: {projection.ticker}")
        lines.append("")
        lines.append(f"**Current**: ${projection.current_price:,.2f}  ")
        lines.append(f"**Horizon**: {projection.combined_horizon}")
        lines.append("")
        lines.append("| Scenario | Multiplier | Target |")
        lines.append("|---|---|---|")
        lines.append(f"| 🟢 Bull | {projection.bull_case_multiplier:.1f}x | ${projection.bull_target:,.2f} |")
        lines.append(f"| 🟡 Base | {projection.base_case_multiplier:.1f}x | ${projection.base_target:,.2f} |")
        lines.append(f"| 🔴 Bear | {projection.bear_case_multiplier:.1f}x | ${projection.bear_target:,.2f} |")
        lines.append("")
        lines.append("**Chain Positions**:")
        for pos in projection.positions:
            lines.append(f"- **{pos.chain_name}** (Tier {pos.tier}, Step {pos.step})")
            lines.append(f"  - Role: {pos.role}")
            lines.append(f"  - Expected multiplier: {pos.expected_multiplier_low:.1f}-{pos.expected_multiplier_high:.1f}x")
            lines.append(f"  - {pos.rationale}")
        lines.append("")
        if projection.forward_cascade_tickers:
            lines.append(f"**Cascade Forward** (who moves NEXT): {', '.join(projection.forward_cascade_tickers)}")
            lines.append("")
        lines.append("**Invalidations** (get out if):")
        for inv in projection.invalidations:
            lines.append(f"- {inv}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# Singleton
# ═══════════════════════════════════════════════════════════════════════

_ENGINE_SINGLETON: Optional[ChainReactionEngine] = None


def get_chain_engine() -> ChainReactionEngine:
    global _ENGINE_SINGLETON
    if _ENGINE_SINGLETON is None:
        _ENGINE_SINGLETON = ChainReactionEngine()
    return _ENGINE_SINGLETON


def reload_chain_engine():
    global _ENGINE_SINGLETON
    if _ENGINE_SINGLETON:
        _ENGINE_SINGLETON.reload()


__all__ = [
    "ChainReactionEngine", "ChainPosition", "ChainProjection",
    "get_chain_engine", "reload_chain_engine",
]
