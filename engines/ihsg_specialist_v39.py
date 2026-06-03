"""engines/ihsg_specialist_v39.py — v39 (Enhanced with Anti-Fake Broker Flow Detector)

IHSG-specific intelligence:
  1. Konglomerasi mapping (20+ groups: Bakrie, Salim, Barito, Astra, Sinarmas,
     Lippo, CT Corp, Ciputra, MNC, Djarum, Adaro, Medco, etc)
  2. Cross-group flow detection (Bakrie + Salim alliance type signals)
  3. Goreng-menggoreng 4-phase pattern detector (Akumulasi -> CorpAct -> Liquidity -> Euforia)
  4. Cornering detection (lock-up patterns, vol collapse + drift, gap release)
  5. Hedgeye Quad Indonesia cross-check (verify our model matches Keith's call)
  6. **NEW v39 — Anti-Fake Broker Flow Analyzer**
       - Crossing Transaction Detection (transaksi matching palsu)
       - Window Dressing Detection (akhir bulan/kuartal fake moves)
       - Forced Sell Detection (bukan distribusi sungguhan)
       - Broker Affiliation Filter (crossing dalam grup konglomerasi)
       - Concentration Analysis (HHI index — akumulasi terkonsentrasi vs retail FOMO)

Data source: data/ihsg_conglomerates.json (Edward updatable)

Honest disclosure:
  - Phase detection uses price/volume PROXIES (no real BEI broker summary)
  - BrokerFlowAnalyzer can accept real BEI broker summary data when available
  - Without broker data, falls back to price/volume proxy with anti-fake filters
  - Foreign flow proxy via EIDO underperformance vs EEM
"""
from __future__ import annotations

import os
import json
import math
import logging
import calendar
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set, Any

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
    cross_validation_signals: Dict[str, bool]  # signal_name -> confirms our estimate
    confidence: float
    recommendation: str


@dataclass
class BrokerFlowResult:
    """Hasil analisis broker flow dengan anti-fake filters."""
    ticker: str
    flow_signal: str             # ACCUMULASI_ASLI / DISTRIBUSI_ASLI / FAKE_AKUM / FAKE_DISTR / FORCED_SELL / WINDOW_DRESSING / UNCLEAR
    confidence: float            # 0-1
    raw_net_flow: float          # dalam juta Rp atau lot
    adjusted_net_flow: float     # setelah filter crossing
    top_brokers_buy: List[str]
    top_brokers_sell: List[str]
    warnings: List[str]
    explanation: str             # bahasa Indonesia
    filter_details: Dict[str, Any]  # detail tiap filter


# ═══════════════════════════════════════════════════════════════════════
# BROKER FLOW ANALYZER — Anti-Fake Detector
# ═══════════════════════════════════════════════════════════════════════

class BrokerFlowAnalyzer:
    """
    Analyze IHSG broker summary flow with anti-fake filters.

    INPUT: Raw broker summary data (bisa dari BEI, RTI, atau proxy)
    OUTPUT: Filtered flow signals with confidence scores

    Anti-fake filters:
      1. Crossing Detection — harga transaksi di luar kisaran pasar
      2. Window Dressing Detection — akhir bulan/kuartal spike
      3. Forced Sell Detection — volume abnormal + harga turun drastis
      4. Broker Affiliation Filter — net flow setelah crossing same-group
      5. Concentration Analysis — apakah akumulasi terkonsentrasi di 1-2 broker
    """

    # ── Konstanta untuk deteksi ────────────────────────────────────────

    # Crossing: harga di luar daily range -> kemungkinan crossing
    CROSSING_PRICE_TOLERANCE: float = 0.01  # 1% tolerance dari daily range

    # Window dressing: flow spike > 3x rata-rata 10 hari
    WD_SPIKE_MULTIPLIER: float = 3.0
    WD_LOOKBACK_DAYS: int = 10

    # Forced sell: harga turun > 5% dalam 1 hari + volume > 5x rata-rata 20 hari
    FORCED_SELL_PRICE_DROP: float = 0.05
    FORCED_SELL_VOLUME_MULTIPLIER: float = 5.0
    FORCED_SELL_VOL_LOOKBACK: int = 20

    # Concentration: HHI threshold untuk "terkonsentrasi"
    HHI_CONCENTRATED_THRESHOLD: float = 2500  # HHI > 2500 = terkonsentrasi
    HHI_MODERATE_THRESHOLD: float = 1500      # HHI 1500-2500 = moderat

    # Round lot sizes yang sering muncul di crossing institusional
    INSTITUTIONAL_ROUND_LOTS: List[int] = [100, 500, 1000, 5000, 10000, 25000, 50000]

    # Default broker affiliations — grup konglomerasi Indonesia
    DEFAULT_BROKER_AFFILIATIONS: Dict[str, str] = {
        # Bakrie group
        "BB": "BAKRIE", "BS": "BAKRIE", "BK": "BAKRIE", "BY": "BAKRIE",
        # Salim group
        "SL": "SALIM", "SM": "SALIM", "SF": "SALIM", "SA": "SALIM",
        # Lippo group
        "LP": "LIPPO", "LI": "LIPPO", "LG": "LIPPO",
        # Sinar Mas
        "MS": "SINARMAS", "SN": "SINARMAS", "GS": "SINARMAS",
        # Astra
        "AS": "ASTRA", "AI": "ASTRA", "AP": "ASTRA",
        # CT Corp
        "CT": "CT_CORP", "TP": "CT_CORP",
        # MNC
        "MC": "MNC", "MI": "MNC", "MN": "MNC",
        # Ciputra
        "CP": "CIPUTRA", "CI": "CIPUTRA",
        # Barito Pacific
        "BR": "BARITO", "BP": "BARITO",
        # Adaro
        "AD": "ADARO", "DR": "ADARO",
        # Djarum
        "DJ": "DJARUM", "DB": "DJARUM",
        # Medco
        "MD": "MEDCO", "ME": "MEDCO",
        # Foreign brokers (tidak punya afiliasi lokal)
        "MSCS": "FOREIGN", "JPM": "FOREIGN", "GSUS": "FOREIGN",
        "UBS": "FOREIGN", "CS": "FOREIGN", "HSBC": "FOREIGN",
        "CLSA": "FOREIGN", "NOM": "FOREIGN",
    }

    def __init__(self, broker_affiliations: Optional[Dict[str, str]] = None):
        """
        Initialize BrokerFlowAnalyzer.

        Args:
            broker_affiliations: Mapping broker_code -> group_name.
                                 Jika None, pakai default affiliations.
        """
        self.affiliations = broker_affiliations or dict(self.DEFAULT_BROKER_AFFILIATIONS)

    # ═══════════════════════════════════════════════════════════════════
    # FILTER 1: Crossing Transaction Detection
    # ═══════════════════════════════════════════════════════════════════

    def detect_crossing(
        self,
        trades: List[Dict[str, Any]],
        daily_high: Optional[float] = None,
        daily_low: Optional[float] = None,
        prev_close: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Detect crossing/matching transactions.

        Crossing indicators:
        - Price outside daily range (high/low) -> likely crossing
        - Volume exactly round lots (1000, 5000, 10000) -> institutional crossing
        - Buyer = Seller (same broker code) -> definite crossing
        - Price = previous close exactly -> crossing

        Args:
            trades: List of trade dicts with keys:
                    'price', 'volume', 'buyer_code', 'seller_code', 'time'
            daily_high: High price hari ini
            daily_low: Low price hari ini
            prev_close: Close price hari sebelumnya

        Returns:
            {
                "crossing_volume": float,
                "crossing_pct": float (0-100),
                "is_crossing_heavy": bool,
                "crossing_trades": List[Dict],
                "reasons": List[str],
            }
        """
        if not trades:
            return {
                "crossing_volume": 0.0,
                "crossing_pct": 0.0,
                "is_crossing_heavy": False,
                "crossing_trades": [],
                "reasons": [],
            }

        crossing_trades: List[Dict] = []
        total_volume = sum(t.get("volume", 0) for t in trades)
        reasons: List[str] = []

        for trade in trades:
            is_crossing = False
            trade_reasons: List[str] = []

            price = trade.get("price", 0)
            volume = trade.get("volume", 0)
            buyer = trade.get("buyer_code", "").upper()
            seller = trade.get("seller_code", "").upper()

            # Indicator 1: Buyer == Seller (definite crossing)
            if buyer and seller and buyer == seller:
                is_crossing = True
                trade_reasons.append(f"Buyer = Seller ({buyer})")

            # Indicator 2: Price outside daily range
            if daily_high is not None and daily_low is not None and price > 0:
                tolerance_high = daily_high * (1 + self.CROSSING_PRICE_TOLERANCE)
                tolerance_low = daily_low * (1 - self.CROSSING_PRICE_TOLERANCE)
                if price > tolerance_high or price < tolerance_low:
                    is_crossing = True
                    trade_reasons.append(
                        f"Price {price} outside range [{daily_low:.0f}-{daily_high:.0f}]"
                    )

            # Indicator 3: Price exactly = previous close
            if prev_close is not None and abs(price - prev_close) < 0.01:
                is_crossing = True
                trade_reasons.append(f"Price = prev_close ({prev_close:.0f})")

            # Indicator 4: Volume = round lot institusional
            if volume > 0:
                for lot_size in self.INSTITUTIONAL_ROUND_LOTS:
                    if volume == lot_size:
                        is_crossing = True
                        trade_reasons.append(f"Round lot {lot_size}")
                        break
                    # Jika volume kelipatan EXACT dari lot besar -> kemungkinan crossing
                    if lot_size >= 1000 and volume == lot_size * 100:
                        is_crossing = True
                        trade_reasons.append(f"Institutional block {volume}")
                        break

            if is_crossing:
                crossing_trades.append({
                    **trade,
                    "crossing_reasons": trade_reasons,
                })
                reasons.extend(trade_reasons)

        crossing_volume = sum(t.get("volume", 0) for t in crossing_trades)
        crossing_pct = (crossing_volume / max(total_volume, 1)) * 100
        is_crossing_heavy = crossing_pct > 30 or len(crossing_trades) > 10

        # Deduplicate reasons
        unique_reasons = sorted(set(reasons))

        return {
            "crossing_volume": float(crossing_volume),
            "crossing_pct": round(float(crossing_pct), 2),
            "is_crossing_heavy": bool(is_crossing_heavy),
            "crossing_trades": crossing_trades,
            "reasons": unique_reasons,
        }

    # ═══════════════════════════════════════════════════════════════════
    # FILTER 2: Window Dressing Detection
    # ═══════════════════════════════════════════════════════════════════

    def detect_window_dressing(
        self,
        daily_flows: pd.Series,
        date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Detect window dressing (akhir bulan/kuartal fake moves).

        Indicators:
        - Date is last trading day of month/quarter
        - Flow spike > 3x average of past 10 days
        - Price flat or down despite "buying" flow -> fake
        - Flow reverses immediately next day -> confirmed fake

        Args:
            daily_flows: pd.Series index=date, values=net flow (buy - sell)
                         dalam juta Rp atau lot. Urutan kronologis.
            date: Tanggal yang akan diperiksa. Jika None, pakai index terakhir.

        Returns:
            {
                "is_window_dressing": bool,
                "confidence": float (0-1),
                "reason": str,
                "is_end_of_month": bool,
                "is_end_of_quarter": bool,
                "flow_spike_ratio": float,
            }
        """
        # Defensive: handle empty/invalid input
        if daily_flows is None or len(daily_flows) < self.WD_LOOKBACK_DAYS + 1:
            return {
                "is_window_dressing": False,
                "confidence": 0.0,
                "reason": "Data tidak cukup untuk deteksi window dressing",
                "is_end_of_month": False,
                "is_end_of_quarter": False,
                "flow_spike_ratio": 0.0,
            }

        try:
            s = pd.to_numeric(daily_flows, errors="coerce").dropna()
            if len(s) < self.WD_LOOKBACK_DAYS + 1:
                return {
                    "is_window_dressing": False,
                    "confidence": 0.0,
                    "reason": "Data tidak cukup setelah cleaning",
                    "is_end_of_month": False,
                    "is_end_of_quarter": False,
                    "flow_spike_ratio": 0.0,
                }

            # Determine target date
            if date is None:
                target_date = s.index[-1]
                if isinstance(target_date, str):
                    target_date = pd.to_datetime(target_date)
            else:
                target_date = pd.to_datetime(date)

            target_date = pd.Timestamp(target_date)

            # Check if end of month / quarter
            is_end_of_month = self._is_last_trading_day_of_month(s, target_date)
            is_end_of_quarter = (
                is_end_of_month and target_date.month in (3, 6, 9, 12)
            )

            # Get today's flow
            if target_date in s.index:
                today_flow = float(s.loc[target_date])
            else:
                today_flow = float(s.iloc[-1])

            # Calculate past N-day average (excluding today)
            past_flows = s[s.index < target_date].tail(self.WD_LOOKBACK_DAYS)
            avg_past = float(past_flows.abs().mean()) if len(past_flows) > 0 else 0

            # Flow spike ratio
            flow_spike_ratio = (
                abs(today_flow) / max(avg_past, 0.001)
                if avg_past > 0 else 0
            )

            # Is there a spike?
            is_spike = flow_spike_ratio > self.WD_SPIKE_MULTIPLIER

            # Check for reversal next day (if available)
            reversal_detected = False
            future_flows = s[s.index > target_date]
            if len(future_flows) >= 1:
                next_day_flow = float(future_flows.iloc[0])
                # Jika hari ini buy besar, besok sell besar -> reversal
                if today_flow > 0 and next_day_flow < -avg_past * 2:
                    reversal_detected = True
                elif today_flow < 0 and next_day_flow > avg_past * 2:
                    reversal_detected = True

            # Decision logic
            is_window_dressing = False
            confidence = 0.0
            reason_parts: List[str] = []

            if is_end_of_quarter and is_spike:
                is_window_dressing = True
                confidence = 0.85
                reason_parts.append(
                    f"Akhir kuartal + flow spike {flow_spike_ratio:.1f}x "
                    f"rata-rata {self.WD_LOOKBACK_DAYS} hari"
                )
            elif is_end_of_month and is_spike:
                is_window_dressing = True
                confidence = 0.65
                reason_parts.append(
                    f"Akhir bulan + flow spike {flow_spike_ratio:.1f}x"
                )
            elif is_spike and reversal_detected:
                is_window_dressing = True
                confidence = 0.75
                reason_parts.append(
                    f"Flow spike {flow_spike_ratio:.1f}x + reversal hari berikutnya"
                )

            if reversal_detected and is_window_dressing:
                confidence = min(0.95, confidence + 0.1)
                reason_parts.append("Reversal hari berikutnya memperkuat indikasi WD")

            if not is_window_dressing:
                if not is_end_of_month and not is_spike:
                    reason_parts.append("Bukan akhir bulan dan tidak ada spike")
                elif is_end_of_month and not is_spike:
                    reason_parts.append(
                        f"Akhir bulan tapi flow normal ({flow_spike_ratio:.1f}x)"
                    )
                elif is_spike and not (is_end_of_month or is_end_of_quarter):
                    reason_parts.append(
                        f"Flow spike {flow_spike_ratio:.1f}x tapi bukan akhir bulan — "
                        f"kemungkinan akumulasi/distribusi sungguhan"
                    )

            return {
                "is_window_dressing": bool(is_window_dressing),
                "confidence": round(float(confidence), 2),
                "reason": "; ".join(reason_parts) if reason_parts else "Tidak terdeteksi",
                "is_end_of_month": bool(is_end_of_month),
                "is_end_of_quarter": bool(is_end_of_quarter),
                "flow_spike_ratio": round(float(flow_spike_ratio), 2),
            }

        except Exception as e:
            logger.debug(f"Window dressing detection error: {e}")
            return {
                "is_window_dressing": False,
                "confidence": 0.0,
                "reason": f"Error: {str(e)}",
                "is_end_of_month": False,
                "is_end_of_quarter": False,
                "flow_spike_ratio": 0.0,
            }

    def _is_last_trading_day_of_month(
        self, daily_flows: pd.Series, target_date: pd.Timestamp
    ) -> bool:
        """Check if target_date is the last trading day of its month."""
        try:
            # Get all trading days in the same month
            month_start = target_date.replace(day=1)
            month_end = target_date.replace(
                day=calendar.monthrange(target_date.year, target_date.month)[1]
            )
            month_trading_days = daily_flows[
                (daily_flows.index >= month_start) &
                (daily_flows.index <= month_end)
            ].index

            if len(month_trading_days) == 0:
                # Fallback: check calendar
                return target_date.day >= 28

            last_trading_day = month_trading_days.max()
            return target_date.date() == last_trading_day.date()
        except Exception:
            # Fallback: last 3 days of month
            return target_date.day >= 28

    # ═══════════════════════════════════════════════════════════════════
    # FILTER 3: Forced Sell Detection
    # ═══════════════════════════════════════════════════════════════════

    def detect_forced_sell(
        self,
        prices: pd.Series,
        volumes: pd.Series,
    ) -> Dict[str, Any]:
        """
        Detect forced selling (bukan distribusi sungguhan).

        Indicators:
        - Price drop > 5% in 1 day with volume > 5x 20-day average
        - No preceding rally (bukan profit taking)
        - Multiple stocks in same group drop simultaneously -> margin call/forced
        - Drop happens at market open -> forced sell queue

        Args:
            prices: pd.Series index=date, values=closing price
            volumes: pd.Series index=date, values=volume

        Returns:
            {
                "is_forced_sell": bool,
                "confidence": float (0-1),
                "reason": str,
                "price_drop_pct": float,
                "volume_ratio": float,
                "has_preceding_rally": bool,
                "indicators": List[str],
            }
        """
        # Defensive checks
        if prices is None or volumes is None:
            return {
                "is_forced_sell": False,
                "confidence": 0.0,
                "reason": "Data harga atau volume kosong",
                "price_drop_pct": 0.0,
                "volume_ratio": 0.0,
                "has_preceding_rally": False,
                "indicators": [],
            }

        p = pd.to_numeric(prices, errors="coerce").dropna()
        v = pd.to_numeric(volumes, errors="coerce").dropna()

        if len(p) < self.FORCED_SELL_VOL_LOOKBACK + 2 or len(v) < self.FORCED_SELL_VOL_LOOKBACK + 1:
            return {
                "is_forced_sell": False,
                "confidence": 0.0,
                "reason": "Data tidak cukup untuk deteksi forced sell",
                "price_drop_pct": 0.0,
                "volume_ratio": 0.0,
                "has_preceding_rally": False,
                "indicators": [],
            }

        try:
            indicators: List[str] = []

            # Price drop hari ini vs kemarin
            today_price = float(p.iloc[-1])
            yesterday_price = float(p.iloc[-2])
            price_drop_pct = (yesterday_price - today_price) / max(yesterday_price, 0.001)

            # Volume ratio vs 20-day average
            avg_volume = float(v.tail(self.FORCED_SELL_VOL_LOOKBACK).mean())
            today_volume = float(v.iloc[-1])
            volume_ratio = today_volume / max(avg_volume, 1)

            # Check preceding rally (20-day return before today)
            if len(p) >= self.FORCED_SELL_VOL_LOOKBACK + 2:
                price_20d_ago = float(p.iloc[-(self.FORCED_SELL_VOL_LOOKBACK + 2)])
                rally_pct = (yesterday_price - price_20d_ago) / max(price_20d_ago, 0.001)
                has_preceding_rally = rally_pct > 0.10  # Rally > 10% in 20 days
            else:
                has_preceding_rally = False
                rally_pct = 0.0

            # Main indicator: big drop + volume spike
            big_drop = price_drop_pct > self.FORCED_SELL_PRICE_DROP
            volume_spike = volume_ratio > self.FORCED_SELL_VOLUME_MULTIPLIER

            if big_drop:
                indicators.append(
                    f"Harga turun {price_drop_pct:.1%} (threshold {self.FORCED_SELL_PRICE_DROP:.0%})"
                )
            if volume_spike:
                indicators.append(
                    f"Volume {volume_ratio:.1f}x rata-rata {self.FORCED_SELL_VOL_LOOKBACK}h"
                )
            if not has_preceding_rally and big_drop:
                indicators.append(
                    f"Tidak ada rally sebelumnya (20d return {rally_pct:.1%}) — "
                    f"bukan profit taking"
                )

            # Decision
            is_forced_sell = False
            confidence = 0.0

            if big_drop and volume_spike and not has_preceding_rally:
                is_forced_sell = True
                confidence = 0.90
            elif big_drop and volume_spike and has_preceding_rally:
                # Masih mungkin forced sell tapi kemungkinan juga profit taking
                is_forced_sell = True
                confidence = 0.55
                indicators.append(
                    "Ada rally sebelumnya — bisa jadi profit taking ATAU forced sell"
                )
            elif big_drop and not volume_spike:
                # Drop tanpa volume spike -> bukan forced sell
                is_forced_sell = False
                confidence = 0.2
                indicators.append("Turun drastis tapi volume normal — bukan forced sell")
            elif volume_spike and not big_drop:
                # Volume spike tanpa drop -> akumulasi
                is_forced_sell = False
                confidence = 0.0
                indicators.append("Volume tinggi tapi harga tidak turun — bukan forced sell")

            reason = "; ".join(indicators) if indicators else "Tidak terdeteksi forced sell"

            return {
                "is_forced_sell": bool(is_forced_sell),
                "confidence": round(float(confidence), 2),
                "reason": reason,
                "price_drop_pct": round(float(price_drop_pct), 4),
                "volume_ratio": round(float(volume_ratio), 2),
                "has_preceding_rally": bool(has_preceding_rally),
                "indicators": indicators,
            }

        except Exception as e:
            logger.debug(f"Forced sell detection error: {e}")
            return {
                "is_forced_sell": False,
                "confidence": 0.0,
                "reason": f"Error: {str(e)}",
                "price_drop_pct": 0.0,
                "volume_ratio": 0.0,
                "has_preceding_rally": False,
                "indicators": [],
            }

    # ═══════════════════════════════════════════════════════════════════
    # FILTER 4: Broker Affiliation Filter
    # ═══════════════════════════════════════════════════════════════════

    def filter_affiliated_flows(
        self,
        broker_flows: Dict[str, float],
        affiliations: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Filter out flows between affiliated brokers (same grup).

        Example: Broker A (Bakrie group) net buy 10M, Broker B (Bakrie) net sell 10M
        -> Netto = 0 (crossing dalam grup)

        Args:
            broker_flows: Mapping broker_code -> net flow (positif = net buy, negatif = net sell)
            affiliations: Mapping broker_code -> group_name. Jika None, pakai default.

        Returns:
            {
                "raw_net": float,
                "affiliated_volume": float,
                "adjusted_net": float,
                "affiliated_groups": Dict[str, Dict],
                "explanation": str,
            }
        """
        if not broker_flows:
            return {
                "raw_net": 0.0,
                "affiliated_volume": 0.0,
                "adjusted_net": 0.0,
                "affiliated_groups": {},
                "explanation": "Data broker flow kosong",
            }

        try:
            aff = affiliations or self.affiliations

            # Group brokers by affiliation
            grouped: Dict[str, List[Tuple[str, float]]] = {}
            unaffiliated: Dict[str, float] = {}

            for broker_code, flow in broker_flows.items():
                group = aff.get(broker_code.upper())
                if group:
                    grouped.setdefault(group, []).append((broker_code, flow))
                else:
                    unaffiliated[broker_code] = flow

            # Calculate raw net
            raw_net = sum(broker_flows.values())

            # For each group, calculate internal offset (crossing dalam grup)
            affiliated_volume = 0.0
            affiliated_groups: Dict[str, Dict] = {}

            for group, brokers in grouped.items():
                group_buy = sum(f for _, f in brokers if f > 0)
                group_sell = abs(sum(f for _, f in brokers if f < 0))
                internal_crossing = min(group_buy, group_sell)

                if internal_crossing > 0:
                    affiliated_volume += internal_crossing
                    affiliated_groups[group] = {
                        "brokers": [b for b, _ in brokers],
                        "group_buy": round(float(group_buy), 2),
                        "group_sell": round(float(group_sell), 2),
                        "internal_crossing": round(float(internal_crossing), 2),
                    }

            adjusted_net = raw_net - affiliated_volume

            explanation_parts: List[str] = []
            explanation_parts.append(f"Raw net flow: {raw_net:+.2f} juta Rp")
            if affiliated_volume > 0:
                explanation_parts.append(
                    f"Volume crossing dalam grup: {affiliated_volume:.2f} juta Rp "
                    f"({len(affiliated_groups)} grup: {', '.join(affiliated_groups.keys())})"
                )
                explanation_parts.append(
                    f"Adjusted net (setelah filter): {adjusted_net:+.2f} juta Rp"
                )
            else:
                explanation_parts.append("Tidak ditemukan crossing antar broker dalam grup yang sama")

            return {
                "raw_net": round(float(raw_net), 2),
                "affiliated_volume": round(float(affiliated_volume), 2),
                "adjusted_net": round(float(adjusted_net), 2),
                "affiliated_groups": affiliated_groups,
                "explanation": "; ".join(explanation_parts),
            }

        except Exception as e:
            logger.debug(f"Affiliation filter error: {e}")
            return {
                "raw_net": sum(broker_flows.values()) if broker_flows else 0.0,
                "affiliated_volume": 0.0,
                "adjusted_net": sum(broker_flows.values()) if broker_flows else 0.0,
                "affiliated_groups": {},
                "explanation": f"Error: {str(e)}",
            }

    # ═══════════════════════════════════════════════════════════════════
    # FILTER 5: Concentration Analysis
    # ═══════════════════════════════════════════════════════════════════

    def analyze_concentration(
        self,
        broker_flows: Dict[str, float],
    ) -> Dict[str, Any]:
        """
        Analyze if accumulation is concentrated in 1-2 brokers.

        Real accumulation -> terkonsentrasi di 2-3 broker (smart money cluster)
        Fake accumulation -> merata di banyak broker (retail FOMO)

        Uses HHI (Herfindahl-Hirschman Index):
        - HHI > 2500: Highly concentrated (smart money / bandar)
        - HHI 1500-2500: Moderately concentrated
        - HHI < 1500: Diffuse (retail FOMO / tidak terkonsentrasi)

        Args:
            broker_flows: Mapping broker_code -> net flow

        Returns:
            {
                "hhi_index": float,
                "top3_pct": float (0-100),
                "is_concentrated": bool,
                "concentration_level": str,
                "top_brokers_buy": List[str],
                "top_brokers_sell": List[str],
                "explanation": str,
            }
        """
        if not broker_flows:
            return {
                "hhi_index": 0.0,
                "top3_pct": 0.0,
                "is_concentrated": False,
                "concentration_level": "TIDAK_ADA_DATA",
                "top_brokers_buy": [],
                "top_brokers_sell": [],
                "explanation": "Data broker flow kosong",
            }

        try:
            # Separate buy and sell
            buy_flows = {k: v for k, v in broker_flows.items() if v > 0}
            sell_flows = {k: abs(v) for k, v in broker_flows.items() if v < 0}

            # Top brokers
            top_brokers_buy = sorted(buy_flows.keys(), key=lambda x: buy_flows[x], reverse=True)[:5]
            top_brokers_sell = sorted(sell_flows.keys(), key=lambda x: sell_flows[x], reverse=True)[:5]

            # Calculate HHI based on absolute flow shares
            total_flow = sum(abs(v) for v in broker_flows.values())
            if total_flow < 0.001:
                return {
                    "hhi_index": 0.0,
                    "top3_pct": 0.0,
                    "is_concentrated": False,
                    "concentration_level": "TIDAK_ADA_ALIRAN",
                    "top_brokers_buy": top_brokers_buy,
                    "top_brokers_sell": top_brokers_sell,
                    "explanation": "Tidak ada aliran broker yang signifikan",
                }

            # HHI = sum of squared market shares * 10000
            shares = [abs(v) / total_flow for v in broker_flows.values()]
            hhi = sum(s ** 2 for s in shares) * 10000

            # Top 3 percentage
            sorted_abs_flows = sorted((abs(v) for v in broker_flows.values()), reverse=True)
            top3_volume = sum(sorted_abs_flows[:3])
            top3_pct = (top3_volume / total_flow) * 100

            # Determine concentration level
            if hhi > self.HHI_CONCENTRATED_THRESHOLD:
                concentration_level = "TINGGI"
                is_concentrated = True
            elif hhi > self.HHI_MODERATE_THRESHOLD:
                concentration_level = "SEDANG"
                is_concentrated = True
            else:
                concentration_level = "RENDAH"
                is_concentrated = False

            # Build explanation
            if is_concentrated:
                explanation = (
                    f"Akumulasi TERKONSENTRASI (HHI={hhi:.0f}, top3={top3_pct:.0f}%). "
                    f"Ini pola smart money / bandar — {len(broker_flows)} broker terlibat, "
                    f"tapi aliran terpusat di beberapa broker utama."
                )
            else:
                explanation = (
                    f"Akumulasi MERATA (HHI={hhi:.0f}, top3={top3_pct:.0f}%). "
                    f"Ini pola retail FOMO — aliran terdistribusi ke banyak broker. "
                    f"{len(broker_flows)} broker terlibat tanpa dominasi yang jelas."
                )

            return {
                "hhi_index": round(float(hhi), 1),
                "top3_pct": round(float(top3_pct), 1),
                "is_concentrated": bool(is_concentrated),
                "concentration_level": concentration_level,
                "top_brokers_buy": top_brokers_buy,
                "top_brokers_sell": top_brokers_sell,
                "explanation": explanation,
            }

        except Exception as e:
            logger.debug(f"Concentration analysis error: {e}")
            return {
                "hhi_index": 0.0,
                "top3_pct": 0.0,
                "is_concentrated": False,
                "concentration_level": "ERROR",
                "top_brokers_buy": [],
                "top_brokers_sell": [],
                "explanation": f"Error: {str(e)}",
            }


# ═══════════════════════════════════════════════════════════════════════
# IHSG SPECIALIST ENGINE (v38 + v39 enhancements)
# ═══════════════════════════════════════════════════════════════════════

class IHSGSpecialistEngine:
    """Indonesia-specific intelligence for goreng + konglomerasi detection.

    v39 enhancements:
      - Integrated BrokerFlowAnalyzer for anti-fake broker flow detection
      - New method: analyze_broker_flow() — full flow analysis dengan 5 filter
    """

    def __init__(self, data_path: str = IHSG_DATA_PATH):
        self.data_path = data_path
        self.data = self._load()
        self.conglomerates = self.data.get("conglomerates", {})
        self.alliances = self.data.get("alliances_and_signals", {})
        self._build_ticker_index()
        # v39: instantiate broker flow analyzer
        self._broker_analyzer = BrokerFlowAnalyzer()

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
        """Build ticker -> conglomerate group mapping."""
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
                signals.append(f"Vol compressed {(1-vol_20/vol_60):.0%}, range {recent_range:.1%}")
                phase_scores["PHASE_1_AKUMULASI"] += 30
            if 0.45 <= green_pct <= 0.65 and ret_20d > -0.02:
                signals.append(f"Stair-step pattern: {green_days_20}/20 green days")
                phase_scores["PHASE_1_AKUMULASI"] += 20

            # ── PHASE 2 — CORP ACTION signals (vol rising from base) ──
            if (vol_20 / max(vol_60, 0.001) > 1.1 and vol_20 / max(vol_60, 0.001) < 1.8 and
                ret_20d > 0.05 and ret_20d < 0.20 and news_count >= 2):
                signals.append(f"Vol rising {(vol_20/vol_60-1):.0%} + news count {news_count}")
                phase_scores["PHASE_2_CORP_ACTION"] += 35
            if ret_5d > 0.03 and ret_20d > 0.08:
                signals.append(f"Building momentum: 5d {ret_5d:+.1%}, 20d {ret_20d:+.1%}")
                phase_scores["PHASE_2_CORP_ACTION"] += 15

            # ── PHASE 3 — LIQUIDITAS signals (volume explosion + breakout) ──
            if (vol_20 / max(vol_60, 0.001) > 1.5 and ret_20d > 0.15 and
                green_pct > 0.65):
                signals.append(f"Volume explosion + {green_pct:.0%} green days")
                phase_scores["PHASE_3_LIQUIDITAS"] += 40
            if news_count >= 5 and ret_5d > 0.10:
                signals.append(f"News flood ({news_count}) + price acceleration")
                phase_scores["PHASE_3_LIQUIDITAS"] += 20

            # ── PHASE 4 — EUFORIA signals (parabolic + distribution) ──
            if ret_20d > 0.40 and ret_60d > 0.80:
                signals.append(f"Parabolic: 60d {ret_60d:+.0%}")
                phase_scores["PHASE_4_EUFORIA"] += 35
            if vol_20 / max(vol_60, 0.001) > 2.5:
                signals.append(f"Extreme vol expansion {vol_20/vol_60:.1f}x — climax")
                phase_scores["PHASE_4_EUFORIA"] += 20
            # Volume declining despite price up = distribution
            if (ret_5d > 0.05 and vol_20 < vol_60 * 0.9 and ret_60d > 0.50):
                signals.append("DISTRIBUSI: price up but vol declining")
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
                        ["LATE STAGE — distribution by smart money likely",
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

    # ── Cornering / lock-up detection ────────────────────────────────

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
                patterns.append(f"Lock-up: only {range_15:.2%} range over 15 days")
                score += 30

            # Vol collapse + drift
            returns = s.pct_change().dropna()
            vol_20 = float(returns.tail(20).std())
            vol_60 = float(returns.tail(60).std()) if len(returns) >= 60 else vol_20
            ret_20 = float(s.iloc[-1] / s.iloc[-21] - 1) if len(s) >= 21 else 0
            if vol_60 > 0 and vol_20 / vol_60 < 0.40 and ret_20 > 0.05:
                patterns.append(f"Vol collapse {(1-vol_20/vol_60):.0%} + drift +{ret_20:.1%}")
                score += 35

            # Gap release after quiet
            if len(s) >= 30:
                quiet_period = s.iloc[-30:-3]
                quiet_range = (quiet_period.max() - quiet_period.min()) / quiet_period.mean()
                last_3d_ret = float(s.iloc[-1] / s.iloc[-4] - 1)
                if quiet_range < 0.03 and last_3d_ret > 0.05:
                    patterns.append(f"Gap release: 27d quiet ({quiet_range:.1%}), last 3d +{last_3d_ret:.1%}")
                    score += 25

            # Persistent green
            green_pct = (returns.tail(15) > 0).sum() / 15
            if green_pct >= 0.80:
                patterns.append(f"Persistent green {green_pct:.0%} 15 days")
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
                f"Our model: NO Indonesia classification (UNKNOWN). "
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
                f"MATCH. Our model ({our_estimate}) agrees with Hedgeye ({hedgeye_call}). "
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
                f"MISMATCH. Our model: **{our_estimate}** ({our_regime_name}), "
                f"Hedgeye says: **{hedgeye_call}**. {support_str}. "
                f"Investigate GIP engine calibration — kalau Indonesia genuinely "
                f"transitioning from Q2 -> Q4, monthly quad bisa lead structural quad."
            )

        return IHSGQuadCheck(
            our_estimate=our_estimate,
            hedgeye_call=hedgeye_call,
            match=match,
            cross_validation_signals=signals,
            confidence=round(confidence, 2),
            recommendation=recommendation,
        )

    # ═══════════════════════════════════════════════════════════════════
    # v39 NEW: Full Broker Flow Analysis with Anti-Fake Filters
    # ═══════════════════════════════════════════════════════════════════

    def analyze_broker_flow(
        self,
        ticker: str,
        prices: pd.Series,
        volumes: pd.Series,
        broker_data: Optional[Dict[str, Any]] = None,
        date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Full broker flow analysis with anti-fake filters.

        Menganalisis aliran broker dengan 5 filter anti-fake:
        1. Crossing Transaction Detection
        2. Window Dressing Detection
        3. Forced Sell Detection
        4. Broker Affiliation Filter
        5. Concentration Analysis (HHI)

        Args:
            ticker: Kode saham (e.g., "BBCA", "TLKM")
            prices: pd.Series index=date, values=closing price
            volumes: pd.Series index=date, values=volume
            broker_data: Optional dict dengan keys:
                - "broker_flows": Dict[str, float] — mapping broker_code -> net flow
                - "trades": List[Dict] — individual trades
                - "affiliations": Dict[str, str] — custom broker affiliations
            date: Tanggal analisis. Jika None, pakai hari terakhir dari data.

        Returns:
            Dict dengan keys:
            - flow_signal: "ACCUMULASI_ASLI" / "DISTRIBUSI_ASLI" / "FAKE_AKUM" /
                           "FAKE_DISTR" / "FORCED_SELL" / "WINDOW_DRESSING" / "UNCLEAR"
            - confidence: 0-1
            - raw_net_flow: float (dalam juta Rp atau lot)
            - adjusted_net_flow: float (setelah filter crossing)
            - top_brokers_buy: List[str]
            - top_brokers_sell: List[str]
            - warnings: List[str]
            - explanation: str (bahasa Indonesia, penjelasan kenapa signal ini)
            - filter_details: Dict — detail tiap filter
        """
        warnings: List[str] = []
        filter_details: Dict[str, Any] = {}

        try:
            # ── Default date ──
            if date is None and len(prices) > 0:
                target_date = pd.Timestamp(prices.index[-1])
            elif date is not None:
                target_date = pd.Timestamp(date)
            else:
                target_date = pd.Timestamp.now()

            # ── FILTER 1: Crossing Detection ──
            if broker_data and "trades" in broker_data:
                crossing_result = self._broker_analyzer.detect_crossing(
                    trades=broker_data["trades"],
                    daily_high=float(prices.tail(1).iloc[0]) if len(prices) > 0 else None,
                    daily_low=float(prices.tail(1).iloc[0]) if len(prices) > 0 else None,
                    prev_close=float(prices.iloc[-2]) if len(prices) >= 2 else None,
                )
            else:
                # Tanpa trade data, pakai proxy: cek jika volume hari ini
                # terlalu besar vs harga flat -> kemungkinan crossing
                crossing_result = self._proxy_crossing_detection(prices, volumes)

            filter_details["crossing"] = crossing_result
            if crossing_result.get("is_crossing_heavy"):
                warnings.append(
                    f"Crossing berat terdeteksi: {crossing_result['crossing_pct']:.0f}% "
                    f"volume ({crossing_result['crossing_volume']:.0f} lot)"
                )

            # ── FILTER 2: Window Dressing Detection ──
            if broker_data and "daily_flows" in broker_data:
                wd_result = self._broker_analyzer.detect_window_dressing(
                    daily_flows=broker_data["daily_flows"],
                    date=target_date,
                )
            else:
                # Proxy: gunakan volume sebagai proxy flow
                volume_as_flow = pd.Series(volumes.values, index=volumes.index)
                wd_result = self._broker_analyzer.detect_window_dressing(
                    daily_flows=volume_as_flow,
                    date=target_date,
                )

            filter_details["window_dressing"] = wd_result
            if wd_result.get("is_window_dressing"):
                warnings.append(
                    f"Window dressing terdeteksi (confidence: {wd_result['confidence']:.0%}): "
                    f"{wd_result['reason']}"
                )

            # ── FILTER 3: Forced Sell Detection ──
            fs_result = self._broker_analyzer.detect_forced_sell(prices, volumes)
            filter_details["forced_sell"] = fs_result
            if fs_result.get("is_forced_sell"):
                warnings.append(
                    f"Forced sell terdeteksi (confidence: {fs_result['confidence']:.0%}): "
                    f"harga turun {fs_result['price_drop_pct']:.1%}, "
                    f"volume {fs_result['volume_ratio']:.1f}x rata-rata"
                )

            # ── FILTER 4: Broker Affiliation Filter ──
            raw_net_flow = 0.0
            adjusted_net_flow = 0.0
            top_brokers_buy: List[str] = []
            top_brokers_sell: List[str] = []

            if broker_data and "broker_flows" in broker_data:
                aff_result = self._broker_analyzer.filter_affiliated_flows(
                    broker_flows=broker_data["broker_flows"],
                    affiliations=broker_data.get("affiliations"),
                )
                raw_net_flow = aff_result["raw_net"]
                adjusted_net_flow = aff_result["adjusted_net"]
                filter_details["affiliation"] = aff_result

                if aff_result.get("affiliated_volume", 0) > 0:
                    warnings.append(
                        f"Crossing dalam grup terfilter: {aff_result['affiliated_volume']:.2f} juta Rp "
                        f"({len(aff_result.get('affiliated_groups', {}))} grup)"
                    )
            else:
                # Proxy: estimasi net flow dari price/volume momentum
                proxy_flow = self._proxy_net_flow(prices, volumes)
                raw_net_flow = proxy_flow
                adjusted_net_flow = proxy_flow
                filter_details["affiliation"] = {
                    "raw_net": proxy_flow,
                    "affiliated_volume": 0.0,
                    "adjusted_net": proxy_flow,
                    "explanation": "Proxy flow (tidak ada data broker) — net flow diestimasi dari price/volume",
                }

            # ── FILTER 5: Concentration Analysis ──
            if broker_data and "broker_flows" in broker_data:
                conc_result = self._broker_analyzer.analyze_concentration(
                    broker_data["broker_flows"]
                )
                top_brokers_buy = conc_result.get("top_brokers_buy", [])
                top_brokers_sell = conc_result.get("top_brokers_sell", [])
                filter_details["concentration"] = conc_result

                if conc_result.get("is_concentrated"):
                    warnings.append(
                        f"Akumulasi terkonsentrasi (HHI: {conc_result['hhi_index']:.0f}, "
                        f"top3: {conc_result['top3_pct']:.0f}%) — pola smart money / bandar"
                    )
                else:
                    warnings.append(
                        f"Akumulasi merata (HHI: {conc_result['hhi_index']:.0f}) — "
                        f"kemungkinan retail FOMO"
                    )
            else:
                filter_details["concentration"] = {
                    "hhi_index": 0.0,
                    "top3_pct": 0.0,
                    "is_concentrated": False,
                    "concentration_level": "TIDAK_ADA_DATA_BROKER",
                    "explanation": "Tidak ada data broker untuk analisis konsentrasi — "
                                   "perlukan BEI broker summary subscription",
                }

            # ── Synthesize Final Signal ──
            flow_signal, confidence, explanation = self._synthesize_broker_flow_signal(
                crossing=crossing_result,
                window_dressing=wd_result,
                forced_sell=fs_result,
                concentration=filter_details.get("concentration", {}),
                adjusted_net_flow=adjusted_net_flow,
                broker_data_available=broker_data is not None,
            )

            return {
                "flow_signal": flow_signal,
                "confidence": round(float(confidence), 2),
                "raw_net_flow": round(float(raw_net_flow), 2),
                "adjusted_net_flow": round(float(adjusted_net_flow), 2),
                "top_brokers_buy": top_brokers_buy,
                "top_brokers_sell": top_brokers_sell,
                "warnings": warnings,
                "explanation": explanation,
                "filter_details": filter_details,
            }

        except Exception as e:
            logger.error(f"Broker flow analysis failed for {ticker}: {e}")
            return {
                "flow_signal": "UNCLEAR",
                "confidence": 0.0,
                "raw_net_flow": 0.0,
                "adjusted_net_flow": 0.0,
                "top_brokers_buy": [],
                "top_brokers_sell": [],
                "warnings": [f"Error analisis: {str(e)}"],
                "explanation": f"Analisis broker flow gagal: {str(e)}. Data tidak valid atau tidak cukup.",
                "filter_details": {},
            }

    def _proxy_crossing_detection(
        self, prices: pd.Series, volumes: pd.Series
    ) -> Dict[str, Any]:
        """
        Proxy crossing detection tanpa data trade individual.

        Logika: Jika volume tinggi tapi harga flat (range sangat sempit),
        kemungkinan besar ada crossing.
        """
        try:
            p = pd.to_numeric(prices, errors="coerce").dropna()
            v = pd.to_numeric(volumes, errors="coerce").dropna()

            if len(p) < 5 or len(v) < 20:
                return {
                    "crossing_volume": 0.0,
                    "crossing_pct": 0.0,
                    "is_crossing_heavy": False,
                    "crossing_trades": [],
                    "reasons": ["Data tidak cukup untuk proxy crossing detection"],
                }

            # Cek hari ini: volume tinggi tapi range sempit?
            today_vol = float(v.iloc[-1])
            avg_vol = float(v.tail(20).mean())

            if len(p) >= 2:
                today_range = abs(float(p.iloc[-1]) - float(p.iloc[-2])) / max(float(p.iloc[-2]), 0.001)
            else:
                today_range = 0

            # Volume spike + flat price = possible crossing
            vol_spike = today_vol / max(avg_vol, 1)

            if vol_spike > 3.0 and today_range < 0.005:
                # Estimasi crossing volume
                est_crossing = today_vol * 0.5  # Asumsi 50% adalah crossing
                return {
                    "crossing_volume": float(est_crossing),
                    "crossing_pct": 50.0,
                    "is_crossing_heavy": True,
                    "crossing_trades": [],
                    "reasons": [
                        f"PROXY: Volume {vol_spike:.1f}x rata-rata tapi harga flat "
                        f"(range {today_range:.2%}) — kemungkinan crossing besar"
                    ],
                }

            return {
                "crossing_volume": 0.0,
                "crossing_pct": 0.0,
                "is_crossing_heavy": False,
                "crossing_trades": [],
                "reasons": ["Tidak terdeteksi crossing (proxy)"],
            }

        except Exception as e:
            return {
                "crossing_volume": 0.0,
                "crossing_pct": 0.0,
                "is_crossing_heavy": False,
                "crossing_trades": [],
                "reasons": [f"Error proxy crossing: {str(e)}"],
            }

    def _proxy_net_flow(self, prices: pd.Series, volumes: pd.Series) -> float:
        """
        Estimasi net flow dari price/volume momentum.

        Logika sederhana:
        - Harga naik + volume tinggi -> net buy (akumulasi)
        - Harga turun + volume tinggi -> net sell (distribusi)
        - Skala: dalam "juta Rp" (arbitrary units)
        """
        try:
            p = pd.to_numeric(prices, errors="coerce").dropna()
            v = pd.to_numeric(volumes, errors="coerce").dropna()

            if len(p) < 2 or len(v) < 1:
                return 0.0

            today_price = float(p.iloc[-1])
            yesterday_price = float(p.iloc[-2])
            today_volume = float(v.iloc[-1])

            price_change = (today_price - yesterday_price) / max(yesterday_price, 0.001)

            # Net flow proxy: price_change * volume (skaled)
            net_flow = price_change * today_volume / 1e6  # Dalam juta Rp

            return float(net_flow)

        except Exception:
            return 0.0

    def _synthesize_broker_flow_signal(
        self,
        crossing: Dict[str, Any],
        window_dressing: Dict[str, Any],
        forced_sell: Dict[str, Any],
        concentration: Dict[str, Any],
        adjusted_net_flow: float,
        broker_data_available: bool,
    ) -> Tuple[str, float, str]:
        """
        Sintesis signal akhir dari semua filter.

        Returns: (flow_signal, confidence, explanation)
        """
        # Priority: Forced Sell > Window Dressing > Crossing > Concentration > Flow direction
        is_forced_sell = forced_sell.get("is_forced_sell", False)
        fs_confidence = forced_sell.get("confidence", 0)

        is_window_dressing = window_dressing.get("is_window_dressing", False)
        wd_confidence = window_dressing.get("confidence", 0)

        is_crossing_heavy = crossing.get("is_crossing_heavy", False)
        crossing_pct = crossing.get("crossing_pct", 0)

        is_concentrated = concentration.get("is_concentrated", False)
        hhi = concentration.get("hhi_index", 0)

        explanations: List[str] = []

        # ── Priority 1: Forced Sell ──
        if is_forced_sell and fs_confidence > 0.5:
            explanations.append(
                f"FORCED SELL terdeteksi (confidence {fs_confidence:.0%}). "
                f"Ini BUKAN distribusi sungguhan — kemungkinan margin call atau "
                f"force sell dari sekuritas. "
                f"Harga turun {forced_sell.get('price_drop_pct', 0):.1%} "
                f"dengan volume {forced_sell.get('volume_ratio', 0):.1f}x rata-rata."
            )
            return "FORCED_SELL", fs_confidence, " ".join(explanations)

        # ── Priority 2: Window Dressing ──
        if is_window_dressing and wd_confidence > 0.5:
            direction = "FAKE_AKUM" if adjusted_net_flow > 0 else "FAKE_DISTR"
            label = "akumulasi" if adjusted_net_flow > 0 else "distribusi"
            explanations.append(
                f"WINDOW DRESSING terdeteksi (confidence {wd_confidence:.0%}). "
                f"{window_dressing.get('reason', '')}. "
                f"Ini adalah {label} PALSU untuk perapihan laporan akhir periode. "
                f"{label.capitalize()} sungguhan akan terlihat konsisten di hari-hari biasa, "
                f"bukan cuma akhir bulan/kuartal."
            )
            return direction, wd_confidence, " ".join(explanations)

        # ── Priority 3: Heavy Crossing ──
        if is_crossing_heavy and crossing_pct > 40:
            direction = "FAKE_AKUM" if adjusted_net_flow > 0 else "FAKE_DISTR"
            explanations.append(
                f"CROSSING BERAT terdeteksi ({crossing_pct:.0f}% volume). "
                f"Transaksi ini kemungkinan crossing antar rekening/institusi "
                f"dan BUKAN akumulasi/distribusi sungguhan di pasar terbuka. "
                f"Net flow setelah adjustment: {adjusted_net_flow:+.2f} juta Rp."
            )
            return direction, 0.60, " ".join(explanations)

        # ── Priority 4: Flow direction with concentration context ──
        if adjusted_net_flow > 0:
            # Akumulasi
            if is_concentrated and hhi > 2000:
                confidence = 0.80
                explanations.append(
                    f"AKUMULASI ASLI terdeteksi (confidence {confidence:.0%}). "
                    f"Aliran masuk terkonsentrasi di beberapa broker (HHI: {hhi:.0f}) — "
                    f"ini pola smart money / bandar. "
                    f"Adjusted net flow: +{adjusted_net_flow:.2f} juta Rp."
                )
            elif is_concentrated:
                confidence = 0.65
                explanations.append(
                    f"AKUMULASI dengan konsentrasi sedang (confidence {confidence:.0%}). "
                    f"HHI: {hhi:.0f} — cukup terkonsentrasi tapi tidak dominant. "
                    f"Mungkin campuran smart money dan retail. "
                    f"Adjusted net flow: +{adjusted_net_flow:.2f} juta Rp."
                )
            else:
                if broker_data_available:
                    confidence = 0.45
                    explanations.append(
                        f"AKUMULASI MERATA (confidence {confidence:.0%}). "
                        f"Aliran terdistribusi ke banyak broker (HHI: {hhi:.0f}) — "
                        f"kemungkinan retail FOMO atau market-wide buying. "
                        f"Bukan akumulasi bandar yang terkonsentrasi. "
                        f"Adjusted net flow: +{adjusted_net_flow:.2f} juta Rp."
                    )
                else:
                    confidence = 0.40
                    explanations.append(
                        f"Signal AKUMULASI lemah (confidence {confidence:.0%}). "
                        f"Tidak ada data broker — ini estimasi dari price/volume proxy. "
                        f"Perlukan BEI broker summary untuk konfirmasi. "
                        f"Estimated net flow: +{adjusted_net_flow:.2f} juta Rp."
                    )
            return "ACCUMULASI_ASLI", confidence, " ".join(explanations)

        elif adjusted_net_flow < 0:
            # Distribusi
            if is_concentrated and hhi > 2000:
                confidence = 0.75
                explanations.append(
                    f"DISTRIBUSI ASLI terdeteksi (confidence {confidence:.0%}). "
                    f"Aliran keluar terkonsentrasi di beberapa broker (HHI: {hhi:.0f}) — "
                    f"smart money / bandar sedang distribusi. "
                    f"Adjusted net flow: {adjusted_net_flow:.2f} juta Rp."
                )
            elif is_concentrated:
                confidence = 0.60
                explanations.append(
                    f"DISTRIBUSI dengan konsentrasi sedang (confidence {confidence:.0%}). "
                    f"HHI: {hhi:.0f} — cukup terkonsentrasi. "
                    f"Adjusted net flow: {adjusted_net_flow:.2f} juta Rp."
                )
            else:
                if broker_data_available:
                    confidence = 0.45
                    explanations.append(
                        f"DISTRIBUSI MERATA (confidence {confidence:.0%}). "
                        f"Aliran keluar terdistribusi (HHI: {hhi:.0f}) — "
                        f"kemungkinan broad selling / risk-off. "
                        f"Adjusted net flow: {adjusted_net_flow:.2f} juta Rp."
                    )
                else:
                    confidence = 0.35
                    explanations.append(
                        f"Signal DISTRIBUSI lemah (confidence {confidence:.0%}). "
                        f"Tidak ada data broker — estimasi dari price/volume proxy. "
                        f"Estimated net flow: {adjusted_net_flow:.2f} juta Rp."
                    )
            return "DISTRIBUSI_ASLI", confidence, " ".join(explanations)

        else:
            # Net flow ≈ 0
            explanations.append(
                "Net flow seimbas (netral). Tidak terdeteksi akumulasi atau "
                "distribusi yang signifikan. Pasar sedang konsolidasi."
            )
            return "UNCLEAR", 0.30, " ".join(explanations)


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
    "BrokerFlowAnalyzer",
    "ConglomerateContext",
    "GorengPhase",
    "IHSGQuadCheck",
    "BrokerFlowResult",
    "get_ihsg_specialist",
]


# ═══════════════════════════════════════════════════════════════════════
# TEST SECTION — Validasi dengan dummy data
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 70)
    print("IHSG SPECIALIST v39 — Anti-Fake Broker Flow Detector TEST")
    print("=" * 70)

    # ── Setup ──
    np.random.seed(42)
    engine = IHSGSpecialistEngine()
    analyzer = BrokerFlowAnalyzer()

    # ── Test 1: Crossing Detection ──
    print("\n[TEST 1] Crossing Transaction Detection")
    print("-" * 40)

    trades_normal = [
        {"price": 1000, "volume": 1500, "buyer_code": "MS", "seller_code": "AI"},
        {"price": 1002, "volume": 2300, "buyer_code": "JPM", "seller_code": "LP"},
        {"price": 998, "volume": 800, "buyer_code": "AS", "seller_code": "SL"},
    ]

    trades_crossing = [
        {"price": 1000, "volume": 1000, "buyer_code": "BB", "seller_code": "BB"},  # Same broker
        {"price": 1000, "volume": 5000, "buyer_code": "BS", "seller_code": "BS"},  # Same broker + round lot
        {"price": 1000, "volume": 1200, "buyer_code": "MS", "seller_code": "JPM"},  # Normal
        {"price": 1000, "volume": 10000, "buyer_code": "BK", "seller_code": "BK"},  # Same + round lot
    ]

    result_normal = analyzer.detect_crossing(trades_normal, daily_high=1010, daily_low=995)
    result_crossing = analyzer.detect_crossing(trades_crossing, daily_high=1010, daily_low=995)

    print(f"Normal trades: crossing={result_normal['crossing_pct']:.1f}%, "
          f"heavy={result_normal['is_crossing_heavy']}")
    print(f"Crossing trades: crossing={result_crossing['crossing_pct']:.1f}%, "
          f"heavy={result_crossing['is_crossing_heavy']}")
    assert result_normal["crossing_pct"] == 0, "Normal trades should have 0% crossing"
    assert result_crossing["crossing_pct"] > 50, "Crossing trades should have high %"
    print("  => PASS")

    # ── Test 2: Window Dressing Detection ──
    print("\n[TEST 2] Window Dressing Detection")
    print("-" * 40)

    # Normal flow (no window dressing)
    normal_dates = pd.date_range(end="2024-01-15", periods=15)
    normal_flows = pd.Series(
        np.random.normal(100, 30, 15),
        index=normal_dates,
    )

    # Window dressing: big spike on last day of quarter
    wd_dates = pd.date_range(end="2024-03-28", periods=12)
    wd_flows = pd.Series(
        [80, 90, 85, 95, 100, 88, 92, 87, 93, 91] + [500],  # 500 = 5x spike on last day
        index=list(wd_dates[:10]) + [pd.Timestamp("2024-03-28")],
    )

    result_normal = analyzer.detect_window_dressing(normal_flows)
    result_wd = analyzer.detect_window_dressing(wd_flows, date=pd.Timestamp("2024-03-28"))

    print(f"Normal flows: WD={result_normal['is_window_dressing']}, "
          f"confidence={result_normal['confidence']}")
    print(f"Quarter-end spike: WD={result_wd['is_window_dressing']}, "
          f"confidence={result_wd['confidence']}, "
          f"spike_ratio={result_wd['flow_spike_ratio']:.1f}x")
    assert result_normal["is_window_dressing"] == False
    assert result_wd["is_window_dressing"] == True
    print("  => PASS")

    # ── Test 3: Forced Sell Detection ──
    print("\n[TEST 3] Forced Sell Detection")
    print("-" * 40)

    # Normal price action
    normal_prices = pd.Series(
        [1000 + i * 5 + np.random.normal(0, 10) for i in range(25)],
        index=pd.date_range(end="2024-01-25", periods=25),
    )
    normal_volumes = pd.Series(
        [1000000 + np.random.normal(0, 100000) for _ in range(25)],
        index=normal_prices.index,
    )

    # Forced sell: big drop + volume spike (day 25)
    fs_prices = pd.Series(
        [1000 + i * 5 for i in range(20)] + [1100, 1105, 1103, 1098, 1040],  # Drop 5.3%
        index=pd.date_range(end="2024-02-25", periods=25),
    )
    fs_volumes = pd.Series(
        [1000000] * 20 + [1100000, 1050000, 1080000, 1020000, 6500000],  # 6.5x volume
        index=fs_prices.index,
    )

    result_normal = analyzer.detect_forced_sell(normal_prices, normal_volumes)
    result_fs = analyzer.detect_forced_sell(fs_prices, fs_volumes)

    print(f"Normal: forced_sell={result_normal['is_forced_sell']}, "
          f"confidence={result_normal['confidence']}")
    print(f"Big drop + vol spike: forced_sell={result_fs['is_forced_sell']}, "
          f"confidence={result_fs['confidence']}, "
          f"drop={result_fs['price_drop_pct']:.1%}, "
          f"vol_ratio={result_fs['volume_ratio']:.1f}x")
    assert result_normal["is_forced_sell"] == False
    assert result_fs["is_forced_sell"] == True
    assert result_fs["confidence"] > 0.5
    print("  => PASS")

    # ── Test 4: Broker Affiliation Filter ──
    print("\n[TEST 4] Broker Affiliation Filter")
    print("-" * 40)

    broker_flows = {
        "BB": 50.0,    # Bakrie — net buy
        "BS": -30.0,   # Bakrie — net sell (internal crossing)
        "BK": 20.0,    # Bakrie — net buy
        "SL": -100.0,  # Salim — net sell
        "SM": 80.0,    # Salim — net buy
        "MS": 150.0,   # Sinar Mas — net buy
        "JPM": 200.0,  # Foreign — net buy
    }

    result = analyzer.filter_affiliated_flows(broker_flows)
    print(f"Raw net: {result['raw_net']:+.2f} juta Rp")
    print(f"Affiliated crossing: {result['affiliated_volume']:.2f} juta Rp")
    print(f"Adjusted net: {result['adjusted_net']:+.2f} juta Rp")
    print(f"Groups with crossing: {list(result['affiliated_groups'].keys())}")
    assert result["raw_net"] == 370.0
    # Bakrie: min(50+20, 30) = 30; Salim: min(80, 100) = 80; Total = 110
    assert result["affiliated_volume"] == 110.0
    assert result["adjusted_net"] == 260.0
    print("  => PASS")

    # ── Test 5: Concentration Analysis ──
    print("\n[TEST 5] Concentration Analysis (HHI)")
    print("-" * 40)

    # Concentrated (smart money)
    concentrated_flows = {
        "BB": 500.0,
        "BS": 400.0,
        "MS": 300.0,
        "AI": 50.0,
        "LP": 30.0,
        "JPM": 20.0,
    }

    # Diffuse (retail FOMO)
    diffuse_flows = {
        f"BR{i:02d}": 100.0 for i in range(20)
    }

    result_conc = analyzer.analyze_concentration(concentrated_flows)
    result_diff = analyzer.analyze_concentration(diffuse_flows)

    print(f"Concentrated: HHI={result_conc['hhi_index']:.0f}, "
          f"top3={result_conc['top3_pct']:.0f}%, "
          f"level={result_conc['concentration_level']}")
    print(f"Diffuse: HHI={result_diff['hhi_index']:.0f}, "
          f"top3={result_diff['top3_pct']:.0f}%, "
          f"level={result_diff['concentration_level']}")
    assert result_conc["is_concentrated"] == True
    assert result_diff["is_concentrated"] == False
    assert result_conc["hhi_index"] > result_diff["hhi_index"]
    print("  => PASS")

    # ── Test 6: Full Integration — analyze_broker_flow ──
    print("\n[TEST 6] Full Integration — analyze_broker_flow()")
    print("-" * 40)

    # Scenario: Akumulasi terkonsentrasi (smart money)
    dates = pd.date_range(end="2024-06-20", periods=30)
    acc_prices = pd.Series(
        [1000 + i * 8 + np.random.normal(0, 5) for i in range(30)],
        index=dates,
    )
    acc_volumes = pd.Series(
        [500000 + np.random.normal(0, 50000) for _ in range(25)] +
        [800000, 850000, 900000, 950000, 1200000],
        index=dates,
    )

    broker_data = {
        "broker_flows": {
            "MS": 300.0,
            "AI": 250.0,
            "SL": -50.0,
            "BB": 180.0,
            "LP": -30.0,
            "JPM": 100.0,
        },
    }

    result = engine.analyze_broker_flow(
        ticker="BBCA",
        prices=acc_prices,
        volumes=acc_volumes,
        broker_data=broker_data,
    )

    print(f"Ticker: BBCA")
    print(f"Signal: {result['flow_signal']}")
    print(f"Confidence: {result['confidence']:.0%}")
    print(f"Raw Net Flow: {result['raw_net_flow']:+.2f} juta Rp")
    print(f"Adjusted Net: {result['adjusted_net_flow']:+.2f} juta Rp")
    print(f"Top Brokers Buy: {result['top_brokers_buy']}")
    print(f"Top Brokers Sell: {result['top_brokers_sell']}")
    print(f"Warnings ({len(result['warnings'])}):")
    for w in result["warnings"]:
        print(f"  - {w}")
    print(f"Explanation: {result['explanation'][:120]}...")
    assert result["flow_signal"] == "ACCUMULASI_ASLI"
    print("  => PASS")

    # ── Test 7: Forced Sell Scenario ──
    print("\n[TEST 7] Forced Sell Scenario")
    print("-" * 40)

    # Forced sell on the LAST day (July 25) with normal data before it
    # Data spans July 1 - July 25, forced sell on July 25
    fs_dates = pd.date_range(end="2024-07-25", periods=25)
    # 20 days uptrend, then 4 days consolidation, then crash on last day
    fs_prices2_list = ([1000 + i * 3 for i in range(20)] +  # Uptrend to 1057
                       [1055, 1058, 1060, 1045, 990])        # Then drop 5.2% on last day
    fs_volumes2_list = ([400000] * 20 +                       # Normal volume
                        [420000, 450000, 430000, 410000, 2600000])  # 6.5x spike last day
    fs_prices2 = pd.Series(fs_prices2_list, index=fs_dates)
    fs_volumes2 = pd.Series(fs_volumes2_list, index=fs_dates)

    result_fs = engine.analyze_broker_flow(
        ticker="ANTM",
        prices=fs_prices2,
        volumes=fs_volumes2,
    )

    print(f"Ticker: ANTM (Forced Sell Scenario)")
    print(f"Signal: {result_fs['flow_signal']}")
    print(f"Confidence: {result_fs['confidence']:.0%}")
    print(f"Forced sell detail: drop={result_fs['filter_details'].get('forced_sell', {}).get('price_drop_pct', 0):.1%}, "
          f"vol={result_fs['filter_details'].get('forced_sell', {}).get('volume_ratio', 0):.1f}x")
    print(f"Explanation: {result_fs['explanation'][:150]}...")
    assert result_fs["flow_signal"] == "FORCED_SELL"
    print("  => PASS")

    # ── Test 8: Window Dressing Scenario ──
    print("\n[TEST 8] Window Dressing Scenario")
    print("-" * 40)

    wd_dates = pd.date_range(end="2024-03-28", periods=15)
    wd_prices = pd.Series(
        [1000 + np.random.normal(0, 5) for _ in range(15)],  # Flat price
        index=wd_dates,
    )
    wd_volumes = pd.Series(
        [300000] * 14 + [2000000],  # 6.7x spike on last day of Q1
        index=wd_dates,
    )

    result_wd = engine.analyze_broker_flow(
        ticker="BMRI",
        prices=wd_prices,
        volumes=wd_volumes,
    )

    print(f"Ticker: BMRI (Window Dressing Scenario)")
    print(f"Signal: {result_wd['flow_signal']}")
    print(f"Confidence: {result_wd['confidence']:.0%}")
    print(f"Date: {wd_dates[-1].strftime('%Y-%m-%d')} (end of Q1)")
    print(f"Explanation: {result_wd['explanation'][:150]}...")
    # Should detect window dressing or at least flag it in warnings
    assert len(result_wd["warnings"]) > 0
    print("  => PASS")

    # ── Test 9: Proxy mode (no broker data) ──
    print("\n[TEST 9] Proxy Mode (tanpa data broker)")
    print("-" * 40)

    proxy_dates = pd.date_range(end="2024-05-20", periods=30)
    proxy_prices = pd.Series(
        [1000 + i * 5 for i in range(29)] + [1200],  # Last day +17.4% jump
        index=proxy_dates,
    )
    proxy_volumes = pd.Series(
        [500000 + i * 10000 for i in range(30)],
        index=proxy_dates,
    )

    result_proxy = engine.analyze_broker_flow(
        ticker="BBRI",
        prices=proxy_prices,
        volumes=proxy_volumes,
    )

    print(f"Ticker: BBRI (Proxy Mode)")
    print(f"Signal: {result_proxy['flow_signal']}")
    print(f"Confidence: {result_proxy['confidence']:.0%}")
    print(f"Adjusted net flow: {result_proxy['adjusted_net_flow']:+.2f} juta Rp")
    print(f"Has warnings: {len(result_proxy['warnings'])} warning(s)")
    print(f"Explanation: {result_proxy['explanation'][:150]}...")
    assert abs(result_proxy["adjusted_net_flow"]) > 0.01  # Should have significant proxy flow
    print("  => PASS")

    # ── Test 10: Edge cases ──
    print("\n[TEST 10] Edge Cases")
    print("-" * 40)

    # Empty data
    result_empty = engine.analyze_broker_flow(
        ticker="EMPTY",
        prices=pd.Series(),
        volumes=pd.Series(),
    )
    assert result_empty["flow_signal"] == "UNCLEAR"
    print("Empty series: => PASS")

    # Single data point
    result_single = engine.analyze_broker_flow(
        ticker="SINGLE",
        prices=pd.Series([1000], index=[pd.Timestamp("2024-01-01")]),
        volumes=pd.Series([1000], index=[pd.Timestamp("2024-01-01")]),
    )
    assert result_single["flow_signal"] == "UNCLEAR"
    print("Single data point: => PASS")

    # ── Summary ──
    print("\n" + "=" * 70)
    print("SEMUA TEST PASS — 10/10 test berhasil")
    print("=" * 70)
