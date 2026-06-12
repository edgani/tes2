"""TAB 5 — TICKER INTELLIGENCE (most important page): one ticker → full conditional readout.
Top: GCFIS contract card · panels: flow/mode/response/BM/rotation · drivers of ITS market."""
from __future__ import annotations

def render(snap: dict):
    import streamlit as st
    from pages_lib._gcfis_inline import get_gcfis_output
    st.title("🔬 Ticker Intelligence")
    out = get_gcfis_output(snap, st)
    if not out:
        st.warning("Need snapshot prices. Rebuild, then reopen."); return
    per = out.get("per_ticker", {}) or {}
    if not per:
        st.caption("no scored tickers (all eliminated or insufficient history)"); return
    tickers = sorted(per.keys())
    tkr = st.selectbox("Ticker", tickers) if hasattr(st, "selectbox") else tickers[0]
    a = per.get(tkr, {})
    rank = out.get("ranking", {}) or {}
    row = None
    for bucket in ("master_long", "master_short", "deferred_longs", "avoided_long_only"):
        row = next((r for r in rank.get(bucket, []) if r.get("ticker") == tkr), None)
        if row: break
    try:
        from gcfis.dashboard import card_html
        if row:
            st.markdown(card_html(row), unsafe_allow_html=True)
        else:
            st.caption("👁 WATCH — did not clear confluence this regime (panels below still live)")
    except Exception:
        pass
    c = st.columns(4)
    c[0].metric("Market", a.get("market", "—"))
    c[1].metric("Mode", (a.get("market_mode") or {}).get("mode", "—"))
    c[2].metric("Flow", (a.get("flow") or {}).get("type", "—"))
    c[3].metric("Stage", a.get("stage", "—"))
    h = a.get("horizon") or {}
    if h.get("ok"):
        s = h.get("signs", {})
        st.caption(f"⏱ multi-TF alignment **{h['alignment']}/100** (d {s.get('daily',0):+d} · w {s.get('weekly',0):+d} · m {s.get('monthly',0):+d}) — doc-6 horizon stack")
    st.caption(f"🔗 causal chain: {a.get('theme') or '—'} → {a.get('bottleneck_node') or '—'} → {tkr}")
    dl = a.get("dealer") or {}
    if dl.get("gex_sign"):
        st.caption(f"🎲 dealer: gex_sign {dl.get('gex_sign'):+d} · regime {dl.get('regime','—')}" + (" · ⚠ proxy" if str(dl.get('source','')).lower()=='proxy' else ""))
    f = a.get("flow") or {}
    st.caption(f"flow: abs {f.get('absorption')} · eff {f.get('efficiency')} · pers {f.get('persistence')} · resil {f.get('resilience')} (OHLCV proxy)")
    rz = a.get("response") or {}
    if rz.get("ok"): st.caption(f"📍 risk-range response: **{rz.get('response')}** (quality {rz.get('quality')}, zone {rz.get('zone')})")
    bm = a.get("bm") or {}
    if bm.get("regime"):
        st.caption(f"🇮🇩 BM: **{bm['regime']}** score {bm.get('flow_score')} · EFD {bm.get('efd')} · ParF {bm.get('par_f')} · CorrF {bm.get('corr_f')} · LPM{'✓' if bm.get('lpm_valid') else '✗'}")
    rot = a.get("rotation") or {}
    if rot: st.caption(f"↻ primed by {rot.get('leader')} (fired {rot.get('days_since_fire')}d ago, ~{rot.get('window')}d window)")
    # drivers of THIS ticker's market
    try:
        from gcfis.market_drivers import ticker_driver_market
        dm = ticker_driver_market(tkr, a.get("market", "us"))
        dd = (out.get("drivers") or {}).get(dm)
        if dd:
            with st.expander(f"📡 what drives {dm.upper()} (surge up/down)"):
                for r in dd.get("drivers", [])[:9]:
                    z = r.get("reading_z"); zs = f"z {z:+.2f}" if z is not None else f"feed: {r['series']}"
                    st.markdown(f"<span style='font-size:.78rem'>[{r['horizon']}·{'★'*r['strength']}] {r['factor']} ({'+' if r['sign']>0 else '−'}) — {zs}</span>", unsafe_allow_html=True)
    except Exception:
        pass
