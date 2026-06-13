"""live_data.py — the MISSING live price loader. This is why the app was stuck on DEMO:
nothing ever fetched real OHLCV. The pipeline got demo_universe() every run.

Uses Yahoo's public chart endpoint (same one data_layer uses for VIX) — no API key, works on
Streamlit Cloud. Sandbox blocks query1.finance.yahoo.com, so this returns empty here (→ demo
fallback, honestly labeled); on Cloud it returns REAL OHLCV and the DEMO banner disappears.

Stooq CSV is wired as a fallback for names Yahoo rejects (Yahoo sometimes 429s).
"""
from __future__ import annotations
import io, json, urllib.request, urllib.parse
import pandas as pd

# market ticker -> Yahoo symbol (what the engines key on : what Yahoo expects)
DEFAULT_UNIVERSE = {
    "NVDA": "NVDA", "PLTR": "PLTR", "SMR": "SMR", "TLT": "TLT", "XLU": "XLU",
    "BTCUSD": "BTC-USD", "ETHUSD": "ETH-USD", "XAUUSD": "GC=F", "USOIL": "CL=F",
    "USDJPY=X": "USDJPY=X", "BREN.JK": "BREN.JK", "DMAS.JK": "DMAS.JK",
    # GIP-quad inputs (so forward_macro gets its real factors, not proxies):
    "SPY": "SPY", "COPPER": "HG=F", "SMH": "SMH", "IWM": "IWM", "UUP": "UUP",
}
_STOOQ = {  # fallback symbols (Yahoo-reject names)
    "NVDA": "nvda.us", "PLTR": "pltr.us", "SMR": "smr.us", "TLT": "tlt.us", "XLU": "xlu.us",
    "BTCUSD": "btcusd", "ETHUSD": "ethusd", "XAUUSD": "xauusd", "USOIL": "cl.f",
    "USDJPY=X": "usdjpy", "BREN.JK": None, "DMAS.JK": None,
}


def _yahoo(sym: str, rng: str, interval: str, timeout: int) -> pd.DataFrame | None:
    q = urllib.parse.quote(sym)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{q}?range={rng}&interval={interval}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        j = json.loads(r.read().decode("utf-8", "replace"))
    res = j["chart"]["result"][0]
    ts = res["timestamp"]; qd = res["indicators"]["quote"][0]
    df = pd.DataFrame({"Open": qd["open"], "High": qd["high"], "Low": qd["low"],
                       "Close": qd["close"], "Volume": qd["volume"]},
                      index=pd.to_datetime(ts, unit="s"))
    return df.dropna(subset=["Close"])


def _stooq(sym: str, timeout: int) -> pd.DataFrame | None:
    url = f"https://stooq.com/q/d/l/?s={sym}&i=d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        df = pd.read_csv(io.StringIO(r.read().decode("utf-8", "replace")))
    if "Close" not in df or len(df) < 2:
        return None
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    return df.set_index("Date")[["Open", "High", "Low", "Close", "Volume"]].sort_index()


def fetch_prices(universe: dict | None = None, rng: str = "1y", interval: str = "1d",
                 timeout: int = 15) -> tuple[dict, list]:
    """→ ({engine_ticker: OHLCV df}, status[]). Yahoo first, Stooq fallback. Graceful per symbol."""
    universe = universe or DEFAULT_UNIVERSE
    out, status, ok = {}, [], 0
    for tkr, ysym in universe.items():
        df = None
        try:
            df = _yahoo(ysym, rng, interval, timeout)
        except Exception as e:                                   # pragma: no cover (network)
            ssym = _STOOQ.get(tkr)
            if ssym:
                try:
                    df = _stooq(ssym, timeout)
                except Exception as e2:
                    status.append(f"{tkr}: yahoo {type(e).__name__} / stooq {type(e2).__name__}")
            else:
                status.append(f"{tkr}: {type(e).__name__}")
        if df is not None and len(df) >= 60:
            out[tkr] = df; ok += 1
    status.insert(0, f"prices: {ok}/{len(universe)} loaded LIVE" if ok else
                  "prices: 0 loaded (network blocked here) — DEMO fallback")
    return out, status
