"""🔬 Ticker Intelligence — doc-15/16: THESIS (35) · POSITIONING (40) · EXECUTION (25)
+ CONFIDENCE STACK. Honest: absent feeds say so instead of faking."""
from __future__ import annotations

_BUCKETS = ("master_long", "master_short", "deferred_longs", "avoided_long_only")
_ARCH = {"BTC": "macro-liquidity asset", "ETH": "utility-liquidity hybrid",
         "SOL": "reflexive high-beta network", "DOGE": "attention derivative",
         "SHIB": "attention derivative", "PEPE": "attention derivative"}


def render(snap):
    import streamlit as st
    from pages_lib._gcfis_inline import get_gcfis_output, num
    out = get_gcfis_output(snap, st)
    if not out:
        st.error("GCFIS output unavailable — click Rebuild."); return
    per = out.get("per_ticker", {}) or {}
    if not per:
        st.warning("no tickers in universe"); return
    tkr = st.selectbox("Ticker", sorted(per)) if hasattr(st, "selectbox") else sorted(per)[0]
    a = per.get(tkr, {}) or {}
    rank = out.get("ranking", {}) or {}
    r = next((x for b in _BUCKETS for x in rank.get(b, []) if x.get("ticker") == tkr), {}) or {}
    act = r.get("action", "WATCH"); d = r.get("direction", "")
    col = "🟢" if d == "long" else "🔴" if d == "short" else "⚪"
    f = a.get("flow") or {}; rz = a.get("response") or {}; bm = a.get("bm") or {}
    dl = a.get("dealer") or {}; mkt = a.get("market", "us")
    crowd = float(a.get("crowding", 50) or 50); vel = float(a.get("adoption_velocity", 0) or 0)

    c1, c2, c3 = st.columns([0.35, 0.40, 0.25])
    with c1:
        st.markdown(f"## {col} {tkr} — {act}")
        st.caption(f"conviction **{r.get('conviction','—')}**"
                   + (f" · EV **{r.get('ev')}%**" if r.get("ev") is not None else "")
                   + (f" · surge {r.get('surge')}" if r.get("surge") is not None else ""))
        st.markdown("**Why now**")
        for w in (r.get("why_now") or ["—"])[:4]: st.caption("· " + str(w))
        st.markdown("**Why market wrong**")
        wmw = []
        if bm.get("regime") == "DOMESTIC_LED" and bm.get("flow_score", 0) > 20:
            wmw.append("consensus reads foreign outflow as bearish — domestic operators are marking up into it")
        if crowd < 35 and float(a.get("acceleration", 0) or 0) > 0:
            wmw.append("underowned while accelerating — institutions not positioned yet")
        if a.get("_short_conflict"):
            wmw.append("⚠ tape conflicts with the short thesis (accumulation/reclaim present)")
        for w in (wmw or ["— (needs consensus/positioning feed — honest seam)"]): st.caption("· " + w)
        gip = (snap or {}).get("gip")
        drv = (out.get("drivers") or {}).get({"commodity": "gold", "fx": "fx", "idx": "idx",
                                              "crypto": "crypto"}.get(mkt, "us"), {}) or {}
        st.markdown("**Regime fit**")
        st.caption(f"quad {getattr(gip,'structural_quad','—')}/{getattr(gip,'monthly_quad','—')}"
                   f" · market bias {drv.get('bias','—')} · stage {a.get('stage','—')}")
        h = a.get("horizon") or {}
        if h.get("ok"):
            s = h.get("signs", {})
            st.caption(f"⏱ multi-TF {h['alignment']}/100 (d {s.get('daily',0):+d} · w {s.get('weekly',0):+d} · m {s.get('monthly',0):+d})")
        inv = r.get("invalidation") or {}
        st.markdown("**Invalidation**")
        st.caption(f"{inv.get('conditions', inv.get('cond','—'))} (px {inv.get('price') or '—'})")
        if mkt == "crypto":
            arch = next((v for k, v in _ARCH.items() if str(tkr).upper().startswith(k)),
                        "alt — attention/unlock risk (unlock feed = seam)")
            st.caption(f"🧬 archetype: {arch} — targets are regime-dependent (doc-17)")
    with c2:
        st.markdown("### 🎲 Positioning")
        lad = [(k, dl.get(k)) for k in ("call_wall", "gamma_flip", "max_pain", "put_wall") if dl.get(k)]
        if lad:
            for k, v in lad: st.caption(f"`{k.replace('_',' ').upper():<12}` ━━ {v}")
        if dl.get("gex_sign"):
            st.caption(f"gex_sign {dl.get('gex_sign'):+d} · regime {dl.get('regime','—')}"
                       + (" · ⚠ proxy" if str(dl.get('source','')).lower() == 'proxy' else ""))
        if not lad and not dl.get("gex_sign"):
            st.caption("— dealer ladder n/a for this market (options feed seam)")
        st.caption(f"flow **{f.get('type','—')}** · abs {f.get('absorption','—')} · eff {f.get('efficiency','—')}"
                   f" · pers {f.get('persistence','—')} (OHLCV proxy)")
        st.caption(f"response **{rz.get('response','—')}** (q {rz.get('quality','—')})")
        st.caption(f"crowding {crowd:.0f} · velocity {vel:+.2f}")
        if bm.get("false_accum"):
            st.warning("⚠ FALSE ACCUMULATION — LPM rising on liq_expand<1 → illiquid trap (doc-16)")
        if bm.get("participation") is not None:
            st.caption(f"participation quality (pressure breadth): {bm.get('participation'):+.2f}")
        if bm.get("regime"):
            st.caption(f"BM **{bm.get('regime')}** score {bm.get('flow_score')} · Par_F {bm.get('par_f','—')}"
                       f" · Corr_F {bm.get('corr_f','—')} · EFD {bm.get('efd','—')}")
        st.caption(f"🔗 chain: {a.get('theme') or '—'} → {a.get('bottleneck_node') or '—'} → {tkr}")
    with c3:
        st.markdown("### ⚡ Execution")
        st.metric("Entry", "—" if act == "AVOID" else (r.get("entry") or "—"))
        st.metric("Stop", r.get("stop") or "—")
        tg = r.get("targets") or [x for x in (r.get("target"),) if x]
        st.caption("targets: " + (" → ".join(str(x) for x in tg) if tg else "—"))
        st.caption(f"size× {r.get('size_x', r.get('size','—'))} · hold {r.get('hold','—')}")
        st.caption(f"EV {r.get('ev','—')}% · R/R {r.get('rr','—')}")
    st.divider()
    st.markdown("**Confidence stack** (from live fields — priors)")
    sc = r.get("scores") or {}
    meta_dir = sc.get("meta_long") if d != "short" else sc.get("meta_short")
    gexs = dl.get("gex_sign")
    rows = [("Macro/regime", meta_dir), ("Liquidity", round(num((out.get('systemic_flat') or out.get('systemic') or {}).get("liquidity"), 50), 0)),
            ("Dealer", {1: 70, -1: 30}.get(gexs, "—") if gexs is not None else "—"),
            ("Flow", round(100 * float(a.get("flow01", 0.5) or 0.5), 0)),
            ("Narrative", 60 if a.get("theme") else 40),
            ("Horizon", (a.get("horizon") or {}).get("alignment", "—"))]
    _num_rows = [(k, float(v)) for k, v in rows if isinstance(v, (int, float))]
    from components.mini_viz import hbar
    if not (_num_rows and hbar(st, "", [k for k, _ in _num_rows], [v for _, v in _num_rows],
                               colors=["#58a6ff"] * len(_num_rows), fmt="{:.0f}")):
        st.markdown("| layer | score |\n|---|---|\n" + "\n".join(f"| {k} | {v} |" for k, v in rows))
    key = {"commodity": ("gold" if "XAU" in str(tkr).upper() or "GOLD" in str(tkr).upper() else "oil"),
           "fx": "fx", "idx": "idx", "crypto": "crypto"}.get(mkt, "us")
    dd = (out.get("drivers") or {}).get(key) or {}
    if dd.get("readings"):
        with st.expander(f"📡 what drives {key.upper()} (surge up/down)"):
            for x in dd["readings"]:
                st.caption(f"[{x.get('horizon','?')}·{'★'*int(x.get('strength',1))}] {x.get('factor','?')} "
                           f"({x.get('sign','+')}) — " + (f"z {x.get('reading_z')}" if x.get("reading_z") is not None
                                                          else f"feed: {x.get('feed','—')}"))
