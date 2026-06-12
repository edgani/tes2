"""TAB 6 — PORTFOLIO & SCENARIO: 'What if I'm wrong?'
Existing stress page + GCFIS concentration guard + scenario-lite (historical betas, labeled) + Research Lab."""
from __future__ import annotations

def render(snap: dict):
    import streamlit as st
    import numpy as np, pandas as pd
    st.title("📊 Portfolio & Scenario")
    try:
        from pages_lib import portfolio_stress
        portfolio_stress.render(snap)
    except Exception as e:
        st.warning(f"stress page unavailable: {e}")
    from pages_lib._gcfis_inline import get_gcfis_output
    out = get_gcfis_output(snap, st)
    if not out: return
    st.divider()
    pf = (out.get("ranking", {}) or {}).get("portfolio", {}) or {}
    if pf:
        st.markdown(f"**📦 Concentration guard** — effective bets: {pf.get('effective_bets','—')}"
                    + (f" · ⚠ {pf['warning']}" if pf.get("warning") else " · clusters ok"))
    # ── scenario-lite: HISTORICAL beta to driver proxies (not causal — labeled) ──
    try:
        from pages_lib import gcfis_intel as gi
        prices, _ = gi._prices_dict(snap)
        proxies = {"Dollar squeeze (DXY +2%)": (gi._find(prices, ["DXY","DX=F","DX-Y.NYB"]), 0.02),
                   "Rates shock (10Y +50bp ~ +3%)": (gi._find(prices, ["US10Y","^TNX","DGS10"]), 0.03),
                   "Oil spike (+20%)": (gi._find(prices, ["USOIL","WTI","CL=F","XTIUSD"]), 0.20)}
        rows_l = (out.get("ranking", {}) or {}).get("master_long", [])
        held = [r["ticker"] for r in rows_l[:10]] or list(prices.keys())[:10]
        scen_any = False
        for name, (proxy, shock) in proxies.items():
            if proxy is None: continue
            pr = pd.Series(proxy).pct_change().tail(120)
            impact = []
            for t in held:
                s = prices.get(t)
                if s is None: continue
                rr = pd.Series(s).pct_change().tail(120)
                ix = rr.index.intersection(pr.index)
                if len(ix) < 60: continue
                b = float(np.cov(rr.loc[ix], pr.loc[ix])[0, 1] / (pr.loc[ix].var() or 1e-9))
                impact.append((t, b * shock * 100))
            if impact:
                scen_any = True
                impact.sort(key=lambda x: x[1])
                losers = ", ".join(f"{t} {v:+.1f}%" for t, v in impact[:3])
                winners = ", ".join(f"{t} {v:+.1f}%" for t, v in impact[-3:][::-1])
                st.markdown(f"**{name}** → worst: {losers} · best: {winners}")
        if scen_any:
            st.caption("scenario-lite = 120d historical beta × shock — correlation, BUKAN causality; regime can flip signs")
    except Exception:
        pass
    with st.expander("🧪 Research Lab — validation status (honest)"):
        st.markdown(
            "- engine logic: **synthetic suite passing** (flow 5/5, BM regimes 3/3, elimination, response, drivers)\n"
            "- real-market edge: **NOT yet validated** — needs walk-forward + Deflated Sharpe + permutation p per market\n"
            "- BM weights 3.0/0.9/0.7 dan stress/scenario weights = **PRIORS**\n"
            "- flow/mode dari OHLCV proxy (tick/L2 absent) · GEX = proxy (labeled) · expectation-gap & narrative-discovery = seam (butuh feed)")
