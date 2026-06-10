"""pages_lib/_gcfis_inline.py — compact GCFIS confluence section foldable into ANY existing tab
(Alpha Center, Dashboard). Reuses the gcfis_intel harvesting + the dashboard card. Fully guarded:
any failure returns silently so it can never break the host tab."""
from __future__ import annotations

def render_gcfis_section(snap: dict, st, max_long: int = 8, max_short: int = 4):
    try:
        from pages_lib import gcfis_intel as gi
        from gcfis.orchestrator import run_gcfis
        from gcfis.dashboard import card_html
    except Exception:
        return
    try:
        prices, volumes = gi._prices_dict(snap)
        if len(prices) < 2:
            return
        bench = gi._find(prices, gi._BENCH)
        if bench is None: bench = next(iter(prices.values()))
        posterior, method = gi._regime_posterior(snap, prices, bench)
        out = run_gcfis(prices, bench, posterior,
                        systemic_inputs=gi._systemic_inputs(prices, bench) or None,
                        cross_asset_snapshot=gi._cross_snapshot(prices) or None,
                        volumes=volumes or None, dealer_by_ticker=gi._dealer_by_ticker(snap, prices) or None)
    except Exception:
        return
    try:
        rank = out.get("ranking", {}) or {}
        longs = rank.get("master_long", []) or []; shorts = rank.get("master_short", []) or []
        deferred = rank.get("deferred_longs", []) or []; pf = rank.get("portfolio", {}) or {}
        cross = (out.get("systemic", {}) or {}).get("cross_asset", {}) or {}
        title = (f"🧭 GCFIS confluence — {len(longs)} long / {len(shorts)} short"
                 f"{' / ' + str(len(deferred)) + ' deferred' if deferred else ''}  ·  regime {method}")
        with st.expander(title, expanded=bool(longs or shorts)):
            if cross.get("ok") and cross.get("regime"):
                st.caption(f"📡 cross-asset: **{cross.get('regime')}** — {cross.get('why','')}")
            if pf.get("warning"):
                st.warning("📦 " + pf["warning"])
            if not (longs or shorts):
                st.caption("No names cleared product-confluence (theme×bottleneck×accumulation×adoption×reflexivity) this regime.")
            for r in longs[:max_long]:
                st.markdown(card_html(r), unsafe_allow_html=True)
            for r in shorts[:max_short]:
                st.markdown(card_html(r), unsafe_allow_html=True)
            for r in deferred[:3]:
                st.markdown(card_html(r, deferred=True), unsafe_allow_html=True)
            st.caption("Full radar + lead–lag + opportunity scenarios in the 🧭 GCFIS tab.")
    except Exception:
        return
