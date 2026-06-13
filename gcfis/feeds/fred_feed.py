"""fred_feed.py — REAL FRED feed via fredgraph CSV (no API key).
NetLiq = WALCL/1000 − WTREGEN − RRPONTSYD  (all in $bn; WALCL is $mn).
Outputs LEVEL series keyed to market_drivers feed ids: FEDLIQ, TIPS10Y, G4M2(seam).
Sandbox blocks fred.stlouisfed.org → live fetch verified on deploy; parser unit-tested on fixtures."""
from __future__ import annotations
import io, urllib.request
import pandas as pd

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={ids}"
_IDS = ["WALCL", "WTREGEN", "RRPONTSYD", "DFII10"]

def parse_fredgraph_csv(text: str) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(text))
    dcol = "DATE" if "DATE" in df.columns else df.columns[0]
    df[dcol] = pd.to_datetime(df[dcol], errors="coerce")
    df = df.set_index(dcol)
    for c in df.columns:
        df[c] = pd.to_numeric(df[c].replace(".", None), errors="coerce")
    return df.sort_index()

def build_series(df: pd.DataFrame) -> dict:
    """LEVEL series; read_all() z-scores the CHANGE itself."""
    out = {}
    have = set(df.columns)
    if {"WALCL", "WTREGEN", "RRPONTSYD"} <= have:
        d = df[["WALCL", "WTREGEN", "RRPONTSYD"]].ffill().dropna()
        netliq = d["WALCL"] / 1000.0 - d["WTREGEN"] - d["RRPONTSYD"]      # $bn
        out["FEDLIQ"] = netliq
    if "DFII10" in have:
        out["TIPS10Y"] = df["DFII10"].ffill().dropna()
    return out

def fetch_fred(timeout: int = 20) -> tuple[dict, str]:
    """→ ({series_id: pd.Series}, status). Graceful: ({}, reason) on any failure."""
    try:
        url = FRED_CSV.format(ids=",".join(_IDS))
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (MacroRegime)"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            text = r.read().decode("utf-8", "replace")
        ser = build_series(parse_fredgraph_csv(text))
        if not ser:
            return {}, "fred: parsed but no usable columns"
        return ser, f"fred: ok ({', '.join(ser)})"
    except Exception as e:                                   # pragma: no cover (network)
        return {}, f"fred: unavailable ({type(e).__name__})"
