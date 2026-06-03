"""engines/frontrun_engine.py — Front-Run Watchlist Engine

The single source of truth for: "What do I buy/short RIGHT NOW, and at what price?"

Aggregates signals from ALL engines into one ranked watchlist:
  1. RegimeTransitionEngine  → macro timing (front_run_window)
  2. BottleneckEngine        → structural scarcity (Level 1/2 at BUY ZONE)
  3. HurstRREngine           → Risk Range (Quality A near LRR)
  4. DiscoveryOrchestrator   → proactive chain (ETA weeks)
  5. NarrativeEngine         → ignition detection

STATUS LABELS (like a flight board):
  🚨 BOARDING NOW    → All signals converge. Entry zone active. Act within 1-3 days.
  ⚡ GATE OPENS SOON → 2-3 signals align. Entry imminent within 1-2 weeks.
  👀 CHECK-IN        → 1 strong signal. Watch for confirmation. 3-6 weeks.
  ⏳ WAIT            → Not ready. Monitor only.

COMPOSITE SCORE formula:
  score = (timing_w × timing_score) + (btk_w × btk_score)
        + (rr_w × rr_score) + (disc_w × disc_score) + (narr_w × narr_score)
  Weights: timing=0.30, btk=0.25, rr=0.25, disc=0.10, narr=0.10

Coverage: US stocks, IHSG, Forex, Commodities, Crypto — all markets.
"""
from __future__ import annotations
import math
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import numpy as np
import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# DATACLASS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FrontRunCandidate:
    ticker: str
    market: str
    sector: str
    direction: str            # "long" | "short"
    status: str               # "BOARDING NOW" | "GATE OPENS SOON" | "CHECK-IN" | "WAIT"
    status_emoji: str
    composite_score: float    # 0.0 → 1.0
    confidence_pct: int       # 0 → 100

    # Entry geometry (from Risk Range + Bottleneck TP)
    entry_zone: Optional[float]   # LRR or current price if at support
    stop_loss: Optional[float]
    tp1: Optional[float]
    tp2: Optional[float]
    tp3: Optional[float]
    current_px: Optional[float]
    range_action: str             # "✅ BUY ZONE" | "⚠️ APPROACHING TRR" etc

    # Signal breakdown
    timing_score: float     # from RegimeTransitionEngine
    btk_score: float        # from BottleneckEngine
    rr_score: float         # from HurstRREngine
    disc_score: float       # from DiscoveryOrchestrator
    narr_score: float       # from NarrativeEngine

    # Context
    regime: str
    duration: str           # "TRADE (≤3wk)" | "TREND (≥3mo)" | "TAIL (≤3yr)"
    thesis: str
    catalyst: str
    risk: str
    narrative_tag: str
    source_signals: List[str] = field(default_factory=list)

    # For paper trader wiring
    ev: float = 0.0
    brewing_score: float = 0.0
    btk_level: str = ""
    rr_quality: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class FrontRunEngine:
    """
    Aggregates all engine outputs into a single ranked, actionable watchlist.
    One call. One list. One decision surface.
    """

    # Score weights — must sum to 1.0
    W_TIMING = 0.30   # Regime transition timing is the primary clock
    W_BTK    = 0.25   # Bottleneck = structural scarcity + TP levels
    W_RR     = 0.25   # Risk Range = price entry geometry
    W_DISC   = 0.10   # Discovery proactive = early lead
    W_NARR   = 0.10   # Narrative ignition = institutional crowding

    def run(
        self,
        snap: dict,
        max_candidates: int = 30,
    ) -> dict:
        """
        One-call aggregation. Pass the full snap dict from orchestrator.
        Returns ranked watchlist + metadata.
        """
        transition = snap.get("transition")
        btk        = snap.get("bottleneck", {})
        rr         = snap.get("risk_ranges", {})
        dv3        = snap.get("discovery_v3", {})
        narr       = snap.get("narratives", {})
        prices     = snap.get("prices", {})
        gip        = snap.get("gip")
        sq         = gip.structural_quad if gip else "Q3"
        mq         = gip.monthly_quad if gip else "Q3"

        # ── 1. Timing signal (macro clock) ────────────────────────────────────
        timing_global, timing_path = self._timing_signal(transition)

        # ── 2. Collect all candidate tickers across all markets ──────────────
        candidates_raw: Dict[str, dict] = {}

        # From Bottleneck (Level 1 + Level 2)
        for level_key in ("level_1", "level_2", "brewing"):
            for item in btk.get(level_key, []):
                t = item.get("ticker", "")
                if not t: continue
                if t not in candidates_raw:
                    candidates_raw[t] = {"btk": item, "rr": {}, "disc": {}, "narr_tag": ""}
                else:
                    candidates_raw[t]["btk"] = item

        # From Risk Range (Quality A + B)
        ar = rr.get("asset_ranges", {})
        for sym, v in ar.items():
            qual = v.get("quality", "none")
            comp = v.get("composite", "neutral")
            if qual in ("A", "B", "short_A", "short_B") or comp in ("bullish", "bearish"):
                if sym not in candidates_raw:
                    candidates_raw[sym] = {"btk": {}, "rr": v, "disc": {}, "narr_tag": ""}
                else:
                    candidates_raw[sym]["rr"] = v

        # From Discovery v3 (reactive + proactive)
        for item in dv3.get("reactive", []) + dv3.get("proactive", []):
            t = item.get("ticker", "")
            if not t: continue
            if t not in candidates_raw:
                candidates_raw[t] = {"btk": {}, "rr": {}, "disc": item, "narr_tag": ""}
            else:
                candidates_raw[t]["disc"] = item

        # ── 3. Narrative ignition map {sector → ignition_score} ───────────────
        narr_ignition = self._narr_ignition_map(narr)

        # ── 4. Score each candidate ───────────────────────────────────────────
        scored: List[FrontRunCandidate] = []
        for ticker, data in candidates_raw.items():
            try:
                candidate = self._score_candidate(
                    ticker=ticker,
                    data=data,
                    timing_global=timing_global,
                    timing_path=timing_path,
                    narr_ignition=narr_ignition,
                    prices=prices,
                    sq=sq,
                )
                if candidate is not None:
                    scored.append(candidate)
            except Exception:
                continue

        # ── 5. Sort by composite score descending ─────────────────────────────
        scored.sort(key=lambda c: c.composite_score, reverse=True)

        # ── 6. Separate long/short and filter by status ────────────────────────
        longs  = [c for c in scored if c.direction == "long"]
        shorts = [c for c in scored if c.direction == "short"]
        boarding = [c for c in scored if c.status == "BOARDING NOW"]
        gate     = [c for c in scored if c.status == "GATE OPENS SOON"]
        checkin  = [c for c in scored if c.status == "CHECK-IN"]

        # ── 7. Market breakdown ───────────────────────────────────────────────
        by_market: Dict[str, List[FrontRunCandidate]] = {}
        for c in scored:
            by_market.setdefault(c.market, []).append(c)

        return {
            "watchlist":     scored[:max_candidates],
            "longs":         longs[:20],
            "shorts":        shorts[:10],
            "boarding_now":  boarding[:10],
            "gate_soon":     gate[:15],
            "check_in":      checkin[:15],
            "by_market":     {k: v[:8] for k, v in by_market.items()},
            "timing_window": getattr(transition, "front_run_window", "not yet") if transition else "not yet",
            "timing_rationale": getattr(transition, "front_run_rationale", "") if transition else "",
            "timing_path":   timing_path,
            "regime":        sq,
            "monthly_quad":  mq,
            "total_candidates": len(scored),
            "meta": {
                "weights": {"timing": self.W_TIMING, "btk": self.W_BTK, "rr": self.W_RR,
                            "disc": self.W_DISC, "narr": self.W_NARR},
                "status_formula": "BOARDING: score≥0.65 + near entry | GATE: 0.45-0.65 | CHECK-IN: 0.30-0.45",
            },
        }

    # ─────────────────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    def _timing_signal(self, transition) -> Tuple[float, str]:
        """Convert front_run_window to a 0-1 timing score."""
        if transition is None:
            return 0.0, ""
        fw = getattr(transition, "front_run_window", "not yet")
        score_map = {"now": 1.0, "1-2w": 0.75, "3-6w": 0.45, "not yet": 0.15}
        paths = getattr(transition, "transition_paths", [])
        path_str = f"{paths[0].from_quad}→{paths[0].to_quad}" if paths else ""
        return score_map.get(fw, 0.15), path_str

    def _narr_ignition_map(self, narr: dict) -> Dict[str, float]:
        """Map sector → narrative ignition score."""
        result: Dict[str, float] = {}
        nd = narr.get("narrative_dashboard", [])
        for n in nd:
            strength = n.get("current_strength", 0.0)
            igniting = n.get("ignition", False)
            score = min(1.0, strength * (1.5 if igniting else 1.0))
            lead_sector = n.get("lead_sector", "")
            if lead_sector:
                result[lead_sector] = max(result.get(lead_sector, 0.0), score)
            # Also map narrative name to sectors in its definition
            narr_name = n.get("narrative", "")
            result[narr_name] = max(result.get(narr_name, 0.0), score)
        ign_det = narr.get("ignition_details", {})
        for name, det in ign_det.items():
            if det.get("ignition"):
                result[det.get("lead_sector", "")] = max(result.get(det.get("lead_sector",""), 0.0), 0.9)
        return result

    def _btk_score_item(self, btk_item: dict) -> Tuple[float, str, str, float]:
        """Returns (score, level, range_action, ev)."""
        if not btk_item:
            return 0.0, "", "—", 0.0
        level = btk_item.get("level", "")
        ev = float(btk_item.get("ev", 0.0))
        regime_fit = float(btk_item.get("regime_fit", 0.5))
        constraint = float(btk_item.get("constraint", 0.5))
        range_action = btk_item.get("range_action", "—")
        trend = btk_item.get("trend", "range")

        level_score = {"level_1": 1.0, "level_2": 0.75, "watch": 0.50, "avoid": 0.10, "brewing": 0.55}.get(level, 0.30)
        action_mult = 1.20 if "BUY" in range_action else 0.75 if "TRIM" in range_action else 1.0
        trend_mult = 1.10 if trend == "uptrend" else 0.85 if trend == "downtrend" else 1.0

        score = float(np.clip(level_score * action_mult * trend_mult * (0.5 + 0.5 * regime_fit), 0.0, 1.0))
        return score, level, range_action, ev

    def _rr_score_item(self, rr_item: dict) -> Tuple[float, str, float, float, float, float, float]:
        """Returns (score, quality, px, lrr, trr, trend_lrr, trend_trr)."""
        if not rr_item:
            return 0.0, "none", float("nan"), float("nan"), float("nan"), float("nan"), float("nan")
        qual = rr_item.get("quality", "none")
        comp = rr_item.get("composite", "neutral")
        stretch = rr_item.get("trade_stretch", "neutral")
        vol_c = rr_item.get("volume_confirm", 0.5)

        qual_score = {"A": 1.0, "B": 0.70, "C": 0.35, "short_A": 1.0, "short_B": 0.70, "none": 0.20}.get(qual, 0.20)
        comp_mult = 1.0 if comp in ("bullish", "bearish") else 0.5
        stretch_mult = 1.20 if stretch in ("oversold", "reset_zone", "overbought", "extended") else 1.0
        vol_mult = 1.0 + 0.15 * max(0, vol_c - 0.5)

        score = float(np.clip(qual_score * comp_mult * stretch_mult * vol_mult, 0.0, 1.0))
        px = rr_item.get("px", float("nan"))
        lrr = rr_item.get("trade_lrr", float("nan"))
        trr = rr_item.get("trade_trr", float("nan"))
        tlrr = rr_item.get("trend_lrr", float("nan"))
        ttrr = rr_item.get("trend_trr", float("nan"))
        return score, qual, px, lrr, trr, tlrr, ttrr

    def _disc_score_item(self, disc_item: dict) -> float:
        if not disc_item:
            return 0.0
        brewing = float(disc_item.get("brewing_score", 0.0))
        ev = float(disc_item.get("ev", 0.0))
        eta = disc_item.get("proactive_eta_weeks")
        eta_mult = 1.20 if eta and int(eta) <= 6 else 0.90 if eta and int(eta) <= 12 else 0.70
        return float(np.clip((brewing * 0.6 + min(ev, 1.0) * 0.4) * eta_mult, 0.0, 1.0))

    def _entry_geometry(
        self,
        px: float,
        lrr: float,
        trr: float,
        tlrr: float,
        ttrr: float,
        btk_tp: dict,
        direction: str,
    ) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float], Optional[float]]:
        """Returns (entry_zone, stop, tp1, tp2, tp3)."""
        def _v(x):
            return float(x) if x and math.isfinite(float(x)) else None

        # Entry zone: LRR (buy zone) for longs, TRR for shorts
        entry = _v(lrr) if direction == "long" else _v(trr)

        # Stop: Trend LRR break = EXIT for longs; Trend TRR break for shorts
        stop = _v(tlrr) if direction == "long" else _v(ttrr)

        # TPs from bottleneck TP or Risk Range TRR
        tp_data = btk_tp or {}
        tp1 = _v(tp_data.get("t1")) or _v(trr)
        tp2 = _v(tp_data.get("t2")) or _v(ttrr)
        tp3 = _v(tp_data.get("t3"))

        # Fallback: use price-based estimates if no data
        if entry is None and _v(px):
            entry = _v(px)  # current price as fallback
        if stop is None and _v(px) and direction == "long":
            stop = _v(px) * 0.92 if _v(px) else None

        return entry, stop, tp1, tp2, tp3

    def _score_candidate(
        self,
        ticker: str,
        data: dict,
        timing_global: float,
        timing_path: str,
        narr_ignition: Dict[str, float],
        prices: dict,
        sq: str,
    ) -> Optional[FrontRunCandidate]:
        btk_item = data.get("btk", {})
        rr_item  = data.get("rr", {})
        disc_item= data.get("disc", {})

        # Skip generic/benchmark tickers
        sector = btk_item.get("sector", rr_item.get("sector", "generic"))
        market = btk_item.get("market", "us_equity")
        if sector == "generic" and not btk_item and not disc_item:
            return None

        # Direction
        btk_dir = btk_item.get("direction", "neutral")
        rr_comp = rr_item.get("composite", "neutral")
        if btk_dir in ("long", "avoid_long") or rr_comp == "bullish":
            direction = "long"
        elif btk_dir in ("short", "avoid_short") or rr_comp == "bearish":
            direction = "short"
        else:
            direction = "long"  # default assumption

        # Sub-scores
        btk_score, btk_level, range_action, ev = self._btk_score_item(btk_item)
        rr_score, rr_qual, px, lrr, trr, tlrr, ttrr = self._rr_score_item(rr_item)
        disc_score = self._disc_score_item(disc_item)

        # Narrative score
        narr_score = narr_ignition.get(sector, narr_ignition.get(
            disc_item.get("narrative_tag", ""), 0.0))

        # Current price from prices dict if not in RR
        if not math.isfinite(px if px else float("nan")):
            s = prices.get(ticker)
            if s is not None:
                s = pd.to_numeric(s, errors="coerce").dropna()
                px = float(s.iloc[-1]) if not s.empty else float("nan")

        # Timing relevance: does this asset class benefit from the current transition?
        # timing_global is universal but we apply market-specific adjustment
        timing_adj = self._timing_market_adj(market, timing_path, sq)
        timing_score = timing_global * timing_adj

        # Composite
        composite = (
            self.W_TIMING * timing_score +
            self.W_BTK    * btk_score +
            self.W_RR     * rr_score +
            self.W_DISC   * disc_score +
            self.W_NARR   * narr_score
        )
        composite = float(np.clip(composite, 0.0, 1.0))

        # Status
        near_entry = range_action in ("✅ BUY ZONE", "approaching_support") or \
                     rr_item.get("trade_stretch", "") in ("oversold", "reset_zone")

        if composite >= 0.65 and near_entry:
            status, emoji = "BOARDING NOW", "🚨"
        elif composite >= 0.65 and not near_entry:
            status, emoji = "GATE OPENS SOON", "⚡"
        elif composite >= 0.45:
            status, emoji = "GATE OPENS SOON" if near_entry else "CHECK-IN", "⚡" if near_entry else "👀"
        elif composite >= 0.30:
            status, emoji = "CHECK-IN", "👀"
        else:
            status, emoji = "WAIT", "⏳"

        # Duration
        if btk_level in ("level_1",) or rr_qual in ("A", "short_A"):
            duration = "TRADE (≤3wk)"
        elif btk_level in ("level_2",) or rr_qual in ("B", "short_B"):
            duration = "TREND (≥3mo)"
        elif disc_item.get("proactive_eta_weeks"):
            eta = disc_item.get("proactive_eta_weeks", 12)
            duration = f"TREND (ETA {eta}wk)"
        else:
            duration = "TREND (≥3mo)"

        # Entry geometry
        btk_tp = btk_item.get("tp", {})
        entry, stop, tp1, tp2, tp3 = self._entry_geometry(px, lrr, trr, tlrr, ttrr, btk_tp, direction)

        # Thesis + context
        thesis   = btk_item.get("thesis") or btk_item.get("known_thesis") or disc_item.get("narrative", f"{sector} | {market}")
        catalyst = btk_item.get("catalyst") or btk_item.get("known_catalyst") or ""
        risk     = btk_item.get("risk") or btk_item.get("known_risk") or ""

        # Source signals
        sources = []
        if btk_item: sources.append(f"BTK:{btk_level or 'watch'}")
        if rr_qual != "none": sources.append(f"RR:{rr_qual}")
        if disc_item: sources.append(f"DISC:{disc_item.get('discovery_mode','reactive')[:5]}")
        if narr_score > 0.4: sources.append(f"NARR:{narr_score:.0%}")
        if timing_score > 0.4: sources.append(f"TIMING:{timing_global:.0%}")

        brewing_score = float(disc_item.get("brewing_score", btk_score * 0.8))

        return FrontRunCandidate(
            ticker=ticker, market=market, sector=sector, direction=direction,
            status=status, status_emoji=emoji, composite_score=round(composite, 3),
            confidence_pct=int(composite * 100),
            entry_zone=round(entry, 4) if entry else None,
            stop_loss=round(stop, 4) if stop else None,
            tp1=round(tp1, 4) if tp1 else None,
            tp2=round(tp2, 4) if tp2 else None,
            tp3=round(tp3, 4) if tp3 else None,
            current_px=round(px, 4) if px and math.isfinite(px) else None,
            range_action=range_action,
            timing_score=round(timing_score, 3), btk_score=round(btk_score, 3),
            rr_score=round(rr_score, 3), disc_score=round(disc_score, 3),
            narr_score=round(narr_score, 3),
            regime=sq, duration=duration,
            thesis=str(thesis)[:120], catalyst=str(catalyst)[:80], risk=str(risk)[:80],
            narrative_tag=disc_item.get("narrative_tag", ""),
            source_signals=sources,
            ev=round(ev, 3), brewing_score=round(brewing_score, 3),
            btk_level=btk_level, rr_quality=rr_qual,
        )

    def _timing_market_adj(self, market: str, timing_path: str, sq: str) -> float:
        """
        Adjust timing score by whether THIS market benefits from the transition.
        E.g. Q3→Q2 = commodity markets get bigger timing boost.
        """
        if not timing_path or "→" not in timing_path:
            return 1.0
        to_q = timing_path.split("→")[1] if "→" in timing_path else sq
        # Q→Q2 = commodities + FX commodity exporters benefit most
        if to_q == "Q2":
            return {"commodity": 1.30, "forex": 1.20, "ihsg": 1.10, "us_equity": 0.90, "crypto": 0.95, "bonds": 0.70}.get(market, 1.0)
        # Q→Q1 = equities + crypto + EM max recovery
        if to_q == "Q1":
            return {"us_equity": 1.30, "crypto": 1.25, "ihsg": 1.20, "commodity": 0.90, "forex": 1.0, "bonds": 0.80}.get(market, 1.0)
        # Q→Q4 = bonds + USD + defensive
        if to_q == "Q4":
            return {"bonds": 1.30, "forex": 1.10, "us_equity": 0.70, "commodity": 0.60, "crypto": 0.50, "ihsg": 0.60}.get(market, 1.0)
        # Q→Q3 = gold + defense + healthcare
        if to_q == "Q3":
            return {"commodity": 1.20, "us_equity": 0.80, "crypto": 0.60, "ihsg": 0.70, "forex": 0.90, "bonds": 1.10}.get(market, 1.0)
        return 1.0
