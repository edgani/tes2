"""data_layer.py — the unlock. ONE place that fetches REAL data and labels provenance.

Design principle (why every previous build was 'sampah'): a beautiful dashboard on OHLCV
proxies produces garbage tickers. The fix is real feeds, each tagged so the UI can NEVER
silently pass proxy off as real again.

Provenance per feed:
  REAL  — fetched from an authoritative source this run
  PROXY — derived from price/OHLCV because the real feed is unavailable (labeled everywhere)
  SEAM  — requires a paid/auth feed we don't have (e.g. options GEX, ETF flow); shown as a gap

Sandbox blocks fred.stlouisfed.org / query1.finance.yahoo.com / idx.co.id, so live fetch is
verifiable only on Streamlit Cloud. Parsers are unit-tested on fixtures here. Nothing is faked.
"""
from __future__ import annotations
import io, urllib.request
import pandas as pd

# ---- FRED: free, no API key. The single biggest real unlock for crash/regime detection. ----
# Credit (HY/IG OAS) is ChatGPT's "VERY HIGH" crash signal #2 — and it is FREE here.
FRED_SERIES = {
    "WALCL": "fed balance sheet ($mn)",
    "WTREGEN": "Treasury General Account ($bn)",
    "RRPONTSYD": "reverse repo ($bn)",
    "BAMLH0A0HYM2": "HY OAS credit spread (%)",      # crash frontrunner
    "BAMLC0A0CM": "IG OAS credit spread (%)",
    "DFII10": "10y real yield (%)",
    "T10YIE": "10y breakeven inflation (%)",          # GIP inflation input (catches oil shocks)
    "DGS10": "10y nominal yield (%)",                 # GIP growth input
    "T10Y2Y": "10y-2y curve (%)",
    "VIXCLS": "VIX spot",
}
_FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={ids}"


def _parse_fred(text: str) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(text))
    dcol = "DATE" if "DATE" in df.columns else df.columns[0]
    df[dcol] = pd.to_datetime(df[dcol], errors="coerce")
    df = df.set_index(dcol)
    for c in df.columns:
        df[c] = pd.to_numeric(df[c].replace(".", None), errors="coerce")
    return df.sort_index()


def fetch_fred(timeout: int = 30):
    """→ (df, status). Graceful on any failure (returns empty df + reason)."""
    try:
        url = _FRED_CSV.format(ids=",".join(FRED_SERIES))
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (MacroRegime)"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            df = _parse_fred(r.read().decode("utf-8", "replace"))
        return df, f"FRED: REAL ({df.shape[1]} series, last {df.index[-1].date()})"
    except Exception as e:                                       # pragma: no cover (network)
        return pd.DataFrame(), f"FRED: unavailable ({type(e).__name__}) — deploy to verify"


def derive_macro(df: pd.DataFrame) -> dict:
    """Turn the FRED frame into the macro feeds the engines consume, with provenance."""
    out = {}

    def put(key, series, label):
        out[key] = {"series": series, "value": (float(series.iloc[-1]) if len(series) else None),
                    "provenance": "REAL", "label": label}

    have = set(df.columns)
    if {"WALCL", "WTREGEN", "RRPONTSYD"} <= have:
        d = df[["WALCL", "WTREGEN", "RRPONTSYD"]].ffill().dropna()
        put("net_liquidity", d["WALCL"] / 1000.0 - d["WTREGEN"] - d["RRPONTSYD"], "NetLiq = FedBS−TGA−RRP ($bn)")
    if "BAMLH0A0HYM2" in have:
        put("hy_oas", df["BAMLH0A0HYM2"].ffill().dropna(), "HY OAS credit spread (%)")
    if "BAMLC0A0CM" in have:
        put("ig_oas", df["BAMLC0A0CM"].ffill().dropna(), "IG OAS credit spread (%)")
    if "DFII10" in have:
        put("real_yield_10y", df["DFII10"].ffill().dropna(), "10y real yield (%)")
    if "T10YIE" in have:
        put("breakeven_10y", df["T10YIE"].ffill().dropna(), "10y breakeven inflation (%)")
    if "DGS10" in have:
        put("y10_nominal", df["DGS10"].ffill().dropna(), "10y nominal yield (%)")
    if "T10Y2Y" in have:
        put("curve_10y2y", df["T10Y2Y"].ffill().dropna(), "10y-2y curve (%)")
    if "VIXCLS" in have:
        put("vix_spot", df["VIXCLS"].ffill().dropna(), "VIX spot")
    return out


# ---- VIX term structure: ChatGPT crash signal #5 (panic-transition). ^VIX3M via yfinance. ----
def fetch_vix_term(timeout: int = 15) -> dict:
    """VIX term structure (spot vs 3M). Backwardation = panic regime. Cloud-only fetch.
    Returns {ratio, state, provenance}. SEAM-labeled here since yfinance is blocked in sandbox."""
    try:                                                         # pragma: no cover (network)
        import json
        out = {}
        for sym, key in (("%5EVIX", "spot"), ("%5EVIX3M", "m3")):
            url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
                   f"?range=5d&interval=1d")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                j = json.loads(r.read().decode("utf-8", "replace"))
            cl = j["chart"]["result"][0]["indicators"]["quote"][0]["close"]
            out[key] = float([x for x in cl if x is not None][-1])
        ratio = out["spot"] / out["m3"] if out.get("m3") else None
        state = "BACKWARDATION (panic)" if ratio and ratio > 1.0 else "contango (calm)"
        return {"ratio": round(ratio, 3) if ratio else None, "state": state, "provenance": "REAL"}
    except Exception as e:
        return {"ratio": None, "state": "n/a", "provenance": "SEAM",
                "note": f"VIX term needs ^VIX/^VIX3M ({type(e).__name__}) — deploy to verify"}


# ---- Feeds we do NOT have without paid/auth access. Declared, never faked. ----
SEAMS = {
    "options_gex": "dealer GEX/Vanna/Charm — needs options chain (FlashAlpha/CBOE)",
    "etf_flow": "ETF/mutual-fund flow — needs paid flow feed",
    "earnings_revision": "EPS revision diffusion — needs estimates feed",
    "breadth": "% above 50/200dma — needs full index constituents (computable on Cloud)",
    "dark_pool": "off-exchange prints — needs FINRA/vendor feed",
    "onchain": "SOPR/MVRV/whale/exchange-reserves — needs on-chain feed",
}


def build_data_context(prices: dict, session=None) -> dict:
    """Assemble the full data context for one run. Cached on session_state when available.

    Returns {macro, vix_term, typef, seams, status[]} — every numeric carries provenance so
    the UI banner can show REAL vs PROXY vs SEAM truthfully.
    """
    ctx = {"macro": {}, "vix_term": {}, "typef": {}, "seams": SEAMS, "status": []}

    cache = session.session_state if (session is not None and hasattr(session, "session_state")) else None

    # FRED macro (+credit) — only cache SUCCESS so a transient timeout doesn't poison the session
    fr = cache.get("_v2_fred") if cache is not None else None
    if not fr or not fr[0]:                       # no cached success → (re)fetch
        df, st = fetch_fred(timeout=30)
        fr = (derive_macro(df), st)
        if cache is not None and fr[0]:           # cache ONLY when real series came back
            cache["_v2_fred"] = fr
    ctx["macro"], st = fr
    ctx["status"].append(st)

    # VIX term
    vt = cache.get("_v2_vix") if cache is not None else None
    if vt is None:
        vt = fetch_vix_term()
        if cache is not None:
            cache["_v2_vix"] = vt
    ctx["vix_term"] = vt
    ctx["status"].append(f"VIX term: {vt.get('provenance')} ({vt.get('state')})")

    # Type-F (IDX foreign flow) — only if .JK names present
    if any(str(k).upper().endswith(".JK") for k in (prices or {})):
        tf = cache.get("_v2_typef") if cache is not None else None
        if tf is None:
            try:
                from core.typef_idx import build_typef
                tf = build_typef(list(prices), days=120)
            except Exception as e:
                tf = ({}, f"typef: error {type(e).__name__}")
            if cache is not None:
                cache["_v2_typef"] = tf
        ctx["typef"], st = tf
        ctx["status"].append(st)

    n_real = sum(1 for v in ctx["macro"].values() if v.get("provenance") == "REAL")
    ctx["status"].insert(0, f"DATA: {n_real} REAL macro series · {len(ctx['seams'])} declared seams")
    return ctx
