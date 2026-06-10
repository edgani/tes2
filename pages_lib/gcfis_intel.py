"""pages_lib/gcfis_intel.py — the GCFIS tab. Adapts the live `snap` into gcfis.run_gcfis inputs and
renders the GCFIS dashboard (systemic radar + cross-asset coherence + ranked tickers w/ reason+entry).

Fully DEFENSIVE: every extraction is wrapped; missing/oddly-shaped data degrades gracefully and the
page never crashes the app. This is an ADDITIVE tab — it does not touch the existing 9 tabs."""
from __future__ import annotations
import pandas as pd

# alias maps: app symbols -> the canonical asset the engine expects
_PRICE_ALIASES = {
    "gold":   ["XAUUSD", "GC=F", "GOLD", "XAU", "XAUUSD=X"],
    "silver": ["XAGUSD", "SI=F", "SILVER", "XAG"],
    "oil":    ["WTI", "CL=F", "USOIL", "BZ=F", "BRENT", "OIL"],
    "spx":    ["US500", "^GSPC", "SPX", "SPY", "^SPX", "ES=F"],
    "ndx":    ["NAS100", "^IXIC", "NDX", "QQQ", "NQ=F"],
    "btc":    ["BTCUSD", "BTC-USD", "BTC", "BTCUSD=X"],
    "eth":    ["ETHUSD", "ETH-USD", "ETH"],
}
_CHG_ALIASES = {
    "ust10y_chg": ["US10Y", "^TNX", "US10Y_YIELD", "DGS10"],
    "ust2y_chg":  ["US02Y", "UST2Y", "^UST2YR", "DGS2"],
    "dxy_chg":    ["DXY", "DX=F", "DX-Y.NYB", "DXY=X"],
    "vix_chg":    ["VIX", "^VIX", "VIX=F"],
}
_BENCH = ["SPY", "^GSPC", "US500", "^SPX", "ES=F"]


def _close(v):
    """Return a clean 1-D close series from a Series or OHLCV DataFrame."""
    try:
        if isinstance(v, pd.DataFrame):
            for c in ("Close", "close", "Adj Close", "adj_close"):
                if c in v.columns:
                    return pd.to_numeric(v[c], errors="coerce").dropna()
            return pd.to_numeric(v.iloc[:, 0], errors="coerce").dropna()
        return pd.to_numeric(pd.Series(v), errors="coerce").dropna()
    except Exception:
        return pd.Series(dtype=float)


def _prices_dict(snap) -> dict:
    raw = snap.get("prices") or {}
    out = {}
    try:
        if isinstance(raw, pd.DataFrame):       # wide frame: columns are tickers
            for c in raw.columns:
                s = _close(raw[c])
                if len(s) >= 60:
                    out[str(c)] = s
        elif isinstance(raw, dict):
            for k, v in raw.items():
                s = _close(v)
                if len(s) >= 60:
                    out[str(k)] = s
    except Exception:
        pass
    return out


def _find(prices: dict, names: list):
    up = {k.upper(): k for k in prices}
    for n in names:
        if n.upper() in up:
            return prices[up[n.upper()]]
    return None


def _pct_chg(s):
    try:
        if s is not None and len(s) >= 2 and s.iloc[-2] != 0:
            return round(float(s.iloc[-1] / s.iloc[-2] - 1) * 100, 3)
    except Exception:
        pass
    return None


def _cross_snapshot(prices: dict) -> dict:
    snap_ca = {}
    for key, aliases in _PRICE_ALIASES.items():
        v = _pct_chg(_find(prices, aliases))
        if v is not None:
            snap_ca[key] = v
    for key, aliases in _CHG_ALIASES.items():
        v = _pct_chg(_find(prices, aliases))
        if v is not None:
            snap_ca[key] = v
    return snap_ca


def _quads(snap):
    gip = snap.get("gip")
    if gip is None:
        return None, None
    g = (lambda k: gip.get(k) if isinstance(gip, dict) else getattr(gip, k, None))
    return g("structural_quad"), g("monthly_quad")


def _posterior(sq, mq) -> dict:
    """Map Hedgeye quad -> soft regime posterior the meta expects."""
    m = {"Q1": {"risk_on": .7, "transition_up": .2, "chop": .1},
         "Q2": {"transition_up": .5, "risk_on": .3, "chop": .2},
         "Q3": {"transition_down": .5, "risk_off": .3, "chop": .2},
         "Q4": {"risk_off": .7, "transition_down": .2, "chop": .1}}
    post = {}
    for q, w in ((sq, 0.5), (mq, 0.5)):
        for k, v in m.get(q or "", {"chop": 1.0}).items():
            post[k] = post.get(k, 0.0) + w * v
    return post or {"chop": 1.0}


def render(snap: dict):
    import streamlit as st
    try:
        from gcfis.orchestrator import run_gcfis
        from gcfis.dashboard import render_gcfis_dashboard
    except Exception as e:
        st.error(f"GCFIS package not importable: {e}")
        return

    st.title("🧭 GCFIS — Global Capital Flow Intelligence")
    st.caption("Change-centric · regime-conditional · validated-not-fabricated. Reads the whole tape "
               "together, ranks the universe with a logical reason + gamma-aware entry per name.")

    prices = _prices_dict(snap)
    if len(prices) < 2:
        st.warning("GCFIS needs the price history from the snapshot (≥2 tickers, ≥60 bars). "
                   "Click **Rebuild**, then reopen this tab. (snap['prices'] was empty or unrecognised.)")
        return

    bench = _find(prices, _BENCH)
    if bench is None:
        bench = next(iter(prices.values()))
    sq, mq = _quads(snap)
    posterior = _posterior(sq, mq)
    cross_snap = _cross_snapshot(prices)

    with st.spinner(f"Running GCFIS on {len(prices)} tickers…"):
        try:
            out = run_gcfis(prices, bench, posterior, cross_asset_snapshot=cross_snap or None)
        except Exception as e:
            st.error(f"GCFIS run failed: {e}")
            import traceback; st.code(traceback.format_exc())
            return

    # show the app's OWN validated quad in the radar (not a no-data forward_macro guess)
    try:
        if sq:
            out.setdefault("systemic", {}).setdefault("forward_macro", {})["forward_quad"] = sq
    except Exception:
        pass

    if sq or mq:
        st.caption(f"Quad context — structural **{sq or '—'}** / monthly **{mq or '—'}**  ·  "
                   f"cross-asset inputs detected: {', '.join(cross_snap) if cross_snap else 'none (add gold/oil/SPX/VIX symbols to your universe)'}")

    render_gcfis_dashboard(out, st=st, title="GCFIS")

    with st.expander("ℹ️ what feeds this tab (honest)"):
        st.markdown(
            "- **Works on price alone:** accumulation (Stage 1–5), theme RS, flow rotation, lead–lag, "
            "entry (trend/momentum/structure + risk-range R/R), cross-asset regime.\n"
            "- **Needs feeds you wire (else `unknown`, never faked):** dealer GEX (options chain), "
            "positioning (COT/OI), crypto on-chain, liquidity (Fed/TGA/RRP).\n"
            "- **Quad** shown is your own GIP engine; cross-asset regime is computed live from the tape.\n"
            "- This is a validated *instrument*, not a proven *edge* — confirm on your universe via `gcfis/backtest.py`.")
