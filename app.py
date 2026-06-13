"""MacroRegime v2 — clean rebuild, data-first, ChatGPT-aligned architecture.

Why this exists: the v40 build was a beautiful dashboard on OHLCV proxies → garbage tickers.
v2 inverts the priority: REAL data layer first (with provenance on every number), then the
7-tab causal structure on top. No number is shown without saying whether it is REAL/PROXY/SEAM.

Run on Streamlit Cloud (point the app to this file). Live feeds (FRED/yfinance/IDX) only
resolve there — this sandbox blocks them, so locally you'll see PROXY/SEAM labels, which is
the honest state, not a bug.

7 tabs (ChatGPT final structure):
  1 Mission Control       — global state, shock engine, causal map, FINAL DESK
  2 Regime & Liquidity    — forward-growth, liquidity dominance, expectation gap
  3 Narratives & Bottlenecks — lifecycle, supply-chain graph, second-order winners
  4 Market Intelligence   — per-market DNA (US/Crypto/FX/Commodities/IHSG)
  5 Ticker Intelligence   — thesis / positioning / execution + confidence stack
  6 Portfolio & Risk      — exposure, correlation, contagion
  7 Research Lab          — walk-forward, feature importance, edge decay (validation gates)
"""
from __future__ import annotations
import streamlit as st


def _provenance_banner(ctx: dict):
    """First thing on screen: what is REAL vs PROXY vs SEAM right now. Never hide it."""
    macro = ctx.get("macro", {})
    real = [v["label"] for v in macro.values() if v.get("provenance") == "REAL"]
    seams = ctx.get("seams", {})
    vt = ctx.get("vix_term", {})
    cols = st.columns([2, 2, 2])
    with cols[0]:
        st.markdown(f"**🟢 REAL feeds: {len(real)}**")
        st.caption(", ".join(real) if real else "none resolved here (deploy to Cloud for live FRED)")
    with cols[1]:
        st.markdown(f"**🟡 VIX term: {vt.get('provenance', 'SEAM')}**")
        st.caption(vt.get("state", vt.get("note", "—")))
    with cols[2]:
        st.markdown(f"**🔴 Declared seams: {len(seams)}**")
        st.caption(" · ".join(list(seams)[:4]) + (" …" if len(seams) > 4 else ""))
    for s in ctx.get("status", []):
        st.caption("📡 " + str(s))
    st.divider()


def main():
    st.set_page_config(page_title="MacroRegime v2", layout="wide")
    st.sidebar.title("🛰 MacroRegime v2")
    st.sidebar.caption("clean rebuild · data-first · ChatGPT-aligned")

    snap = st.session_state.get("_snap")          # built by the data/build step (host-specific)
    prices = (snap or {}).get("prices", {}) if snap else {}

    from core.data_layer import build_data_context
    ctx = build_data_context(prices, session=st)

    tabs = st.tabs(["🛰 Mission Control", "🌊 Regime & Liquidity", "🧬 Narratives & Bottlenecks",
                    "🗺 Market Intelligence", "🔬 Ticker Intelligence", "📊 Portfolio & Risk",
                    "🧪 Research Lab"])

    with tabs[0]:
        st.subheader("Mission Control — what changed globally")
        _provenance_banner(ctx)
        from engines.shock_engine import run_shock_engine
        shock = run_shock_engine(ctx.get("macro", {}), ctx.get("vix_term", {}))
        c = st.columns([1, 3])
        with c[0]:
            st.metric("SHOCK PRESSURE", shock["shock_prob"], shock["crash_type"])
            st.caption(f"confidence: {shock['confidence']}")
        with c[1]:
            st.caption("crash basis: " + shock["basis"])
            for k, v in shock["components"].items():
                st.caption(f"{k}: {v:.2f}  ·  {shock['provenance'][k]}")
        st.info("FINAL DESK (quality-gated picks) + causal map mount here once the build step "
                "feeds real per-market state. This pass delivers the data foundation they stand on.")

    with tabs[1]:
        st.subheader("Regime & Liquidity")
        st.caption("forward-growth index · liquidity-dominance switch · expectation gap — built on the REAL feeds above")
        macro = ctx.get("macro", {})
        for key in ("net_liquidity", "hy_oas", "ig_oas", "real_yield_10y", "curve_10y2y", "vix_spot"):
            v = macro.get(key)
            if v and v.get("value") is not None:
                st.caption(f"· {v['label']}: **{v['value']:.2f}**  ({v['provenance']})")
        if not any(macro.get(k, {}).get("value") is not None for k in macro):
            st.warning("No REAL macro resolved in this environment — deploy to Cloud for live FRED.")

    for i, name in ((2, "Narratives & Bottlenecks"), (5, "Portfolio & Risk"), (6, "Research Lab")):
        with tabs[i]:
            st.subheader(name)
            st.caption("scaffolded — built on top of the data layer in the next pass")

    with tabs[3]:
        st.subheader("Market Intelligence — per-market DNA")
        st.caption("US: gamma/breadth/credit · Crypto: liquidity/reflexivity · FX: differentials · "
                   "Commodities: inventory/term · IHSG: foreign/LPM/participation")

    with tabs[4]:
        st.subheader("Ticker Intelligence — thesis / positioning / execution")
        st.caption("decision page (not indicator page) — wired after market-state classifier")


if __name__ == "__main__":
    main()
