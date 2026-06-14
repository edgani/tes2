"""data/loader.py — Minimal price loader for MacroRegime
Falls back to yfinance directly if primary loader fails.
"""
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import os, pickle

_CACHE_PATH = ".price_cache.pkl"

def load_prices(tickers, days=756, max_age_hours=12.0, progress_cb=None):
    """Fetch close prices from Yahoo Finance."""
    prices = {}
    total = len(tickers)
    for i, t in enumerate(tickers):
        try:
            if progress_cb and i % 10 == 0:
                progress_cb(f"Fetching {t}...", 0.1 + 0.8 * i / total)
            data = yf.download(t, period=f"{days}d", interval="1d", progress=False, auto_adjust=True)
            if data is not None and len(data) > 50:
                prices[t] = data["Close"].squeeze()
        except Exception:
            pass
    return prices


def load_ohlcv(tickers, days=756):
    """Fetch FULL OHLCV+Volume per ticker → {ticker: DataFrame[Open,High,Low,Close,Volume]}.
    Parallel to load_prices (non-breaking); needed for volume-based engines (bandarmetrics,
    maker_framework volume signals). Defensive: skips tickers that fail."""
    out = {}
    for t in tickers or []:
        try:
            data = yf.download(t, period=f"{days}d", interval="1d", progress=False, auto_adjust=True)
            if data is None or len(data) < 60:
                continue
            # flatten possible MultiIndex columns (yfinance v1.x)
            if hasattr(data.columns, "nlevels") and data.columns.nlevels > 1:
                data = data.copy()
                data.columns = [c[0] if isinstance(c, tuple) else c for c in data.columns]
            cols = {c: c for c in ("Open", "High", "Low", "Close", "Volume") if c in data.columns}
            if len(cols) >= 5:
                out[t] = data[list(cols)].dropna(how="all")
        except Exception:
            pass
    return out


def load_snapshot(max_age_hours=12.0):
    if not os.path.exists(_CACHE_PATH):
        return None
    try:
        mtime = os.path.getmtime(_CACHE_PATH)
        age_hours = (datetime.now().timestamp() - mtime) / 3600
        if age_hours > max_age_hours:
            return None
        with open(_CACHE_PATH, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None

def save_snapshot(obj):
    try:
        with open(_CACHE_PATH, "wb") as f:
            pickle.dump(obj, f)
    except Exception:
        pass

def snapshot_age_str():
    if not os.path.exists(_CACHE_PATH):
        return "no cache"
    try:
        mtime = os.path.getmtime(_CACHE_PATH)
        age = datetime.now().timestamp() - mtime
        if age < 60:
            return f"{int(age)}s ago"
        elif age < 3600:
            return f"{int(age/60)}m ago"
        else:
            return f"{int(age/3600)}h ago"
    except Exception:
        return "unknown"
