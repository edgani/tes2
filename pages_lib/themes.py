"""themes.py — Scenario narratives consolidated"""
import streamlit as st

def render(snap):
    st.title("📖 Themes & Scenarios")
    st.caption("Playbook per quad, macro narratives (Ricky2212/MentorBaik), active scenarios, permanent themes.")

    # ── PLAYBOOK PER QUAD (all 4 GIP quads; current one highlighted) ──
    try:
        from engines.quad_explainer import _PLAYBOOK, _NAME
        gip = snap.get("gip", {}) or {}
        cur_sq = (gip.get("structural_quad") if isinstance(gip, dict) else None) or snap.get("current_quad", "Q3")
        cur_mq = (gip.get("monthly_quad") if isinstance(gip, dict) else None) or cur_sq
        st.markdown("### 🎯 Playbook per Quad (GIP Hedgeye)")
        qcol = st.columns(4)
        qcolors = {"Q1": "#3FB950", "Q2": "#D29922", "Q3": "#F85149", "Q4": "#A371F7"}
        for i, q in enumerate(["Q1", "Q2", "Q3", "Q4"]):
            pb = _PLAYBOOK.get(q, {})
            tag = ""
            if q == cur_sq:
                tag += " · 🔵 Structural"
            if q == cur_mq:
                tag += " · ✕ Monthly"
            border = "3px solid #fff" if (q in (cur_sq, cur_mq)) else "1px solid #30363d"
            with qcol[i]:
                st.markdown(
                    f"<div style='border:{border};border-radius:8px;padding:8px;background:{qcolors[q]}22;min-height:150px'>"
                    f"<div style='font-weight:800;color:{qcolors[q]}'>{q} · {_NAME.get(q,'')}{tag}</div>"
                    f"<div style='font-size:0.72rem;margin-top:6px;color:#3FB950'><b>Strong:</b> {pb.get('strong','')}</div>"
                    f"<div style='font-size:0.72rem;margin-top:4px;color:#F85149'><b>Weak:</b> {pb.get('weak','')}</div>"
                    f"</div>", unsafe_allow_html=True)
        st.caption("Quad sekarang ditandai border putih. Strong = sektor/aset yang biasanya outperform di quad itu; "
                   "Weak = yang underperform. Ini peta rotasi: posisikan ke 'Strong' quad sekarang + ancang-ancang ke next quad (bawah).")
        st.divider()
    except Exception as e:
        st.caption(f"Playbook per quad unavailable: {e}")

    # ── NEXT-QUAD PLAYBOOK — position AHEAD of the transition (Keith storm-prep) ──
    try:
        from engines.narrative_engine import generate_next_quad_playbook
        pb = generate_next_quad_playbook(snap)
        if pb.get("next_quad"):
            with st.container(border=True):
                hdr = f"### 🧭 Next-Quad Playbook — ancang-ancang"
                st.markdown(hdr)
                so = pb.get("storm_or_opportunity")
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown(f"**Sekarang:** {pb['current_quad']}")
                with c2:
                    st.markdown(f"**Berikutnya:** {pb['next_quad']} ({pb.get('next_prob',0):.0%})")
                if so:
                    st.markdown(f"**{so}**")
                if pb.get("early_rotation_edge"):
                    st.success(f"🎯 **Early edge** (next-quad winners yang masih murah krn belum quad-nya): "
                               + ", ".join(pb["early_rotation_edge"]))
                cc1, cc2 = st.columns(2)
                with cc1:
                    st.markdown("**🟢 Rotate INTO (akumulasi duluan):**")
                    for x in pb.get("rotate_into", [])[:7]:
                        st.markdown(f"- {x}")
                with cc2:
                    st.markdown("**🔴 Rotate OUT OF (kurangi sebelum shift):**")
                    for x in pb.get("rotate_out_of", [])[:7]:
                        st.markdown(f"- {x}")
                if pb.get("next_quad_factor"):
                    st.caption(f"Factor tilt berikutnya: **{pb['next_quad_factor']}**")
                if pb.get("stag_on_lag"):
                    st.warning("🟡 **Stag-on-a-Lag** terdeteksi — Q2→Q3 pivot building. Mulai hedge inflasi + de-risk growth.")
        st.divider()
    except Exception as e:
        pass

    # ── RICKY2212 NARRATIVES (from narrative_universe) ───────────────────
    narrative = snap.get("narrative", {})
    if narrative and isinstance(narrative, dict):
        macro = narrative.get("macro_narrative", {})
        if macro and macro.get("headline"):
            st.markdown(f"### 🧠 Macro Narrative")
            st.info(f"**{macro.get('headline','')}**\n\n{macro.get('narrative','')}")
        bn = narrative.get("active_bottlenecks", [])
        if bn:
            with st.expander(f"🔒 Active Bottlenecks ({len(bn)})", expanded=False):
                for b in bn[:8]:
                    st.caption(f"• **{b.get('name','').replace('_',' ').title()}** — {b.get('description', b.get('thesis',''))[:140]}")
        chains = narrative.get("active_causal_chains", [])
        if chains:
            with st.expander(f"🔗 Active Causal Chains ({len(chains)})", expanded=False):
                for c in chains[:8]:
                    st.caption(f"• **{c.get('name','').replace('_',' ').title()}** — {c.get('description','')[:140]}")

    # ── Ricky thesis library (browsable) ─────────────────────────────────
    try:
        from config.narrative_universe import NARRATIVES, TICKER_NARRATIVES
        with st.expander(f"📚 Ricky2212 Thesis Library ({len(NARRATIVES)} articles)", expanded=False):
            search = st.text_input("Search narratives (ticker / theme)", key="narr_search")
            shown = 0
            for nid, n in NARRATIVES.items():
                title = n.get("title", nid)
                tickers = n.get("tickers", [])
                themes_l = n.get("themes", [])
                hay = (title + " " + " ".join(tickers) + " " + " ".join(themes_l)).lower()
                if search and search.lower() not in hay:
                    continue
                if shown >= 15:
                    break
                shown += 1
                st.markdown(f"**{title}**")
                meta = []
                if tickers: meta.append(f"Tickers: {', '.join(tickers[:6])}")
                if n.get("regime_signal"): meta.append(f"Signal: {n['regime_signal']}")
                if n.get("priority"): meta.append(f"Priority: {n['priority']}/10")
                st.caption(" · ".join(meta))
                content = n.get("content", "")
                if content:
                    st.caption(content[:280] + "…")
                st.divider()
    except Exception as e:
        st.caption(f"Narrative library: {e}")

    st.markdown("### 🌐 Active Scenarios")

    scenarios = snap.get("scenarios", []) or snap.get("active_scenarios", [])
    # Normalize wrap before fallback
    if isinstance(scenarios, dict):
        scenarios = scenarios.get("active_scenarios", []) or scenarios.get("all_scenarios", [])
    scenarios = [s for s in (scenarios or []) if isinstance(s, dict)]

    if not scenarios:
        # Fallback: run scenario_discovery directly
        try:
            from engines.scenario_discovery_engine import run_scenario_discovery
            gip = snap.get("gip", {})
            quad = "Q3"
            if isinstance(gip, dict):
                quad = gip.get("monthly_quad") or gip.get("structural_quad") or "Q3"
            elif gip is not None:
                quad = getattr(gip, "monthly_quad", None) or getattr(gip, "structural_quad", None) or "Q3"
            result = run_scenario_discovery(gip_result=gip, current_quad=quad)
            scenarios = result.get("active_scenarios", []) if isinstance(result, dict) else []
        except Exception as e:
            st.warning(f"Scenario discovery error: {e}")
            scenarios = []

    if not scenarios:
        st.info("No scenarios available.")
        return

    # Theme cards
    for sc in scenarios:
        # Normalize fields — handle both run_scenario_discovery format and legacy format
        name = sc.get("name") or sc.get("scenario") or "?"
        thesis = sc.get("thesis", "")
        catalyst = sc.get("catalyst", "")
        prob = sc.get("probability")
        if prob is None:
            prob = sc.get("active_score", 0)
        prob_pct = prob * 100 if prob < 1.5 else prob
        prob_color = "#3FB950" if prob_pct > 70 else "#D29922" if prob_pct > 50 else "#8B949E"

        longs = sc.get("tickers_long") or sc.get("tickers") or []
        shorts = sc.get("tickers_short", [])

        with st.container():
            st.markdown(f"""<div class='narrative-card'>
                <div style='display:flex;align-items:center;justify-content:space-between;'>
                    <span style='font-weight:700;font-size:1rem;color:#E6EDF3;'>{name}</span>
                    <span style='background:{prob_color};color:#0D1117;padding:2px 10px;border-radius:12px;font-size:0.7rem;font-weight:800;'>{prob_pct:.0f}% prob</span>
                </div>
                <div style='font-size:0.78rem;color:#E6EDF3;margin-top:8px;line-height:1.5;'>{thesis}</div>
                <div style='font-size:0.65rem;color:#8B949E;margin-top:6px;'><b>Catalyst:</b> {catalyst}</div>
            </div>""", unsafe_allow_html=True)

            if longs or shorts:
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**🟢 Long Exposure**")
                    for t in longs:
                        st.caption(f"• {t}")
                with c2:
                    if shorts:
                        st.markdown("**🔴 Short Exposure**")
                        for t in shorts:
                            st.caption(f"• {t}")
            st.markdown("---")
    
    # Citrini themes (always-on)
    st.subheader("📚 Permanent Themes (Citrini + Hedgeye)")
    permanent = [
        {
            "name": "Atoms Over Bits",
            "thesis": "Citrini thesis — physical AI bottlenecks (packaging, memory, optical, materials) outperform software. Seagate +200% in 2025 = early proof.",
            "tickers": ["MU", "STX", "WDC", "AVGO", "MRVL", "COHR", "LITE", "AMKR", "ASX", "TSM"],
        },
        {
            "name": "AI Power Infrastructure",
            "thesis": "Data center power crisis — 1000W+ chips need liquid cooling, transformers, gas turbines, nuclear baseload, GaN power.",
            "tickers": ["VRT", "ETN", "VST", "CEG", "CCJ", "SMR", "OKLO", "NVTS", "GEV"],
        },
        {
            "name": "China REE Export Controls",
            "thesis": "China weaponizing rare earth exports → Western miners + processors + magnet alternatives.",
            "tickers": ["MP", "USAR", "TMC", "UAMY", "LMT", "NOC"],
        },
        {
            "name": "AI Bureaucracy Alpha",
            "thesis": "Citrini — companies cutting headcount via AI: insurers, consultants, ad agencies, SaaS adopters.",
            "tickers": ["ACN", "CAP", "OMC", "WPP", "SAP"],
        },
        {
            "name": "Quad Rotation (Hedgeye)",
            "thesis": "Current Quad determines sector book — Q2=cyclicals/commodities, Q3=gold/defensives, Q4=duration/USD.",
            "tickers": ["XLE", "XLU", "XLF", "TLT", "UUP", "GLD"],
        },
    ]
    for theme in permanent:
        with st.expander(f"📌 {theme['name']}"):
            st.markdown(theme["thesis"])
            st.caption(f"**Tickers:** {', '.join(theme['tickers'])}")
