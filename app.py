"""MacroRegime v2 — clean rebuild, data-first, ChatGPT-aligned. Populated from the real pipeline."""
from __future__ import annotations
import streamlit as st


def _banner(ctx):
    macro = ctx.get("macro", {})
    real = [v["label"] for v in macro.values() if v.get("provenance") == "REAL"]
    vt = ctx.get("vix_term", {})
    c = st.columns([2, 2, 2])
    with c[0]:
        st.markdown(f"**🟢 REAL feeds: {len(real)}**")
        st.caption(", ".join(real) if real else "none here — deploy to Cloud for live FRED credit/NetLiq")
    with c[1]:
        st.markdown(f"**🟡 VIX term: {vt.get('provenance', 'SEAM')}**")
        st.caption(vt.get("state", vt.get("note", "—")))
    with c[2]:
        st.markdown(f"**🔴 Seams: {len(ctx.get('seams', {}))}**")
        st.caption(" · ".join(list(ctx.get("seams", {}))[:4]) + " …")
    for s in ctx.get("status", []):
        st.caption("📡 " + str(s))


def _pick_card(p):
    col = "#3fb950" if p["side"] == "long" else "#f85149"
    rs = "".join(f"<div style='color:#c9d1d9;font-size:11px'>· {w}</div>" for w in p.get("reasons", []))
    return (f"<div style='border:1px solid #30363d;border-left:4px solid {col};border-radius:8px;"
            f"padding:8px 12px;margin:6px 0;background:#0d1117'>"
            f"<span style='font-size:15px;font-weight:800'>{p['ticker']}</span> "
            f"<span style='color:{col};font-weight:800'>{p['side'].upper()}</span> "
            f"<span style='color:#8b949e;font-size:12px'>conv {p['conviction']} · EV {p['ev']}% · RR {p['rr']} · {p['market']}" + (f" · {p.get('stage')}" if p.get('stage') else '') + "</span>"
            f"{rs}<div style='color:#8b949e;font-size:11px;margin-top:3px'>entry {p['entry']} · stop {p['stop']} · target {p['target']}</div></div>")


def main():
    st.set_page_config(page_title="MacroRegime v2", layout="wide")
    st.sidebar.title("🛰 MacroRegime v2")
    st.sidebar.caption("clean rebuild · data-first · ChatGPT-aligned")

    from core.data_layer import build_data_context
    from core.pipeline import run_pipeline, demo_universe
    from engines.shock_engine import run_shock_engine
    from core.live_data import fetch_prices, DEFAULT_UNIVERSE

    if st.sidebar.button("🔄 Reload live data"):
        for k in ("_snap", "_v2_fred", "_v2_vix", "_price_status"):
            st.session_state.pop(k, None)

    snap = st.session_state.get("_snap")
    prices = (snap or {}).get("prices") if snap else None
    if not prices:                                  # try LIVE before falling back to demo
        live, pstatus = fetch_prices(DEFAULT_UNIVERSE)
        st.session_state["_price_status"] = pstatus
        if live:
            prices = live
            st.session_state["_snap"] = {"prices": live}
    pstatus = st.session_state.get("_price_status", [])
    is_demo = not prices
    if is_demo:
        prices = demo_universe()

    ctx = build_data_context(prices, session=st)
    out = run_pipeline(prices, data_ctx=ctx)
    per, picks, internals, crash = out["per_ticker"], out["picks"], out["internals"], out["crash"]

    if is_demo:
        st.warning("⚠ DEMO universe — live price fetch returned nothing in THIS environment "
                   "(sandbox blocks Yahoo/FRED). On Streamlit Cloud this loads real OHLCV and the "
                   "banner flips to LIVE. Status: " + (pstatus[0] if pstatus else "n/a"))
    else:
        st.success(f"🟢 LIVE — {pstatus[0] if pstatus else 'real prices loaded'}. "
                   "Use '🔄 Reload live data' (sidebar) to refresh.")

    tabs = st.tabs(["🛰 Mission Control", "🌊 Regime & Liquidity", "🧬 Narratives & Bottlenecks",
                    "🗺 Market Intelligence", "🔬 Ticker Intelligence", "📊 Portfolio & Risk", "🧪 Research Lab"])

    with tabs[0]:
        st.subheader("Mission Control")
        _banner(ctx); st.divider()
        from core.visuals import (compute_quad, quad_map_figure, stress_bar_html,
                                  big_metric_html)
        shock = run_shock_engine(ctx.get("macro", {}), ctx.get("vix_term", {}), breadth=internals.get("breadth"))
        qe = compute_quad(prices, ctx.get("macro", {}))

        # regime policy: dynamic weighting + HARD override (systemic credit → longs off)
        from core.regime_policy import classify_regime, apply_hard_override
        from engines.ai_capex import run_ai_capex
        from core.what_changed import snapshot_state, diff_state
        ri = classify_regime(shock, qe)
        picks, override_note = apply_hard_override(picks, ri)
        ai = run_ai_capex(prices)
        if override_note:
            st.error(override_note)

        # WHAT CHANGED (vs last refresh, stored in session)
        cur = snapshot_state(qe, shock, picks, ai)
        deltas = diff_state(st.session_state.get("_prev_state"), cur)
        st.session_state["_prev_state"] = cur

        # ── HERO: Hedgeye quad (left, large) + risk stress bars (right) ──
        hero_l, hero_r = st.columns([0.62, 0.38])
        with hero_l:
            st.markdown(f"#### 🧭 GIP Quad — **{qe['structural_quad']} · {qe['structural_name']}** "
                        f"→ implied **{qe['where_it_goes']['implied_next']}**")
            try:
                st.plotly_chart(quad_map_figure(qe), use_container_width=True, config={"displayModeBar": False})
            except Exception:
                st.caption(f"quad: {qe['structural_quad']} {qe['structural_name']} (plotly unavailable)")
            st.caption(f"GROC {qe['GROC']:+.2f} · IROC {qe['IROC']:+.2f} · {qe['provenance']}")
        with hero_r:
            scol = "#3fb950" if shock["shock_prob"] < 40 else "#d29922" if shock["shock_prob"] < 65 else "#f85149"
            st.markdown(big_metric_html("Shock pressure", shock["shock_prob"],
                                        f"{shock['crash_type']} · conf {shock['confidence']}", scol),
                        unsafe_allow_html=True)
            bars = "".join(stress_bar_html(k.replace("_", " "), v * 100, shock["provenance"][k])
                           for k, v in shock["components"].items())
            st.markdown(f"<div style='margin-top:8px'>{bars}</div>", unsafe_allow_html=True)
            st.markdown(big_metric_html("Crash (cohort)", crash["pressure"],
                                        f"{crash['type']} · {crash['bottom']['state']}"), unsafe_allow_html=True)
        st.caption("shock basis: " + shock["basis"])
        st.markdown(f"**Regime:** `{ri['regime']}` — {ri['why']}"
                    + (f"  ·  **AI-cycle {ai['ai_cycle_score']}** ({ai['phase']})" if ai.get("ok") else ""))
        st.divider()

        # ── WHAT CHANGED TODAY (delta cards) ──
        st.markdown("##### ⚡ What changed")
        wc_cols = st.columns(min(3, len(deltas)) or 1)
        _wc_col = {"regime": "#d29922", "shock": "#f85149", "crash": "#f85149", "ai": "#39d0d8",
                   "new_pick": "#3fb950", "dropped": "#8b949e", "crowding": "#d29922"}
        for i, c in enumerate(deltas[:6]):
            with wc_cols[i % len(wc_cols)]:
                col = _wc_col.get(c["kind"], "#6e7681")
                st.markdown(f"<div style='border-left:3px solid {col};background:#12161c;border-radius:6px;"
                            f"padding:6px 10px;margin:3px 0;font-size:12px;color:#c9d1d9'>{c['text']}</div>",
                            unsafe_allow_html=True)
        st.divider()

        # ── WHAT CHANGED (delta-lite) + FINAL DESK ──
        st.markdown(f"### 🎯 FINAL DESK — {len(picks)} cleared the quality gate")
        st.caption(out["note"] + " · quality > quantity, no padding")
        if picks:
            cols = st.columns(2)
            for i, p in enumerate(picks[:10]):
                with cols[i % 2]:
                    st.markdown(_pick_card(p), unsafe_allow_html=True)
        else:
            st.info("0 setups clear the gate on this universe. The flow-classifier is direction-gated "
                    "so it won't emit a wrong-side call; richer accumulation/RS staging drives the long "
                    "side (see Research Lab for the open calibration item).")

    with tabs[1]:
        st.subheader("Regime & Liquidity")
        macro = ctx.get("macro", {}); shown = False
        for key in ("net_liquidity", "hy_oas", "ig_oas", "real_yield_10y", "curve_10y2y", "vix_spot"):
            v = macro.get(key)
            if v and v.get("value") is not None:
                st.caption(f"· {v['label']}: **{v['value']:.2f}** ({v['provenance']})"); shown = True
        if not shown:
            st.warning("No REAL macro here (sandbox). On Cloud: NetLiq, HY/IG OAS credit, real yield, curve, VIX — REAL via FRED.")
        st.divider(); st.markdown("**Cross-asset internals (relative > absolute)**")
        if internals.get("breadth") is not None:
            st.caption(f"breadth (>50dma proxy): {internals['breadth']:.0%} · top-5 share {internals.get('top5_share','—')}")
        for pr in internals.get("pairs", []):
            st.caption(f"`{pr['pair']}` z20 {pr['z20']:+.2f} — {pr['note']}")
        for d in internals.get("divergences", []):
            st.warning("🧬 " + d)

    with tabs[2]:
        st.subheader("Narratives & Bottlenecks")
        from core.supply_chain import run_supply_chain
        from core.visuals import stress_bar_html
        sc = run_supply_chain()
        st.markdown(f"##### 🔗 Bottleneck network (Citrini) — tightest: **{sc['tightest']}** · "
                    f"hidden second-order winner: **{sc['hidden_winner']}**")
        st.caption("pressure = tightness × propagation centrality. Retail buys the obvious node; "
                   "the hidden winner is high-pressure but downstream/overlooked.")
        for n in sc["ranked"]:
            nd = sc["nodes"][n]
            tk = ", ".join(nd["tickers"][:4])
            st.markdown(stress_bar_html(f"{n} ({tk})", nd["pressure"] * 100,
                                        f"tight {nd['tightness']} · centrality {nd['centrality']}"),
                        unsafe_allow_html=True)
        st.divider()
        st.markdown("**Surge pre-conditioning leaders (price-derived):**")
        top = sorted(((t, (a.get("surge") or {}).get("score", 0)) for t, a in per.items()), key=lambda kv: -kv[1])[:6]
        st.caption(" · ".join(f"{t} {s}" for t, s in top))

    with tabs[3]:
        st.subheader("Market Intelligence — per-market state")
        markets = {}
        for t, a in per.items():
            markets.setdefault(a["market"], []).append(a)
        sub = st.tabs([f"{m.upper()} ({len(v)})" for m, v in markets.items()]) if markets else []
        for i, (m, rows) in enumerate(markets.items()):
            with (sub[i] if sub else st.container()):
                st.caption({"us": "DNA: gamma/breadth/credit/semis-RS", "crypto": "DNA: liquidity/reflexivity/funding",
                            "fx": "DNA: rate differentials/DXY/carry", "commodity": "DNA: inventory/term-structure",
                            "idx": "DNA: foreign flow/LPM/participation (long-only)"}.get(m, ""))
                import pandas as _pd
                tbl = _pd.DataFrame([{
                    "ticker": a["ticker"],
                    "flow": (a["flow"] or {}).get("type", "—"),
                    "mode": (a["market_mode"] or {}).get("mode", "—"),
                    "align": (a["horizon"] or {}).get("alignment", "—"),
                    "surge": (a["surge"] or {}).get("score", "—"),
                    "stage": a.get("stage", "—"),
                    "RS": (round(a["alpha_rs"], 2) if a.get("alpha_rs") is not None else "—"),
                    "verdict": (a["verdict"]["side"].upper() if a.get("verdict") else "watch"),
                } for a in rows])
                st.dataframe(tbl, use_container_width=True, hide_index=True)

    with tabs[4]:
        st.subheader("Ticker Intelligence — thesis / positioning / execution")
        if per:
            tkr = st.selectbox("Ticker", sorted(per)) if hasattr(st, "selectbox") else sorted(per)[0]
            a = per.get(tkr, {}); vd = a.get("verdict")
            t1, t2, t3 = st.columns([0.35, 0.4, 0.25])
            with t1:
                st.markdown(f"### {tkr} — {(vd['side'].upper() if vd else 'WATCH')}")
                st.caption(f"market {a.get('market')}")
                if vd:
                    for r in vd["reasons"]:
                        st.caption("· " + r)
                else:
                    st.caption("no actionable setup — flow/mode/alignment not aligned")
                h = a.get("horizon") or {}
                if h.get("ok"):
                    s = h["signs"]; st.caption(f"⏱ multi-TF {h['alignment']}/100 (d {s['daily']:+d} w {s['weekly']:+d} m {s['monthly']:+d})")
            with t2:
                st.markdown("**Positioning / flow**"); f = a.get("flow") or {}
                st.caption(f"flow {f.get('type','—')} · abs {f.get('absorption','—')} · eff {f.get('efficiency','—')} (OHLCV proxy)")
                st.caption(f"mode {(a.get('market_mode') or {}).get('mode','—')}")
                st.caption(f"surge {(a.get('surge') or {}).get('score','—')}")
                st.caption("dealer GEX/Vanna — SEAM (needs options feed)")
            with t3:
                st.markdown("**Execution**")
                if vd:
                    st.metric("Entry", vd["entry"]); st.metric("Stop", vd["stop"]); st.caption(f"target {vd['target']} · RR {vd['rr']} · EV {vd['ev']}%")
                else:
                    st.caption("—")

    with tabs[5]:
        st.subheader("Portfolio & Risk")
        longs = [p for p in picks if p["side"] == "long"]; shorts = [p for p in picks if p["side"] == "short"]
        st.caption(f"actionable book: {len(longs)} long · {len(shorts)} short")
        st.caption("contagion engine + correlation cluster guard — next pass (oil→inflation→rates→growth)")

    with tabs[6]:
        st.subheader("Research Lab — validation gates (anti-overfit)")
        st.caption("Every weight is a PRIOR until DSR ≥ 0.95 + permutation p < 0.05, else labeled NOISE. "
                   "No live edge claimed from synthetic validation.")
        st.markdown("**Known open calibration items (honest):**")
        st.caption("1. flow_type direction-blindness (volume ramp → DISTRIBUTION on uptrends) — top priority")
        st.caption("2. breadth/forward-growth need index constituents (free, computable on Cloud)")
        st.caption("3. options GEX / ETF-flow / earnings-revision = paid seams (declared, not faked)")


if __name__ == "__main__":
    main()
