"""engines/movement_timing_engine.py — v38

Classifies per-ticker movement regime to answer Edward's question:
"Kapan movement langsung naik/turun, atau volatile dulu, atau gimana?"

6 Movement Regimes:
  🚀 DIRECT_TREND               — Buy and hold (firm direction)
  🌪️ VOLATILE_FIRST_THEN_TREND  — Scalp first weeks, then swing
  ⏳ VOL_COMPRESSION_BREAKOUT    — Wait for breakout, then ride
  🔄 MEAN_REVERSION              — Range trade between dealer walls
  💥 VOL_EXPANSION               — Avoid OR vol harvest
  📌 GAMMA_PINNING               — Stuck near key strikes / max pain

Detection signals:
  - Markov regime + transition probability
  - Realized vol vs Implied vol proxy (vol-of-vol)
  - ATR compression ratio (recent vs prior 60-bar)
  - Bollinger Band width percentile
  - Gamma regime (proxy from price patterns since no real options data)
  - Composite signal confidence trajectory

OUTPUT: Per ticker recommendation:
  - Regime classification
  - Action plan (HOLD, SCALP_FIRST, WAIT_BREAKOUT, RANGE_TRADE, AVOID)
  - Expected pattern duration
  - Concrete entry tactic
"""
from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# DATACLASSES
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class MovementRegime:
    """Movement regime classification for a ticker."""
    ticker: str
    regime: str                  # DIRECT_TREND / VOLATILE_FIRST_THEN_TREND / etc
    direction_bias: str          # LONG / SHORT / NEUTRAL
    confidence: float            # 0-1
    action: str                  # BUY_AND_HOLD / SCALP_FIRST / WAIT_BREAKOUT / RANGE_TRADE / AVOID
    
    # Pattern characteristics
    expected_duration_days: int  # how long this regime expected to last
    pattern_signals: List[str]   # which signals detected this regime
    
    # Tactical guidance
    entry_tactic: str
    sizing_guidance: str         # FULL_SIZE / SCALE_IN / SMALL_TEST
    stop_management: str         # FIXED / TRAILING / WIDE / TIGHT
    
    # Underlying metrics
    realized_vol_pct: float
    vol_compression_ratio: float  # recent vol / prior vol
    bb_width_percentile: float
    momentum_consistency: float
    gamma_proxy_regime: str       # POSITIVE / NEGATIVE / NEUTRAL


# ═══════════════════════════════════════════════════════════════════════
# CORE DETECTOR
# ═══════════════════════════════════════════════════════════════════════

class MovementTimingDetector:
    """Detect WHEN a movement happens — pattern classifier."""

    def detect(self, ticker: str, prices: pd.Series,
               snap: Optional[Dict] = None,
               direction_bias: str = "LONG") -> Optional[MovementRegime]:
        """
        Classify movement regime for a ticker.

        Returns MovementRegime with tactical guidance.
        """
        s = pd.to_numeric(prices, errors="coerce").dropna()
        if len(s) < 60:
            return None

        try:
            # ── Compute base metrics ──
            metrics = self._compute_metrics(s)

            # ── Get Markov / gamma context if available ──
            context = self._get_context(ticker, snap) if snap else {}

            # ── Classify regime ──
            regime, signals = self._classify_regime(metrics, context)

            # ── Build tactical guidance ──
            action, tactic, sizing, stop_mgmt, duration = self._build_tactics(
                regime, direction_bias, metrics, context
            )

            confidence = self._compute_confidence(signals, metrics)

            return MovementRegime(
                ticker=ticker,
                regime=regime,
                direction_bias=direction_bias,
                confidence=round(confidence, 2),
                action=action,
                expected_duration_days=duration,
                pattern_signals=signals,
                entry_tactic=tactic,
                sizing_guidance=sizing,
                stop_management=stop_mgmt,
                realized_vol_pct=round(metrics["rv_21d"] * 100, 2),
                vol_compression_ratio=round(metrics["vol_compression"], 3),
                bb_width_percentile=round(metrics["bb_width_pct"], 1),
                momentum_consistency=round(metrics["momentum_consistency"], 2),
                gamma_proxy_regime=context.get("gamma_regime", "UNKNOWN"),
            )
        except Exception as e:
            logger.debug(f"Movement detect failed for {ticker}: {e}")
            return None

    # ── Helpers ────────────────────────────────────────────────────────

    def _compute_metrics(self, s: pd.Series) -> Dict:
        """Compute volatility, compression, momentum metrics."""
        returns = s.pct_change().dropna()

        # Realized vol (annualized)
        rv_21d = float(returns.tail(21).std() * math.sqrt(252))
        rv_63d = float(returns.tail(63).std() * math.sqrt(252)) if len(returns) >= 63 else rv_21d

        # Vol compression ratio
        vol_compression = rv_21d / max(rv_63d, 0.001)

        # ATR proxy (close-to-close)
        atr_5 = float(returns.tail(5).abs().mean())
        atr_60 = float(returns.tail(60).abs().mean()) if len(returns) >= 60 else atr_5
        atr_compression = atr_5 / max(atr_60, 0.0001)

        # Bollinger Band width (using SMA20 + 2 std)
        sma_20 = s.tail(20).mean()
        std_20 = s.tail(20).std()
        bb_upper = sma_20 + 2 * std_20
        bb_lower = sma_20 - 2 * std_20
        bb_width = (bb_upper - bb_lower) / sma_20 if sma_20 > 0 else 0
        
        # BB width percentile (compare to 60-bar history of BB widths)
        bb_widths = []
        for i in range(20, min(80, len(s))):
            window = s.iloc[-i-20:-i] if i > 0 else s.tail(20)
            if len(window) >= 20:
                sma = window.mean()
                std = window.std()
                bb_widths.append((4 * std) / max(sma, 0.001))
        bb_width_pct = (
            float(np.searchsorted(sorted(bb_widths), bb_width) / len(bb_widths) * 100)
            if bb_widths else 50.0
        )

        # Momentum consistency (% of up days in last 20)
        up_days = (returns.tail(20) > 0).sum()
        momentum_consistency = up_days / 20

        # 21-day return (direction strength)
        ret_21d = float(s.iloc[-1] / s.iloc[-22] - 1) if len(s) >= 22 else 0

        # Recent range
        recent_range_pct = float((s.tail(15).max() - s.tail(15).min()) / s.tail(15).mean())

        return {
            "rv_21d": rv_21d,
            "rv_63d": rv_63d,
            "vol_compression": vol_compression,
            "atr_compression": atr_compression,
            "bb_width": bb_width,
            "bb_width_pct": bb_width_pct,
            "momentum_consistency": momentum_consistency,
            "ret_21d": ret_21d,
            "recent_range_pct": recent_range_pct,
            "current_price": float(s.iloc[-1]),
            "sma_20": float(sma_20),
        }

    def _get_context(self, ticker: str, snap: Dict) -> Dict:
        """Pull Markov regime + gamma data from snap."""
        context = {}

        # Markov regime
        markov = snap.get("markov_v3", {}) or {}
        if isinstance(markov, dict):
            per_ticker = markov.get("per_ticker", {}).get(ticker, {})
            if isinstance(per_ticker, dict):
                context["markov_regime"] = per_ticker.get("current_regime", "UNKNOWN")
                context["transition_prob"] = per_ticker.get("transition_probability", 0.0)
            else:
                context["markov_regime"] = markov.get("current_regime", "UNKNOWN")

        # Gamma proxy
        gamma = (snap.get("gamma_data", {}) or {}).get(ticker, {})
        if isinstance(gamma, dict) and gamma.get("ok"):
            context["gamma_regime"] = gamma.get("regime", "UNKNOWN")

        # Composite signal
        composite = (snap.get("composite_signals", {}) or {}).get(ticker, {})
        if isinstance(composite, dict):
            context["composite_direction"] = composite.get("direction", "NEUTRAL")
            context["composite_confidence"] = composite.get("confidence", 0)

        return context

    def _classify_regime(self, m: Dict, ctx: Dict) -> Tuple[str, List[str]]:
        """Classify the movement regime based on metrics + context."""
        signals = []

        # ── DIRECT_TREND signals ──
        if (m["vol_compression"] < 1.1 and m["vol_compression"] > 0.7 and
            m["momentum_consistency"] >= 0.65 and abs(m["ret_21d"]) > 0.05 and
            m["bb_width_pct"] > 30):
            signals.append(f"Stable vol ratio {m['vol_compression']:.2f}")
            signals.append(f"Strong momentum: {m['momentum_consistency']:.0%} up days")
            signals.append(f"21d return {m['ret_21d']*100:+.1f}% (clear direction)")
            if ctx.get("gamma_regime") in ("POSITIVE", "DEEP_POSITIVE"):
                signals.append("Gamma POSITIVE — mechanical support")
                return "DIRECT_TREND", signals
            elif ctx.get("composite_confidence", 0) > 0.6:
                signals.append("Composite confidence HIGH")
                return "DIRECT_TREND", signals

        # ── VOL_COMPRESSION_BREAKOUT signals ──
        if (m["vol_compression"] < 0.6 and m["bb_width_pct"] < 25 and
            m["recent_range_pct"] < 0.06):
            signals.append(f"Vol DROPPED {(1-m['vol_compression']):.0%} (compression)")
            signals.append(f"BB width {m['bb_width_pct']:.0f}th percentile (narrow)")
            signals.append(f"15-day range only {m['recent_range_pct']*100:.1f}%")
            return "VOL_COMPRESSION_BREAKOUT", signals

        # ── VOLATILE_FIRST_THEN_TREND signals ──
        if (m["vol_compression"] > 1.3 and abs(m["ret_21d"]) > 0.04 and
            m["bb_width_pct"] > 50):
            signals.append(f"Vol expanding {m['vol_compression']:.2f}x")
            signals.append(f"Direction present but choppy: 21d {m['ret_21d']*100:+.1f}%")
            signals.append(f"BB wide ({m['bb_width_pct']:.0f}th percentile)")
            return "VOLATILE_FIRST_THEN_TREND", signals

        # ── VOL_EXPANSION (dangerous) ──
        if (m["vol_compression"] > 1.8 and ctx.get("gamma_regime") in 
            ("NEGATIVE", "DEEP_NEGATIVE")):
            signals.append(f"Vol explosion {m['vol_compression']:.2f}x")
            signals.append("Gamma NEGATIVE — trend amplification mode")
            return "VOL_EXPANSION", signals

        # ── GAMMA_PINNING ──
        if (ctx.get("gamma_regime") in ("DEEP_POSITIVE", "POSITIVE") and
            m["recent_range_pct"] < 0.04 and m["momentum_consistency"] > 0.4 and
            m["momentum_consistency"] < 0.6):
            signals.append("Gamma POSITIVE + tight range = pinning")
            signals.append(f"Momentum oscillating: {m['momentum_consistency']:.0%} up days")
            return "GAMMA_PINNING", signals

        # ── MEAN_REVERSION (default for choppy) ──
        if (m["momentum_consistency"] > 0.4 and m["momentum_consistency"] < 0.6 and
            abs(m["ret_21d"]) < 0.04):
            signals.append("No directional bias")
            signals.append(f"Momentum oscillates: {m['momentum_consistency']:.0%} up days")
            return "MEAN_REVERSION", signals

        # ── Default fallback ──
        signals.append("Mixed signals, no clear regime")
        return "MEAN_REVERSION", signals

    def _build_tactics(self, regime: str, direction: str, m: Dict,
                       ctx: Dict) -> Tuple[str, str, str, str, int]:
        """Build action, tactic, sizing, stop management, duration."""
        if regime == "DIRECT_TREND":
            action = "BUY_AND_HOLD" if direction == "LONG" else "SHORT_AND_HOLD"
            tactic = (
                f"Enter NOW at market. Direction firm. "
                f"Add on minor pullbacks (5-7%). Hold through normal volatility."
            )
            sizing = "FULL_SIZE"
            stop_mgmt = "TRAILING (1.5x ATR)"
            duration = 30

        elif regime == "VOL_COMPRESSION_BREAKOUT":
            action = "WAIT_BREAKOUT"
            tactic = (
                f"DO NOT chase. Wait for breakout above ${m['sma_20']*1.03:.2f} "
                f"with volume expansion. Then enter aggressive."
            )
            sizing = "SCALE_IN (30% on breakout, 30% on retest, 40% on follow-through)"
            stop_mgmt = "TIGHT (below breakout level)"
            duration = 21

        elif regime == "VOLATILE_FIRST_THEN_TREND":
            action = "SCALP_FIRST"
            tactic = (
                f"Edward style: main cepet dulu 1-2 minggu. "
                f"Buy dip {direction}, sell rip, repeat. After volatility settles "
                f"(vol_compression drops below 1.0), build full position for trend."
            )
            sizing = "SMALL_TEST first 1-2 weeks (1-2% size), full size after vol settles"
            stop_mgmt = "WIDE initially (3x ATR), tighten after trend confirmation"
            duration = 14

        elif regime == "VOL_EXPANSION":
            action = "AVOID"
            tactic = (
                f"DO NOT take directional position. Negative gamma = trend amplification. "
                f"Either skip or vol harvest (sell premium, hedge tails). "
                f"Wait for vol_compression to drop below 1.3."
            )
            sizing = "SMALL_TEST only or skip"
            stop_mgmt = "VERY_WIDE if must take position"
            duration = 7

        elif regime == "MEAN_REVERSION":
            action = "RANGE_TRADE"
            tactic = (
                f"Range trade between Trade Low and Trade High. Buy near bottom of range, "
                f"sell near top. Take quick profits. No directional bias."
            )
            sizing = "SMALL_TEST per trade (0.5-1% per cycle)"
            stop_mgmt = "TIGHT (just outside range)"
            duration = 14

        elif regime == "GAMMA_PINNING":
            action = "WAIT_OR_SELL_PREMIUM"
            tactic = (
                f"Stuck near gamma pin. Wait for catalyst that breaks pinning, "
                f"or sell premium (covered calls / iron condor) to harvest decay."
            )
            sizing = "NONE_DIRECTIONAL (or premium selling small)"
            stop_mgmt = "WIDE (gamma releases sometimes violent)"
            duration = 10

        else:
            action = "MONITOR"
            tactic = "Unknown regime, wait for clearer signal."
            sizing = "NONE"
            stop_mgmt = "N/A"
            duration = 7

        return action, tactic, sizing, stop_mgmt, duration

    def _compute_confidence(self, signals: List[str], m: Dict) -> float:
        """Confidence in regime classification."""
        base = 0.4
        base += min(0.3, len(signals) * 0.1)
        # Stronger if extreme metrics
        if m["vol_compression"] < 0.5 or m["vol_compression"] > 2.0:
            base += 0.15
        if m["bb_width_pct"] < 15 or m["bb_width_pct"] > 85:
            base += 0.10
        if m["momentum_consistency"] > 0.75 or m["momentum_consistency"] < 0.25:
            base += 0.10
        return min(0.95, base)


# ═══════════════════════════════════════════════════════════════════════
# Formatting helper for display
# ═══════════════════════════════════════════════════════════════════════

def format_movement_regime_markdown(reg: MovementRegime) -> str:
    """Format MovementRegime as markdown."""
    if not reg:
        return ""

    emoji_map = {
        "DIRECT_TREND": "🚀",
        "VOLATILE_FIRST_THEN_TREND": "🌪️",
        "VOL_COMPRESSION_BREAKOUT": "⏳",
        "MEAN_REVERSION": "🔄",
        "VOL_EXPANSION": "💥",
        "GAMMA_PINNING": "📌",
    }
    emoji = emoji_map.get(reg.regime, "🎯")

    lines = []
    lines.append(f"### ⏱️ Movement Timing: {emoji} {reg.regime}")
    lines.append(f"**Confidence**: {reg.confidence*100:.0f}% · **Direction Bias**: {reg.direction_bias}")
    lines.append("")
    lines.append(f"**ACTION**: `{reg.action}`")
    lines.append(f"**Expected duration of regime**: ~{reg.expected_duration_days} days")
    lines.append("")
    lines.append(f"**Entry Tactic**: {reg.entry_tactic}")
    lines.append("")
    lines.append(f"- Sizing: {reg.sizing_guidance}")
    lines.append(f"- Stop management: {reg.stop_management}")
    lines.append("")
    lines.append("**Pattern signals detected**:")
    for sig in reg.pattern_signals:
        lines.append(f"- {sig}")
    lines.append("")
    lines.append(f"**Underlying metrics**:")
    lines.append(f"- Realized vol 21d: {reg.realized_vol_pct:.1f}%")
    lines.append(f"- Vol compression ratio: {reg.vol_compression_ratio:.2f}")
    lines.append(f"- BB width percentile: {reg.bb_width_percentile:.0f}th")
    lines.append(f"- Momentum consistency: {reg.momentum_consistency*100:.0f}%")
    lines.append(f"- Gamma regime: {reg.gamma_proxy_regime}")
    return "\n".join(lines)


__all__ = [
    "MovementTimingDetector",
    "MovementRegime",
    "format_movement_regime_markdown",
]
