"""engines/discovery_brain.py — Unified Discovery Brain v1.0 (Sprint 3)

Replaces auto_discovery_engine_v3 with three-mode parallel architecture:

ADAPTIVE MODE — regime-conditional playbook adaptation
  Triggers: quad shift, structural transition, intensity change

REACTIVE MODE — event-driven (news, price, vol)
  Triggers: new narrative cluster, price anomaly, vol regime shift, COT extreme

PROACTIVE MODE — pre-narrative detection
  Triggers: filing language (10-K), insider clusters, capex announcements,
            patent activity, narrative_universe.py reference matching

OUTPUT: unified DiscoveryCandidate list with mode tag, confidence, action plan.
"""
from __future__ import annotations

import logging
import time
import re
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryCandidate:
    name: str
    category: str           # "bottleneck" | "narrative" | "transition" | "scenario" | "ticker"
    mode: str               # "adaptive" | "reactive" | "proactive"
    stage: str              # "active" | "building" | "watch" | "early"
    thesis: str
    confidence: float
    beneficiary_tickers: List[str] = field(default_factory=list)
    fade_tickers: List[str] = field(default_factory=list)
    source_signals: List[str] = field(default_factory=list)
    confirmation_signal: str = ""
    invalidators: List[str] = field(default_factory=list)
    regime_fit: float = 0.5
    discovered_at: str = ""
    new_ticker: bool = False  # Flag for tickers not in current universe


# ════════════════════════════════════════════════════════════════════════
# ADAPTIVE MODE — Regime-conditional adaptation
# ════════════════════════════════════════════════════════════════════════

class AdaptiveDiscovery:
    """When quad shifts, regenerate playbook & flag stale positions."""

    def run(self, prev_quad: Optional[str], current_quad: str,
            monthly_quad: str, gip_features: Dict) -> List[DiscoveryCandidate]:
        candidates = []

        # Quad transition detected
        if prev_quad and prev_quad != current_quad:
            candidates.append(DiscoveryCandidate(
                name=f"QUAD_SHIFT_{prev_quad}_TO_{current_quad}",
                category="transition",
                mode="adaptive",
                stage="active",
                thesis=f"Structural regime shifted from {prev_quad} to {current_quad}. Full playbook rotation required.",
                confidence=0.85,
                source_signals=["quad_shift_detected"],
                confirmation_signal=f"Sector rotation aligned with {current_quad} playbook within 2 weeks",
                invalidators=[f"Quad reverts to {prev_quad} within 4 weeks (false signal)"],
                regime_fit=1.0,
                discovered_at=time.strftime("%Y-%m-%d %H:%M"),
            ))

        # Monthly divergence (early signal for next structural shift)
        if current_quad != monthly_quad:
            candidates.append(DiscoveryCandidate(
                name=f"MONTHLY_DIVERGENCE_{monthly_quad}_INSIDE_{current_quad}",
                category="transition",
                mode="adaptive",
                stage="building",
                thesis=f"Monthly {monthly_quad} diverging from structural {current_quad}. Early front-run signal for next quad.",
                confidence=0.65,
                source_signals=["monthly_structural_divergence"],
                confirmation_signal=f"Monthly stays {monthly_quad} for 2+ months",
                invalidators=["Monthly reverts to align with structural"],
                regime_fit=0.6,
                discovered_at=time.strftime("%Y-%m-%d %H:%M"),
            ))

        # Intensity change (deepening regime)
        gm = gip_features.get("growth_momentum", 0)
        im = gip_features.get("inflation_momentum", 0)
        if current_quad == "Q3" and im > 0.3:
            candidates.append(DiscoveryCandidate(
                name="STAGFLATION_INTENSIFYING",
                category="transition",
                mode="adaptive",
                stage="building",
                thesis=f"Q3 deepening — inflation momentum {im:.2f}. Defensive tilt should intensify.",
                confidence=0.70,
                beneficiary_tickers=["GLD", "SLV", "GDX", "XLP", "XLU", "TLT"],
                fade_tickers=["QQQ", "XLK", "IWM"],
                source_signals=["inflation_momentum_high"],
                regime_fit=1.0,
                discovered_at=time.strftime("%Y-%m-%d %H:%M"),
            ))

        return candidates


# ════════════════════════════════════════════════════════════════════════
# REACTIVE MODE — Event-driven detection
# ════════════════════════════════════════════════════════════════════════

class ReactiveDiscovery:
    """React to NEW info: news clusters, price anomalies, vol shifts, COT extremes."""

    def run(self, prices: Dict, news_analysis: Dict,
            cot_data: Optional[Dict] = None) -> List[DiscoveryCandidate]:
        candidates = []

        # 1. New theme cluster from news (>5 mentions in 7d, not yet active)
        emergent = (news_analysis or {}).get("emergent_narratives", [])
        for theme in emergent[:5]:
            if theme.get("mentions", 0) >= 5 and abs(theme.get("avg_sentiment", 0)) >= 0.2:
                candidates.append(DiscoveryCandidate(
                    name=f"NEW_NARRATIVE_{theme['name']}",
                    category="narrative",
                    mode="reactive",
                    stage="building",
                    thesis=(
                        f"Emergent narrative: '{theme['name']}' — {theme['mentions']} mentions in 7d, "
                        f"sentiment {theme.get('avg_sentiment', 0):+.2f}."
                    ),
                    confidence=min(0.50 + 0.05 * theme["mentions"], 0.85),
                    beneficiary_tickers=theme.get("tickers", [])[:8],
                    source_signals=["news_cluster_emergent"],
                    confirmation_signal="Price confirmation in 3+ tickers within 14d",
                    invalidators=["Narrative dies within 7d", "Price action contradicts"],
                    discovered_at=time.strftime("%Y-%m-%d %H:%M"),
                ))

        # 2. Rumor watch — high rumor + bullish/bearish skew
        rumors = (news_analysis or {}).get("rumor_watch", [])
        for r in rumors[:5]:
            if r.get("rumor", 0) >= 0.3:
                signal_word = r.get("signal", "").lower()
                direction = "long" if "bull" in signal_word or "build" in signal_word else "short" if "bear" in signal_word else "neutral"
                candidates.append(DiscoveryCandidate(
                    name=f"RUMOR_{r['ticker']}",
                    category="ticker",
                    mode="reactive",
                    stage="watch",
                    thesis=(
                        f"Rumor cluster on {r['ticker']}: sentiment {r.get('sentiment', 0):+.2f}, "
                        f"rumor score {r.get('rumor', 0):.2f}. Headline: '{r.get('headline', '')[:80]}'"
                    ),
                    confidence=0.45 + r.get("rumor", 0) * 0.3,
                    beneficiary_tickers=[r["ticker"]] if direction == "long" else [],
                    fade_tickers=[r["ticker"]] if direction == "short" else [],
                    source_signals=["rumor_watch"],
                    confirmation_signal="Confirmed news within 7d OR price moves >5% in direction",
                    invalidators=["No follow-through in 14d"],
                    discovered_at=time.strftime("%Y-%m-%d %H:%M"),
                ))

        # 3. Price anomalies — high vol breakout
        for ticker, s in (prices or {}).items():
            try:
                ser = pd.to_numeric(s, errors="coerce").dropna()
                if len(ser) < 60:
                    continue
                ret_5d = float(ser.iloc[-1] / ser.iloc[-6] - 1)
                ret_30d = float(ser.iloc[-1] / ser.iloc[-22] - 1)
                vol_60d = float(ser.pct_change().tail(60).std()) if len(ser) >= 60 else 0.02

                # Breakout: 5d return > 3 standard deviations OR 30d return >20%
                if (vol_60d > 0 and abs(ret_5d) > 3 * vol_60d * np.sqrt(5)) or abs(ret_30d) > 0.20:
                    direction = "long" if ret_30d > 0 else "short"
                    candidates.append(DiscoveryCandidate(
                        name=f"PRICE_BREAKOUT_{ticker}",
                        category="ticker",
                        mode="reactive",
                        stage="building",
                        thesis=(
                            f"{ticker} price anomaly: 5d {ret_5d:+.1%}, 30d {ret_30d:+.1%}. "
                            f"Volatility regime shift detected."
                        ),
                        confidence=0.55,
                        beneficiary_tickers=[ticker] if direction == "long" else [],
                        fade_tickers=[ticker] if direction == "short" else [],
                        source_signals=["price_anomaly_breakout"],
                        confirmation_signal="Trend persists 2+ weeks with volume",
                        invalidators=["Reverses to mean within 5d (squeeze)"],
                        discovered_at=time.strftime("%Y-%m-%d %H:%M"),
                    ))
            except Exception:
                continue

        # 4. COT extremes
        if cot_data:
            for ticker, cot in cot_data.items():
                if not isinstance(cot, dict):
                    continue
                pos = cot.get("commercial_net_pct", None)
                if pos is None:
                    continue
                if pos > 80:
                    candidates.append(DiscoveryCandidate(
                        name=f"COT_EXTREME_LONG_{ticker}",
                        category="ticker",
                        mode="reactive",
                        stage="watch",
                        thesis=f"COT commercial net long extreme {pos:.0f}% — contrarian sell signal building.",
                        confidence=0.55,
                        fade_tickers=[ticker],
                        source_signals=["cot_extreme"],
                        invalidators=["Position normalizes within 4 weeks"],
                        discovered_at=time.strftime("%Y-%m-%d %H:%M"),
                    ))
                elif pos < 20:
                    candidates.append(DiscoveryCandidate(
                        name=f"COT_EXTREME_SHORT_{ticker}",
                        category="ticker",
                        mode="reactive",
                        stage="watch",
                        thesis=f"COT commercial net short extreme {pos:.0f}% — contrarian buy signal building.",
                        confidence=0.55,
                        beneficiary_tickers=[ticker],
                        source_signals=["cot_extreme"],
                        invalidators=["Position normalizes within 4 weeks"],
                        discovered_at=time.strftime("%Y-%m-%d %H:%M"),
                    ))

        return candidates


# ════════════════════════════════════════════════════════════════════════
# PROACTIVE MODE — Pre-narrative detection
# ════════════════════════════════════════════════════════════════════════

class ProactiveDiscovery:
    """Surface things BEFORE consensus catches on."""

    # Constraint language patterns (regex)
    BOTTLENECK_PATTERNS = [
        r"capacity\s+constrain",
        r"supply\s+constrain",
        r"limited\s+supplier",
        r"sole\s+source",
        r"only\s+supplier",
        r"shortage\s+of",
        r"lead\s+time.{0,30}(extend|increas)",
        r"backlog.{0,30}(grow|increas)",
        r"unable\s+to\s+meet\s+demand",
        r"order\s+backlog",
        r"demand\s+exceed.{0,20}supply",
        r"bottleneck",
        r"tight\s+supply",
    ]

    def run(self, news_analysis: Dict, prices: Dict,
            bottleneck_ref: Dict) -> List[DiscoveryCandidate]:
        candidates = []
        candidates.extend(self._scan_filings_language(news_analysis))
        candidates.extend(self._scan_capex_announcements(news_analysis))
        candidates.extend(self._reference_match(news_analysis, bottleneck_ref))
        candidates.extend(self._scan_bottleneck_cascade_forward(prices, bottleneck_ref))
        return candidates

    def _scan_filings_language(self, news_analysis: Dict) -> List[DiscoveryCandidate]:
        """Scan news for bottleneck language patterns."""
        candidates = []
        ticker_specific = (news_analysis or {}).get("ticker_specific", {})
        for ticker, items in ticker_specific.items():
            matched_patterns = set()
            sample_headline = ""
            for item in items[:5]:
                text = (item.get("title") or "").lower()
                for pattern in self.BOTTLENECK_PATTERNS:
                    if re.search(pattern, text):
                        matched_patterns.add(pattern)
                        if not sample_headline:
                            sample_headline = item.get("title", "")
            if matched_patterns:
                candidates.append(DiscoveryCandidate(
                    name=f"FILING_BOTTLENECK_LANGUAGE_{ticker}",
                    category="bottleneck",
                    mode="proactive",
                    stage="early",
                    thesis=(
                        f"{ticker} headlines contain constraint language: "
                        f"{len(matched_patterns)} patterns matched. "
                        f"Headline: '{sample_headline[:100]}'"
                    ),
                    confidence=0.40 + len(matched_patterns) * 0.10,
                    beneficiary_tickers=[ticker],
                    source_signals=["filing_constraint_language"],
                    confirmation_signal="Price action confirms within 30d",
                    invalidators=["Subsequent earnings normalizes guidance"],
                    discovered_at=time.strftime("%Y-%m-%d %H:%M"),
                ))
        return candidates

    def _scan_capex_announcements(self, news_analysis: Dict) -> List[DiscoveryCandidate]:
        """Detect capex / investment announcements (forward demand signal)."""
        candidates = []
        capex_patterns = [
            r"invest.{0,30}\$\s*\d+\s*billion",
            r"capex.{0,30}\$\s*\d+",
            r"announce.{0,30}\$\s*\d+\s*billion",
            r"partnership.{0,30}\$\s*\d+\s*billion",
            r"build.{0,30}(plant|facility|factory)",
            r"\$\s*\d+\s*billion.{0,30}commitment",
        ]
        ticker_specific = (news_analysis or {}).get("ticker_specific", {})
        for ticker, items in ticker_specific.items():
            for item in items[:5]:
                text = (item.get("title") or "").lower()
                for pattern in capex_patterns:
                    m = re.search(pattern, text)
                    if m:
                        candidates.append(DiscoveryCandidate(
                            name=f"CAPEX_ANNOUNCED_{ticker}",
                            category="ticker",
                            mode="proactive",
                            stage="building",
                            thesis=f"{ticker} capex/investment announcement detected: '{item.get('title', '')[:100]}'",
                            confidence=0.55,
                            beneficiary_tickers=[ticker],
                            source_signals=["capex_announcement"],
                            confirmation_signal="Supplier tickers move within 30d",
                            discovered_at=time.strftime("%Y-%m-%d %H:%M"),
                        ))
                        break
        return candidates

    def _reference_match(self, news_analysis: Dict, bottleneck_ref: Dict) -> List[DiscoveryCandidate]:
        """Match news to existing bottleneck_reference.json entries."""
        candidates = []
        if not bottleneck_ref:
            return candidates

        # Get bottleneck-tracked tickers
        tracked = set()
        for item in bottleneck_ref.get("consensus_heatmap", []):
            t = (item.get("ticker") or "").upper()
            if t:
                tracked.add(t)
        for phase in bottleneck_ref.get("institutional_rotation", []):
            for t in phase.get("tickers", []):
                if t:
                    tracked.add(t.upper())

        # Match news to tracked
        ticker_specific = (news_analysis or {}).get("ticker_specific", {})
        for ticker, items in ticker_specific.items():
            if ticker.upper() not in tracked or not items:
                continue
            # Find the bottleneck entry
            entry = None
            for item in bottleneck_ref.get("consensus_heatmap", []):
                if (item.get("ticker") or "").upper() == ticker.upper():
                    entry = item
                    break
            if not entry:
                continue
            sentiment = sum(i.get("sentiment", 0) for i in items[:5]) / max(len(items[:5]), 1)
            if abs(sentiment) < 0.10:
                continue
            candidates.append(DiscoveryCandidate(
                name=f"BTK_REF_ACTIVATION_{ticker}",
                category="bottleneck",
                mode="proactive",
                stage="active" if abs(sentiment) > 0.30 else "building",
                thesis=(
                    f"{ticker} (Layer {entry.get('layer', '?')}, Role: {entry.get('role', '?')}) "
                    f"tracked by {len(entry.get('accounts', []))} accounts now active in news. "
                    f"Sentiment {sentiment:+.2f}."
                ),
                confidence=0.50 + abs(sentiment) * 0.3,
                beneficiary_tickers=[ticker] if sentiment > 0 else [],
                fade_tickers=[ticker] if sentiment < 0 else [],
                source_signals=["bottleneck_ref_activated", "news_confirmation"],
                regime_fit=0.7,
                discovered_at=time.strftime("%Y-%m-%d %H:%M"),
            ))
        return candidates

    def _scan_bottleneck_cascade_forward(self, prices: Dict, bottleneck_ref: Dict) -> List[DiscoveryCandidate]:
        """If L3_Power constrains → next bottleneck is L4 or L2 (Citrini cascade logic)."""
        candidates = []
        if not bottleneck_ref or not prices:
            return candidates

        # Look at institutional_rotation for "NEXT" or "FUTURE" phases
        for phase in bottleneck_ref.get("institutional_rotation", []):
            status = phase.get("status", "")
            if "NEXT" in status or "FUTURE" in status:
                tickers = phase.get("tickers", [])
                if not tickers:
                    continue
                # Check if early price action confirms (any ticker up >5% in 30d)
                confirmed = []
                for t in tickers[:8]:
                    s = prices.get(t.upper())
                    if s is None:
                        continue
                    try:
                        ser = pd.to_numeric(s, errors="coerce").dropna()
                        if len(ser) >= 22 and float(ser.iloc[-1] / ser.iloc[-22] - 1) > 0.05:
                            confirmed.append(t)
                    except Exception:
                        continue
                if confirmed:
                    candidates.append(DiscoveryCandidate(
                        name=f"CASCADE_FORWARD_{phase.get('theme', 'unknown').replace(' ', '_')}",
                        category="bottleneck",
                        mode="proactive",
                        stage="early",
                        thesis=(
                            f"Next bottleneck cascade: {phase.get('theme')} "
                            f"(timeline {phase.get('timeline')}). "
                            f"Early confirmation in {len(confirmed)} tickers: {', '.join(confirmed[:5])}"
                        ),
                        confidence=0.50,
                        beneficiary_tickers=confirmed,
                        source_signals=["cascade_forward_propagation"],
                        confirmation_signal="3+ tickers show >15% gain within 90d",
                        discovered_at=time.strftime("%Y-%m-%d %H:%M"),
                    ))
        return candidates


# ════════════════════════════════════════════════════════════════════════
# UNIFIED BRAIN
# ════════════════════════════════════════════════════════════════════════

class DiscoveryBrain:
    """Three-mode parallel discovery orchestrator."""

    def __init__(self):
        self.adaptive = AdaptiveDiscovery()
        self.reactive = ReactiveDiscovery()
        self.proactive = ProactiveDiscovery()

    def run(self, prices: Dict, news_analysis: Dict,
            gip_features: Dict, current_quad: str, monthly_quad: str,
            prev_quad: Optional[str] = None,
            cot_data: Optional[Dict] = None,
            bottleneck_ref: Optional[Dict] = None) -> Dict:
        """
        Main entry. Runs all 3 modes, returns unified candidates.
        """
        all_candidates: List[DiscoveryCandidate] = []

        # Adaptive
        try:
            adaptive_results = self.adaptive.run(prev_quad, current_quad, monthly_quad, gip_features)
            all_candidates.extend(adaptive_results)
        except Exception as e:
            logger.warning(f"Adaptive discovery failed: {e}")

        # Reactive
        try:
            reactive_results = self.reactive.run(prices, news_analysis, cot_data)
            all_candidates.extend(reactive_results)
        except Exception as e:
            logger.warning(f"Reactive discovery failed: {e}")

        # Proactive
        try:
            proactive_results = self.proactive.run(news_analysis, prices, bottleneck_ref or {})
            all_candidates.extend(proactive_results)
        except Exception as e:
            logger.warning(f"Proactive discovery failed: {e}")

        # Group by mode
        by_mode = {"adaptive": [], "reactive": [], "proactive": []}
        for c in all_candidates:
            by_mode[c.mode].append(asdict(c))

        # Sort each by confidence
        for mode in by_mode:
            by_mode[mode].sort(key=lambda x: x["confidence"], reverse=True)

        return {
            "ok": True,
            "total": len(all_candidates),
            "by_mode": by_mode,
            "by_category": self._group_by_category(all_candidates),
            "top_10": sorted([asdict(c) for c in all_candidates],
                            key=lambda x: x["confidence"], reverse=True)[:10],
            "new_tickers": [c.beneficiary_tickers[0] for c in all_candidates
                           if c.new_ticker and c.beneficiary_tickers][:20],
            "summary": {
                "adaptive": len(by_mode["adaptive"]),
                "reactive": len(by_mode["reactive"]),
                "proactive": len(by_mode["proactive"]),
                "high_conviction": len([c for c in all_candidates if c.confidence >= 0.65]),
            },
        }

    def _group_by_category(self, candidates: List[DiscoveryCandidate]) -> Dict:
        by_cat = {}
        for c in candidates:
            by_cat.setdefault(c.category, []).append(asdict(c))
        for cat in by_cat:
            by_cat[cat].sort(key=lambda x: x["confidence"], reverse=True)
        return by_cat


def run_discovery_brain(prices: Dict, news_analysis: Dict,
                       gip_features: Dict, current_quad: str, monthly_quad: str,
                       prev_quad: Optional[str] = None,
                       cot_data: Optional[Dict] = None,
                       bottleneck_ref: Optional[Dict] = None) -> Dict:
    """Convenience entry point for orchestrator."""
    brain = DiscoveryBrain()
    return brain.run(prices, news_analysis, gip_features, current_quad, monthly_quad,
                     prev_quad, cot_data, bottleneck_ref)
