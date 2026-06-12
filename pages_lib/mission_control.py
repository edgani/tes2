"""TAB 1 — MISSION CONTROL: 'What changed that matters NOW?' (attachment-1 final design).
System State summary → Stress/Shock → rotation → TOP EV TRADES. Stress weights are PRIORS."""
from __future__ import annotations

def render(snap: dict):
    import streamlit as st
    from pages_lib._gcfis_inline import get_gcfis_output
    try:
        from gcfis.dashboard import card_html, quad_label, regime_color
    except Exception as e:
        st.error(f"GCFIS unavailable: {e}"); return
    st.title("🛰 Mission Control")
    out = get_gcfis_output(snap, st)
    if not out:
        st.warning("Need snapshot prices (≥2 tickers, ≥60 bars). Rebuild, then reopen."); return
    sysd = out.get("systemic", {}); rank = out.get("ranking", {})
    fwd = sysd.get("forward_macro", {}); cross = sysd.get("cross_asset", {}) or {}
    frag = (sysd.get("fragility", {}) or {}).get("fragility", 0) or 0
    shock = (sysd.get("shock", {}) or {}).get("shock_prob", 0) or 0
    liq = (sysd.get("liquidity", {}) or {}).get("liquidity_regime", 50) or 50
    longs = rank.get("master_long", []); shorts = rank.get("master_short", [])
    crowd = [r.get("crowding", 50) for r in longs[:8]]
    avg_crowd = sum(crowd)/len(crowd) if crowd else 50.0
    stress = 0.30*(100-liq) + 0.30*frag + 0.25*shock + 0.15*avg_crowd   # PRIOR weights (doc formula adapted to live feeds)
    # ── SYSTEM STATE (master regime summary) ──
    q = quad_label(fwd.get("forward_quad")); cr = cross.get("regime") or "—"
    themes = {}
    for r in longs:
        th = r.get("theme") or r.get("category") or "—"; themes[th] = themes.get(th, 0) + 1
    best = ", ".join(k for k, _ in sorted(themes.items(), key=lambda kv: -kv[1])[:3]) or "—"
    avoid = ", ".join(r["ticker"] for r in (rank.get("sections", {}) or {}).get("distribution_warning", [])[:4]) or "—"
    risk_line = ("Liquidation tape — new longs deferred" if cross.get("defer_longs")
                 else f"Shock {shock:.0f} / Fragility {frag:.0f}" if (shock > 50 or frag > 60)
                 else "No acute systemic trigger")
    st.markdown(
        f"**SYSTEM STATE** — {q} · cross-asset <span style='color:{regime_color(cr)}'>{cr}</span> · "
        f"regime engine: {out.get('_regime_method','—')}<br>"
        f"**STRESS** {stress:.0f}/100 (liq {100-liq:.0f} · frag {frag:.0f} · shock {shock:.0f} · crowd {avg_crowd:.0f} — prior weights)<br>"
        f"**BEST** {best} &nbsp;·&nbsp; **AVOID/REDUCE** {avoid}<br>"
        f"**TOP RISK** {risk_line}", unsafe_allow_html=True)
    c = st.columns(5)
    c[0].metric("Forward Quad", q); c[1].metric("Stress", f"{stress:.0f}")
    c[2].metric("Fragility", f"{frag:.0f}"); c[3].metric("Shock P", f"{shock:.0f}"); c[4].metric("Liquidity", f"{liq:.0f}")
    if cross.get("ok"):
        st.caption("📡 " + (cross.get("why") or ""))
        for d in cross.get("divergences", []): st.warning(d)
    intern = out.get("internals") or {}
    for d in intern.get("divergences", []): st.warning("🧬 " + d)
    pf = rank.get("portfolio", {}) or {}
    if pf.get("warning"): st.warning("📦 " + pf["warning"])
    rot = out.get("rotation") or {}
    if rot:
        st.caption("↻ rotation primed: " + " · ".join(f"{f}←{d.get('leader')} (~{d.get('window')}d)" for f, d in list(rot.items())[:4]))
    st.divider()
    st.markdown("#### 🎯 TOP EV TRADES")
    if not longs and not shorts:
        st.caption("No names cleared product-confluence this regime.")
    for r in longs[:5]: st.markdown(card_html(r), unsafe_allow_html=True)
    for r in shorts[:2]: st.markdown(card_html(r), unsafe_allow_html=True)
    if rank.get("deferred_longs"):
        with st.expander(f"⏸ deferred longs ({len(rank['deferred_longs'])}) — cross-asset gate"):
            for r in rank["deferred_longs"][:4]: st.markdown(card_html(r, deferred=True), unsafe_allow_html=True)
    if rank.get("eliminated"):
        st.caption("🗑 stage-1 eliminated: " + ", ".join(e["ticker"] for e in rank["eliminated"][:8]))
