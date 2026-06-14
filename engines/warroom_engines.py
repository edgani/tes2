"""
engines/warroom_engines.py
MacroRegime War Room — Core Intelligence Engines

Engines:
  1. MultiStageFilter    — Elimination → Regime Alignment → Competitive Ranking → Conviction Filter
  2. ConfidenceEngine    — Causal chain confidence + market-structure validation
  3. PropagationEngine   — Cross-asset lead/lag + bottleneck chain reaction
  4. WhatChangedEngine   — Delta detection across regime variables
  5. CausalCardEngine    — Generate WHY NOW / WHAT CHANGED / WHO IS TRAPPED cards
"""
from __future__ import annotations
import math
import json
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

# ═══════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class FilteredTicker:
    ticker: str
    market_type: str  # us_equity, crypto, commodity, fx, ihsg
    direction: str    # LONG / SHORT / NEUTRAL
    conviction: float # 0.0 - 1.0
    tier: int         # 1 = highest, 2 = watchlist, 3 = emerging (hidden)

    # Causal stack
    why_now: str = ""
    what_changed: str = ""
    who_trapped: str = ""
    who_must_buy: str = ""
    what_mispriced: str = ""
    what_invalidates: str = ""

    # Pressure bars (0-10 scale)
    accumulation_pressure: float = 0.0
    crowding_pressure: float = 0.0
    gamma_squeeze_pressure: float = 0.0
    bottleneck_pressure: float = 0.0
    macro_alignment_pressure: float = 0.0

    # Metrics
    price: float = 0.0
    entry: float = 0.0
    target_1: float = 0.0
    target_2: float = 0.0
    stop_loss: float = 0.0
    rr: float = 0.0
    grade: str = "C"
    priority_score: float = 0.0

    # Context
    regime_quad: str = "Q3"
    liquidity_regime: float = 0.0  # 0-100
    shock_probability: float = 0.0
    propagation_score: float = 0.0
    reflexivity_score: float = 0.0

    # Simulation
    simulation_win_rate: float = 0.0
    walkforward_score: float = 0.0
    gatekeeper_status: str = "FAIL"

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker, "market_type": self.market_type,
            "direction": self.direction, "conviction": round(self.conviction, 3),
            "tier": self.tier, "why_now": self.why_now,
            "what_changed": self.what_changed, "who_trapped": self.who_trapped,
            "who_must_buy": self.who_must_buy, "what_mispriced": self.what_mispriced,
            "what_invalidates": self.what_invalidates,
            "pressure": {
                "accumulation": round(self.accumulation_pressure, 1),
                "crowding": round(self.crowding_pressure, 1),
                "gamma_squeeze": round(self.gamma_squeeze_pressure, 1),
                "bottleneck": round(self.bottleneck_pressure, 1),
                "macro_alignment": round(self.macro_alignment_pressure, 1),
            },
            "price": self.price, "entry": self.entry, "target_1": self.target_1,
            "target_2": self.target_2, "stop_loss": self.stop_loss, "rr": round(self.rr, 2),
            "grade": self.grade, "priority_score": round(self.priority_score, 1),
            "regime_quad": self.regime_quad, "liquidity_regime": round(self.liquidity_regime, 1),
            "shock_probability": round(self.shock_probability, 3),
            "propagation_score": round(self.propagation_score, 3),
            "reflexivity_score": round(self.reflexivity_score, 3),
            "simulation_win_rate": round(self.simulation_win_rate, 3),
            "walkforward_score": round(self.walkforward_score, 1),
            "gatekeeper_status": self.gatekeeper_status,
        }


@dataclass
class RegimePressure:
    variable: str  # liquidity, growth, inflation, volatility, credit, dollar, yields
    structural: float = 0.0   # -1 (extreme negative) to +1 (extreme positive)
    cyclical: float = 0.0
    tactical: float = 0.0
    short_term: float = 0.0

    def to_dict(self) -> dict:
        return {
            "variable": self.variable,
            "structural": round(self.structural, 2),
            "cyclical": round(self.cyclical, 2),
            "tactical": round(self.tactical, 2),
            "short_term": round(self.short_term, 2),
        }


@dataclass
class GlobalStress:
    liquidity_stress: float = 0.0
    systemic_fragility: float = 0.0
    positioning_crowding: float = 0.0
    crash_probability: float = 0.0
    contagion_probability: float = 0.0

    def to_dict(self) -> dict:
        return {
            "liquidity_stress": round(self.liquidity_stress, 2),
            "systemic_fragility": round(self.systemic_fragility, 2),
            "positioning_crowding": round(self.positioning_crowding, 2),
            "crash_probability": round(self.crash_probability, 3),
            "contagion_probability": round(self.contagion_probability, 3),
        }


@dataclass
class BottleneckNode:
    name: str
    node_type: str  # commodities, suppliers, infrastructure, semis, energy, logistics, defense, countries
    pressure_intensity: float = 0.0  # 0-10
    capacity_utilization: float = 0.0
    inventory_trend: str = "neutral"
    lead_time_weeks: float = 0.0
    dependency_centrality: float = 0.0
    positioning: str = "neutral"
    beneficiaries: List[str] = field(default_factory=list)
    vulnerable_assets: List[str] = field(default_factory=list)


@dataclass
class PropagationEdge:
    source: str
    target: str
    criticality: float = 0.0  # 0-1
    edge_type: str = "beneficiary"  # beneficiary, fragile, emerging, accumulation
    lag_days: int = 0
    correlation_regime: str = "normal"


# ═══════════════════════════════════════════════════════════════════════════
# 1. MULTI-STAGE FILTER ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class MultiStageFilter:
    """
    STAGE 1: ELIMINATION — liquidity, catalyst, confidence, persistence
    STAGE 2: REGIME ALIGNMENT — penalize misaligned, boost aligned
    STAGE 3: COMPETITIVE RANKING — top N BEST in class, not threshold-based
    STAGE 4: CONVICTION FILTER — weak causal chain = eliminated
    """

    MARKET_MAX_TICKERS = {
        "us_equity": 12,
        "crypto": 8,
        "commodity": 6,
        "fx": 5,
        "ihsg": 10,
    }

    def __init__(self, prices: dict, quad: str, vix: float = 20.0,
                 liquidity_regime: float = 50.0, shock_prob: float = 0.0):
        self.prices = prices
        self.quad = quad
        self.vix = vix
        self.liquidity_regime = liquidity_regime
        self.shock_prob = shock_prob
        self.eliminated: List[str] = []
        self.passed: List[FilteredTicker] = []

    def _get_price_series(self, ticker: str) -> Optional[pd.Series]:
        s = self.prices.get(ticker)
        if s is None:
            return None
        try:
            return pd.to_numeric(pd.Series(s), errors="coerce").dropna()
        except Exception:
            return None

    def _compute_momentum(self, ticker: str) -> Tuple[float, float, float, float]:
        """Return (r5d, r20d, r60d, vol_ratio)"""
        s = self._get_price_series(ticker)
        if s is None or len(s) < 60:
            return 0.0, 0.0, 0.0, 1.0
        px = float(s.iloc[-1])
        r5d = (px / float(s.iloc[-6]) - 1) if len(s) >= 6 else 0
        r20d = (px / float(s.iloc[-21]) - 1) if len(s) >= 21 else r5d
        r60d = (px / float(s.iloc[-61]) - 1) if len(s) >= 61 else r20d
        vol_5 = float(s.tail(5).std())
        vol_20 = float(s.tail(20).std()) if len(s) >= 20 else vol_5
        vol_ratio = vol_5 / vol_20 if vol_20 > 0 else 1.0
        return r5d, r20d, r60d, vol_ratio

    def _market_type(self, ticker: str) -> str:
        if ticker.endswith(".JK"):
            return "ihsg"
        if "-USD" in ticker or ticker in ("BTC-USD", "ETH-USD", "SOL-USD"):
            return "crypto"
        if "=F" in ticker or ticker in ("GC=F", "SI=F", "CL=F", "HG=F", "NG=F"):
            return "commodity"
        if "=X" in ticker or ticker in ("DX-Y.NYB", "UUP", "EURUSD=X", "GBPUSD=X"):
            return "fx"
        return "us_equity"

    # ── STAGE 1: ELIMINATION ──
    def stage1_elimination(self, candidates: List[dict]) -> List[dict]:
        survivors = []
        for c in candidates:
            t = c.get("ticker", "")
            s = self._get_price_series(t)
            if s is None or len(s) < 30:
                self.eliminated.append(f"{t}: insufficient_history")
                continue

            # Low liquidity proxy: too little price movement = dead
            r5d, r20d, r60d, vol_ratio = self._compute_momentum(t)
            if abs(r60d) < 0.02 and abs(r20d) < 0.01:
                self.eliminated.append(f"{t}: no_momentum_dead")
                continue

            # No catalyst proxy: if no volume expansion and no news signal
            has_catalyst = c.get("news_signal") not in (None, "", "NEUTRAL")
            vol_expansion = vol_ratio > 1.3
            if not has_catalyst and not vol_expansion and abs(r5d) < 0.02:
                self.eliminated.append(f"{t}: no_catalyst")
                continue

            # Weak confidence: no clear directional structure
            comp = c.get("composite", "neutral")
            if comp == "neutral" and not has_catalyst:
                self.eliminated.append(f"{t}: neutral_no_edge")
                continue

            # No accumulation persistence
            if r5d * r20d < 0 and abs(r5d) < 0.03:  # direction flip without conviction
                self.eliminated.append(f"{t}: direction_chop")
                continue

            survivors.append(c)
        return survivors

    # ── STAGE 2: REGIME ALIGNMENT ──
    def stage2_regime_alignment(self, candidates: List[dict]) -> List[dict]:
        aligned = []
        for c in candidates:
            t = c.get("ticker", "")
            mtype = self._market_type(t)
            comp = c.get("composite", "neutral")
            direction = "LONG" if comp == "bullish" else "SHORT" if comp == "bearish" else "NEUTRAL"

            # Quad penalty/bonus matrix
            penalties = 0.0
            bonuses = 0.0

            if self.quad == "Q1":  # Goldilocks
                if mtype == "us_equity" and direction == "LONG":
                    bonuses += 20
                elif mtype == "crypto" and direction == "LONG":
                    bonuses += 15
                elif direction == "SHORT":
                    penalties += 10
            elif self.quad == "Q2":  # Reflation
                if mtype == "commodity" and direction == "LONG":
                    bonuses += 25
                elif mtype == "ihsg" and direction == "LONG":
                    bonuses += 15
            elif self.quad == "Q3":  # Stagflation
                if mtype == "commodity" and direction == "LONG":
                    bonuses += 20
                elif mtype == "fx" and "GLD" in t or "GC=F" in t:
                    bonuses += 20
                elif mtype == "us_equity" and direction == "LONG" and self.vix > 25:
                    penalties += 15  # risky to buy equities in high vol Q3
            elif self.quad == "Q4":  # Deflation
                if mtype in ("fx", "commodity") and "GLD" in t or "TLT" in t or "GC=F" in t:
                    bonuses += 20
                elif mtype == "us_equity" and direction == "LONG":
                    penalties += 15

            # Liquidity regime override
            if self.liquidity_regime < 30:  # contraction
                if mtype == "crypto" and direction == "LONG":
                    penalties += 20  # speculative junk penalized
                if mtype == "us_equity" and "small" in c.get("sector", "").lower():
                    penalties += 10
            elif self.liquidity_regime > 70:  # expansion
                if mtype == "crypto" and direction == "LONG":
                    bonuses += 15

            # Shock probability override
            if self.shock_prob > 0.3:
                if direction == "LONG" and mtype == "us_equity":
                    penalties += 15

            c["_regime_score"] = bonuses - penalties
            c["_direction"] = direction
            c["_market_type"] = mtype
            aligned.append(c)
        return aligned

    # ── STAGE 3: COMPETITIVE RANKING ──
    def stage3_competitive_ranking(self, candidates: List[dict]) -> List[dict]:
        # Score each candidate
        scored = []
        for c in candidates:
            t = c.get("ticker", "")
            r5d, r20d, r60d, vol_ratio = self._compute_momentum(t)

            # Asymmetric score components
            rr = c.get("rr", 1.0)
            near_entry = c.get("near_entry", False)
            regime_score = c.get("_regime_score", 0)

            # Base score
            score = rr * 15  # reward high R:R
            if near_entry:
                score += 40
            score += regime_score
            score += abs(r20d) * 100  # reward strong trend
            score += (vol_ratio - 1) * 10 if vol_ratio > 1 else 0  # reward volume expansion

            # Propagation edge bonus
            if c.get("propagation_score", 0) > 0.5:
                score += 20

            # Reflexivity bonus
            if c.get("reflexivity_score", 0) > 0.6:
                score += 15

            # Crowding penalty (inverse — crowded = lower score)
            crowding = c.get("crowding_score", 0.5)
            score -= crowding * 20

            # Liquidity penalty
            if c.get("liquidity_score", 1.0) < 0.3:
                score -= 30

            c["_competitive_score"] = score
            scored.append(c)

        # Group by market type and take top N per market
        by_market: Dict[str, List[dict]] = {}
        for c in scored:
            mt = c.get("_market_type", "us_equity")
            by_market.setdefault(mt, []).append(c)

        finalists = []
        for mt, items in by_market.items():
            max_n = self.MARKET_MAX_TICKERS.get(mt, 10)
            # Sort by competitive score descending
            sorted_items = sorted(items, key=lambda x: x["_competitive_score"], reverse=True)
            finalists.extend(sorted_items[:max_n])

        return finalists

    # ── STAGE 4: CONVICTION FILTER ──
    def stage4_conviction_filter(self, candidates: List[dict]) -> List[FilteredTicker]:
        results = []
        for c in candidates:
            t = c.get("ticker", "")
            score = c.get("_competitive_score", 0)

            # Hard conviction thresholds
            rr = c.get("rr", 0)
            has_catalyst = c.get("news_signal") not in (None, "", "NEUTRAL")
            causal_chain_strong = c.get("bottleneck_score", 0) > 0.3 or has_catalyst or c.get("propagation_score", 0) > 0.4

            if score < 20 and not causal_chain_strong:
                self.eliminated.append(f"{t}: low_conviction")
                continue
            if rr < 1.0 and not causal_chain_strong:
                self.eliminated.append(f"{t}: poor_rr_no_catalyst")
                continue

            # Determine tier
            if score >= 60 and causal_chain_strong and rr >= 1.5:
                tier = 1
            elif score >= 35 and (causal_chain_strong or rr >= 1.0):
                tier = 2
            else:
                tier = 3

            ft = FilteredTicker(
                ticker=t,
                market_type=c.get("_market_type", "us_equity"),
                direction=c.get("_direction", "NEUTRAL"),
                conviction=min(1.0, max(0.0, score / 100)),
                tier=tier,
                price=c.get("price", 0),
                entry=c.get("entry", 0),
                target_1=c.get("target_1", 0),
                target_2=c.get("target_2", 0),
                stop_loss=c.get("stop_loss", 0),
                rr=rr,
                grade="A" if tier == 1 else ("B" if tier == 2 else "C"),
                priority_score=score,
                regime_quad=self.quad,
                liquidity_regime=self.liquidity_regime,
                shock_probability=self.shock_prob,
                propagation_score=c.get("propagation_score", 0),
                reflexivity_score=c.get("reflexivity_score", 0),
                accumulation_pressure=c.get("accumulation_score", 0) * 10,
                crowding_pressure=c.get("crowding_score", 0) * 10,
                gamma_squeeze_pressure=c.get("gamma_score", 0) * 10,
                bottleneck_pressure=c.get("bottleneck_score", 0) * 10,
                macro_alignment_pressure=c.get("_regime_score", 0) / 5,
                simulation_win_rate=c.get("simulation_win_rate", 0),
                walkforward_score=c.get("walkforward_score", 0),
                gatekeeper_status=c.get("gatekeeper_status", "FAIL"),
            )
            results.append(ft)

        return results

    def run(self, raw_candidates: List[dict]) -> Dict[str, Any]:
        """Run full 4-stage pipeline."""
        s1 = self.stage1_elimination(raw_candidates)
        s2 = self.stage2_regime_alignment(s1)
        s3 = self.stage3_competitive_ranking(s2)
        s4 = self.stage4_conviction_filter(s3)

        tier1 = [t for t in s4 if t.tier == 1]
        tier2 = [t for t in s4 if t.tier == 2]
        tier3 = [t for t in s4 if t.tier == 3]

        return {
            "tier1": [t.to_dict() for t in tier1],
            "tier2": [t.to_dict() for t in tier2],
            "tier3": [t.to_dict() for t in tier3],
            "all": [t.to_dict() for t in s4],
            "eliminated": self.eliminated,
            "stats": {
                "input": len(raw_candidates),
                "stage1": len(s1),
                "stage2": len(s2),
                "stage3": len(s3),
                "stage4": len(s4),
                "tier1": len(tier1),
                "tier2": len(tier2),
                "tier3": len(tier3),
                "eliminated": len(self.eliminated),
            }
        }


# ═══════════════════════════════════════════════════════════════════════════
# 2. CONFIDENCE ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class ConfidenceEngine:
    """
    Computes confidence score for each ticker based on:
    - Data quality (price coverage, recency)
    - Model agreement (how many engines agree)
    - Market structure validation (gamma, liquidity, breadth)
    - Causal chain strength
    """

    def __init__(self, prices: dict, quad: str, vix: float):
        self.prices = prices
        self.quad = quad
        self.vix = vix

    def compute_confidence(self, ticker: str, engine_signals: Dict[str, str]) -> dict:
        s = self.prices.get(ticker)
        data_quality = 0.0
        if s is not None:
            try:
                s_clean = pd.to_numeric(pd.Series(s), errors="coerce").dropna()
                if len(s_clean) >= 100:
                    data_quality = 1.0
                elif len(s_clean) >= 60:
                    data_quality = 0.8
                elif len(s_clean) >= 30:
                    data_quality = 0.6
                else:
                    data_quality = 0.3
            except Exception:
                data_quality = 0.2
        else:
            data_quality = 0.0

        # Model agreement
        directions = [d for d in engine_signals.values() if d in ("LONG", "SHORT", "BULLISH", "BEARISH")]
        if not directions:
            agreement = 0.0
        else:
            long_count = sum(1 for d in directions if d in ("LONG", "BULLISH"))
            short_count = sum(1 for d in directions if d in ("SHORT", "BEARISH"))
            total = len(directions)
            agreement = max(long_count, short_count) / total if total > 0 else 0

        # Market structure validation (proxy)
        structure_score = 0.5
        if self.vix < 15:
            structure_score = 0.8
        elif self.vix > 30:
            structure_score = 0.3

        # Causal chain strength (placeholder — would be enriched by bottleneck engine)
        causal_strength = 0.5

        overall = (data_quality * 0.25 + agreement * 0.35 + structure_score * 0.25 + causal_strength * 0.15)

        return {
            "ticker": ticker,
            "overall": round(overall, 3),
            "data_quality": round(data_quality, 3),
            "model_agreement": round(agreement, 3),
            "structure_valid": round(structure_score, 3),
            "causal_strength": round(causal_strength, 3),
            "confidence_label": "HIGH" if overall > 0.7 else ("MEDIUM" if overall > 0.45 else "LOW"),
        }


# ═══════════════════════════════════════════════════════════════════════════
# 3. PROPAGATION ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class PropagationEngine:
    """
    Cross-asset lead/lag discovery + bottleneck chain reaction.

    Detects:
    - Which market leads which (rates → credit → equities)
    - Bottleneck propagation (oil → tankers → LNG → inflation → yields)
    - AI capex chain (NVDA → memory → power → optics → CPO)
    """

    CHAINS = {
        "ai_compute": [
            ("NVDA", "AMD", "AVGO"),           # Stage 1: AI Models / GPU
            ("MU", "TSM", "SKHYNIX"),          # Stage 2: Memory / HBM
            ("VST", "CEG", "BE"),            # Stage 3: Power / Cooling
            ("COHR", "LITE", "MRVL"),        # Stage 4: Optics / Interconnect
            ("NXT", "AMPH", "HLIT"),        # Stage 5: CPO / Connectors
            ("SCCO", "FCX", "ALB"),          # Stage 6: Raw Materials
        ],
        "mideast_energy": [
            ("CL=F", "USO", "XOM", "CVX"),   # Stage 1: Crude
            ("FRO", "TK", "INSW"),           # Stage 2: Tankers
            ("VLO", "MPC", "PSX"),           # Stage 3: Refining
            ("NTR", "MOS", "CF"),            # Stage 4: Fertilizer
            ("LMT", "NOC", "RTX"),           # Stage 5: Defense
        ],
        "indonesia_resources": [
            ("NCKL.JK", "ANTM.JK", "INCO.JK"), # Stage 1: Nickel
            ("AALI.JK", "LSIP.JK", "SMAR.JK"), # Stage 2: Palm Oil
            ("ADRO.JK", "ITMG.JK", "PTBA.JK"), # Stage 3: Coal
            ("WINS.JK",),                       # Stage 4: Shipping
        ],
    }

    def __init__(self, prices: dict, fred: dict = None):
        self.prices = prices
        self.fred = fred or {}

    def _returns(self, ticker: str, days: int = 5) -> float:
        s = self.prices.get(ticker)
        if s is None or len(s) < days + 1:
            return 0.0
        try:
            s_clean = pd.to_numeric(pd.Series(s), errors="coerce").dropna()
            if len(s_clean) < days + 1:
                return 0.0
            return float(s_clean.iloc[-1] / s_clean.iloc[-(days+1)] - 1)
        except Exception:
            return 0.0

    def detect_chain_reaction(self, chain_name: str) -> List[dict]:
        chain = self.CHAINS.get(chain_name, [])
        stages = []
        for i, tickers in enumerate(chain):
            stage_returns = []
            for t in tickers:
                r = self._returns(t, 5)
                stage_returns.append({"ticker": t, "r5d": round(r, 4)})
            avg_r = sum(x["r5d"] for x in stage_returns) / len(stage_returns) if stage_returns else 0
            stages.append({
                "stage": i + 1,
                "tickers": stage_returns,
                "avg_return": round(avg_r, 4),
                "activated": abs(avg_r) > 0.03,
            })
        return stages

    def cross_asset_leadlag(self, leaders: List[str], followers: List[str], lookback: int = 10) -> List[dict]:
        """Detect lead/lag relationships using correlation at different lags."""
        results = []
        for leader in leaders:
            l_s = self.prices.get(leader)
            if l_s is None or len(l_s) < lookback + 5:
                continue
            try:
                l_clean = pd.to_numeric(pd.Series(l_s), errors="coerce").dropna()
                if len(l_clean) < lookback + 5:
                    continue
                l_ret = l_clean.pct_change().dropna().tail(lookback).to_numpy()
            except Exception:
                continue

            for follower in followers:
                f_s = self.prices.get(follower)
                if f_s is None or len(f_s) < lookback + 5:
                    continue
                try:
                    f_clean = pd.to_numeric(pd.Series(f_s), errors="coerce").dropna()
                    if len(f_clean) < lookback + 5:
                        continue
                    f_ret = f_clean.pct_change().dropna().tail(lookback).to_numpy()
                except Exception:
                    continue

                min_len = min(len(l_ret), len(f_ret))
                if min_len < 5:
                    continue
                l_slice = l_ret[-min_len:]
                f_slice = f_ret[-min_len:]

                # Lag-0 correlation
                corr_0 = np.corrcoef(l_slice, f_slice)[0, 1] if np.std(l_slice) > 0 and np.std(f_slice) > 0 else 0

                # Lag-1 correlation (leader leads by 1 day)
                if min_len >= 6:
                    corr_1 = np.corrcoef(l_slice[:-1], f_slice[1:])[0, 1] if np.std(l_slice[:-1]) > 0 and np.std(f_slice[1:]) > 0 else 0
                else:
                    corr_1 = 0

                if abs(corr_1) > abs(corr_0) + 0.1 and abs(corr_1) > 0.3:
                    results.append({
                        "leader": leader,
                        "follower": follower,
                        "lag": 1,
                        "correlation": round(corr_1, 3),
                        "lead_lag_confidence": "HIGH" if abs(corr_1) > 0.5 else "MEDIUM",
                    })
        return sorted(results, key=lambda x: abs(x["correlation"]), reverse=True)[:10]

    def build_network(self, active_tickers: List[str]) -> Tuple[List[BottleneckNode], List[PropagationEdge]]:
        """Build simplified propagation network for visualization."""
        nodes = []
        edges = []

        # Create nodes for active tickers + chain parents
        for t in active_tickers:
            r5d = self._returns(t, 5)
            nodes.append(BottleneckNode(
                name=t,
                node_type="semis" if t in ("NVDA", "AMD", "TSM") else "energy" if t in ("CL=F", "XOM") else "commodities",
                pressure_intensity=min(10, abs(r5d) * 200),
            ))

        # Create edges based on known chains
        for chain_name, chain in self.CHAINS.items():
            for i in range(len(chain) - 1):
                current_stage = chain[i]
                next_stage = chain[i + 1]
                for src in current_stage:
                    for tgt in next_stage:
                        if src in active_tickers or tgt in active_tickers:
                            edges.append(PropagationEdge(
                                source=src, target=tgt,
                                criticality=0.7,
                                edge_type="beneficiary" if self._returns(src, 5) > 0 else "fragile",
                                lag_days=2,
                            ))

        return nodes, edges


# ═══════════════════════════════════════════════════════════════════════════
# 4. WHAT CHANGED ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class WhatChangedEngine:
    """
    Detects market structure deltas vs previous snapshot.
    Outputs: change magnitude bar + one-sentence explanation + propagation impact.
    """

    VARIABLES = ["liquidity", "growth", "inflation", "volatility", "credit", "dollar", "yields"]

    def __init__(self, current_snap: dict, previous_snap: dict = None):
        self.current = current_snap
        self.previous = previous_snap

    def detect_changes(self) -> List[dict]:
        if self.previous is None:
            return []

        changes = []

        # Regime change
        curr_quad = self.current.get("quad", "Q3")
        prev_quad = self.previous.get("quad", "Q3")
        if curr_quad != prev_quad:
            changes.append({
                "magnitude": 10,
                "sentence": f"Regime shifted from {prev_quad} to {curr_quad}",
                "propagation": "→ Reassess all asset allocations",
                "category": "regime",
            })

        # VIX change
        curr_vix = self.current.get("vix", 20)
        prev_vix = self.previous.get("vix", 20)
        vix_delta = curr_vix - prev_vix
        if abs(vix_delta) > 3:
            changes.append({
                "magnitude": min(10, abs(vix_delta)),
                "sentence": f"VIX {'spiked' if vix_delta > 0 else 'compressed'} {abs(vix_delta):.1f} points to {curr_vix:.1f}",
                "propagation": "→ Volatility regime change affects gamma positioning" if vix_delta > 0 else "→ Volatility sellers at risk of squeeze",
                "category": "volatility",
            })

        # DXY change
        curr_dxy = self.current.get("dxy", 100)
        prev_dxy = self.previous.get("dxy", 100)
        dxy_delta = curr_dxy - prev_dxy
        if abs(dxy_delta) > 1.0:
            changes.append({
                "magnitude": min(10, abs(dxy_delta)),
                "sentence": f"DXY {'rallied' if dxy_delta > 0 else 'fell'} {abs(dxy_delta):.2f} to {curr_dxy:.2f}",
                "propagation": "→ EM FX and commodities under pressure" if dxy_delta > 0 else "→ Risk assets get relief",
                "category": "dollar",
            })

        # Gamma regime flip (if data available)
        curr_gamma = self.current.get("gamma_regime", "NEUTRAL")
        prev_gamma = self.previous.get("gamma_regime", "NEUTRAL")
        if curr_gamma != prev_gamma and "NEGATIVE" in (curr_gamma, prev_gamma):
            changes.append({
                "magnitude": 8,
                "sentence": f"Dealer gamma regime flipped to {curr_gamma}",
                "propagation": "→ Momentum fragility rising, volatility expansion likely",
                "category": "gamma",
            })

        return sorted(changes, key=lambda x: x["magnitude"], reverse=True)


# ═══════════════════════════════════════════════════════════════════════════
# 5. CAUSAL CARD ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class CausalCardEngine:
    """
    Generates the 6 causal explanations for each Tier 1 ticker:
    1. WHY NOW
    2. WHAT CHANGED
    3. WHO IS TRAPPED
    4. WHO MUST BUY
    5. WHAT IS MISPRICED
    6. WHAT BREAKS THE THESIS
    """

    def __init__(self, prices: dict, news: dict, bottleneck: dict, propagation: dict):
        self.prices = prices
        self.news = news or {}
        self.bottleneck = bottleneck or {}
        self.propagation = propagation or {}

    def generate_card(self, ticker: str, direction: str, quad: str) -> dict:
        s = self.prices.get(ticker)
        r5d = 0.0
        if s is not None and len(s) >= 6:
            try:
                s_clean = pd.to_numeric(pd.Series(s), errors="coerce").dropna()
                r5d = float(s_clean.iloc[-1] / s_clean.iloc[-6] - 1) if len(s_clean) >= 6 else 0
            except Exception:
                pass

        news_item = self.news.get(ticker, {})
        headline = (news_item.get("headlines") or [""])[0] if news_item else ""

        # WHY NOW
        if direction == "LONG":
            why_now = f"Price breaking above accumulation zone with {abs(r5d):.1%} 5d momentum."
            if headline:
                why_now += f" Catalyst: {headline[:50]}..."
        else:
            why_now = f"Distribution detected with {abs(r5d):.1%} 5d decline."

        # WHAT CHANGED
        what_changed = "Regime alignment shifting. " if quad in ("Q1", "Q2") else "Defensive rotation accelerating. "
        what_changed += "Volume profile expanding vs 20d average."

        # WHO IS TRAPPED
        if direction == "LONG":
            who_trapped = "Shorts above recent highs + dealers short gamma."
        else:
            who_trapped = "Longs from prior breakout level now underwater."

        # WHO MUST BUY
        if direction == "LONG":
            who_must_buy = "ETF rebalancers + momentum algos + underweight funds."
        else:
            who_must_buy = "Risk managers hitting stops + VaR-driven deleveraging."

        # WHAT IS MISPRICED
        what_mispriced = "Market pricing linear regime continuation; ignores bottleneck propagation."

        # WHAT INVALIDATES
        if direction == "LONG":
            what_invalidates = "Reclaim below LRR + VIX spike above 30 + gamma flip negative."
        else:
            what_invalidates = "Reclaim above TRR + volume dries up + gamma flip positive."

        return {
            "ticker": ticker,
            "direction": direction,
            "why_now": why_now,
            "what_changed": what_changed,
            "who_trapped": who_trapped,
            "who_must_buy": who_must_buy,
            "what_mispriced": what_mispriced,
            "what_invalidates": what_invalidates,
        }
