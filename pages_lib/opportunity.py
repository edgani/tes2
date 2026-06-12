"""TAB 3 — OPPORTUNITY ENGINE: 'What has the highest conditional EV NOW?'
GCFIS doc-4 sections (lifecycle-aware) + the existing Alpha Center engines below."""
from __future__ import annotations

def render(snap: dict):
    import streamlit as st
    from pages_lib._gcfis_inline import get_gcfis_output
    st.title("⚡ Opportunity Engine")
    out = get_gcfis_output(snap, st)
    if out:
        try:
            from gcfis.dashboard import card_html
            sec = (out.get("ranking", {}) or {}).get("sections", {}) or {}
            def _sec(rows, head, note):
                st.markdown(f"#### {head} · {len(rows)}"); st.caption(note)
                for r in rows[:6]: st.markdown(card_html(r), unsafe_allow_html=True)
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
