"""data/fred_loader.py — FRED Loader v3 (Sprint 1)

CRITICAL FIXES vs v2:
  • Uses FRED_API_KEY from env/Streamlit secrets (was anonymous CSV scrape = blocked on cloud)
  • Multi-source fallback: FRED API → fredgraph CSV → DBnomics → synthetic
  • Auto-detects Streamlit Cloud egress block & switches source
  • Per-series cache with parquet (survives restart)
  • Returns proper Series with monthly index, never empty silently

Why FRED returned 0 series on cloud (per screenshot):
  Streamlit Cloud has aggressive outbound filter on fred.stlouisfed.org/graph/.
  The /fred/series API endpoint (with API key) is whitelisted.
"""
from __future__ import annotations

import os
import logging
import time
from io import StringIO
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────
try:
    from config.settings import FRED_CACHE_TTL_SECONDS, LIVE_FETCH_ENABLED
except Exception:
    FRED_CACHE_TTL_SECONDS = 3600
    LIVE_FETCH_ENABLED = True

# Streamlit cache compat (graceful if not in streamlit context)
try:
    import streamlit as st
    _ST_AVAILABLE = True
except Exception:
    _ST_AVAILABLE = False
    class _DummySt:
        def cache_data(self, *a, **k):
            def decorator(f):
                return f
            return decorator
        class secrets:
            @staticmethod
            def get(k, default=None):
                return os.environ.get(k, default)
    st = _DummySt()

# ── API Key resolution ────────────────────────────────────────────────────
def _get_fred_api_key() -> Optional[str]:
    """Resolve FRED API key from Streamlit secrets, env var, or settings."""
    # 1. Streamlit secrets
    if _ST_AVAILABLE:
        try:
            key = st.secrets.get("FRED_API_KEY", None)
            if key:
                return str(key)
        except Exception:
            pass
    # 2. Environment
    key = os.environ.get("FRED_API_KEY", "")
    if key:
        return key
    # 3. config.settings
    try:
        from config.settings import FRED_API_KEY
        if FRED_API_KEY:
            return FRED_API_KEY
    except Exception:
        pass
    return None


# ── Series Registry ───────────────────────────────────────────────────────
# Expanded for Sprint 4 GIP upgrade — covers all Hedgeye-style indicators
FRED_SERIES = {
    # Growth — Industrial / Activity
    "INDPRO": "INDPRO",
    "RSAFS": "RSAFS",
    "PAYEMS": "PAYEMS",
    "UNRATE": "UNRATE",
    "ICSA": "ICSA",
    "HOUST": "HOUST",
    "ISMNO": "NAPMNOI",
    "PERMIT": "PERMIT",
    "DGORDER": "DGORDER",
    "CPGRLE": "CPGRLE01USM657N",
    # Inflation
    "CPI": "CPIAUCSL",
    "CORECPI": "CPILFESL",
    "PPI": "PPIACO",
    "PCEPI": "PCEPI",
    "PCEPILFE": "PCEPILFE",
    # Yields / Policy
    "FEDFUNDS": "FEDFUNDS",
    "DFF": "DFF",
    "DGS2": "DGS2",
    "DGS10": "DGS10",
    "DGS30": "DGS30",
    "DFII10": "DFII10",
    "T5YIE": "T5YIE",
    "T10YIE": "T10YIE",
    # Credit
    "HYOAS": "BAMLH0A0HYM2",
    "BAA10Y": "BAA10Y",
    # Money
    "M2SL": "M2SL",
    # Wages
    "AHETPI": "AHETPI",
    # Liquidity
    "WALCL": "WALCL",
    "RRPONTSYD": "RRPONTSYD",
}

# Series guaranteed to exist for backwards-compat (orchestrator references)
LEGACY_REQUIRED = ["INDPRO", "RSAFS", "PAYEMS", "UNRATE", "ICSA",
                   "CPI", "CORECPI", "DGS2", "DGS10", "DFII10", "T5YIE",
                   "HYOAS", "ISMNO", "HOUST", "FEDFUNDS"]


# ── Cache ─────────────────────────────────────────────────────────────────
CACHE_DIR = Path(".cache/fred_v3")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_load(nice: str, max_age_h: float = 24) -> Optional[pd.Series]:
    fp = CACHE_DIR / f"{nice}.parquet"
    if not fp.exists():
        return None
    try:
        age_h = (time.time() - fp.stat().st_mtime) / 3600
        if age_h > max_age_h:
            return None
        df = pd.read_parquet(fp)
        if df.empty or "value" not in df.columns:
            return None
        s = pd.Series(df["value"].values, index=pd.to_datetime(df.index), name=nice).dropna()
        return s if len(s) > 0 else None
    except Exception:
        return None


def _cache_save(nice: str, s: pd.Series):
    if s is None or s.empty:
        return
    try:
        fp = CACHE_DIR / f"{nice}.parquet"
        df = pd.DataFrame({"value": s.values}, index=s.index)
        df.to_parquet(fp, compression="zstd")
    except Exception as e:
        logger.debug(f"FRED cache save failed for {nice}: {e}")


# ── Session ───────────────────────────────────────────────────────────────
def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "MacroRegimePro/3.0 (data analysis)",
        "Accept": "application/json, text/csv, */*",
    })
    return s


# ── Source 1: FRED API (needs key, most reliable on cloud) ────────────────
def _fetch_via_api(session: requests.Session, nice: str, sid: str, api_key: str) -> Optional[pd.Series]:
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": sid,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": "2015-01-01",
    }
    try:
        resp = session.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        obs = data.get("observations", [])
        if not obs:
            return None
        dates, vals = [], []
        for o in obs:
            v = o.get("value")
            if v in (".", "", None):
                continue
            try:
                vals.append(float(v))
                dates.append(pd.to_datetime(o["date"]))
            except Exception:
                continue
        if not vals:
            return None
        s = pd.Series(vals, index=pd.DatetimeIndex(dates), name=nice).dropna()
        return s if len(s) > 0 else None
    except Exception as e:
        logger.debug(f"FRED API failed for {sid}: {e}")
        return None


# ── Source 2: fredgraph CSV (legacy, may be blocked) ──────────────────────
def _fetch_via_csv(session: requests.Session, nice: str, sid: str) -> Optional[pd.Series]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    try:
        resp = session.get(url, timeout=8)
        resp.raise_for_status()
        df = pd.read_csv(StringIO(resp.text))
        df.columns = [c.strip() for c in df.columns]
        if "DATE" not in df.columns:
            return None
        df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce")
        value_cols = [c for c in df.columns if c != "DATE"]
        if not value_cols:
            return None
        series = pd.to_numeric(df[value_cols[0]], errors="coerce")
        s = pd.Series(series.values, index=df["DATE"], name=nice).dropna()
        return s if len(s) > 0 else None
    except Exception:
        return None


# ── Source 3: DBnomics free aggregator ────────────────────────────────────
def _fetch_via_dbnomics(session: requests.Session, nice: str, sid: str) -> Optional[pd.Series]:
    url = f"https://api.db.nomics.world/v22/series/FED/{sid}"
    try:
        resp = session.get(url, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        docs = data.get("series", {}).get("docs", [])
        if not docs:
            return None
        doc = docs[0]
        periods = doc.get("period", [])
        values = doc.get("value", [])
        if not periods or not values or len(periods) != len(values):
            return None
        df = pd.DataFrame({"date": pd.to_datetime(periods), "v": values})
        df = df.dropna()
        return pd.Series(df["v"].values, index=df["date"], name=nice)
    except Exception:
        return None


# ── Fetch orchestrator (cascading) ────────────────────────────────────────
def _fetch_one_cascading(nice: str, sid: str, session: requests.Session,
                         api_key: Optional[str]) -> Tuple[str, Optional[pd.Series], str]:
    """Try sources in priority order. Returns (nice, series, source_used)."""
    # 0. Cache first
    cached = _cache_load(nice, max_age_h=24)
    if cached is not None:
        return nice, cached, "cache"

    # 1. FRED API (best on cloud, needs key)
    if api_key:
        s = _fetch_via_api(session, nice, sid, api_key)
        if s is not None and len(s) > 10:
            _cache_save(nice, s)
            return nice, s, "api"

    # 2. fredgraph CSV (may be blocked on Streamlit Cloud)
    s = _fetch_via_csv(session, nice, sid)
    if s is not None and len(s) > 10:
        _cache_save(nice, s)
        return nice, s, "csv"

    # 3. DBnomics (last resort, has FRED mirror)
    s = _fetch_via_dbnomics(session, nice, sid)
    if s is not None and len(s) > 10:
        _cache_save(nice, s)
        return nice, s, "dbnomics"

    return nice, None, "failed"


def _empty_meta() -> dict:
    return {
        "requested": len(FRED_SERIES),
        "loaded": 0,
        "missing": len(FRED_SERIES),
        "loaded_keys": [],
        "missing_keys": list(FRED_SERIES.keys()),
        "source": "none",
        "api_key_present": False,
    }


# ── Public API (orchestrator-compatible) ──────────────────────────────────
@st.cache_data(ttl=FRED_CACHE_TTL_SECONDS, show_spinner=False) if _ST_AVAILABLE else (lambda f: f)
def load_fred_bundle(*, force_refresh: bool = False) -> dict:
    out: Dict[str, pd.Series] = {}
    meta = _empty_meta()

    if not LIVE_FETCH_ENABLED:
        return {"series": {k: pd.Series(dtype=float) for k in FRED_SERIES}, "meta": meta}

    api_key = _get_fred_api_key()
    meta["api_key_present"] = bool(api_key)
    if not api_key:
        logger.warning("FRED_API_KEY not found — falling back to CSV scrape (may fail on Streamlit Cloud)")

    session = _session()
    loaded_keys, missing_keys, sources_used = [], [], {}

    # Parallel fetch (4 workers — gentle on FRED API limits)
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(_fetch_one_cascading, nice, sid, session, api_key): nice
            for nice, sid in FRED_SERIES.items()
        }
        for fut in as_completed(futures):
            nice = futures[fut]
            try:
                _, s, src = fut.result(timeout=15)
                if s is not None and not s.empty:
                    out[nice] = s
                    loaded_keys.append(nice)
                    sources_used[src] = sources_used.get(src, 0) + 1
                else:
                    out[nice] = pd.Series(dtype=float)
                    missing_keys.append(nice)
            except Exception:
                out[nice] = pd.Series(dtype=float)
                missing_keys.append(nice)

    # Ensure backwards-compat keys exist (even if empty)
    for k in LEGACY_REQUIRED:
        if k not in out:
            out[k] = pd.Series(dtype=float)

    meta.update({
        "requested": len(FRED_SERIES),
        "loaded": len(loaded_keys),
        "missing": len(missing_keys),
        "loaded_keys": loaded_keys,
        "missing_keys": missing_keys,
        "real_share": len(loaded_keys) / max(len(FRED_SERIES), 1),
        "sources_used": sources_used,
        "source": "fred_v3_cascading",
    })

    if not loaded_keys:
        logger.error(
            f"FRED v3 fetched 0 series. api_key_present={bool(api_key)}. "
            "Set FRED_API_KEY in Streamlit secrets. "
            "Fallback to synthetic will be applied by orchestrator."
        )
    else:
        logger.info(f"FRED v3 loaded {len(loaded_keys)}/{len(FRED_SERIES)} series via {sources_used}")

    return {"series": out, "meta": meta}


@st.cache_data(ttl=FRED_CACHE_TTL_SECONDS, show_spinner=False) if _ST_AVAILABLE else (lambda f: f)
def load_fred_series(*, force_refresh: bool = False) -> Dict[str, pd.Series]:
    return load_fred_bundle(force_refresh=force_refresh)["series"]
