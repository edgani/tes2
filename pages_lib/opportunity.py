"""TAB 3 — OPPORTUNITY ENGINE: 'What has the highest conditional EV NOW?'
GCFIS doc-4 sections (lifecycle-aware) + the existing Alpha Center engines below."""
from __future__ import annotations

def render(snap: dict):
    import streamlit as st
    from pages_lib._gcfis_inline import get_gcfis_output
    st.title("⚡ Opportunity Engine")
    out = get_gcfis_output(snap, st)
    if out:
        desk = out.get("final_desk") or {}
        st.markdown(f"## 🎯 FINAL DESK — Top {len(desk.get('picks', []))}")
        st.caption(desk.get("note", ""))
        from gcfis.dashboard import desk_card_html
        for pk in desk.get("picks", []): st.markdown(desk_card_html(pk), unsafe_allow_html=True)
        st.divider()
        with st.expander("🧬 narrative lifecycle (doc-16: Emerging→Institutional→Crowded→Mania→Exhaustion)"):
            per = out.get("per_ticker") or {}
            agg = {}
            for av in per.values():
                th = av.get("theme")
                if not th: continue
                agg.setdefault(th, []).append((float(av.get("crowding", 50) or 50),
                                               float(av.get("adoption_velocity", 0) or 0)))
            pts = [(th, sum(x for x, _ in v) / len(v), sum(y for _, y in v) / len(v)) for th, v in agg.items()]
            drew = False
            if pts:
                try:
                    import plotly.graph_objects as go
                    fig = go.Figure(go.Scatter(x=[p1 for _, p1, _ in pts], y=[p2 for _, _, p2 in pts],
                                               mode="markers+text", text=[n0 for n0, _, _ in pts],
                                               textposition="top center", textfont={"size": 10, "color": "#c9d1d9"},
                                               marker={"size": 13, "color": "#58a6ff"}))
                    for x0, x1, lbl in [(0, 35, "EMERGING"), (35, 60, "INSTITUTIONAL"), (60, 85, "CROWDED"), (85, 100, "MANIA")]:
                        fig.add_vrect(x0=x0, x1=x1, fillcolor="rgba(88,166,255,0.04)", line_width=0,
                                      annotation_text=lbl, annotation_position="top left",
                                      annotation_font={"size": 9, "color": "#8b949e"})
                    fig.add_hline(y=0, line={"color": "#30363d", "width": 1})
                    fig.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(13,17,23,0.5)",
                                      font={"color": "#8b949e", "size": 10}, margin={"t": 18, "b": 30, "l": 40, "r": 12},
                                      xaxis={"title": "crowding →", "gridcolor": "#21262d", "range": [0, 100]},
                                      yaxis={"title": "adoption velocity (vel<0 below line = EXHAUSTION)", "gridcolor": "#21262d"})
                    st.plotly_chart(fig, use_container_width=True)
                    drew = True
                except Exception:
                    drew = False
            if not drew:
                for n0, c0, v0 in pts: st.caption(f"{n0}: crowd {c0:.0f} · vel {v0:+.2f}")
                if not pts: st.caption("no live themes in universe")
    if out:
        try:
            from gcfis.dashboard import card_html, card_scan_html
            sec = (out.get("ranking", {}) or {}).get("sections", {}) or {}
            def _sec(rows, head, note):
                st.markdown(f"#### {head} · {len(rows)}"); st.caption(note)
                for r in rows[:6]: st.markdown(card_scan_html(r), unsafe_allow_html=True)
            _sec(sec.get("early_monsters", []), "💎 EARLY MONSTERS", "structural accumulation · uncrowded · weeks–months")
            _sec(sec.get("squeeze", []), "⚡ SQUEEZE ENGINE", "forced-flow potential · tactical")
            _sec(sec.get("tactical_momentum", []), "🚀 TACTICAL MOMENTUM", "accepted expansion · days–weeks")
            _sec(sec.get("mean_reversion", []), "🔄 MEAN REVERSION", "exhaustion / reclaim scalps")
            _sec(sec.get("distribution_warning", []), "🔴 DISTRIBUTION WARNING", "late-stage / reduce / short where shortable")
        except Exception as e:
            st.warning(f"GCFIS sections unavailable: {e}")
    st.divider()
    with st.expander("🧠 Alpha Center engines (bottleneck thesis · conviction · narrative)", expanded=False):
        try:
            from pages_lib import alpha_center
            alpha_center.render(snap)
        except Exception as e:
            st.warning(f"alpha center unavailable: {e}")
    with st.expander("📖 Themes & narratives"):
        try:
            from pages_lib import themes
            themes.render(snap)
        except Exception as e:
            st.warning(f"themes unavailable: {e}")
