"""engines/yves_engine.py — Yves Lamoureux Behavioral Extremes v39

Exact Yves Methodology:
  Casino Mode: AAII bull > 90th percentile AND VIX < 20th percentile AND PCR < 0.85
  Capitulation: AAII bear > 90th percentile AND VIX > 80th percentile AND PCR > 1.2

  Thresholds are PERCENTILE-BASED, not absolute:
    - 50% bull might be top decile in bear market but median in bull market
    - Must compare vs historical distribution

  Contrarian at extremes:
    Casino = SELL signal (extreme bullish + low fear)
    Capitulation = BUY signal (extreme bearish + high fear)

Returns:
  {
    "signal": "CASINO" | "CAPITULATION" | "NEUTRAL",
    "direction": "SELL" | "BUY" | "NEUTRAL",
    "confidence": 0-100,
    "percentiles": {"bull": 95, "bear": 5, "vix": 15, "pcr": 30},
    "reason": "AAII bull at 95th percentile + VIX at 15th percentile = Casino mode"
  }
"""
from __future__ import annotations
import logging
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

def calculate_percentile(value: float, history: List[float]) -> float:
    """Calculate percentile of value in historical distribution."""
    if not history:
        return 50.0
    sorted_hist = sorted(history)
    n = len(sorted_hist)
    # Find position
    pos = sum(1 for x in sorted_hist if x < value)
    # Handle exact match
    exact = sum(1 for x in sorted_hist if x == value)
    percentile = (pos + exact / 2) / n * 100
    return min(100, max(0, percentile))

def yves_signal(
    aaii_bull: float,
    aaii_bear: float,
    vix: float,
    put_call_ratio: float,
    history: Optional[Dict[str, List[float]]] = None,
) -> Dict:
    """Generate Yves behavioral signal with percentile-based thresholds."""

    # Default history (fallback if no history provided)
    if history is None:
        history = {
            "aaii_bull": [20, 25, 30, 35, 40, 45, 50, 55, 60],
            "aaii_bear": [15, 20, 25, 30, 35, 40, 45, 50, 55],
            "vix": [10, 12, 14, 16, 18, 20, 22, 25, 28, 32, 38],
            "pcr": [0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5],
        }

    # Calculate percentiles
    bull_pct = calculate_percentile(aaii_bull, history.get("aaii_bull", [50]))
    bear_pct = calculate_percentile(aaii_bear, history.get("aaii_bear", [50]))
    vix_pct = calculate_percentile(vix, history.get("vix", [20]))
    pcr_pct = calculate_percentile(put_call_ratio, history.get("pcr", [1.0]))

    # Casino Mode: extreme bullish + low fear
    if bull_pct > 90 and vix_pct < 20 and put_call_ratio < 0.85:
        confidence = min(100, (bull_pct - 90) * 2 + (20 - vix_pct) * 2)
        return {
            "signal": "CASINO",
            "direction": "SELL",
            "confidence": round(confidence, 1),
            "percentiles": {
                "bull": round(bull_pct, 1),
                "bear": round(bear_pct, 1),
                "vix": round(vix_pct, 1),
                "pcr": round(pcr_pct, 1),
            },
            "reason": f"AAII bull at {bull_pct:.0f}th percentile + VIX at {vix_pct:.0f}th percentile + PCR {put_call_ratio:.2f} = CASINO MODE (contrarian SELL)",
            "raw": {"aaii_bull": aaii_bull, "aaii_bear": aaii_bear, "vix": vix, "pcr": put_call_ratio},
        }

    # Capitulation: extreme bearish + high fear
    if bear_pct > 90 and vix_pct > 80 and put_call_ratio > 1.2:
        confidence = min(100, (bear_pct - 90) * 2 + (vix_pct - 80) * 2)
        return {
            "signal": "CAPITULATION",
            "direction": "BUY",
            "confidence": round(confidence, 1),
            "percentiles": {
                "bull": round(bull_pct, 1),
                "bear": round(bear_pct, 1),
                "vix": round(vix_pct, 1),
                "pcr": round(pcr_pct, 1),
            },
            "reason": f"AAII bear at {bear_pct:.0f}th percentile + VIX at {vix_pct:.0f}th percentile + PCR {put_call_ratio:.2f} = CAPITULATION (contrarian BUY)",
            "raw": {"aaii_bull": aaii_bull, "aaii_bear": aaii_bear, "vix": vix, "pcr": put_call_ratio},
        }

    # Neutral
    return {
        "signal": "NEUTRAL",
        "direction": "NEUTRAL",
        "confidence": 0,
        "percentiles": {
            "bull": round(bull_pct, 1),
            "bear": round(bear_pct, 1),
            "vix": round(vix_pct, 1),
            "pcr": round(pcr_pct, 1),
        },
        "reason": f"No extreme sentiment: bull {bull_pct:.0f}th pct, bear {bear_pct:.0f}th pct, vix {vix_pct:.0f}th pct",
        "raw": {"aaii_bull": aaii_bull, "aaii_bear": aaii_bear, "vix": vix, "pcr": put_call_ratio},
    }

def yves_batch(sentiment_data: Dict[str, dict], history: Optional[Dict] = None) -> Dict[str, Dict]:
    """Batch process Yves signals for multiple tickers."""
    results = {}
    for ticker, data in sentiment_data.items():
        results[ticker] = yves_signal(
            aaii_bull=data.get("aaii_bull", 30),
            aaii_bear=data.get("aaii_bear", 30),
            vix=data.get("vix", 20),
            put_call_ratio=data.get("pcr", 1.0),
            history=history,
        )
    return results
