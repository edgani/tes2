"""🛰 Mission Control — doc-16 layout: WORLD STATE → macro strip → divergences →
OPPORTUNITY MATRIX (LONG/SHORT/EARLY/HEDGE) → FRAGILITY STACK (crash engine)."""
from __future__ import annotations


def render(snap):
    import streamlit as st
    from pages_lib._gcfis_inline import get_gcfis_output, num
    from gcfis.dashboard import card_scan_html
    out = get_gcfis_output(snap, st)
    if not out:
        st.error("GCFIS output unavailable — click Rebuild."); return
    rank = out.get("ranking", {}) or {}
    per = out.get("per_ticker", {}) or {}
    sysf = out.get("systemic_flat") or out.get("systemic") or {}
    crash = out.get("crash") or {}
    gip = (snap or {}).get("gip")
    sq = getattr(gip, "structural_quad", "—"); mq = getattr(gip, "monthly_quad", "—")
    cross = (sysf.get("cross_asset") or out.get("cross_asset") or {})
    xreg = cross.get("regime", "MIXED")
    rmethod = out.get("_regime_method") or out.get("regime_method") or "—"
    liq = num(sysf.get("liquidity"), 50); frag = num(sysf.get("fragility"), 50)
    shock = num(sysf.get("shock_prob"), 50)
    crowd_avg = (sum(float(a.get("crowding", 50) or 50) for a in per.values()) / max(len(per), 1)) if per else 50.0
    stress = 0.30 * (100 - liq) + 0.30 * frag + 0.25 * shock + 0.15 * crowd_avg
    intern = out.get("internals") or {}
    breadth = intern.get("breadth")

    # ---- Tier 1: WORLD STATE ----
    ctype = crash.get("type", "LOW")
    st.markdown(f"## 🌍 {sq} structural · {mq} monthly — cross-asset **{xreg}**"
                + (f" · ⚠ crash-type **{ctype}**" if ctype not in ("LOW", None) else ""))
    st.caption(f"regime engine: {rmethod} · crash basis: {crash.get('basis','—')}")
    for fs_ in (out.get("_feeds_status") or []): st.caption("📡 " + str(fs_))
    # ---- macro strip ----
    st.caption(f"LIQ {liq:.0f} · FRAG {frag:.0f} · SHOCK {shock:.0f} · CROWD {crowd_avg:.0f}"
               + (f" · BREADTH {breadth:.0%}" if breadth is not None else "")
               + f" · STRESS {stress:.0f}/100 (prior weights)")
    for dv in (cross.get("divergences") or []): st.warning(dv)
    for dv in (intern.get("divergences") or []): st.warning("🧬 " + dv)
    st.divider()

    from components.causal_map import render_causal_map
    st.markdown("### 🕸 Causal propagation")
    render_causal_map(st, out)
    st.divider()

    desk = out.get("final_desk") or {}
    picks = desk.get("picks", [])
    st.markdown(f"## 🎯 FINAL DESK — Top {len(picks)} · the only list that matters")
    st.caption(desk.get("note", ""))
    from gcfis.dashboard import desk_card_html
    for pk in picks: st.markdown(desk_card_html(pk), unsafe_allow_html=True)
    if not picks: st.caption("no pick clears the bar in this regime — standing aside IS the call")
    if desk.get("rejected_summary"):
        st.caption("rejected: " + " · ".join(f"{k} ×{v}" for k, v in desk["rejected_summary"].items()))
    st.divider()

    # ---- OPPORTUNITY MATRIX + FRAGILITY STACK (secondary inventory) ----
    rows_all = [x for b in ("master_long", "master_short", "deferred_longs", "avoided_long_only")
                for x in rank.get(b, [])]
    longs = rank.get("master_long", []); shorts = rank.get("master_short", [])
    early = sorted([r for r in rows_all
                    if (r.get("surge") or 0) >= 60 and float((per.get(r["ticker"], {}) or {}).get("crowding", 50) or 50) < 60
                    and r not in longs],
                   key=lambda r: -(r.get("surge") or 0))
    hedge = rank.get("deferred_longs", []) + (rank.get("sections", {}) or {}).get("distribution_warning", [])
    _seen = {r.get("ticker") for r in longs + shorts}
    hedge = [r for r in hedge if r.get("ticker") not in _seen]

    def _evkey(r): return (0 if r.get("entry_valid") else 1, -(r.get("ev") if r.get("ev") is not None else -999))
    colMain, colFrag = st.columns([3, 1])
    with colMain:
        st.markdown("### 🎯 Opportunity matrix")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown("**🟢 LONG**")
            for r in sorted(longs, key=_evkey)[:3]: st.markdown(card_scan_html(r), unsafe_allow_html=True)
            if not longs: st.caption("—")
        with c2:
            st.markdown("**🔴 SHORT**")
            for r in sorted(shorts, key=_evkey)[:3]: st.markdown(card_scan_html(r), unsafe_allow_html=True)
            if not shorts: st.caption("—")
        with c3:
            st.markdown("**🌱 EARLY** · surge & uncrowded")
            for r in early[:3]: st.markdown(card_scan_html(r), unsafe_allow_html=True)
            if not early: st.caption("—")
        with c4:
            st.markdown("**🛡 HEDGE/AVOID**")
            for r in hedge[:3]:
                st.caption(f"· **{r.get('ticker')}** {r.get('action','')} — {(r.get('why_now') or ['—'])[0][:60]}")
            if not hedge: st.caption("—")
    with colFrag:
        st.markdown("### 🧱 Fragility stack")
        st.metric("CRASH PRESSURE", f"{crash.get('pressure','—')}", ctype)
        comps = crash.get("components") or {}
        from components.mini_viz import hbar
        if comps and not hbar(st, "crash components", list(comps), list(comps.values()),
                              colors=["#f0883e"] * len(comps), fmt="{:.2f}"):
            for k, v in comps.items(): st.caption(f"{k}: {v:.2f}")
        bt = (crash.get("bottom") or {})
        st.caption(f"bottom: **{bt.get('state','—')}** ({bt.get('score','—')}/100)")
        st.caption(f"deferred {len(rank.get('deferred_longs', []))} · eliminated {len(rank.get('eliminated', []))}")

    if not longs:
        dl = [m.upper() for m, dd in (out.get("drivers") or {}).items() if "LONG" in str(dd.get("bias", ""))]
        if dl: st.caption("driver-bias longs (no GCFIS long yet): " + ", ".join(dl[:3]))
