"""engines/aaii_scraper.py — Live AAII Sentiment + Yves Lamoureux Proxy"""
from __future__ import annotations
import re, json, math, logging
from datetime import datetime, timedelta
from typing import Dict, Optional
import pandas as pd
import numpy as np

logger = logging.getLogger("aaii_scraper")

try:
    import requests
    _HAS_REQUESTS = True
except Exception:
    _HAS_REQUESTS = False

_AAII_CACHE: Optional[Dict] = None
_AAII_CACHE_TIME: Optional[datetime] = None

def _fetch_aaii_live() -> Optional[Dict]:
    if not _HAS_REQUESTS:
        return None
    try:
        r = requests.get("https://www.aaii.com/sentiment/survey", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code == 200:
            text = r.text
            bull_match = re.search(r'Bullish.*?(\d+\.?\d*)%', text, re.S)
            bear_match = re.search(r'Bearish.*?(\d+\.?\d*)%', text, re.S)
            neut_match = re.search(r'Neutral.*?(\d+\.?\d*)%', text, re.S)
            if bull_match and bear_match:
                return {
                    "bullish": float(bull_match.group(1)),
                    "bearish": float(bear_match.group(1)),
                    "neutral": float(neut_match.group(1)) if neut_match else 0.0,
                    "source": "AAII_WEB",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                }
    except Exception as e:
        logger.debug(f"AAII web scrape failed: {e}")
    return None

def _aaii_proxy(vix: float, put_call_ratio: float = 1.0, dxy_ret: float = 0.0) -> Dict:
    fear = max(0, min(100, (35 - vix) / 35 * 100))
    if put_call_ratio > 1.2:
        fear += 15
    elif put_call_ratio < 0.8:
        fear -= 15
    if dxy_ret > 0.02:
        fear += 10
    fear = max(10, min(90, fear))
    bullish = max(5, min(70, 55 - fear * 0.4))
    bearish = max(5, min(70, 20 + fear * 0.5))
    neutral = max(0, 100 - bullish - bearish)
    total = bullish + bearish + neutral
    return {
        "bullish": round(bullish / total * 100, 1),
        "bearish": round(bearish / total * 100, 1),
        "neutral": round(neutral / total * 100, 1),
        "source": "PROXY_VIX",
        "date": datetime.now().strftime("%Y-%m-%d"),
    }

def _yves_alert(aaii: Dict, vix: float, real_yield: float, bond_asleep: bool) -> Dict:
    bull = aaii.get("bullish", 30)
    bear = aaii.get("bearish", 30)
    spread = bull - bear
    alert = None
    alert_level = "NONE"
    action = "HOLD"
    if bull > 50 and vix < 18:
        alert = "CASINO BEHAVIOR — Retail euphoric. RAISE CASH."
        alert_level = "CRITICAL"
        action = "RAISE_CASH"
    elif bear > 45 and vix > 28:
        alert = "EXTREME FEAR — Contrarian BUY signal. Deploy cash."
        alert_level = "OPPORTUNITY"
        action = "DEPLOY_CASH"
    elif real_yield < 1.0 and bond_asleep:
        alert = "BOND TRADERS ASLEEP — Disinflation illusion. Defensive posture."
        alert_level = "WARNING"
        action = "REDUCE_BETA"
    elif spread > 25:
        alert = "BULL SPREAD EXTREME — Euphoria risk. Trim winners."
        alert_level = "CAUTION"
        action = "TRIM_POSITIONS"
    return {
        "alert": alert,
        "alert_level": alert_level,
        "action": action,
        "spread": round(spread, 1),
        "fear_index": round(bear - bull * 0.5, 1),
    }

def get_behavioral_macro(vix: float = 20.0, real_yield: float = 2.0,
                         put_call_ratio: float = 1.0, dxy_ret: float = 0.0,
                         force_refresh: bool = False) -> Dict:
    global _AAII_CACHE, _AAII_CACHE_TIME
    if not force_refresh and _AAII_CACHE is not None and _AAII_CACHE_TIME is not None:
        if datetime.now() - _AAII_CACHE_TIME < timedelta(hours=24):
            aaii = _AAII_CACHE.copy()
            aaii["cached"] = True
            aaii["cache_age_h"] = round((datetime.now() - _AAII_CACHE_TIME).total_seconds() / 3600, 1)
            bond_asleep = real_yield < 1.0 and real_yield > -0.5
            yves = _yves_alert(aaii, vix, real_yield, bond_asleep)
            return {**aaii, "yves": yves, "vix": vix, "real_yield": real_yield}

    live = _fetch_aaii_live()
    if live:
        _AAII_CACHE = live
        _AAII_CACHE_TIME = datetime.now()
        aaii = live.copy()
        aaii["cached"] = False
    else:
        aaii = _aaii_proxy(vix, put_call_ratio, dxy_ret)
        aaii["cached"] = False

    bond_asleep = real_yield < 1.0 and real_yield > -0.5
    yves = _yves_alert(aaii, vix, real_yield, bond_asleep)
    return {
        **aaii,
        "yves": yves,
        "vix": vix,
        "real_yield": real_yield,
        "bond_asleep": bond_asleep,
    }
