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
    import importlib
    for i, m in enumerate(mods):
        def _draw(mod=m):
            try:
                importlib.import_module(f"pages_lib.{mod}").render(snap)
            except Exception as e:
                st.warning(f"{mod} unavailable: {e}")
        if tabs is not None:
            with tabs[i]: _draw()
        else:
            st.markdown(f"### {names[i]}"); _draw()
