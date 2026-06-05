"""dashboard.py — Restored from tes.zip original + Tier1Alpha panel moved to TOP."""
import streamlit as st


def render(snap: dict):
    """Entry point — Tier1Alpha is now MERGED into the regime card (no separate panel)."""
    # Tight layout so the whole dashboard fits ~one frame. The biggest win is killing Streamlit's
    # default ~6rem block-container top padding; then we tighten every gap/margin.
    st.markdown("""<style>
    .block-container{padding-top:1.3rem !important;padding-bottom:3rem !important;max-width:100% !important;}
    [data-testid="stVerticalBlock"]{gap:0.22rem !important;}
    [data-testid="stHorizontalBlock"]{gap:0.4rem !important;}
    [data-testid="stMetric"]{padding:0 !important;}
    [data-testid="stMetricValue"]{font-size:1.05rem !important;line-height:1.1 !important;}
    [data-testid="stMetricLabel"]{font-size:0.6rem !important;}
    [data-testid="stMetricLabel"] p{font-size:0.6rem !important;}
    .element-container{margin-bottom:0 !important;}
    [data-testid="stMarkdownContainer"] p{margin-bottom:0.08rem !important;font-size:0.82rem !important;}
    [data-testid="stCaptionContainer"]{margin:0 !important;}
    [data-testid="stCaptionContainer"] p{font-size:0.72rem !important;margin:0 !important;}
    .stPlotlyChart{margin:0 !important;}
    [data-testid="stExpander"]{margin:0 !important;}
    hr{margin:0.15rem 0 !important;}
    h1,h2,h3,h4{margin-top:0.05rem !important;margin-bottom:0.15rem !important;padding-top:0 !important;}
    [data-testid="stVerticalBlockBorderWrapper"]{border:1px solid #30363d !important;border-radius:10px !important;}
    </style>""", unsafe_allow_html=True)
    try:
        from pages_lib._dashboard_legacy import render as _legacy_render
    except Exception as e:
        st.error(f"Dashboard legacy module failed to load: {e}")
        _fallback_dashboard(snap)
        return

    prices = snap.get("prices", {}) or {}
    vix_now = snap.get("vix", 20.0)
    if vix_now is None or vix_now == 0:
        try:
            vix_series = prices.get("^VIX")
            if vix_series is not None and len(vix_series) > 0:
                vix_now = float(vix_series.iloc[-1])
        except Exception:
            vix_now = 20.0

    # ── HEADLINE FIRST: Quad Decoder is the most important macro read, so it leads. ──
    try:
        _render_quad_explainer(snap)
    except Exception:
        pass

    try:
        _legacy_render(snap, prices, vix_now)
    except Exception as e:
        import traceback
        st.error(f"Legacy dashboard error: {e}")
        with st.expander("Traceback"):
            st.code(traceback.format_exc())
        _fallback_dashboard(snap)
    return


_QM_CENTER = {"Q1": (-0.5, 0.5), "Q2": (0.5, 0.5), "Q3": (0.5, -0.5), "Q4": (-0.5, -0.5)}
_QM_FILL = {"Q1": "rgba(63,185,80,0.16)", "Q2": "rgba(210,153,34,0.16)",
            "Q3": "rgba(248,81,73,0.15)", "Q4": "rgba(88,166,255,0.15)"}
_QM_NAME = {"Q1": "Q1 · Goldilocks", "Q2": "Q2 · Reflation", "Q3": "Q3 · Stagflation", "Q4": "Q4 · Deflation"}


def _quad_map_figure(qe: dict, explanation: str = None):
    """2×2 Hedgeye GIP map: x=inflation RoC, y=growth RoC. Plots structural + monthly
    position and the transition arrow — the whole regime story in one picture."""
    import plotly.graph_objects as go
    sq = qe.get("structural_quad", "Q3")
    mq = qe.get("monthly_quad", sq)
    gq = qe.get("global_quad", sq)
    nq = (qe.get("where_it_goes", {}) or {}).get("implied_next", sq)

    fig = go.Figure()
    # quadrant backgrounds
    rects = {"Q1": (-1, 0, 0, 1), "Q2": (0, 1, 0, 1), "Q3": (0, 1, -1, 0), "Q4": (-1, 0, -1, 0)}
    for q, (x0, x1, y0, y1) in rects.items():
        fig.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1, line={"width": 0},
                      fillcolor=_QM_FILL[q], layer="below")
        cx, cy = _QM_CENTER[q]
        _nx, _ny = {"Q1": (-0.5, 0.88), "Q2": (0.5, 0.88), "Q3": (0.5, -0.12), "Q4": (-0.5, -0.12)}[q]
        fig.add_annotation(x=_nx, y=_ny, text=_QM_NAME[q], showarrow=False,
                           font={"size": 10, "color": "#8b949e"})
    # zero axes
    fig.add_shape(type="line", x0=0, x1=0, y0=-1, y1=1, line={"color": "#30363d", "width": 1})
    fig.add_shape(type="line", x0=-1, x1=1, y0=0, y1=0, line={"color": "#30363d", "width": 1})

    # three horizons, small deterministic offsets so co-located markers stay visible
    base = {"S": _QM_CENTER.get(sq, (0.5, -0.5)), "M": _QM_CENTER.get(mq, (0.5, -0.5)),
            "G": _QM_CENTER.get(gq, (0.5, -0.5))}
    offs = {"S": (-0.16, -0.13), "M": (0.16, 0.13), "G": (0.16, -0.13)}
    pos = {k: (base[k][0] + offs[k][0], base[k][1] + offs[k][1]) for k in base}
    # projected path toward implied-next quad (dashed) if it differs from structural
    if nq != sq:
        nx, ny = _QM_CENTER.get(nq, pos["M"])
        sx, sy = pos["S"]
        fig.add_annotation(x=nx, y=ny, ax=sx, ay=sy, xref="x", yref="y", axref="x", ayref="y",
                           showarrow=True, arrowhead=2, arrowsize=1.2, arrowwidth=2,
                           arrowcolor="#f0b429", opacity=0.85)
    for k, sym, col, lbl, tp, q in [
        ("S", "circle-open", "#e6edf3", "Structural", "bottom center", sq),
        ("M", "x", "#39d0d8", "Monthly", "bottom center", mq),
        ("G", "diamond-open", "#f0b429", "Global", "middle right", gq),
    ]:
        px_, py_ = pos[k]
        fig.add_trace(go.Scatter(x=[px_], y=[py_], mode="markers+text", text=[f"{lbl}"],
                                 textposition=tp, textfont={"color": col, "size": 10},
                                 marker={"symbol": sym, "size": 20, "color": col,
                                         "line": {"color": col, "width": 3}},
                                 hovertemplate=f"{lbl}: {q}<extra></extra>", showlegend=False))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#c9d1d9", "family": "Inter, sans-serif"},
        margin={"t": 8, "b": 28, "l": 44, "r": 10}, height=140, showlegend=False,
        xaxis={"title": {"text": "← Disinflasi      Inflasi (RoC)      Inflasi ↑ →",
                         "font": {"size": 10, "color": "#8b949e"}}, "range": [-1, 1],
               "zeroline": False, "showgrid": False, "tickvals": []},
        yaxis={"title": {"text": "← Growth ↓      Growth (RoC)      Growth ↑ →",
                         "font": {"size": 10, "color": "#8b949e"}}, "range": [-1, 1],
               "zeroline": False, "showgrid": False, "tickvals": []},
    )
    # ── Explanation INSIDE the map plot (Edward: merge the circled text into the map box) ──
    if explanation:
        # compact 1–2 line headline only (top-left, small) so it doesn't blanket the cells/markers.
        # The full why/transition detail is rendered as a caption BELOW the map by the caller.
        fig.update_layout(height=210, margin={"t": 6, "b": 24, "l": 40, "r": 8})
        fig.add_annotation(xref="paper", yref="paper", x=0.0, y=1.0, xanchor="left", yanchor="top",
                           text=explanation, showarrow=False, align="left",
                           font={"size": 9, "color": "#e6edf3"},
                           bgcolor="rgba(13,17,23,0.80)", bordercolor="#d29922", borderwidth=1, borderpad=4)
    return fig


def _render_quad_explainer(snap: dict, in_tab: bool = False):
    """🧭 Quad Decoder — why this quad, what changes it, where it goes, + Ricky scenarios."""
    qe = snap.get("quad_explainer") or {}
    if not qe or not qe.get("ok"):
        if in_tab:
            st.caption("Quad Decoder belum tersedia (rebuild snapshot).")
        return

    if not in_tab:
        st.markdown("<div style='font-size:0.95rem;font-weight:700;margin:0 0 2px;'>🧭 Quad Decoder — kenapa · apa yang ngubah · ke mana</div>", unsafe_allow_html=True)

    wig = qe.get("where_it_goes", {})
    stage = wig.get("stage", "—")
    color = {"RIPE": "#cf222e", "BUILDING": "#bf8700", "DORMANT": "#1a7f37"}.get(stage, "#57606a")
    c1, c2, c3, c4 = st.columns([1.2, 1, 1, 1])
    c1.markdown(f"<div style='background:{color};color:white;padding:8px;border-radius:6px;"
                f"text-align:center;font-weight:700'>Transition: {stage}<br>"
                f"<span style='font-size:0.9rem'>→ {wig.get('implied_next','?')} {('('+wig.get('implied_next_name','')+')') if wig.get('implied_next_name') else ''}</span></div>",
                unsafe_allow_html=True)
    c2.metric("Structural", qe.get("structural_quad", "?"), qe.get("structural_name", ""))
    c3.metric("Monthly (leading)", qe.get("monthly_quad", "?"), qe.get("monthly_name", ""))
    c4.metric("Global (50-country)", qe.get("global_quad", "?"), qe.get("global_name", ""))

    # ── Quad Decoder box (map + simplified explanation, all in ONE bordered box) | Economic Calendar ──
    mcol, ecol = st.columns([1.35, 1])
    with mcol:
        with st.container(border=True):
            # Build the explanation FIRST so it renders INSIDE the map plot (not as a block below)
            wc = qe.get("what_changes", [])
            _pindah = " · ".join(f"→{w['to']} {w['trigger']}" for w in wc) if wc else ""
            _hint = wig.get("action_hint", "")
            try:
                from pages_lib._dashboard_legacy import _catalyst_monitor_v2
                _cats, _ = _catalyst_monitor_v2(snap, sq=qe.get("structural_quad", "Q3"),
                                                mq=qe.get("monthly_quad", "Q2"),
                                                next_q=wig.get("implied_next", "Q2"))
                _chips = " ".join(f"{_e}{_n}" for _n, _v, _e, _d, _im in _cats[:5]) if _cats else ""
            except Exception:
                _chips = ""
            # In-plot: SHORT headline only (current→next + action). Keeps it "in the map" without
            # blanketing the quad labels/markers (simpel, gak nutupin, tetap kebaca).
            _nq = wig.get("implied_next", "?"); _nqn = wig.get("implied_next_name", "")
            _headline = "<br>".join([x for x in [
                f"<b>{qe.get('structural_quad','')} → {_nq}</b>"
                + (f" · {qe.get('structural_name','')}→{_nqn}" if _nqn else ""),
                (f"🎯 <b>{_hint}</b>" if _hint else ""),
            ] if x])
            try:
                st.plotly_chart(_quad_map_figure(qe, explanation=_headline), width='stretch',
                                config={"displayModeBar": False})
            except Exception:
                pass
            # Full detail BELOW the map, inside the SAME bordered box — readable, covers nothing.
            _detail = " · ".join([x for x in [qe.get('why', ''),
                                              (f"<b>Pindah:</b> {_pindah}" if _pindah else ""),
                                              (f"⚡ {_chips}" if _chips else "")] if x])
            if _detail:
                st.markdown(f"<div style='font-size:0.72rem;color:#b9c2cc;line-height:1.35;"
                            f"margin-top:4px'>{_detail}</div>", unsafe_allow_html=True)
    with ecol:
        with st.container(border=True):
            try:
                from pages_lib._dashboard_legacy import _economic_calendar_mini
                st.markdown(_economic_calendar_mini(sq=qe.get("structural_quad", "Q3"),
                                                    mq=qe.get("monthly_quad", "Q2")), unsafe_allow_html=True)
            except Exception:
                pass

    with st.expander("📖 Detail — playbook per-quad + skenario Ricky", expanded=False):
        pb = qe.get("playbook", {})
        cur, nxt = pb.get("current", {}), pb.get("next", {})
        if cur:
            pc1, pc2 = st.columns(2)
            with pc1:
                st.caption(f"**Playbook {qe.get('structural_quad','')} (sekarang)**")
                st.caption(f"🟢 Strong: {cur.get('strong','')}")
                st.caption(f"🔴 Weak: {cur.get('weak','')}")
            with pc2:
                if nxt and wig.get("implied_next") != qe.get("structural_quad"):
                    st.caption(f"**Playbook {wig.get('implied_next','')} (kalau transisi kejadian)**")
                    st.caption(f"🟢 Strong: {nxt.get('strong','')}")
                    st.caption(f"🔴 Weak: {nxt.get('weak','')}")
            for cav in pb.get("caveats", []):
                st.caption(f"⚠️ {cav}")

        scen = qe.get("scenarios", [])
        if scen:
            st.markdown(f"**📚 Skenario Ricky relevan ({len(scen)}):**")
            for s in scen:
                tick = " · ".join(s.get("tickers", [])) if s.get("tickers") else ""
                st.caption(f"**{s['title']}** — _{s.get('signal','')}_ {('· ' + tick) if tick else ''}")
    # (Bias Guard panel removed from dashboard per spec — engine still runs in background.)


def _render_bias_guard(snap: dict):
    """🪞 Bias Guard — steelman the opposite, base rate, active biases, pre-mortem."""
    bg = snap.get("perspective") or {}
    if not bg or not bg.get("ok"):
        return
    st.divider()
    with st.expander(f"🪞 Bias Guard / Perspektif — lawan view sendiri (lean: {bg.get('current_lean','')})",
                     expanded=False):
        st.markdown(f"**🔄 Steelman ({bg.get('opposite','')} case):** {bg.get('steelman','')}")
        st.info(f"📏 Outside view: {bg.get('outside_view','')}")
        st.markdown("**⚠️ Bias yang aktif sekarang (cek sebelum entry):**")
        for b in bg.get("active_biases", []):
            st.caption(f"• **{b['bias']}** — {b['why']} → _{b['check']}_")
        st.markdown(f"**💀 Pre-mortem:** {bg.get('pre_mortem','')}")
        st.caption(bg.get("note", ""))


def _render_tier1alpha_panel(snap: dict):
    """Tier1Alpha-style 4-signal market structure — COMPACT horizontal strip at top.
    Consolidates the market-structure signals + SPX levels + global quad into one tight block."""
    import streamlit as st

    t1a = snap.get("tier1alpha", {})
    if not t1a:
        try:
            from engines.tier1alpha_model import compute_tier1alpha
            t1a = compute_tier1alpha(snap)
        except Exception:
            t1a = {}

    st.markdown("##### 📐 Market Structure Report (Tier1Alpha-style)")

    if t1a and t1a.get("signals"):
        sigs = t1a["signals"]

        def _sig_color(name, val):
            green = {"gamma_exposure": "Positive", "systematic_flow": "Bullish",
                     "pv_band_rr": "Long", "strategic_allocation": "Risk On"}
            red = {"gamma_exposure": "Negative", "systematic_flow": "Bearish",
                   "pv_band_rr": "Short", "strategic_allocation": "Risk Off"}
            if val == green.get(name): return "#1a7f37"
            if val == red.get(name): return "#cf222e"
            return "#bf8700"

        labels = {
            "gamma_exposure": "SPX Gamma",
            "systematic_flow": "Systematic Flow",
            "pv_band_rr": "PV Band R/R",
            "strategic_allocation": "Strategic Alloc",
        }
        # 4 colored boxes in ONE horizontal row (compact)
        cols = st.columns(4)
        for col, (key, label) in zip(cols, labels.items()):
            sig = sigs.get(key, {})
            val = sig.get("value", "Neutral")
            color = _sig_color(key, val)
            col.markdown(
                f"<div style='background:{color};color:white;padding:8px 6px;"
                f"border-radius:6px;text-align:center;font-weight:700;font-size:0.78rem;'>"
                f"{label}<br><span style='font-size:0.9rem;'>{val}</span></div>",
                unsafe_allow_html=True)

        # SPX levels + Global Quad (Structural/Monthly intentionally omitted —
        # they live in the regime box below; no duplication)
        lv = t1a.get("spx_levels", {})
        gip = snap.get("gip", {})
        if isinstance(gip, dict):
            global_q = gip.get("global_quad") or gip.get("structural_quad") or snap.get("current_quad", "Q3")
        else:
            global_q = getattr(gip, "global_quad", None) or getattr(gip, "structural_quad", None) or "Q3"
        quad_names = {"Q1": "Goldilocks", "Q2": "Reflation", "Q3": "Stagflation", "Q4": "Deflation"}

        m = st.columns(4)
        m[0].metric("SPX Last", f"{lv.get('last_price', 0):,.0f}" if lv.get('last_price') else "—")
        m[1].metric("Upper PV (TRR)", f"{lv.get('upper_pv_band', 0):,.0f}" if lv.get('upper_pv_band') else "—")
        m[2].metric("Lower PV (LRR)", f"{lv.get('lower_pv_band', 0):,.0f}" if lv.get('lower_pv_band') else "—")
        m[3].metric("🌍 Global Quad (Hedgeye)", global_q, quad_names.get(global_q, ""))

        # Compact notes (collapsed)
        with st.expander("ℹ️ Signal notes", expanded=False):
            for key, label in labels.items():
                note = sigs.get(key, {}).get("note", "")
                if note:
                    st.caption(f"**{label}:** {note}")
            if t1a.get("data_quality") == "vix_proxy":
                st.caption("⚠️ Gamma using VIX proxy — SPY options give precise GEX on Rebuild.")
            st.caption(f"Hedgeye GIP: Global economy in **{global_q}** — {quad_names.get(global_q, '')}. "
                       f"(Structural/Monthly/Markov quads di box bawah.)")
    else:
        st.caption("Tier1Alpha signals computing — click Rebuild.")

    st.divider()


def _fallback_dashboard(snap: dict):
    """Fallback minimal dashboard if legacy fails."""
    st.title("🏠 Dashboard (fallback)")
    gip = snap.get("gip", {})
    if isinstance(gip, dict):
        sq = gip.get("structural_quad", "?")
        mq = gip.get("monthly_quad", "?")
    else:
        sq = getattr(gip, "structural_quad", "?")
        mq = getattr(gip, "monthly_quad", "?")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Structural Quad", sq)
    c2.metric("Monthly Quad", mq)
    c3.metric("VIX", f"{(snap.get('vix') or 0):.2f}")
    c4.metric("DXY", f"{(snap.get('dxy') or 0):.2f}")
    health = snap.get("market_health", {})
    score = health.get("score", 50) if isinstance(health, dict) else 50
    c5.metric("Health", f"{score:.0f}/100")
