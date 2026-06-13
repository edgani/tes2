"""typef_idx.py — REAL Type-F (foreign flow) feed from IDX daily stock summary.
Endpoint: https://www.idx.co.id/primary/TradingSummary/GetStockSummary?length=10000&start=0&date=YYYYMMDD
ForeignBuy/ForeignSell are VALUE (Rp) — exactly the fb/fs the FlowRegimeEngine requires.
Sandbox blocks idx.co.id → live fetch verified on deploy; parser unit-tested on fixtures.
First warm-up fetch (~120 sessions) is slow once; per-day CSV cache under cache_dir after that."""
from __future__ import annotations
import json, os, time, urllib.request
import pandas as pd

IDX_URL = ("https://www.idx.co.id/primary/TradingSummary/GetStockSummary"
           "?length=10000&start=0&date={d}")
_HDRS = {"User-Agent": "Mozilla/5.0 (MacroRegime)", "Referer": "https://www.idx.co.id/",
         "Accept": "application/json"}

_KEYS = {"code": ("StockCode", "Code", "stockCode", "KodeSaham"),
         "open": ("OpenPrice", "Open", "openPrice", "open"),
         "high": ("High", "high"), "low": ("Low", "low"), "close": ("Close", "close"),
         "volume": ("Volume", "volume"), "value": ("Value", "TotalValue", "value"),
         "fb": ("ForeignBuy", "foreignBuy", "foreign_buy"),
         "fs": ("ForeignSell", "foreignSell", "foreign_sell")}

def _pick(row: dict, names) -> object:
    for n in names:
        if n in row:
            return row[n]
    low = {str(k).lower(): v for k, v in row.items()}
    for n in names:
        if n.lower() in low:
            return low[n.lower()]
    return None

def parse_stock_summary(text: str, date: str) -> pd.DataFrame:
    """Tolerant parser → long rows [date, code, open, high, low, close, volume, value, fb, fs]."""
    try:
        j = json.loads(text)
    except Exception:
        return pd.DataFrame()
    rows = j.get("data") if isinstance(j, dict) else j
    if not isinstance(rows, list):
        return pd.DataFrame()
    rec = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        code = _pick(r, _KEYS["code"])
        if not code:
            continue
        rec.append({"date": date, "code": str(code).upper(),
                    **{k: pd.to_numeric(_pick(r, _KEYS[k]), errors="coerce")
                       for k in ("open", "high", "low", "close", "volume", "value", "fb", "fs")}})
    return pd.DataFrame(rec)

def fetch_day(date_yyyymmdd: str, timeout: int = 25) -> pd.DataFrame:    # pragma: no cover (network)
    req = urllib.request.Request(IDX_URL.format(d=date_yyyymmdd), headers=_HDRS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return parse_stock_summary(r.read().decode("utf-8", "replace"), date_yyyymmdd)

def build_typef(tickers, days: int = 120, cache_dir: str = "/tmp/typef_cache",
                sleep_s: float = 0.12, min_days: int = 60):
    """→ ({'BREN.JK': df(REQUIRED cols)}, status). Per-day CSV cache; graceful on failures."""
    want = {str(t).upper().replace(".JK", "") for t in tickers if str(t).upper().endswith(".JK")}
    if not want:
        return {}, "typef: no .JK tickers in universe"
    os.makedirs(cache_dir, exist_ok=True)
    frames, fetched, cached, failed = [], 0, 0, 0
    bdays = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=int(days * 1.15))
    for d in bdays[-days:]:
        ds = d.strftime("%Y%m%d")
        fp = os.path.join(cache_dir, f"idx_{ds}.csv")
        try:
            if os.path.exists(fp):
                df = pd.read_csv(fp); cached += 1
            else:
                df = fetch_day(ds); fetched += 1
                if len(df):
                    df.to_csv(fp, index=False)
                time.sleep(sleep_s)
        except Exception:
            failed += 1
            continue
        if len(df):
            frames.append(df[df["code"].isin(want)])
    if not frames:
        return {}, f"typef: no data (fetched {fetched}, cached {cached}, failed {failed}) — verify idx.co.id reachable"
    allf = pd.concat(frames, ignore_index=True)
    out = {}
    for code, g in allf.groupby("code"):
        g = g.dropna(subset=["close"]).copy()
        if len(g) < min_days:
            continue
        g["date"] = pd.to_datetime(g["date"], format="%Y%m%d", errors="coerce")
        g = g.sort_values("date").set_index("date")
        df = g[["open", "high", "low", "close", "volume", "fb", "fs"]].astype(float)
        df["total_value"] = pd.to_numeric(g["value"], errors="coerce").fillna(df["close"] * df["volume"])
        out[f"{code}.JK"] = df
    return out, (f"typef: ok {len(out)} tickers (fetched {fetched} · cached {cached} · failed {failed}"
                 + (" · WARM-UP run, next loads cached" if fetched > 30 else "") + ")")
