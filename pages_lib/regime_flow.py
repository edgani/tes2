"""TAB 2 — REGIME & CAPITAL FLOW: 'Why is the market behaving this way?'
Macro/liquidity pulse (existing dashboard) + driver map (conditional relationships) + lead-lag."""
from __future__ import annotations

def render(snap: dict):
    import streamlit as st
    st.title("🌐 Regime & Capital Flow")
    try:
        from pages_lib import dashboard
        dashboard.render(snap)
    except Exception as e:
        st.warning(f"macro pulse unavailable: {e}")
    from pages_lib._gcfis_inline import get_gcfis_output
    out = get_gcfis_output(snap, st)
    if not out: return
    st.divider()
    drv = out.get("drivers") or {}
    if drv:
        st.markdown("#### 📡 Conditional driver map (surge-up / surge-down per market)")
        for mkt, dd in drv.items():
            bias = dd.get("bias")
            col = "#1a7f37" if bias == "LONG" else "#cf222e" if bias == "SHORT" else "#57606a"
            with st.expander(f"{mkt.upper()} — bias {bias}" + (f" (score {dd.get('score')}, {dd.get('fed')} feeds)" if dd.get('score') is not None else "")):
                for r in dd.get("drivers", []):
                    z = r.get("reading_z")
                    zs = f"z {z:+.2f}" if z is not None else f"feed: {r['series']}"
                    st.markdown(f"<span style='font-size:.78rem'>[{r['horizon']}·{'★'*r['strength']}] {r['factor']} ({'+' if r['sign']>0 else '−'}) — <b style='color:{col}'>{zs}</b><br><span style='color:#8b949e'>{r['note']}</span></span>", unsafe_allow_html=True)
    intern = out.get("internals") or {}
    if intern.get("pairs") or intern.get("breadth") is not None:
        with st.expander("🔀 relative & internals (doc-12: relative > absolute)"):
            if intern.get("breadth") is not None:
                st.caption(f"breadth (>50dma): {intern['breadth']:.0%} · top-5 share of +returns: {intern.get('top5_share','—')}")
            for pr in intern.get("pairs", []):
                st.markdown(f"`{pr['pair']}` z20 **{pr['z20']:+.2f}** — {pr['note']}")
            for d in intern.get("divergences", []): st.warning(d)
    ll = out.get("leadlag") or {}
    with st.expander("🕸 capital-flow lead–lag (discovered, not hardcoded)"):
        edges = ll.get("edges") or []
        if not edges: st.caption("no significant stable edges in current universe")
        for e in edges[:10]:
            st.markdown(f"`{e.get('leader')}` → `{e.get('follower')}` · lag {e.get('lag')}d · conf {e.get('confidence')} · {e.get('sign')}")
