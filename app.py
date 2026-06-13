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
            f"<span style='color:#8b949e;font-size:12px'>conv {p['conviction']} · EV {p['ev']}% · RR {p['rr']} · {p['market']}</span>"
            f"{rs}<div style='color:#8b949e;font-size:11px;margin-top:3px'>entry {p['entry']} · stop {p['stop']} · target {p['target']}</div></div>")


def main():
    st.set_page_config(page_title="MacroRegime v2", layout="wide")
    st.sidebar.title("🛰 MacroRegime v2")
    st.sidebar.caption("clean rebuild · data-first · ChatGPT-aligned")

    from core.data_layer import build_data_context
    from core.pipeline import run_pipeline, demo_universe
    from engines.shock_engine import run_shock_engine

    snap = st.session_state.get("_snap")
    prices = (snap or {}).get("prices") if snap else None
    is_demo = not prices
    if is_demo:
        prices = demo_universe()

    ctx = build_data_context(prices, session=st)
    out = run_pipeline(prices, data_ctx=ctx)
    per, picks, internals, crash = out["per_ticker"], out["picks"], out["internals"], out["crash"]

    if is_demo:
        st.warning("⚠ DEMO universe (sandbox blocks live feeds). Engine output below is REAL on this "
                   "synthetic data; deploy to Cloud + provide your universe for live results.")

    tabs = st.tabs(["🛰 Mission Control", "🌊 Regime & Liquidity", "🧬 Narratives & Bottlenecks",
                    "🗺 Market Intelligence", "🔬 Ticker Intelligence", "📊 Portfolio & Risk", "🧪 Research Lab"])

    with tabs[0]:
        st.subheader("Mission Control")
        _banner(ctx); st.divider()
        shock = run_shock_engine(ctx.get("macro", {}), ctx.get("vix_term", {}), breadth=internals.get("breadth"))
        cc = st.columns([1, 1, 2])
        with cc[0]:
            st.metric("SHOCK PRESSURE", shock["shock_prob"], shock["crash_type"]); st.caption(f"confidence: {shock['confidence']}")
        with cc[1]:
            st.metric("CRASH (cohort)", crash["pressure"], crash["type"]); st.caption(f"bottom: {crash['bottom']['state']}")
        with cc[2]:
            st.caption("shock basis: " + shock["basis"])
            for k, v in shock["components"].items():
                st.caption(f"{k}: {v:.2f} · {shock['provenance'][k]}")
        st.divider()
        st.markdown(f"### 🎯 FINAL DESK — {len(picks)} cleared the quality gate")
        st.caption(out["note"] + " · quality > quantity: only valid setups, no padding")
        for p in picks[:10]:
            st.markdown(_pick_card(p), unsafe_allow_html=True)
        if not picks:
            st.info("0 setups clear the gate on this universe. **Honest finding:** flow_type is "
                    "direction-blind — it reads volume expansion as DISTRIBUTION even on strong uptrends "
                    "(NVDA +33% → NEUTRAL, never ACCUMULATION). That is the #1 calibration fix queued next; "
                    "verdicts are gated so it can't emit a wrong-side call meanwhile. This is a logic gap, not data.")

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
        st.caption("lifecycle + supply-chain graph + second-order winners — next pass")
        top = sorted(((t, (a.get("surge") or {}).get("score", 0)) for t, a in per.items()), key=lambda kv: -kv[1])[:6]
        st.markdown("**Surge pre-conditioning leaders (doc-20, OHLCV layers):**")
        for t, s in top:
            st.caption(f"· {t}: surge {s}")

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
                st.markdown("| ticker | flow | mode | align | surge | verdict |\n|---|---|---|---|---|---|")
                lines = []
                for a in rows:
                    vd = a.get("verdict")
                    lines.append(f"| {a['ticker']} | {(a['flow'] or {}).get('type','—')} | "
                                 f"{(a['market_mode'] or {}).get('mode','—')} | {(a['horizon'] or {}).get('alignment','—')} | "
                                 f"{(a['surge'] or {}).get('score','—')} | {(vd['side'].upper() if vd else 'watch')} |")
                st.markdown("\n".join(lines))

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
