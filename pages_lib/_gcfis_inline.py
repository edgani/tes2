"""pages_lib/_gcfis_inline.py — compact GCFIS confluence section foldable into ANY existing tab
(Alpha Center, Dashboard). Reuses the gcfis_intel harvesting + the dashboard card. Fully guarded:
any failure returns silently so it can never break the host tab."""
from __future__ import annotations

def render_gcfis_section(snap: dict, st, max_long: int = 8, max_short: int = 4):
    try:
        from pages_lib import gcfis_intel as gi
        from gcfis.orchestrator import run_gcfis
        from gcfis.dashboard import card_html
    except Exception:
        return
    try:
        prices, volumes = gi._prices_dict(snap)
        if len(prices) < 2:
            return
        bench = gi._find(prices, gi._BENCH)
        if bench is None: bench = next(iter(prices.values()))
        posterior, method = gi._regime_posterior(snap, prices, bench)
        out = run_gcfis(prices, bench, posterior,
                        systemic_inputs=gi._systemic_inputs(prices, bench) or None,
                        cross_asset_snapshot=gi._cross_snapshot(prices) or None,
                        volumes=volumes or None, dealer_by_ticker=gi._dealer_by_ticker(snap, prices) or None)
    except Exception:
        return
    try:
        rank = out.get("ranking", {}) or {}
        longs = rank.get("master_long", []) or []; shorts = rank.get("master_short", []) or []
        deferred = rank.get("deferred_longs", []) or []; pf = rank.get("portfolio", {}) or {}
        cross = (out.get("systemic", {}) or {}).get("cross_asset", {}) or {}
        title = (f"🧭 GCFIS confluence — {len(longs)} long / {len(shorts)} short"
                 f"{' / ' + str(len(deferred)) + ' deferred' if deferred else ''}  ·  regime {method}")
        with st.expander(title, expanded=bool(longs or shorts)):
            if cross.get("ok") and cross.get("regime"):
                st.caption(f"📡 cross-asset: **{cross.get('regime')}** — {cross.get('why','')}")
            if pf.get("warning"):
                st.warning("📦 " + pf["warning"])
            if not (longs or shorts):
                st.caption("No names cleared product-confluence (theme×bottleneck×accumulation×adoption×reflexivity) this regime.")
            for r in longs[:max_long]:
                st.markdown(card_html(r), unsafe_allow_html=True)
            for r in shorts[:max_short]:
                st.markdown(card_html(r), unsafe_allow_html=True)
            for r in deferred[:3]:
                st.markdown(card_html(r, deferred=True), unsafe_allow_html=True)
            st.caption("Full radar + lead–lag + opportunity scenarios in the 🧭 GCFIS tab.")
    except Exception:
        return


def get_gcfis_output(snap: dict, st):
    """Run GCFIS once per snapshot and cache in session_state (all 6 tabs reuse this)."""
    try:
        key = "_gcfis_out_" + str(id(snap.get("prices")))
        if hasattr(st, "session_state") and key in st.session_state:
            return st.session_state[key]
        from pages_lib import gcfis_intel as gi
        from gcfis.orchestrator import run_gcfis
        prices, volumes = gi._prices_dict(snap)
        if len(prices) < 2:
            return None
        bench = gi._find(prices, gi._BENCH)
        if bench is None: bench = next(iter(prices.values()))
        posterior, method = gi._regime_posterior(snap, prices, bench)
        drv = {}
        for k, al in {"DXY": ["DXY","DX=F","DX-Y.NYB"], "TIPS10Y": ["US10Y","^TNX","DGS10"],
                      "VIX": gi._VIX, "USDIDR": ["USDIDR","IDR=X","USDIDR=X"]}.items():
            s = gi._find(prices, al)
            if s is not None: drv[k] = s
        feeds_status = []
        try:                                                   # REAL FRED: NetLiq + 10Y TIPS (level series)
            fr = None
            if hasattr(st, "session_state"):
                fr = st.session_state.get("_fred_feed")
            if fr is None:
                from gcfis.feeds.fred_feed import fetch_fred
                fr = fetch_fred()
                if hasattr(st, "session_state"): st.session_state["_fred_feed"] = fr
            fser, fstat = fr
            drv.update(fser)                                   # FEDLIQ + TIPS10Y override price proxies
            feeds_status.append(fstat)
        except Exception as e:
            feeds_status.append(f"fred: error {type(e).__name__}")
        typef = None
        try:                                                   # REAL Type-F from IDX daily summary (per-day cached)
            if any(str(k).upper().endswith(".JK") for k in prices):
                tf = st.session_state.get("_typef_feed") if hasattr(st, "session_state") else None
                if tf is None:
                    from gcfis.feeds.typef_idx import build_typef
                    tf = build_typef(list(prices), days=120)
                    if hasattr(st, "session_state"): st.session_state["_typef_feed"] = tf
                typef, tstat = tf
                feeds_status.append(tstat)
        except Exception as e:
            feeds_status.append(f"typef: error {type(e).__name__}")
        out = run_gcfis(prices, bench, posterior,
                        systemic_inputs=gi._systemic_inputs(prices, bench) or None,
                        cross_asset_snapshot=gi._cross_snapshot(prices) or None,
                        volumes=volumes or None, dealer_by_ticker=gi._dealer_by_ticker(snap, prices) or None,
                        driver_data=drv or None, typef_by_ticker=typef or None)
        out["_regime_method"] = method
        out["_feeds_status"] = feeds_status
        try:
            sq, mq = gi._quads(snap)
            if sq: out.setdefault("systemic", {}).setdefault("forward_macro", {})["forward_quad"] = sq
        except Exception:
            pass
        if hasattr(st, "session_state"):
            try: st.session_state[key] = out
            except Exception: pass
        return out
    except Exception:
        return None


def num(x, default=50.0):
    """Robust numeric extractor: accepts number OR nested engine dict ({'score':..}/{'value':..}/first numeric)."""
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, dict):
        for k in ("score", "value", "level", "pressure", "composite", "prob", "pct"):
            v = x.get(k)
            if isinstance(v, (int, float)):
                return float(v)
        for v in x.values():
            if isinstance(v, (int, float)):
                return float(v)
    return float(default)
