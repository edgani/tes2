"""TAB 4 — MARKET INTELLIGENCE: per-market specialized engines as SUBTABS (no universal model)."""
from __future__ import annotations

def render(snap: dict):
    import streamlit as st
    st.title("🗺 Market Intelligence")
    names = ["🇺🇸 US Stocks", "₿ Crypto", "💱 Forex", "🛢 Commodities", "🇮🇩 IHSG"]
    mods = ["us_stocks", "crypto", "forex", "commodities", "ihsg"]
    try:
        tabs = st.tabs(names)
    except Exception:
        tabs = None
    from pages_lib._gcfis_inline import get_gcfis_output
    out = get_gcfis_output(snap, st)
    _MKT = {"us_stocks": (["us"], ["us"]), "crypto": (["crypto"], ["crypto"]), "forex": (["fx"], ["fx"]),
            "commodities": (["commodity"], ["gold", "oil"]), "ihsg": (["idx"], ["idx"])}

    def _engine_header(mod):
        if not out: return
        rks, dks = _MKT.get(mod, ([], []))
        drv = out.get("drivers") or {}
        bias_bits = []
        for dk in dks:
            dd = drv.get(dk) or {}
            b = dd.get("bias", "—")
            bias_bits.append(f"**{dk.upper()}** {b}" + (f" ({dd.get('score')})" if dd.get("score") is not None else ""))
        rows = []
        for bkt in ("master_long", "master_short", "deferred_longs", "avoided_long_only"):
            rows += [r for r in (out.get("ranking", {}) or {}).get(bkt, []) if r.get("market") in rks]
        cats = {}
        for r in rows: cats[r.get("category", "?")] = cats.get(r.get("category", "?"), 0) + 1
        top = sorted(rows, key=lambda r: -float(r.get("conviction", 0)))[:3]
        st.markdown("🧠 **Market engine** — driver bias: " + " · ".join(bias_bits))
        if cats:
            st.caption("GCFIS: " + " · ".join(f"{k} {v}" for k, v in sorted(cats.items(), key=lambda kv: -kv[1])))
        for r in top:
            f = r.get("flow") or {}; bm = r.get("bm") or {}
            extra = (f" · BM {bm.get('regime')} {bm.get('flow_score')}" if bm.get("regime") else
                     f" · flow {f.get('type')}" if f.get("type") else "")
            st.caption(f"· **{r['ticker']}** {r.get('direction','')} conv {r.get('conviction')} · mode {r.get('market_mode','—')}{extra}")
        if mod == "ihsg":
            fa = [r["ticker"] for r in rows if (r.get("bm") or {}).get("false_accum")]
            if fa: st.warning("⚠ FALSE-ACCUM traps: " + ", ".join(fa[:8]))
        st.divider()

    import importlib
    for i, m in enumerate(mods):
        def _draw(mod=m):
            try:
                _engine_header(mod)
                importlib.import_module(f"pages_lib.{mod}").render(snap)
            except Exception as e:
                st.warning(f"{mod} unavailable: {e}")
        if tabs is not None:
            with tabs[i]: _draw()
        else:
            st.markdown(f"### {names[i]}"); _draw()
