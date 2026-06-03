"""engines/daily_play_engine.py — v38

DAILY PLAYS untuk scalping + short swing (1-5 days holding).

Edward's ask: "Daily play mau itu long/short/buy untuk jangka pendek yang bisa
generate money, boleh scalping atau swing pendek."

7 Setup Types:
  1. GAP_AND_GO          — Open gap + momentum continuation (intraday-1d)
  2. GAP_FILL            — Open gap fades back (intraday)
  3. SQUEEZE_SETUP       — Low float + RR bullish + composite LONG (2-5d)
  4. MEAN_REVERT_FADE    — Overextended at Trade extreme (1-3d)
  5. RANGE_BREAK         — Tight consolidation breaks (2-5d)
  6. GAMMA_FLIP_PLAY     — Markov regime shift + trend (2-5d)
  7. MOMENTUM_PULLBACK   — Strong trend + healthy pullback to entry (1-3d)

Output per setup:
  - Direction (LONG/SHORT) with entry/target/stop + R:R
  - Time horizon (intraday / 1-2d / 3-5d)
  - Confidence score
  - Position size guidance
  - Setup-specific reasoning

Cross-market: works on US stocks, IHSG (LONG only), crypto, forex.
Filter: only outputs setups with R:R >= 1.8 and confidence >= 60%.
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
# DATACLASS
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class DailyPlay:
    """A single daily play setup."""
    ticker: str
    setup_type: str            # GAP_AND_GO / SQUEEZE_SETUP / etc
    direction: str             # LONG / SHORT
    horizon: str               # intraday / 1-2d / 3-5d
    
    entry: float
    target_1: float
    target_2: float
    stop: float
    risk_reward: float
    
    confidence: float          # 0-100
    sizing_pct: float          # recommended position size %
    
    reasoning: List[str]       # why this setup fires
    invalidation: str          # what kills the setup
    execution_notes: str       # specific entry tactic


# ═══════════════════════════════════════════════════════════════════════
# DAILY PLAY DETECTOR
# ═══════════════════════════════════════════════════════════════════════

class DailyPlayEngine:
    """Scan for daily/short-swing setups."""

    def __init__(self, market: str = "us_stocks"):
        self.market = market
        self.allow_short = market != "ihsg"   # IHSG long-only retail
        self.min_rr = 1.8
        self.min_confidence = 60

    # ── Master scanner ────────────────────────────────────────────────

    def scan_ticker(self, ticker: str, prices: pd.Series,
                     snap: Optional[Dict] = None) -> List[DailyPlay]:
        """Scan a ticker through all setup detectors. Return matching plays."""
        s = pd.to_numeric(prices, errors="coerce").dropna()
        if len(s) < 30:
            return []

        snap = snap or {}
        plays = []

        try:
            # Compute base metrics once
            metrics = self._compute_base_metrics(s)
            context = self._extract_context(ticker, snap)

            # Run each setup detector
            for detector in (
                self._detect_gap_and_go,
                self._detect_gap_fill,
                self._detect_squeeze_setup,
                self._detect_mean_revert_fade,
                self._detect_range_break,
                self._detect_gamma_flip_play,
                self._detect_momentum_pullback,
            ):
                try:
                    play = detector(ticker, s, metrics, context)
                    if play and self._passes_filter(play):
                        plays.append(play)
                except Exception as e:
                    logger.debug(f"{detector.__name__} failed for {ticker}: {e}")
        except Exception as e:
            logger.debug(f"scan_ticker outer failed for {ticker}: {e}")

        return plays

    def scan_universe(self, universe: List[str], snap: Dict,
                       prices: Dict) -> List[DailyPlay]:
        """Scan all tickers and return sorted by confidence."""
        all_plays = []
        for ticker in universe:
            p = prices.get(ticker)
            if p is None:
                continue
            plays = self.scan_ticker(ticker, p, snap)
            all_plays.extend(plays)
        # Sort by R:R * confidence (highest first)
        all_plays.sort(key=lambda x: x.risk_reward * x.confidence, reverse=True)
        return all_plays

    def _passes_filter(self, play: DailyPlay) -> bool:
        """Strict filter — Edward 'ga asal2an'."""
        if play.risk_reward < self.min_rr:
            return False
        if play.confidence < self.min_confidence:
            return False
        if play.direction == "SHORT" and not self.allow_short:
            return False
        return True

    # ── Base metrics ──────────────────────────────────────────────────

    def _compute_base_metrics(self, s: pd.Series) -> Dict:
        """Pre-compute price/vol metrics."""
        returns = s.pct_change().dropna()
        current = float(s.iloc[-1])
        prior_close = float(s.iloc[-2]) if len(s) >= 2 else current

        # ATR proxy (mean abs return × price)
        atr_14 = float(returns.tail(14).abs().mean() * current) if len(returns) >= 14 else current * 0.02

        # Recent range
        high_15 = float(s.tail(15).max())
        low_15 = float(s.tail(15).min())
        mid_15 = (high_15 + low_15) / 2

        # Vol metrics
        vol_5 = float(returns.tail(5).std()) if len(returns) >= 5 else 0
        vol_20 = float(returns.tail(20).std()) if len(returns) >= 20 else vol_5

        # Momentum
        ret_5d = float(s.iloc[-1] / s.iloc[-6] - 1) if len(s) >= 6 else 0
        ret_20d = float(s.iloc[-1] / s.iloc[-21] - 1) if len(s) >= 21 else 0

        # SMA
        sma_20 = float(s.tail(20).mean())
        sma_5 = float(s.tail(5).mean())

        # Gap (today's open vs prior close — proxy via last 2 closes if no OHLC)
        gap_pct = float((current / prior_close - 1)) if prior_close > 0 else 0

        # Range compression
        range_15_pct = (high_15 - low_15) / mid_15 if mid_15 > 0 else 0

        return {
            "current": current,
            "prior_close": prior_close,
            "atr_14": atr_14,
            "high_15": high_15,
            "low_15": low_15,
            "mid_15": mid_15,
            "vol_5": vol_5,
            "vol_20": vol_20,
            "vol_compression": vol_5 / max(vol_20, 0.001),
            "ret_5d": ret_5d,
            "ret_20d": ret_20d,
            "sma_20": sma_20,
            "sma_5": sma_5,
            "gap_pct": gap_pct,
            "range_15_pct": range_15_pct,
        }

    def _extract_context(self, ticker: str, snap: Dict) -> Dict:
        """Extract Risk Range + composite signals from snap."""
        rr_all = (snap.get("risk_ranges", {}) or {}).get("asset_ranges", {})
        rr = rr_all.get(ticker, {})
        composite = (snap.get("composite_signals", {}) or {}).get(ticker, {})
        markov = (snap.get("markov_v3", {}) or {})
        markov_per = markov.get("per_ticker", {}).get(ticker, {}) if isinstance(markov, dict) else {}
        gamma = (snap.get("gamma_data", {}) or {}).get(ticker, {})

        return {
            "rr_ok": rr.get("ok", False),
            "rr_quality": rr.get("quality", "C"),
            "rr_formation": rr.get("composite", ""),
            "rr_trade_low": rr.get("trade_low", 0),
            "rr_trade_high": rr.get("trade_high", 0),
            "rr_trend_line": rr.get("trend_line", 0),
            "rr_tail_line": rr.get("tail_line", 0),
            "composite_dir": composite.get("direction", "NEUTRAL"),
            "composite_conf": composite.get("confidence", 0),
            "markov_regime": markov_per.get("current_regime", "UNKNOWN") if markov_per else "UNKNOWN",
            "markov_transition_prob": markov_per.get("transition_probability", 0) if markov_per else 0,
            "gamma_regime": gamma.get("regime", "UNKNOWN") if isinstance(gamma, dict) else "UNKNOWN",
        }

    # ── Setup 1: GAP_AND_GO ───────────────────────────────────────────

    def _detect_gap_and_go(self, ticker: str, s: pd.Series, m: Dict,
                            ctx: Dict) -> Optional[DailyPlay]:
        """Open gap with momentum continuation."""
        gap = m["gap_pct"]
        if abs(gap) < 0.025:   # need >=2.5% gap
            return None
        # Gap and HOLD (current near top of recent range if up gap)
        if gap > 0:
            # Up gap continuation
            if m["current"] < m["high_15"] * 0.97:
                return None
            if ctx.get("composite_dir") not in ("LONG", "NEUTRAL"):
                return None
            direction = "LONG"
            entry = m["current"] - m["atr_14"] * 0.3  # pull back slightly
            target_1 = m["current"] + m["atr_14"] * 1.5
            target_2 = m["current"] + m["atr_14"] * 2.5
            stop = m["current"] - m["atr_14"] * 0.6
        else:
            if not self.allow_short:
                return None
            if m["current"] > m["low_15"] * 1.03:
                return None
            if ctx.get("composite_dir") == "LONG":
                return None
            direction = "SHORT"
            entry = m["current"] + m["atr_14"] * 0.3
            target_1 = m["current"] - m["atr_14"] * 1.5
            target_2 = m["current"] - m["atr_14"] * 2.5
            stop = m["current"] + m["atr_14"] * 0.6

        rr = abs(target_1 - entry) / max(abs(entry - stop), 0.001)
        confidence = 65 + min(15, abs(gap) * 200)

        reasoning = [
            f"Gap {gap:+.1%} with momentum continuation",
            f"Current price holding {'top' if gap>0 else 'bottom'} of 15-day range",
            f"Composite direction supports {direction}",
        ]

        return DailyPlay(
            ticker=ticker, setup_type="GAP_AND_GO", direction=direction,
            horizon="intraday-1d",
            entry=round(entry, 2), target_1=round(target_1, 2),
            target_2=round(target_2, 2), stop=round(stop, 2),
            risk_reward=round(rr, 2),
            confidence=round(confidence, 0), sizing_pct=1.5,
            reasoning=reasoning,
            invalidation="Price closes back through prior close (gap fill triggered)",
            execution_notes="Enter on shallow pullback to entry. Scale out half at T1.",
        )

    # ── Setup 2: GAP_FILL ─────────────────────────────────────────────

    def _detect_gap_fill(self, ticker: str, s: pd.Series, m: Dict,
                          ctx: Dict) -> Optional[DailyPlay]:
        """Open gap that reverses back."""
        gap = m["gap_pct"]
        if abs(gap) < 0.03:
            return None
        # Reversal: gap up but composite SHORT bias OR very overextended
        if gap > 0:
            if not self.allow_short:
                return None
            # Look for distribution: vol expansion + can't hold high
            if m["vol_5"] / max(m["vol_20"], 0.001) < 1.4:
                return None
            if ctx.get("composite_dir") == "LONG" and ctx.get("composite_conf", 0) > 0.6:
                return None
            direction = "SHORT"
            entry = m["current"]
            target_1 = m["prior_close"]
            target_2 = m["prior_close"] - m["atr_14"] * 0.5
            stop = m["current"] + m["atr_14"] * 0.5
        else:
            if m["vol_5"] / max(m["vol_20"], 0.001) < 1.4:
                return None
            if ctx.get("composite_dir") == "SHORT" and ctx.get("composite_conf", 0) > 0.6:
                return None
            direction = "LONG"
            entry = m["current"]
            target_1 = m["prior_close"]
            target_2 = m["prior_close"] + m["atr_14"] * 0.5
            stop = m["current"] - m["atr_14"] * 0.5

        rr = abs(target_1 - entry) / max(abs(entry - stop), 0.001)
        confidence = 60 + min(15, m["vol_5"] / max(m["vol_20"], 0.001) * 5)

        return DailyPlay(
            ticker=ticker, setup_type="GAP_FILL", direction=direction,
            horizon="intraday",
            entry=round(entry, 2), target_1=round(target_1, 2),
            target_2=round(target_2, 2), stop=round(stop, 2),
            risk_reward=round(rr, 2),
            confidence=round(confidence, 0), sizing_pct=1.0,
            reasoning=[
                f"Gap {gap:+.1%} with vol expansion {m['vol_5']/max(m['vol_20'],0.001):.1f}x",
                "Volatility suggests gap rejection",
            ],
            invalidation="Gap holds and extends — exit at stop",
            execution_notes="Quick scalp. Exit fast at T1, don't be greedy.",
        )

    # ── Setup 3: SQUEEZE_SETUP ────────────────────────────────────────

    def _detect_squeeze_setup(self, ticker: str, s: pd.Series, m: Dict,
                               ctx: Dict) -> Optional[DailyPlay]:
        """High vol compression + RR bullish + composite LONG = squeeze ready."""
        if m["vol_compression"] > 0.65:
            return None  # need compression
        if m["range_15_pct"] > 0.08:
            return None
        if ctx.get("rr_formation") != "bullish":
            return None
        if ctx.get("composite_dir") != "LONG":
            return None
        if ctx.get("rr_quality") not in ("A+", "A", "B"):
            return None

        direction = "LONG"
        breakout_level = m["high_15"] * 1.01
        entry = breakout_level
        target_1 = entry + m["atr_14"] * 2.0
        target_2 = entry + m["atr_14"] * 3.5
        stop = m["sma_20"]

        rr = (target_1 - entry) / max(entry - stop, 0.001)
        confidence = 70
        if ctx.get("rr_quality") == "A+":
            confidence += 10
        if ctx.get("composite_conf", 0) > 0.7:
            confidence += 5

        return DailyPlay(
            ticker=ticker, setup_type="SQUEEZE_SETUP", direction=direction,
            horizon="2-5d",
            entry=round(entry, 2), target_1=round(target_1, 2),
            target_2=round(target_2, 2), stop=round(stop, 2),
            risk_reward=round(rr, 2),
            confidence=round(confidence, 0), sizing_pct=2.0,
            reasoning=[
                f"Vol compressed {(1-m['vol_compression']):.0%}",
                f"Range tight: {m['range_15_pct']:.1%} over 15 days",
                f"RR Bullish formation, quality {ctx.get('rr_quality')}",
                f"Composite LONG confidence {ctx.get('composite_conf',0):.0%}",
            ],
            invalidation="Breakout fails, price closes back below SMA20",
            execution_notes=f"Enter on confirmed break above {breakout_level:.2f} with volume. Trail stop to break-even after T1.",
        )

    # ── Setup 4: MEAN_REVERT_FADE ─────────────────────────────────────

    def _detect_mean_revert_fade(self, ticker: str, s: pd.Series, m: Dict,
                                   ctx: Dict) -> Optional[DailyPlay]:
        """Price at Trade extreme + overextended = fade."""
        if not ctx.get("rr_ok"):
            return None
        trade_low = ctx.get("rr_trade_low", 0)
        trade_high = ctx.get("rr_trade_high", 0)
        if trade_low <= 0 or trade_high <= 0:
            return None

        # At Trade HIGH = SHORT fade
        if m["current"] >= trade_high * 0.995 and m["ret_5d"] > 0.05:
            if not self.allow_short:
                return None
            direction = "SHORT"
            entry = m["current"]
            target_1 = (trade_high + trade_low) / 2
            target_2 = trade_low + (trade_high - trade_low) * 0.3
            stop = trade_high + m["atr_14"] * 0.5
        # At Trade LOW = LONG fade
        elif m["current"] <= trade_low * 1.005 and m["ret_5d"] < -0.05:
            direction = "LONG"
            entry = m["current"]
            target_1 = (trade_high + trade_low) / 2
            target_2 = trade_low + (trade_high - trade_low) * 0.7
            stop = trade_low - m["atr_14"] * 0.5
        else:
            return None

        rr = abs(target_1 - entry) / max(abs(entry - stop), 0.001)
        confidence = 65 + min(10, abs(m["ret_5d"]) * 100)

        return DailyPlay(
            ticker=ticker, setup_type="MEAN_REVERT_FADE", direction=direction,
            horizon="1-3d",
            entry=round(entry, 2), target_1=round(target_1, 2),
            target_2=round(target_2, 2), stop=round(stop, 2),
            risk_reward=round(rr, 2),
            confidence=round(confidence, 0), sizing_pct=1.0,
            reasoning=[
                f"Price at Trade {('High' if direction=='SHORT' else 'Low')} extreme",
                f"5-day move {m['ret_5d']:+.1%} = overextended",
                "Mean reversion probability elevated at boundary",
            ],
            invalidation=f"Trade {('High' if direction=='SHORT' else 'Low')} breaks decisively",
            execution_notes="Quick fade. Exit half at T1, trail for T2.",
        )

    # ── Setup 5: RANGE_BREAK ──────────────────────────────────────────

    def _detect_range_break(self, ticker: str, s: pd.Series, m: Dict,
                              ctx: Dict) -> Optional[DailyPlay]:
        """Tight consolidation + composite directional = breakout play."""
        if m["range_15_pct"] > 0.06:
            return None   # not tight enough
        composite_dir = ctx.get("composite_dir", "NEUTRAL")
        if composite_dir == "NEUTRAL":
            return None
        if composite_dir == "SHORT" and not self.allow_short:
            return None

        direction = composite_dir
        if direction == "LONG":
            entry = m["high_15"] * 1.005
            target_1 = entry + m["atr_14"] * 2.0
            target_2 = entry + m["atr_14"] * 3.5
            stop = m["mid_15"]
        else:
            entry = m["low_15"] * 0.995
            target_1 = entry - m["atr_14"] * 2.0
            target_2 = entry - m["atr_14"] * 3.5
            stop = m["mid_15"]

        rr = abs(target_1 - entry) / max(abs(entry - stop), 0.001)
        confidence = 65 + min(15, (0.06 - m["range_15_pct"]) * 200)

        return DailyPlay(
            ticker=ticker, setup_type="RANGE_BREAK", direction=direction,
            horizon="2-5d",
            entry=round(entry, 2), target_1=round(target_1, 2),
            target_2=round(target_2, 2), stop=round(stop, 2),
            risk_reward=round(rr, 2),
            confidence=round(confidence, 0), sizing_pct=1.5,
            reasoning=[
                f"Tight 15-day range: {m['range_15_pct']:.1%}",
                f"Composite signals {direction} bias",
                "Range break setup ready",
            ],
            invalidation=f"Breakout fails, returns to range midpoint",
            execution_notes=f"Enter on confirmed break at {entry:.2f} with volume expansion.",
        )

    # ── Setup 6: GAMMA_FLIP_PLAY ──────────────────────────────────────

    def _detect_gamma_flip_play(self, ticker: str, s: pd.Series, m: Dict,
                                  ctx: Dict) -> Optional[DailyPlay]:
        """Markov regime change + trend setup."""
        markov_regime = ctx.get("markov_regime", "UNKNOWN")
        transition_prob = ctx.get("markov_transition_prob", 0)
        if transition_prob < 0.35:
            return None
        if markov_regime == "UNKNOWN":
            return None

        # Map regime to direction
        if "BULL" in markov_regime or "TREND_UP" in markov_regime:
            direction = "LONG"
        elif "BEAR" in markov_regime or "TREND_DOWN" in markov_regime:
            if not self.allow_short:
                return None
            direction = "SHORT"
        else:
            return None

        if direction == "LONG":
            entry = m["current"]
            target_1 = entry + m["atr_14"] * 1.5
            target_2 = entry + m["atr_14"] * 3.0
            stop = entry - m["atr_14"] * 0.8
        else:
            entry = m["current"]
            target_1 = entry - m["atr_14"] * 1.5
            target_2 = entry - m["atr_14"] * 3.0
            stop = entry + m["atr_14"] * 0.8

        rr = abs(target_1 - entry) / max(abs(entry - stop), 0.001)
        confidence = 60 + min(20, transition_prob * 40)

        return DailyPlay(
            ticker=ticker, setup_type="GAMMA_FLIP_PLAY", direction=direction,
            horizon="2-5d",
            entry=round(entry, 2), target_1=round(target_1, 2),
            target_2=round(target_2, 2), stop=round(stop, 2),
            risk_reward=round(rr, 2),
            confidence=round(confidence, 0), sizing_pct=1.5,
            reasoning=[
                f"Markov regime: {markov_regime}",
                f"Transition probability: {transition_prob:.0%}",
                f"Direction aligned with new regime: {direction}",
            ],
            invalidation="Markov regime reverses within 3 days",
            execution_notes="Enter on regime confirmation. Trail tight after T1.",
        )

    # ── Setup 7: MOMENTUM_PULLBACK ────────────────────────────────────

    def _detect_momentum_pullback(self, ticker: str, s: pd.Series, m: Dict,
                                    ctx: Dict) -> Optional[DailyPlay]:
        """Strong trend + healthy pullback = continuation entry."""
        # Need strong 20-day trend
        if abs(m["ret_20d"]) < 0.10:
            return None
        # Recent pullback against trend
        if m["ret_20d"] > 0:
            # Uptrend, want pullback (5d negative or flat)
            if m["ret_5d"] > 0.02:
                return None
            if m["current"] < m["sma_20"] * 0.95:
                return None  # gone too deep
            direction = "LONG"
            entry = m["current"]
            target_1 = entry + m["atr_14"] * 2.0
            target_2 = entry + m["atr_14"] * 4.0
            stop = max(m["sma_20"] * 0.97, entry - m["atr_14"] * 1.2)
        else:
            if not self.allow_short:
                return None
            if m["ret_5d"] < -0.02:
                return None
            if m["current"] > m["sma_20"] * 1.05:
                return None
            direction = "SHORT"
            entry = m["current"]
            target_1 = entry - m["atr_14"] * 2.0
            target_2 = entry - m["atr_14"] * 4.0
            stop = min(m["sma_20"] * 1.03, entry + m["atr_14"] * 1.2)

        rr = abs(target_1 - entry) / max(abs(entry - stop), 0.001)
        if rr < 1.8:
            return None
        confidence = 65 + min(15, abs(m["ret_20d"]) * 50)

        return DailyPlay(
            ticker=ticker, setup_type="MOMENTUM_PULLBACK", direction=direction,
            horizon="1-3d",
            entry=round(entry, 2), target_1=round(target_1, 2),
            target_2=round(target_2, 2), stop=round(stop, 2),
            risk_reward=round(rr, 2),
            confidence=round(confidence, 0), sizing_pct=1.5,
            reasoning=[
                f"Strong 20d trend: {m['ret_20d']:+.1%}",
                f"Healthy pullback: 5d {m['ret_5d']:+.1%}",
                f"Near SMA20 support — continuation setup",
            ],
            invalidation="SMA20 breaks (trend invalidated)",
            execution_notes="Enter on confirmation bar (close back in trend direction).",
        )


# ═══════════════════════════════════════════════════════════════════════
# Formatting helper
# ═══════════════════════════════════════════════════════════════════════

def format_daily_play_markdown(play: DailyPlay) -> str:
    """Format daily play as markdown for display."""
    if not play:
        return ""
    emoji = {"LONG": "🟢", "SHORT": "🔴"}.get(play.direction, "⚪")
    lines = []
    lines.append(f"### {emoji} {play.ticker} · {play.setup_type} · {play.direction}")
    lines.append(f"**Horizon**: {play.horizon} · **Confidence**: {play.confidence:.0f}% · **R:R**: {play.risk_reward:.2f}")
    lines.append("")
    lines.append(f"- **Entry**: ${play.entry:.2f}")
    lines.append(f"- **Target 1**: ${play.target_1:.2f} (close 50%)")
    lines.append(f"- **Target 2**: ${play.target_2:.2f} (full close)")
    lines.append(f"- **Stop**: ${play.stop:.2f}")
    lines.append(f"- **Size**: {play.sizing_pct:.1f}% portfolio")
    lines.append("")
    lines.append("**Why this setup**:")
    for r in play.reasoning:
        lines.append(f"- {r}")
    lines.append("")
    lines.append(f"**Execution**: {play.execution_notes}")
    lines.append(f"**Invalidation**: {play.invalidation}")
    return "\n".join(lines)


__all__ = [
    "DailyPlayEngine",
    "DailyPlay",
    "format_daily_play_markdown",
]
