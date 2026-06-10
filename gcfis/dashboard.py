"""dashboard.py — GCFIS render layer. ONE reusable renderer you call from ANY tab (Market, Alpha
Center, etc.). Pure-logic helpers (badges/formatting) are streamlit-free so they're unit-tested.
Aesthetic: dark, minimal, horizontal dividers (no heavy boxes)."""
from __future__ import annotations

# ---------- pure logic (testable without streamlit) ----------
def alpha_badge(row: dict, deferred: bool = False) -> tuple[str, str]:
    """Map a GCFIS signal to an Alpha-Center-style verdict badge -> (label, hex)."""
    act, valid, direction = row.get("action"), row.get("entry_valid"), row.get("direction")
    if deferred:                                   return ("⏸ DEFER (liquidation)", "#b08900")
    if act == "BUILD_LONG" and valid:              return ("✅ ALPHA-READY", "#1a7f37")
    if act == "BUILD_LONG" and not valid:          return ("🟡 READY · WAIT ENTRY", "#b08900")
    if act == "BUILD_SHORT":                       return ("🔻 SHORT", "#cf222e")
    if act == "START_SCALING":                     return ("🔶 WARMING", "#bc4c00")
    return ("👁 WATCH", "#57606a")

def format_entry(row: dict) -> str:
    if not row.get("entry_type"):
        return "—"
    return (f"{row['entry_type']} · γ={row.get('gamma_regime','?')} · "
            f"in {row.get('entry_px','?')} / stop {row.get('stop','?')} / tgt {row.get('target','?')} · "
            f"R/R {row.get('rr','?')}")

def regime_color(regime: str | None) -> str:
    return {"DELEVERAGING": "#cf222e", "DEFLATION_GROWTH_SCARE": "#cf222e", "STAGFLATION_SCARE": "#bc4c00",
            "GROWTH_ON": "#1a7f37", "MONETARY_EASING": "#1a7f37", "MIXED": "#57606a"}.get(regime or "", "#57606a")

def quad_label(q: str | None) -> str:
    return {"Q1": "Q1 Goldilocks", "Q2": "Q2 Reflation", "Q3": "Q3 Stagflation", "Q4": "Q4 Deflation"}.get(q or "", "Quad —")

# ---------- streamlit render ----------
def render_gcfis_dashboard(out: dict, st=None, title: str = "GCFIS"):
    if st is None:
        import streamlit as st  # noqa
    if not out or not out.get("ok"):
        st.warning("GCFIS produced no output."); return
    sysd = out.get("systemic", {}); rank = out.get("ranking", {})
    fwd = sysd.get("forward_macro", {}); cross = sysd.get("cross_asset", {})
    frag = sysd.get("fragility", {}); shock = sysd.get("shock", {}); liq = sysd.get("liquidity", {})

    st.markdown(f"### {title} — systemic radar")
    c = st.columns(5)
    c[0].metric("Forward Quad", quad_label(fwd.get("forward_quad")))
    cr = cross.get("regime") if cross.get("ok") else "—"
    c[1].markdown(f"**Cross-Asset**<br><span style='color:{regime_color(cr)};font-size:1.1rem'>{cr}</span>", unsafe_allow_html=True)
    c[2].metric("Fragility", frag.get("fragility", "—"))
    c[3].metric("Shock P", shock.get("shock_prob", "—"))
    c[4].metric("Liquidity", liq.get("liquidity_regime", "—"))

    if cross.get("ok"):
        st.caption(f"📡 {cross.get('why','')}")
        for d in cross.get("divergences", []):
            st.warning(d)
    st.divider()

    def _table(rows, header, empty):
        st.markdown(f"#### {header}  ·  {len(rows)}")
        if not rows:
            st.caption(empty); return
        deferred_set = header.startswith("⏸")
        for r in rows:
            label, col = alpha_badge(r, deferred=deferred_set)
            st.markdown(
                f"<div style='border-left:3px solid {col};padding:.3rem .6rem;margin:.25rem 0'>"
                f"<b>{r['ticker']}</b> <span style='color:{col}'>{label}</span> "
                f"<span style='float:right;color:#8b949e'>conv {r.get('conviction','?')}</span><br>"
                f"<span style='color:#c9d1d9;font-size:.85rem'>{r.get('reason','')}</span></div>",
                unsafe_allow_html=True)

    _table(rank.get("master_long", []), "🟢 LONG", "No qualified longs this regime.")
    _table(rank.get("master_short", []), "🔴 SHORT", "No qualified shorts.")
    _table(rank.get("master_spot", []), "💎 SPOT (uncrowded accumulation)", "No sweet-spot names.")
    deferred = rank.get("deferred_longs", [])
    if deferred:
        _table(deferred, "⏸ DEFERRED LONGS (cross-asset gate)", "")

    with st.expander("lead–lag (discovered)"):
        ll = out.get("leadlag", {})
        st.json(ll if ll.get("ok") else {"note": "need >=2 tickers / pairs"})
