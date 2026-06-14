"""dashboard.py — GCFIS render layer. ONE reusable renderer callable from ANY tab.
Renders the FULL per-ticker output contract as a multi-panel card (Identity/Scores/Options/
Macro/Risk/Opportunity/Entry). Pure-logic helpers are streamlit-free (unit-tested)."""
from __future__ import annotations

# ---------- pure logic (testable without streamlit) ----------
def alpha_badge(row: dict, deferred: bool = False) -> tuple[str, str]:
    act, valid = row.get("action"), row.get("entry_valid")
    if deferred:                          return ("⏸ DEFER (liquidation)", "#b08900")
    if act == "BUILD_LONG" and valid:     return ("✅ ALPHA-READY", "#1a7f37")
    if act == "BUILD_LONG" and not valid: return ("🟡 READY · WAIT ENTRY", "#b08900")
    if act == "BUILD_SHORT":              return ("🔻 SHORT", "#cf222e")
    if act == "START_SCALING":            return ("🔶 WARMING", "#bc4c00")
    return ("👁 WATCH", "#57606a")

def format_entry(row: dict) -> str:
    if not row.get("entry_type"): return "—"
    return (f"{row['entry_type']} · γ={row.get('gamma_regime','?')} · "
            f"in {row.get('entry_px','?')} / stop {row.get('stop','?')} / tgt {row.get('target','?')} · "
            f"R/R {row.get('rr','?')}")

def regime_color(regime: str | None) -> str:
    return {"DELEVERAGING": "#cf222e", "DEFLATION_GROWTH_SCARE": "#cf222e", "STAGFLATION_SCARE": "#bc4c00",
            "GROWTH_ON": "#1a7f37", "MONETARY_EASING": "#1a7f37", "MIXED": "#57606a"}.get(regime or "", "#57606a")

def quad_label(q: str | None) -> str:
    return {"Q1": "Q1 Goldilocks", "Q2": "Q2 Reflation", "Q3": "Q3 Stagflation", "Q4": "Q4 Deflation"}.get(q or "", "Quad —")

def _chip(label, value, color="#8b949e"):
    if value is None or value == "": return ""
    return (f"<span style='display:inline-block;margin:1px 6px 1px 0;font-size:.72rem;color:#c9d1d9'>"
            f"<span style='color:{color}'>{label}</span> {value}</span>")

def _stack_block(r: dict) -> str:
    """doc 6 decision stack: Type / Why-Now / Who-is-Trapped / Execution / Invalidation."""
    cat = r.get("category")
    if not cat or cat == "WATCH":
        return ""
    ex = r.get("execution") or {}; inv = r.get("invalidation") or {}; tg = ex.get("targets") or {}
    why = " · ".join((r.get("why_now") or [])[:2])
    conds = (inv.get("conditions") or ["—"])[0]
    return ("<div style='margin-top:4px;padding:4px 7px;background:#161b22;border-radius:4px;"
            "font-size:.74rem;color:#c9d1d9;line-height:1.5'>"
            f"🧭 <b>{cat}</b> · mode {r.get('market_mode','-')} · hold {ex.get('holding','-')}<br>"
            f"⚡ {why}<br>"
            f"🪤 {r.get('whos_trapped','')}<br>"
            f"▶ {ex.get('mode','-')} · aggression {ex.get('aggression','-')} · size×{ex.get('size_x','-')} · "
            f"targets {tg.get('near','-')} → {tg.get('expansion','-')} → {tg.get('convex','-')}<br>"
            f"✋ invalid: {conds} (px {inv.get('price') or '—'})</div>")


def card_html(r: dict, deferred: bool = False) -> str:
    """Full per-ticker contract card (pure string; no streamlit)."""
    label, col = alpha_badge(r, deferred=deferred)
    sc = r.get("scores", {}); opt = r.get("options", {}); mac = r.get("macro", {}); opp = r.get("opportunity", {})
    head = (f"<b style='font-size:1rem'>{r['ticker']}</b>"
            f"{' · ' + r['theme'] if r.get('theme') else ''}"
            f"{'/' + r['subtheme'] if r.get('subtheme') else ''} "
            f"<span style='color:{col}'>{label}</span>"
            f"<span style='float:right;color:#8b949e'>conv {r.get('conviction','?')} · meta {r.get('meta_score','?')}</span>")
    scores = (_chip("Acc", sc.get("accumulation"), "#58a6ff") + _chip("Theme", sc.get("theme"), "#58a6ff")
              + _chip("Bottle", sc.get("bottleneck"), "#58a6ff") + _chip("Reflex", sc.get("reflexivity"), "#58a6ff")
              + _chip("Pos", sc.get("positioning"), "#58a6ff")
              + (_chip("⚡runaway", "yes", "#bc4c00") if r.get("runaway") else "")
              + _chip("conflu", sc.get("confluence"), "#3fb950"))
    rot = r.get("rotation") or {}
    rotation_chip = (_chip("↻ rotation", f"primed by {rot.get('leader')} (fired {rot.get('days_since_fire')}d, ~{rot.get('window')}d window)", "#3fb950") if rot else "")
    if opt.get("is_real"):
        options = (_chip("GEX", ("+" if opt.get("gex_sign", 0) >= 0 else "") + str(opt.get("gex")), "#a371f7")
                   + _chip("γflip", opt.get("gamma_flip"), "#a371f7")
                   + _chip("call_wall", opt.get("call_wall"), "#a371f7") + _chip("put_wall", opt.get("put_wall"), "#a371f7")
                   + _chip("vanna", opt.get("vanna"), "#a371f7") + _chip("charm", opt.get("charm"), "#a371f7"))
    elif opt.get("gex") is not None:
        options = (_chip("GEX·proxy", ("+" if opt.get("gex_sign", 0) >= 0 else "") + str(opt.get("gex")), "#8a63d2")
                   + _chip("γflip·proxy", opt.get("gamma_flip"), "#8a63d2")
                   + _chip("call_wall", opt.get("call_wall"), "#8a63d2") + _chip("put_wall", opt.get("put_wall"), "#8a63d2"))
    else:
        options = _chip("options", "no real chain (n/a)", "#57606a")
    macro = (_chip("Quad", (mac.get("quad") or "—"), "#d29922") + _chip("Liq", mac.get("liquidity_regime"), "#d29922")
             + _chip("Frag", mac.get("fragility"), "#d29922") + _chip("Shock", mac.get("shock_prob"), "#d29922")
             + _chip("X-asset", mac.get("cross_asset_regime"), "#d29922"))
    bm = r.get("bm") or {}
    bm_chips = ((_chip("BM", bm.get("regime"), "#ff7b72") + _chip("EFD", bm.get("efd"), "#ff7b72")
                 + _chip("ParF", bm.get("par_f"), "#ff7b72") + _chip("CorrF", bm.get("corr_f"), "#ff7b72")
                 + _chip("LPM✓" if bm.get("lpm_valid") else "LPM✗", bm.get("flow_score"), "#ff7b72"))
                if bm.get("regime") else "")
    fl = r.get("flow") or {}
    modeflow = (_chip("Mode", r.get("market_mode"), "#e3b341") + _chip("Mkt", r.get("market"), "#e3b341")
                + (_chip("Flow", fl.get("type"), "#79c0ff") if fl.get("type") else "")
                + _chip("abs", fl.get("absorption"), "#79c0ff") + _chip("eff", fl.get("efficiency"), "#79c0ff")
                + (_chip("⚠proxy", "OHLCV", "#57606a") if fl.get("proxy") else ""))
    entry = _chip("Entry", ("—" if r.get("action") == "AVOID" else format_entry(r)), "#3fb950")
    ev_chip = _chip("EV%", r.get("ev"), "#3fb950") if r.get("ev") is not None else ""
    scen = (_chip("bear", opp.get("bear"), "#cf222e") + _chip("base", opp.get("base"), "#8b949e")
            + _chip("bull", opp.get("bull"), "#1a7f37") + _chip("super", opp.get("supercycle"), "#1a7f37"))
    return (f"<div style='border-left:3px solid {col};padding:.45rem .7rem;margin:.35rem 0;background:#0f1117'>"
            f"<div>{head}</div>"
            f"<div style='margin-top:3px'>{scores}</div>"
            f"<div>{options}</div>"
            f"<div>{macro}</div>"
            f"<div>{modeflow}{bm_chips}</div>"
            f"<div style='margin-top:2px'>{entry}{ev_chip}{rotation_chip}{_chip('size×', r.get('alloc_mult'), '#8b949e') if r.get('alloc_mult',1)!=1 else ''}</div>"
            f"<div>📈 {scen}</div>"
            f"<div style='color:#8b949e;font-size:.78rem;margin-top:3px'>{r.get('reason','')}</div>"
            f"{_stack_block(r)}</div>")

# ---------- streamlit render ----------
def render_gcfis_dashboard(out: dict, st=None, title: str = "GCFIS"):
    if st is None:
        import streamlit as st  # noqa
    if not out or not out.get("ok"):
        st.warning("GCFIS produced no output."); return
    sysd = out.get("systemic", {}); rank = out.get("ranking", {})
    fwd = sysd.get("forward_macro", {}); cross = sysd.get("cross_asset", {})
    frag = sysd.get("fragility", {}); shock = sysd.get("shock", {}); liq = sysd.get("liquidity", {})

    st.markdown(f"### {title} — systemic radar")
    c = st.columns(5)
    c[0].metric("Forward Quad", quad_label(fwd.get("forward_quad")))
    cr = cross.get("regime") if cross.get("ok") else "—"
    c[1].markdown(f"**Cross-Asset**<br><span style='color:{regime_color(cr)};font-size:1.1rem'>{cr}</span>", unsafe_allow_html=True)
    c[2].metric("Fragility", frag.get("fragility", "—"))
    c[3].metric("Shock P", shock.get("shock_prob", "—"))
    c[4].metric("Liquidity", liq.get("liquidity_regime", "—"))
    if cross.get("ok"):
        st.caption(f"📡 {cross.get('why','')}")
        for d in cross.get("divergences", []):
            st.warning(d)
    st.divider()

    def _section(rows, header, empty, deferred=False):
        st.markdown(f"#### {header}  ·  {len(rows)}")
        if not rows:
            st.caption(empty); return
        for r in rows:
            st.markdown(card_html(r, deferred=deferred), unsafe_allow_html=True)

    sec = rank.get("sections") or {}
    if sec:
        _section(sec.get("early_monsters", []), "💎 EARLY MONSTERS — structural accumulation (weeks–months)", "none this regime")
        _section(sec.get("squeeze", []), "⚡ SQUEEZE ENGINE — forced-flow potential (tactical)", "none")
        _section(sec.get("tactical_momentum", []), "🚀 TACTICAL MOMENTUM — accepted expansion (days–weeks)", "none")
        _section(sec.get("mean_reversion", []), "🔄 MEAN REVERSION — exhaustion/reclaim scalps", "none")
        _section(sec.get("distribution_warning", []), "🔴 DISTRIBUTION WARNING — reduce / short (where shortable)", "none")
        if rank.get("eliminated"):
            st.caption("🗑 eliminated (stage-1): " + ", ".join(f"{e['ticker']} ({e['reasons'][0][:38]}…)" for e in rank["eliminated"][:6]))
    else:
        _section(rank.get("master_long", []), "🟢 LONG", "No qualified longs this regime.")
        _section(rank.get("master_short", []), "🔴 SHORT", "No qualified shorts.")
        _section(rank.get("master_spot", []), "💎 SPOT (uncrowded accumulation)", "No sweet-spot names.")
    pf = rank.get("portfolio", {})
    if pf.get("warning"):
        st.warning("📦 Portfolio concentration: " + pf["warning"])
    elif pf.get("effective_bets") is not None and pf.get("n_longs"):
        st.caption(f"📦 Portfolio: {pf['effective_bets']} independent bets across {pf['n_longs']} longs")
    if rank.get("deferred_longs"):
        _section(rank["deferred_longs"], "⏸ DEFERRED LONGS (cross-asset gate)", "", deferred=True)
    if rank.get("avoided_long_only"):
        st.markdown(f"#### 🚫 AVOID — long-only market, bearish/distribution  ·  {len(rank['avoided_long_only'])}")
        st.caption("Buy-only market (IDX): can't short. Reduce if holding; wait for reclaim. No short, no target-below-entry.")
        for r in rank["avoided_long_only"]:
            st.markdown(card_html(r), unsafe_allow_html=True)

    drv = out.get("drivers") or {}
    if drv:
        with st.expander("📡 Market Driver Map — surge-up / surge-down per market (researched Jun-2026)"):
            for mkt, dd in drv.items():
                bias = dd.get("bias"); col = "#1a7f37" if bias == "LONG" else "#cf222e" if bias == "SHORT" else "#9a6700" if str(bias).startswith("LEAN") else "#57606a"
                st.markdown(f"**{mkt.upper()}** — bias <span style='color:{col}'>{bias}</span>"
                            f"{' (score ' + str(dd.get('score')) + ', ' + str(dd.get('fed')) + ' feeds live)' if dd.get('score') is not None else ' — wire feeds to activate'}",
                            unsafe_allow_html=True)
                for r in dd.get("drivers", []):
                    z = r.get("reading_z")
                    zs = (f"<b style='color:{'#1a7f37' if r['sign']*z>0 else '#cf222e'}'>z {z:+.2f}</b>" if z is not None
                          else f"<span style='color:#57606a'>feed: {r['series']}</span>")
                    st.markdown(f"<span style='font-size:.76rem;color:#c9d1d9'>· [{r['horizon']}·{'★'*r['strength']}] "
                                f"{r['factor']} ({'+' if r['sign']>0 else '−'}) — {zs}<br>"
                                f"<span style='color:#8b949e'>&nbsp;&nbsp;{r['note']}</span></span>", unsafe_allow_html=True)
    with st.expander("lead–lag (discovered)"):
        ll = out.get("leadlag", {})
        st.json(ll if ll.get("ok") else {"note": "need >=2 tickers / pairs"})


def card_scan_html(r) -> str:
    """Doc-15 scan-first card: one headline + one context line; full card behind <details>."""
    act = r.get("action", "—"); d = r.get("direction", "")
    col = "#3fb950" if d == "long" else "#f85149" if d == "short" else "#8b949e"
    conv = r.get("conviction"); ev = r.get("ev"); surge = r.get("surge")
    ftype = (r.get("flow") or {}).get("type") or "—"
    why = (r.get("why_now") or [""])[0]
    bits = f"conv {conv}"
    if ev is not None: bits += f" · EV {ev}%"
    if surge is not None: bits += f" · surge {surge}"
    return (f"<div style='border-left:3px solid {col};padding:6px 10px;margin:6px 0;"
            f"background:#0d1117;border-radius:6px'>"
            f"<span style='font-weight:700;font-size:15px'>{r.get('ticker')}</span> "
            f"<span style='color:{col};font-weight:700'>{act}</span> "
            f"<span style='color:#8b949e;font-size:12px;white-space:nowrap'>{bits}</span>"
            f"<div style='color:#8b949e;font-size:11px;margin-top:2px'>{ftype} · mode {r.get('market_mode','—')}" + (' · ⚠FALSE-ACCUM' if (r.get('bm') or {}).get('false_accum') else '')
            + (f" — {why}" if why else "") + "</div>"
            f"<details style='margin-top:4px'><summary style='cursor:pointer;color:#58a6ff;font-size:11px'>"
            f"detail</summary>{card_html(r)}</details></div>")


def desk_card_html(p) -> str:
    """FINAL DESK pick: rank · side · conv/EV · ≤3 reasons · execution · invalidation."""
    col = "#3fb950" if p.get("side") == "long" else "#f85149"
    tg = " → ".join(str(x) for x in (p.get("targets") or [])[:3]) or "—"
    inv = p.get("invalidation") or {}
    reasons = "".join(f"<div style='color:#c9d1d9;font-size:11px'>· {w}</div>" for w in p.get("reasons", []))
    pt = p.get("primary_target")
    return (f"<div style='border:1px solid #30363d;border-left:4px solid {col};border-radius:8px;"
            f"padding:8px 12px;margin:7px 0;background:#0d1117'>"
            f"<span style='color:#8b949e;font-weight:700'>#{p.get('rank')}</span> "
            f"<span style='font-size:16px;font-weight:800'>{p.get('ticker')}</span> "
            f"<span style='color:{col};font-weight:800'>{str(p.get('side','')).upper()}</span> "
            f"<span style='color:#8b949e;font-size:12px;white-space:nowrap'>conv {p.get('conviction')} · EV {p.get('ev')}% "
            f"· {p.get('market')} · {p.get('flow') or '—'}/{p.get('mode') or '—'}</span>"
            f"{reasons}"
            f"<div style='color:#8b949e;font-size:11px;margin-top:3px'>entry {p.get('entry')} · stop {p.get('stop')}"
            f" · tgt {tg}" + (f" · primary {pt}" if pt else "") +
            f" · size× {p.get('size_x') or '—'} · hold {p.get('hold') or '—'}</div>"
            f"<div style='color:#f0883e;font-size:11px'>✋ invalid: {inv.get('conditions', inv.get('cond', '—'))}"
            f" (px {inv.get('price') or '—'})</div></div>")
