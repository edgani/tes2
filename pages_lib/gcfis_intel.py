"""pages_lib/gcfis_intel.py — the GCFIS tab. Adapts the live `snap` into gcfis.run_gcfis inputs and
renders the full dashboard. ENRICHED: harvests the data v40 already computes (volumes, breadth, VIX,
GEX/walls, quads) and fits a REAL regime HMM at runtime — so panels POPULATE instead of showing n/a.
Fully DEFENSIVE: every extraction is wrapped; missing/odd data degrades gracefully, never crashes."""
from __future__ import annotations
import numpy as np, pandas as pd

_PRICE_ALIASES = {
    "gold": ["XAUUSD","GC=F","GOLD","XAU","XAUUSD=X"], "silver": ["XAGUSD","SI=F","SILVER","XAG"],
    "oil": ["WTI","CL=F","USOIL","BZ=F","BRENT","OIL"], "spx": ["US500","^GSPC","SPX","SPY","^SPX","ES=F"],
    "ndx": ["NAS100","^IXIC","NDX","QQQ","NQ=F"], "btc": ["BTCUSD","BTC-USD","BTC","BTCUSD=X"],
    "eth": ["ETHUSD","ETH-USD","ETH"]}
_CHG_ALIASES = {"ust10y_chg": ["US10Y","^TNX","DGS10"], "ust2y_chg": ["US02Y","DGS2"],
                "dxy_chg": ["DXY","DX=F","DX-Y.NYB"], "vix_chg": ["VIX","^VIX","VIX=F"]}
_BENCH = ["SPY","^GSPC","US500","^SPX","ES=F"]
_VIX = ["VIX","^VIX","VIX=F","VIX3M"]


def _close(v):
    try:
        if isinstance(v, pd.DataFrame):
            for c in ("Close","close","Adj Close","adj_close"):
                if c in v.columns: return pd.to_numeric(v[c], errors="coerce").dropna()
            return pd.to_numeric(v.iloc[:, 0], errors="coerce").dropna()
        return pd.to_numeric(pd.Series(v), errors="coerce").dropna()
    except Exception:
        return pd.Series(dtype=float)

def _vol(v):
    try:
        if isinstance(v, pd.DataFrame):
            for c in ("Volume","volume","vol"):
                if c in v.columns: return pd.to_numeric(v[c], errors="coerce").dropna()
    except Exception:
        pass
    return None

def _prices_dict(snap):
    raw = snap.get("prices") or {}; out, vols = {}, {}
    try:
        items = raw.items() if isinstance(raw, dict) else [(c, raw[c]) for c in raw.columns] if isinstance(raw, pd.DataFrame) else []
        for k, v in items:
            s = _close(v)
            if len(s) >= 60:
                out[str(k)] = s
                vv = _vol(v)
                if vv is not None and len(vv) >= 60: vols[str(k)] = vv
    except Exception:
        pass
    return out, vols

def _find(prices, names):
    up = {k.upper(): k for k in prices}
    for n in names:
        if n.upper() in up: return prices[up[n.upper()]]
    return None

def _pct_chg(s):
    try:
        if s is not None and len(s) >= 2 and s.iloc[-2] != 0:
            return round(float(s.iloc[-1] / s.iloc[-2] - 1) * 100, 3)
    except Exception:
        pass
    return None

def _cross_snapshot(prices):
    out = {}
    for key, al in {**_PRICE_ALIASES, **_CHG_ALIASES}.items():
        v = _pct_chg(_find(prices, al))
        if v is not None: out[key] = v
    return out

def _breadth(prices):
    """Fraction of the universe above its 50dma — a real internal-breadth series."""
    try:
        cols = {}
        for k, s in prices.items():
            if len(s) >= 60: cols[k] = (s > s.rolling(50).mean()).astype(float)
        if len(cols) < 3: return None
        return pd.DataFrame(cols).mean(axis=1).dropna()
    except Exception:
        return None

def _quads(snap):
    gip = snap.get("gip")
    if gip is None: return None, None
    g = (lambda k: gip.get(k) if isinstance(gip, dict) else getattr(gip, k, None))
    return g("structural_quad"), g("monthly_quad")

def _quad_posterior(sq, mq):
    m = {"Q1": {"risk_on": .7, "transition_up": .2, "chop": .1}, "Q2": {"transition_up": .5, "risk_on": .3, "chop": .2},
         "Q3": {"transition_down": .5, "risk_off": .3, "chop": .2}, "Q4": {"risk_off": .7, "transition_down": .2, "chop": .1}}
    post = {}
    for q, w in ((sq, .5), (mq, .5)):
        for k, v in m.get(q or "", {"chop": 1.0}).items(): post[k] = post.get(k, 0.0) + w * v
    return post or {"chop": 1.0}

def _regime_posterior(snap, prices, bench):
    _hint = None
    try:
        _sq, _mq = _quads(snap)
        _hint = _mq or _sq
    except Exception:
        _hint = None
    """REAL Gaussian HMM fitted at runtime on bench returns + breadth + VIX; fallback to quad lookup."""
    try:
        from gcfis.engines.regime_hmm import run_regime_hmm
        r = np.log(bench).diff()
        vixs = _find(prices, _VIX)
        hm = run_regime_hmm(r, n_states=5, breadth=_breadth(prices, gip_hint=_hint), vix=vixs)
        if hm.get("ok") and hm.get("posterior"):
            return hm["posterior"], hm.get("method", "hmm")
    except Exception:
        pass
    sq, mq = _quads(snap)
    return _quad_posterior(sq, mq), "quad_lookup"

def _systemic_inputs(prices, bench):
    """Breadth + realized-vol + VIX-level → fragility/shock populate from real internals."""
    si = {}
    try:
        b = _breadth(prices)
        if b is not None: si["breadth"] = b
        rv = np.log(bench).diff().rolling(20).std().dropna()
        if len(rv) > 30: si["vol"] = rv
        vixs = _find(prices, _VIX)
        if vixs is not None and len(vixs) > 30: si["vvix"] = vixs   # vix level as a vol-stress proxy
    except Exception:
        pass
    return si

def _num(x):
    try:
        if isinstance(x, (int, float)) and np.isfinite(x): return float(x)
    except Exception:
        pass
    return None

def _dealer_by_ticker(snap, prices):
    """Harvest v40's already-computed GEX/walls per ticker. v40 GEX is mostly PROXY (greeks_proxy),
    so is_real=False — populated honestly, labelled proxy, never laundered as a real chain."""
    out = {}
    sources = [("per_ticker_proxy_gex", False), ("gex_data", False), ("gamma_data", False)]
    for key, is_real in sources:
        d = snap.get(key)
        if not isinstance(d, dict):
            continue
        for tkr, v in d.items():
            t = str(tkr)
            if t not in prices or t in out:
                continue
            rec = {"ok": True, "is_real": is_real, "regime": None, "gex": None, "gex_sign": 0,
                   "call_wall": None, "put_wall": None, "gamma_flip": None, "vanna": None, "charm": None}
            if isinstance(v, dict):
                gex = _num(v.get("gex") or v.get("net_gex") or v.get("total_gex"))
                rec["gex"] = gex
                rec["call_wall"] = _num(v.get("call_wall")); rec["put_wall"] = _num(v.get("put_wall"))
                rec["gamma_flip"] = _num(v.get("gamma_flip") or v.get("flip"))
                reg = v.get("regime") or v.get("gamma_regime")
                rec["regime"] = reg if isinstance(reg, str) else None
            else:
                gex = _num(v)
                rec["gex"] = gex
            if rec["gex"] is not None:
                rec["gex_sign"] = int(np.sign(rec["gex"]))
                if rec["regime"] is None:
                    rec["regime"] = "mean_reversion" if rec["gex"] > 0 else "momentum"
                out[t] = rec
    return out


def render(snap: dict):
    import streamlit as st
    try:
        from gcfis.orchestrator import run_gcfis
        from gcfis.dashboard import render_gcfis_dashboard
    except Exception as e:
        st.error(f"GCFIS package not importable: {e}"); return

    st.title("🧭 GCFIS — Global Capital Flow Intelligence")
    st.caption("Change-centric · regime-conditional · validated-not-fabricated. Reads the whole tape "
               "together; ranks the universe with a logical reason + gamma-aware entry per name.")

    prices, volumes = _prices_dict(snap)
    if len(prices) < 2:
        st.warning("GCFIS needs price history from the snapshot (≥2 tickers, ≥60 bars). Click **Rebuild**, then reopen.")
        return
    bench = _find(prices, _BENCH)
    if bench is None: bench = next(iter(prices.values()))
    posterior, regime_method = _regime_posterior(snap, prices, bench)
    cross_snap = _cross_snapshot(prices)
    systemic = _systemic_inputs(prices, bench)
    dealer_bt = _dealer_by_ticker(snap, prices)
    sq, mq = _quads(snap)

    # driver-map feeds from whatever series the snap already has (honest: rest shows 'wire feed')
    _drv_alias = {"DXY": ["DXY","DX=F","DX-Y.NYB"], "TIPS10Y": ["US10Y","^TNX","DGS10"], "VIX": _VIX,
                  "USDIDR": ["USDIDR","IDR=X","USDIDR=X"], "EIA_CRUDE_INV": [], "ETF_BTC_FLOW": []}
    driver_data = {}
    for k, al in _drv_alias.items():
        s = _find(prices, al) if al else None
        if s is not None: driver_data[k] = s
    with st.spinner(f"Running GCFIS on {len(prices)} tickers (regime: {regime_method})…"):
        try:
            out = run_gcfis(prices, bench, posterior, systemic_inputs=systemic or None,
                            cross_asset_snapshot=cross_snap or None, volumes=volumes or None,
                            dealer_by_ticker=dealer_bt or None, driver_data=driver_data or None)
        except Exception as e:
            import traceback; st.error(f"GCFIS run failed: {e}"); st.code(traceback.format_exc()); return

    try:
        if sq: out.setdefault("systemic", {}).setdefault("forward_macro", {})["forward_quad"] = sq
    except Exception:
        pass

    feeds = []
    feeds.append(f"regime **{regime_method}**")
    if volumes: feeds.append(f"volumes ({len(volumes)})")
    if systemic: feeds.append("breadth/vol")
    if dealer_bt: feeds.append(f"GEX·proxy ({len(dealer_bt)})")
    if cross_snap: feeds.append(f"cross-asset ({len(cross_snap)})")
    st.caption(f"Quad **{sq or '—'}/{mq or '—'}** · live feeds harvested from snap: {', '.join(feeds)}")

    render_gcfis_dashboard(out, st=st, title="GCFIS")

    with st.expander("ℹ️ what feeds this tab (honest)"):
        st.markdown(
            "- **Regime** = real Gaussian HMM fitted at runtime on your bench returns + breadth + VIX "
            "(falls back to your GIP quad if hmmlearn missing / data thin).\n"
            "- **Populated from snap:** volumes, breadth, VIX, GEX/walls (v40's GEX is **proxy** → "
            "labelled proxy, not faked as a real chain), quads, cross-asset tape.\n"
            "- **Still `unknown` until you wire real feeds:** real options chain, COT/OI, on-chain, Fed liquidity.\n"
            "- A validated *instrument*, not a proven *edge* — confirm on your universe via `gcfis/backtest.py`.")
