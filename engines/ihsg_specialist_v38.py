"""engines/ihsg_specialist_v38.py — v38

IHSG-specific intelligence:
  1. Konglomerasi mapping (20+ groups: Bakrie, Salim, Barito, Astra, Sinarmas,
     Lippo, CT Corp, Ciputra, MNC, Djarum, Adaro, Medco, etc)
  2. Cross-group flow detection (Bakrie + Salim alliance type signals)
  3. Goreng-menggoreng 4-phase pattern detector (Akumulasi → CorpAct → Liquidity → Euforia)
  4. Cornering detection (lock-up patterns, vol collapse + drift, gap release)
  5. Hedgeye Quad Indonesia cross-check (verify our model matches Keith's call)

Data source: data/ihsg_conglomerates.json (Edward updatable)

Honest disclosure:
  - Phase detection uses price/volume PROXIES (no real BEI broker summary)
  - For real broker concentration analysis, need BEI subscription
  - Foreign flow proxy via EIDO underperformance vs EEM
"""
from __future__ import annotations

import os
import json
import math
import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

IHSG_DATA_PATH = "data/ihsg_conglomerates.json"


# ═══════════════════════════════════════════════════════════════════════
# DATACLASSES
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class ConglomerateContext:
    """Context for a ticker within Indonesian conglomerate structure."""
    ticker: str
    group: str                   # bakrie, salim, etc
    patriarch: str
    sector_role: str             # coal, property, media, etc
    sister_tickers: List[str]    # other tickers in same group
    alliances: List[Dict]        # cross-group alliances active
    broker_affiliate: Optional[str]


@dataclass
class GorengPhase:
    """Goreng-menggoreng phase classification."""
    ticker: str
    current_phase: str           # PHASE_1_AKUMULASI / PHASE_2_CORP_ACTION / PHASE_3_LIQUIDITAS / PHASE_4_EUFORIA / UNCLEAR
    confidence: float
    signals_detected: List[str]
    action: str                  # ACCUMULATE / RIDE / DISTRIBUTE_HALF / EXIT / AVOID
    estimated_phase_duration_remaining: str
    risk_warnings: List[str]


@dataclass
class IHSGQuadCheck:
    """Hedgeye Quad cross-check for Indonesia."""
    our_estimate: str            # Q1 / Q2 / Q3 / Q4 / TRANSITION
    hedgeye_call: str            # What Hedgeye publicly says
    match: bool
    cross_validation_signals: Dict[str, bool]  # signal_name → confirms our estimate
    confidence: float
    recommendation: str


# ═══════════════════════════════════════════════════════════════════════
# IHSG SPECIALIST ENGINE
# ═══════════════════════════════════════════════════════════════════════

class IHSGSpecialistEngine:
    """Indonesia-specific intelligence for goreng + konglomerasi detection."""

    def __init__(self, data_path: str = IHSG_DATA_PATH):
        self.data_path = data_path
        self.data = self._load()
        self.conglomerates = self.data.get("conglomerates", {})
        self.alliances = self.data.get("alliances_and_signals", {})
        self._build_ticker_index()

    def _load(self) -> Dict:
        """Load conglomerates JSON."""
        paths_to_try = [self.data_path, "data/ihsg_conglomerates.json",
                       "ihsg_conglomerates.json"]
        for path in paths_to_try:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception as e:
                    logger.error(f"IHSG data load failed {path}: {e}")
        logger.warning(f"IHSG conglomerates JSON not found")
        return {"conglomerates": {}, "alliances_and_signals": {}}

    def _build_ticker_index(self):
        """Build ticker → conglomerate group mapping."""
        self.ticker_to_group = {}
        for group_id, group_data in self.conglomerates.items():
            for sector, tickers in group_data.get("tickers", {}).items():
                for ticker in tickers:
                    tu = ticker.upper()
                    self.ticker_to_group.setdefault(tu, []).append({
                        "group_id": group_id,
                        "group_data": group_data,
                        "sector_role": sector,
                    })

    # ── Conglomerate context lookup ──────────────────────────────────

    def get_conglomerate_context(self, ticker: str) -> Optional[ConglomerateContext]:
        """Get conglomerate context for a ticker. Handles .JK suffix transparently."""
        tu = ticker.upper()
        entries = self.ticker_to_group.get(tu, [])
        # Try stripping .JK suffix
        if not entries and tu.endswith(".JK"):
            entries = self.ticker_to_group.get(tu[:-3], [])
        # Try adding .JK suffix (reverse case)
        if not entries and not tu.endswith(".JK"):
            entries = self.ticker_to_group.get(tu + ".JK", [])
        if not entries:
            return None

        # Primary entry (first one)
        primary = entries[0]
        group_data = primary["group_data"]

        # Get all sister tickers in same group
        sister_tickers = []
        for sector, tickers in group_data.get("tickers", {}).items():
            for t in tickers:
                if t.upper() != tu:
                    sister_tickers.append(t.upper())
        sister_tickers = sorted(set(sister_tickers))[:15]

        # Active alliances involving this group
        active_alliances = []
        for alliance in self.alliances.get("active_alliances", []):
            if (primary["group_id"] in alliance.get("name", "").lower() or
                primary["group_id"] in str(alliance.get("vehicle", "")).lower()):
                active_alliances.append(alliance)

        return ConglomerateContext(
            ticker=ticker,
            group=primary["group_id"],
            patriarch=group_data.get("patriarch", "?"),
            sector_role=primary["sector_role"],
            sister_tickers=sister_tickers,
            alliances=active_alliances,
            broker_affiliate=group_data.get("broker_affiliate"),
        )

    def get_group_tickers(self, group: str) -> List[str]:
        """Get all tickers for a specific conglomerate group."""
        out = []
        group_data = self.conglomerates.get(group.lower(), {})
        for sector, tickers in group_data.get("tickers", {}).items():
            out.extend(t.upper() for t in tickers)
        return sorted(set(out))

    # ── Goreng-menggoreng 4-phase detector ────────────────────────────

    def detect_goreng_phase(self, ticker: str, prices: pd.Series,
                             news_count: int = 0) -> Optional[GorengPhase]:
        """
        Detect which of 4 phases the ticker is in:
          PHASE_1_AKUMULASI: Low vol + tight range, smart money accumulating quietly
          PHASE_2_CORP_ACTION: Right issues, M&A, restructuring announcements + vol rising
          PHASE_3_LIQUIDITAS: Foreign inflow, volume explosion, narrative meledak
          PHASE_4_EUFORIA: Parabolic + retail FOMO + smart money distribusi
        """
        s = pd.to_numeric(prices, errors="coerce").dropna()
        if len(s) < 60:
            return None

        try:
            signals = []
            phase_scores = {
                "PHASE_1_AKUMULASI": 0,
                "PHASE_2_CORP_ACTION": 0,
                "PHASE_3_LIQUIDITAS": 0,
                "PHASE_4_EUFORIA": 0,
            }

            # ── Compute base metrics ──
            returns = s.pct_change().dropna()
            ret_5d = float(s.iloc[-1] / s.iloc[-6] - 1) if len(s) >= 6 else 0
            ret_20d = float(s.iloc[-1] / s.iloc[-21] - 1) if len(s) >= 21 else 0
            ret_60d = float(s.iloc[-1] / s.iloc[-61] - 1) if len(s) >= 61 else 0

            vol_20 = float(returns.tail(20).std())
            vol_60 = float(returns.tail(60).std()) if len(returns) >= 60 else vol_20

            recent_range = (s.tail(20).max() - s.tail(20).min()) / s.tail(20).mean()
            prior_range = ((s.iloc[-60:-20].max() - s.iloc[-60:-20].min()) / 
                          s.iloc[-60:-20].mean()) if len(s) >= 60 else recent_range

            green_days_20 = (returns.tail(20) > 0).sum()
            green_pct = green_days_20 / 20

            # ── PHASE 1 — AKUMULASI signals ──
            if (vol_20 / max(vol_60, 0.001) < 0.7 and recent_range < 0.05 and
                abs(ret_20d) < 0.05):
                signals.append(f"📦 Vol compressed {(1-vol_20/vol_60):.0%}, range {recent_range:.1%}")
                phase_scores["PHASE_1_AKUMULASI"] += 30
            if 0.45 <= green_pct <= 0.65 and ret_20d > -0.02:
                signals.append(f"🤫 Stair-step pattern: {green_days_20}/20 green days")
                phase_scores["PHASE_1_AKUMULASI"] += 20

            # ── PHASE 2 — CORP ACTION signals (vol rising from base) ──
            if (vol_20 / max(vol_60, 0.001) > 1.1 and vol_20 / max(vol_60, 0.001) < 1.8 and
                ret_20d > 0.05 and ret_20d < 0.20 and news_count >= 2):
                signals.append(f"📰 Vol rising {(vol_20/vol_60-1):.0%} + news count {news_count}")
                phase_scores["PHASE_2_CORP_ACTION"] += 35
            if ret_5d > 0.03 and ret_20d > 0.08:
                signals.append(f"📈 Building momentum: 5d {ret_5d:+.1%}, 20d {ret_20d:+.1%}")
                phase_scores["PHASE_2_CORP_ACTION"] += 15

            # ── PHASE 3 — LIQUIDITAS signals (volume explosion + breakout) ──
            if (vol_20 / max(vol_60, 0.001) > 1.5 and ret_20d > 0.15 and
                green_pct > 0.65):
                signals.append(f"💥 Volume explosion + {green_pct:.0%} green days")
                phase_scores["PHASE_3_LIQUIDITAS"] += 40
            if news_count >= 5 and ret_5d > 0.10:
                signals.append(f"🔥 News flood ({news_count}) + price acceleration")
                phase_scores["PHASE_3_LIQUIDITAS"] += 20

            # ── PHASE 4 — EUFORIA signals (parabolic + distribution) ──
            if ret_20d > 0.40 and ret_60d > 0.80:
                signals.append(f"🚀 Parabolic: 60d {ret_60d:+.0%}")
                phase_scores["PHASE_4_EUFORIA"] += 35
            if vol_20 / max(vol_60, 0.001) > 2.5:
                signals.append(f"🌪️ Extreme vol expansion {vol_20/vol_60:.1f}x — climax")
                phase_scores["PHASE_4_EUFORIA"] += 20
            # Volume declining despite price up = distribution
            if (ret_5d > 0.05 and vol_20 < vol_60 * 0.9 and ret_60d > 0.50):
                signals.append("⚠️ DISTRIBUTION: price up but vol declining")
                phase_scores["PHASE_4_EUFORIA"] += 30

            # Determine winning phase
            max_score = max(phase_scores.values())
            if max_score < 30:
                current_phase = "UNCLEAR"
                confidence = 0.3
            else:
                current_phase = max(phase_scores, key=phase_scores.get)
                confidence = min(0.95, max_score / 100)

            # ── Build action + warnings ──
            action, duration, warnings = self._goreng_action_plan(
                current_phase, ret_60d, vol_20 / max(vol_60, 0.001)
            )

            return GorengPhase(
                ticker=ticker,
                current_phase=current_phase,
                confidence=round(confidence, 2),
                signals_detected=signals,
                action=action,
                estimated_phase_duration_remaining=duration,
                risk_warnings=warnings,
            )
        except Exception as e:
            logger.debug(f"Goreng detect failed for {ticker}: {e}")
            return None

    def _goreng_action_plan(self, phase: str, ret_60d: float,
                             vol_ratio: float) -> Tuple[str, str, List[str]]:
        """Build action plan based on phase."""
        if phase == "PHASE_1_AKUMULASI":
            return ("ACCUMULATE",
                    "3-6 months (waiting for corp action catalysts)",
                    ["Patience required — early stage, no catalysts yet",
                     "Position small, build over time"])

        elif phase == "PHASE_2_CORP_ACTION":
            return ("ACCUMULATE_AGGRESSIVE",
                    "2-4 months (waiting for liquidity inflection)",
                    ["Corporate actions de-risk thesis",
                     "Monitor for right issue dilution"])

        elif phase == "PHASE_3_LIQUIDITAS":
            return ("RIDE",
                    "1-3 months (riding the wave)",
                    ["Tight trailing stop — distribution can start any time",
                     "Take partial profits at 30-50% gain",
                     "Foreign flow can reverse fast"])

        elif phase == "PHASE_4_EUFORIA":
            if ret_60d > 1.0:  # >100% in 3 months
                return ("DISTRIBUTE_OR_EXIT",
                        "1-4 weeks (parabolic phase)",
                        ["🚨 LATE STAGE — distribution by smart money likely",
                         "If long, exit 75-100% positions",
                         "If shorting, wait for volume divergence confirmation",
                         "Retail FOMO = top signal"])
            else:
                return ("PARTIAL_EXIT",
                        "1-2 months (late accelerating)",
                        ["Reduce position size 50%",
                         "Trail stop tight",
                         "Watch for distribution pattern"])
        else:
            return ("MONITOR", "Unclear", ["No clear phase, wait for signal"])

    # ── Cornering / lock-up detection (improved from v35) ─────────────

    def detect_cornering(self, ticker: str, prices: pd.Series) -> Dict:
        """Detect supply cornering / float compression patterns."""
        s = pd.to_numeric(prices, errors="coerce").dropna()
        if len(s) < 60:
            return {"detected": False, "score": 0, "patterns": []}

        patterns = []
        score = 0

        try:
            # Lock-up: tight range over many days
            recent_15 = s.tail(15)
            range_15 = (recent_15.max() - recent_15.min()) / recent_15.mean()
            if range_15 < 0.02:
                patterns.append(f"🔒 Lock-up: only {range_15:.2%} range over 15 days")
                score += 30

            # Vol collapse + drift
            returns = s.pct_change().dropna()
            vol_20 = float(returns.tail(20).std())
            vol_60 = float(returns.tail(60).std()) if len(returns) >= 60 else vol_20
            ret_20 = float(s.iloc[-1] / s.iloc[-21] - 1) if len(s) >= 21 else 0
            if vol_60 > 0 and vol_20 / vol_60 < 0.40 and ret_20 > 0.05:
                patterns.append(f"📉 Vol collapse {(1-vol_20/vol_60):.0%} + drift +{ret_20:.1%}")
                score += 35

            # Gap release after quiet
            if len(s) >= 30:
                quiet_period = s.iloc[-30:-3]
                quiet_range = (quiet_period.max() - quiet_period.min()) / quiet_period.mean()
                last_3d_ret = float(s.iloc[-1] / s.iloc[-4] - 1)
                if quiet_range < 0.03 and last_3d_ret > 0.05:
                    patterns.append(f"💥 Gap release: 27d quiet ({quiet_range:.1%}), last 3d +{last_3d_ret:.1%}")
                    score += 25

            # Persistent green
            green_pct = (returns.tail(15) > 0).sum() / 15
            if green_pct >= 0.80:
                patterns.append(f"🟢 Persistent green {green_pct:.0%} 15 days")
                score += 15

        except Exception:
            pass

        return {
            "detected": score >= 35,
            "score": score,
            "patterns": patterns,
        }

    # ── Hedgeye Quad Indonesia cross-check ─────────────────────────────

    def check_indonesia_quad(self, snap: Dict, prices: Dict,
                              hedgeye_call: str = "Q4") -> IHSGQuadCheck:
        """
        Cross-check our Indonesia Quad estimate against Hedgeye call.

        Reads from snap["global"]["country_list"] (where dashboard stores it),
        with fallback to snap["gip"] keys.

        Looks at:
          - global country_list for Indonesia entry
          - USDIDR trajectory
          - EIDO performance vs SPY/EEM
          - Foreign flow proxy
        """
        # ── Get our estimate (CORRECTED — read from global.country_list) ──
        our_estimate = "UNKNOWN"
        our_regime_name = ""

        # Primary source: snap["global"]["country_list"]
        global_data = snap.get("global", {}) or {}
        if isinstance(global_data, dict):
            country_list = global_data.get("country_list", []) or []
            for entry in country_list:
                if isinstance(entry, dict):
                    country = str(entry.get("country", "")).lower()
                    if country in ("indonesia", "ihsg", "id"):
                        our_estimate = entry.get("quad", "UNKNOWN")
                        our_regime_name = entry.get("regime_name", "")
                        break

        # Fallback: snap["gip"] keys
        if our_estimate == "UNKNOWN":
            gip = snap.get("gip", {}) or {}
            if isinstance(gip, dict):
                id_gip = gip.get("indonesia") or gip.get("IDN") or gip.get("EIDO") or {}
                if isinstance(id_gip, dict):
                    our_estimate = id_gip.get("structural_quad",
                                              id_gip.get("quad", "UNKNOWN"))

        # Cross-validation signals
        signals = {}

        # USDIDR signal
        usdidr = prices.get("USDIDR=X") or prices.get("IDR=X")
        if usdidr is not None:
            try:
                s = pd.to_numeric(pd.Series(usdidr), errors="coerce").dropna()
                if len(s) >= 60:
                    current = float(s.iloc[-1])
                    avg_60d = float(s.tail(60).mean())
                    signals["usdidr_weakening"] = current > avg_60d * 1.02
            except Exception:
                pass

        # EIDO vs SPY
        eido = prices.get("EIDO")
        spy = prices.get("SPY")
        if eido is not None and spy is not None:
            try:
                e_s = pd.to_numeric(pd.Series(eido), errors="coerce").dropna()
                s_s = pd.to_numeric(pd.Series(spy), errors="coerce").dropna()
                if len(e_s) >= 20 and len(s_s) >= 20:
                    eido_ret = float(e_s.iloc[-1] / e_s.iloc[-21] - 1)
                    spy_ret = float(s_s.iloc[-1] / s_s.iloc[-21] - 1)
                    signals["eido_underperforms_spy"] = (eido_ret - spy_ret) < -0.05
            except Exception:
                pass

        # ── FIXED match logic ──
        # Only "match" if our_estimate is NOT UNKNOWN AND equals hedgeye_call
        if our_estimate == "UNKNOWN":
            match = False
            confidence = 0.0
            recommendation = (
                f"⚠️ Our model: NO Indonesia classification (UNKNOWN). "
                f"Hedgeye says: {hedgeye_call}. Cannot verify match — "
                f"GIP engine doesn't have Indonesia entry. "
                f"Check page_global() country_list output for Indonesia row."
            )
        elif our_estimate == hedgeye_call:
            match = True
            confirms = sum(1 for v in signals.values() if v)
            total = len([v for v in signals.values() if v is not None])
            confidence = (confirms / max(total, 1)) if total > 0 else 0.7
            recommendation = (
                f"✅ MATCH. Our model ({our_estimate}) agrees with Hedgeye ({hedgeye_call}). "
                f"Cross-validation: {confirms}/{total} signals confirm Indonesia bearish."
            )
        else:
            # MISMATCH — explicitly call out
            match = False
            confirms = sum(1 for v in signals.values() if v)
            total = len([v for v in signals.values() if v is not None])
            confidence = (confirms / max(total, 1)) if total > 0 else 0.3
            # Determine which view signals support
            if confirms >= total / 2 and total > 0:
                support_str = f"Signals SUPPORT Hedgeye view ({confirms}/{total} confirm Q4 bias)"
            else:
                support_str = f"Signals SUPPORT our view ({total-confirms}/{total} contradict Q4 bias)"
            recommendation = (
                f"⚠️ MISMATCH. Our model: **{our_estimate}** ({our_regime_name}), "
                f"Hedgeye says: **{hedgeye_call}**. {support_str}. "
                f"Investigate GIP engine calibration — kalau Indonesia genuinely "
                f"transitioning from Q2 → Q4, monthly quad bisa lead structural quad."
            )

        return IHSGQuadCheck(
            our_estimate=our_estimate,
            hedgeye_call=hedgeye_call,
            match=match,
            cross_validation_signals=signals,
            confidence=round(confidence, 2),
            recommendation=recommendation,
        )

    def analyze(self, prices, snap=None):
        """Adapter for orchestrator's `.analyze(prices)` → {goreng_phases,
        conglomerate_flows, hedgeye_check}. Maps to the real detection methods.
        FULLY DEFENSIVE: any per-ticker failure is skipped, never raised — worst case
        returns empty lists (= feature off, same as before restore), best case populates
        goreng + conglomerate. (The orchestrator was written against a `.analyze()` API
        that neither v38 nor v39 shipped; this restores the contract.)"""
        from dataclasses import asdict, is_dataclass
        out = {"goreng_phases": [], "conglomerate_flows": [], "hedgeye_check": {},
               "maker_framework": {}}
        prices = prices or {}
        tickers = list(prices.keys())
        for t in tickers:
            try:
                s = pd.to_numeric(pd.Series(prices.get(t)), errors="coerce").dropna()
                if len(s) < 30:
                    continue
                gp = self.detect_goreng_phase(t, s)
                if gp is not None:
                    out["goreng_phases"].append(asdict(gp) if is_dataclass(gp) else gp)
                # Maker roadmap / thought-process (price/volume based — the essay's framework)
                try:
                    from engines.maker_framework import analyze_maker_framework
                    mf = analyze_maker_framework(t, s)
                    if mf.get("phase") != "UNCLEAR" or mf.get("traps"):
                        out["maker_framework"][t] = mf
                except Exception:
                    pass
            except Exception:
                continue
        for t in tickers:
            try:
                ctx = self.get_conglomerate_context(t)
                if ctx is not None:
                    out["conglomerate_flows"].append(asdict(ctx) if is_dataclass(ctx) else ctx)
            except Exception:
                continue
        try:
            if snap is not None:
                qc = self.check_indonesia_quad(snap, prices)
                out["hedgeye_check"] = asdict(qc) if is_dataclass(qc) else (qc or {})
        except Exception:
            out["hedgeye_check"] = {}
        return out


# ═══════════════════════════════════════════════════════════════════════
# Singleton
# ═══════════════════════════════════════════════════════════════════════

_IHSG_SINGLETON: Optional[IHSGSpecialistEngine] = None


def get_ihsg_specialist() -> IHSGSpecialistEngine:
    global _IHSG_SINGLETON
    if _IHSG_SINGLETON is None:
        _IHSG_SINGLETON = IHSGSpecialistEngine()
    return _IHSG_SINGLETON


__all__ = [
    "IHSGSpecialistEngine",
    "ConglomerateContext",
    "GorengPhase",
    "IHSGQuadCheck",
    "get_ihsg_specialist",
]
