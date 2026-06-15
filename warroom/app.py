"""app.py — MacroRegime War Room (7 tabs, per FINAL_REDESIGN_SPEC).

A decision war room, NOT a data terminal: hierarchy by importance, integrated visuals
over tiny cards, competitive ranking (3-5 conviction, not 60), causal cards, propagation
graph, market-specific flow. Computable signals drive it; paid feeds (gamma/on-chain/COT)
are shown LOCKED, never faked. Not financial advice.

Run:  pip install -r requirements.txt ; streamlit run app.py
"""
from __future__ import annotations
import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))
import bridge
from gcfis.engines.competitive_ranking_engine import causal_summary
from gcfis.data.moonshot_universe import DOMAINS

st.set_page_config(page_title="MacroRegime War Room", page_icon="🛰", layout="wide",
                   initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap");
html,body,[class*="css"]{font-family:"Inter",sans-serif}
.stApp{background:#0B0E11}
.block-container{padding-top:.5rem!important;max-width:1560px!important}
[data-testid="stMetric"]{background:#12161C;border:1px solid rgba(255,255,255,.06);border-radius:10px;padding:8px 12px!important}
[data-testid="stMetricValue"]{font-size:1.25rem!important;font-weight:700!important}
[data-testid="stMetricLabel"]{font-size:.58rem!important;letter-spacing:.6px;text-transform:uppercase;opacity:.55}
.stTabs [data-baseweb="tab"]{font-weight:600;font-size:.86rem}
.hero{background:linear-gradient(180deg,#11161d,#0d1117);border:1px solid #21262d;border-radius:14px;padding:16px 18px}
.htitle{font-size:11px;letter-spacing:.8px;text-transform:uppercase;color:#8b949e;margin-bottom:10px}
.card{background:#12161C;border:1px solid rgba(255,255,255,.06);border-radius:12px;padding:14px 16px;margin-bottom:10px}
.locked{background:#0d1117;border:1px dashed #30363d;border-radius:12px;padding:12px 14px;margin-bottom:10px;color:#6e7681}
.pill{display:inline-block;font-size:11px;padding:3px 9px;border-radius:7px;margin:2px 3px;font-weight:600}
.arrow{color:#475059;margin:0 3px;font-weight:700}
small.muted{color:#8b949e}
.barwrap{height:9px;background:#1c2128;border-radius:5px;overflow:hidden;margin:3px 0}
</style>
""", unsafe_allow_html=True)


# ── loaders ──
@st.cache_data(ttl=3600, show_spinner=False)
def load_all(days=820):
    out = {}
    try:
        import yfinance as yf
    except Exception:
        return out
    for market, tickers in bridge.UNIVERSE.items():
        dd = {}
        for t in tickers:
            try:
                d = yf.download(t, period=f"{days}d", interval="1d", progress=False, auto_adjust=True)
                if d is None or len(d) < 80:
                    continue
                d.columns = [c[0] if isinstance(c, tuple) else c for c in d.columns]
                dd[t] = d.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].dropna()
            except Exception:
                continue
        if dd:
            out[market] = dd
    return out


@st.cache_data(ttl=3600, show_spinner=False)
def load_netliq():
    try:
        from gcfis.feeds.fred_feed import fetch_fred
        ser, _ = fetch_fred()
        nl = ser.get("FEDLIQ")
        if nl is None or len(nl) < 10:
            return None, None
        return float(nl.iloc[-1]), float(nl.iloc[-1] - nl.iloc[-6])
    except Exception:
        return None, None


@st.cache_data(ttl=1800, show_spinner=False)
def get_state():
    netliq, chg = load_netliq()
    data = load_all()
    if not data:
        return {"rows": [], "regime": None, "ranking": None, "netliq": netliq, "nl_chg": chg}
    out = bridge.build(data, netliq_chg=chg)
    out["netliq"], out["nl_chg"] = netliq, chg
    return out


# ── html helpers ──
def _cellcolor(v):  # v in -1..1
    if v is None:
        return "#161b22", "feed"
    if v > 0.33:
        return "#1a4d2e", ""
    if v > -0.33:
        return "#5c4d1a", ""
    return "#5c1f1f", ""


def _matrix(reg):
    cols = ["structural", "cyclical", "tactical", "short-term"]
    # computable rows (single read shown across horizons); feed-gated rows = None
    g, lq = reg["growth"], reg["liquidity"]
    vol = -(reg["crash"] / 50 - 1)  # high crash → red
    rows = {"liquidity": lq, "growth": g, "volatility": vol,
            "inflation": None, "credit": None, "yields": None, "dollar": None}
    html = '<div style="display:grid;grid-template-columns:90px repeat(4,1fr);gap:5px">'
    html += '<div></div>' + "".join(f'<div style="font-size:10px;color:#8b949e;text-align:center">{c}</div>' for c in cols)
    for name, val in rows.items():
        html += f'<div style="font-size:11px;color:#c9d1d9;display:flex;align-items:center">{name}</div>'
        for i in range(4):
            col, lab = _cellcolor(val)
            html += f'<div style="height:34px;background:{col};border-radius:5px;display:flex;align-items:center;justify-content:center;font-size:9px;color:#8b949e">{lab}</div>'
    html += '</div>'
    return html


def _tower(label, val, color):
    h = max(4, min(100, val))
    return (f'<div style="display:flex;flex-direction:column;align-items:center;width:18%">'
            f'<div style="font-size:13px;font-weight:700;color:{color}">{val}</div>'
            f'<div style="height:120px;width:26px;background:#1c2128;border-radius:6px;display:flex;align-items:flex-end;overflow:hidden;margin:4px 0">'
            f'<div style="width:100%;height:{h}%;background:{color}"></div></div>'
            f'<div style="font-size:9px;color:#8b949e;text-align:center;line-height:1.2">{label}</div></div>')


def _pbar(label, val, color):
    return (f'<div style="display:flex;align-items:center;gap:8px;margin:3px 0">'
            f'<small class="muted" style="width:104px">{label}</small>'
            f'<div class="barwrap" style="flex:1"><div style="height:100%;width:{max(2,min(100,val))}%;background:{color}"></div></div>'
            f'<small class="muted" style="width:26px;text-align:right">{round(val)}</small></div>')


def _band(lrr, close, trr):
    rng = max(trr - lrr, 1e-9)
    pos = max(0, min(1, (close - lrr) / rng)) * 100
    return (f'<div style="position:relative;height:10px;background:#1c2128;border-radius:5px;margin:8px 0">'
            f'<div style="position:absolute;height:100%;width:{pos:.0f}%;background:#21323f;border-radius:5px"></div>'
            f'<div style="position:absolute;top:-3px;left:calc({pos:.0f}% - 2px);width:4px;height:16px;background:#e6edf3;border-radius:2px"></div></div>'
            f'<small class="muted">LRR {lrr} · <b style="color:#e6edf3">close {close}</b> · TRR {trr}</small>')


def _empty(msg):
    st.info(msg + "  \n(Sandbox tanpa data market → wajar; jalan penuh di deploy dgn yfinance + FRED.)")


# ════════════ TAB 1 · COMMAND CENTER ════════════
def t_command(s):
    if not s["rows"]:
        _empty("Belum ada data market.")
        return
    reg = s["regime"]
    h1, h2 = st.columns([1.55, 1])
    with h1:
        st.markdown('<div class="hero"><div class="htitle">Regime Pressure Matrix · variable × horizon</div>'
                    + _matrix(reg)
                    + '<small class="muted" style="display:block;margin-top:8px">computed: liquidity (NetLiq) · growth (breadth/RS) · volatility (crash). '
                      'inflation/credit/yields/dollar = feed-gated (dim).</small></div>', unsafe_allow_html=True)
    with h2:
        towers = ("".join([
            _tower("liquidity stress", reg["liq_stress"], "#f0883e"),
            _tower("fragility", reg["fragility"], "#d29922"),
            _tower("crowding", reg["crowding"], "#58a6ff"),
            _tower("crash prob", reg["crash"], "#f85149"),
            _tower("contagion", reg["contagion"], "#bc4fce"),
        ]))
        st.markdown('<div class="hero"><div class="htitle">Global Stress Engine</div>'
                    f'<div style="display:flex;justify-content:space-between;align-items:flex-end">{towers}</div></div>',
                    unsafe_allow_html=True)

    # What changed / hot now (computable notables — true day-deltas need prior-session state)
    rows = s["rows"]
    movers = sorted([r for r in rows if r["rs63"] is not None], key=lambda r: -r["rs63"])[:3] + \
        sorted([r for r in rows if r["rs63"] is not None], key=lambda r: r["rs63"])[:2]
    chips = ""
    for r in movers:
        col = "#3fb950" if r["rs63"] >= 0 else "#f85149"
        chips += (f'<div class="card" style="display:inline-block;width:220px;margin-right:10px;vertical-align:top">'
                  f'<div class="barwrap"><div style="height:100%;width:{min(100, abs(r["rs63"])*4):.0f}%;background:{col}"></div></div>'
                  f'<b>{r["ticker"]}</b> <small class="muted">{bridge.MKT_LABEL[r["market"]]}</small><br>'
                  f'<small class="muted">RS {r["rs63"]:+.1f} · {r["formation"].lower()} · crowd {r["crowding"]}</small></div>')
    st.markdown('<div class="htitle" style="margin-top:14px">What changed · biggest relative-strength shifts</div>'
                f'<div style="white-space:nowrap;overflow-x:auto;padding-bottom:6px">{chips}</div>', unsafe_allow_html=True)

    # active propagation chains (compact; full graph in Bottleneck Map)
    st.markdown('<div class="htitle" style="margin-top:8px">Active cross-asset chains →</div>', unsafe_allow_html=True)
    cols = st.columns(len(bridge.PROPAGATION))
    rolecol = {"src": "#8b949e", "ben": "#3fb950", "fragile": "#f85149", "infl": "#d29922"}
    for i, (name, chain) in enumerate(bridge.PROPAGATION.items()):
        nodes = " ".join(f'<span class="pill" style="background:{rolecol[r]}22;color:{rolecol[r]}">{n}</span><span class="arrow">→</span>'
                         for n, r in chain[:4])
        cols[i].markdown(f'<div class="card"><small class="muted">{name}</small><br>{nodes}…</div>', unsafe_allow_html=True)


# ════════════ TAB 2 · OPPORTUNITY RADAR ════════════
def t_opportunity(s):
    if not s["rows"]:
        _empty("Belum ada data market.")
        return
    rows, rk = s["rows"], s["ranking"]
    sm = rk["summary"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Measured", sm["in"])
    c2.metric("Said NO", f"{sm['eliminated']} ({int(sm['say_no_ratio']*100)}%)")
    c3.metric("Tier-1 conviction", sm["tier1"])
    c4.metric("Tier-2 watchlist", sm["tier2"])

    st.markdown("##### Opportunity cluster · crowding × bottleneck pressure (size = reflexivity)")
    dfm = pd.DataFrame([{"ticker": r["ticker"], "crowding": r["crowding"], "pressure": r["bottleneck"],
                         "reflexivity": max(r["reflexivity"], 5), "tier": r.get("tier", "hidden")} for r in rows])
    if len(dfm):
        st.scatter_chart(dfm, x="crowding", y="pressure", size="reflexivity", color="tier", height=300)

    st.markdown("### Tier 1 — highest conviction (the only primary screen)")
    t1 = [r for r in rows if r.get("tier") == "highest_conviction"]
    if not t1:
        st.info("Ga ada nama yang lolos bar conviction sekarang — standing aside.")
    cols = st.columns(2)
    for i, r in enumerate(sorted(t1, key=lambda x: -x["score"])):
        cz = causal_summary(r["candidate"])
        cand = r["candidate"]
        with cols[i % 2]:
            stack = ("".join([
                _pbar("accumulation", cand.accumulation_persistence * 100, "#3fb950"),
                _pbar("bottleneck", cand.bottleneck_pressure * 100, "#bc4fce"),
                _pbar("positioning asym", cand.positioning_asymmetry * 100, "#58a6ff"),
                _pbar("reflexivity", cand.reflexivity_potential * 100, "#d29922"),
                _pbar("regime fit", cand.regime_alignment * 100, "#39c5cf"),
            ]))
            st.markdown(
                f'<div class="card"><span style="font-size:18px;font-weight:800">{r["ticker"]}</span> '
                f'<small class="muted">{bridge.MKT_LABEL[r["market"]]} · conviction T1 · score {r["score"]}</small>'
                f'<div style="margin-top:8px">{stack}</div>'
                f'<div style="margin-top:8px;font-size:12.5px;line-height:1.7">'
                f'<b>why now</b> {cz["why_now"]}<br>'
                f'<b>what changed</b> {cz["what_changed"]}<br>'
                f'<b>mispriced</b> {cz["what_is_mispriced"]}<br>'
                f'<b>who trapped</b> <small class="muted">{cz["who_is_trapped"]}</small><br>'
                f'<b>who must buy</b> <small class="muted">{cz["who_must_buy"]}</small><br>'
                f'<b>invalidation</b> {cz["invalidation"]}</div></div>', unsafe_allow_html=True)

    t2 = [r for r in rows if r.get("tier") == "watchlist"]
    with st.expander(f"Tier 2 — watchlist ({len(t2)})"):
        if t2:
            st.dataframe(pd.DataFrame([{"ticker": r["ticker"], "mkt": bridge.MKT_LABEL[r["market"]], "score": r["score"],
                                        "form": r["formation"], "RS": r["rs63"], "crowd": r["crowding"]} for r in t2]),
                         use_container_width=True, hide_index=True)
    st.caption(f"Tier 3 emerging + {sm['eliminated']} eliminated are hidden — the engine says NO so you don't drown in 60 names.")


# ════════════ TAB 3 · BOTTLENECK MAP ════════════
def t_bottleneck(s):
    st.markdown("### Cross-asset propagation — event → bottleneck → 2nd order → loser")
    rolecol = {"src": "#8b949e", "ben": "#3fb950", "fragile": "#f85149", "infl": "#d29922"}
    for name, chain in bridge.PROPAGATION.items():
        nodes = ""
        for j, (n, role) in enumerate(chain):
            nodes += f'<span class="pill" style="background:{rolecol[role]}22;color:{rolecol[role]};border:1px solid {rolecol[role]}55">{n}</span>'
            if j < len(chain) - 1:
                nodes += '<span class="arrow">→</span>'
        st.markdown(f'<div class="card"><small class="muted">{name}</small>'
                    f'<div style="margin-top:6px;white-space:nowrap;overflow-x:auto">{nodes}</div></div>', unsafe_allow_html=True)
    st.markdown('<small class="muted">green = beneficiary · red = fragile/hurt · amber = macro pass-through · gray = trigger. '
                'Node intensity (capacity util / inventories / lead times) = feed-gated upgrade.</small>', unsafe_allow_html=True)

    st.markdown("### Asymmetric / Moonshot Radar — hidden bottleneck names")
    st.warning("Structural screen, not a return forecast. Higher tier = lower base rate; tier-4/5 mostly go to zero. Not advice.")
    tcol = {1: "#8b949e", 2: "#58a6ff", 3: "#d29922", 4: "#f0883e", 5: "#f85149"}
    for dom in DOMAINS[:6]:
        names = []
        for node in dom["nodes"]:
            for tkr in node["hidden"]:
                names.append((tkr, node["tier"], node["scarcity"]))
        if not names:
            continue
        with st.expander(f"{dom['domain']} · {dom['source']}"):
            for tkr, tier, scar in names:
                st.markdown(f'<div class="card"><b>{tkr}</b> <span style="color:{tcol.get(tier)};font-weight:700">T{tier}</span>'
                            f'<br><small class="muted">{scar}</small></div>', unsafe_allow_html=True)


# ════════════ TAB 4 · FLOW & POSITIONING (market-specific) ════════════
def t_flow(s):
    if not s["rows"]:
        _empty("Belum ada data market.")
        return
    rows = s["rows"]
    st.caption("Tiap market beda — yang feed-gated ditandai locked, ga dipalsuin.")
    # computable per-market: accumulation / crowding / RS leaders
    SPEC = {
        "us": ("US equity", ["gamma", "vanna", "charm", "dark pool", "ETF concentration", "dealer positioning"]),
        "crypto": ("Crypto", ["exchange reserves", "stablecoin flows", "whale accumulation", "funding", "liquidation heatmap", "staking unlocks"]),
        "idx": ("IHSG", ["LPM", "DTE", "foreign corr", "broker entropy", "participation persistence"]),
        "commodity": ("Commodity", ["inventories", "curve structure", "shipping rates", "refinery utilization", "positioning (COT)"]),
        "fx": ("FX", ["rate differentials", "DXY", "reserve flows", "carry", "commodity linkage"]),
    }
    for mk, (label, feeds) in SPEC.items():
        mr = [r for r in rows if r["market"] == mk]
        if not mr:
            continue
        st.markdown(f"#### {label}")
        a, b = st.columns([1, 1])
        with a:
            st.markdown('<div class="card"><small class="muted">Computable now (price/volume)</small>'
                        + "".join(_pbar(r["ticker"], r["accumulation"], "#3fb950") for r in sorted(mr, key=lambda x: -x["accumulation"])[:6])
                        + '</div>', unsafe_allow_html=True)
        with b:
            st.markdown(f'<div class="locked"><b>🔒 {label}-specific feeds</b><br>'
                        + " · ".join(feeds) + '</div>', unsafe_allow_html=True)


# ════════════ TAB 5 · MARKET INTERNALS (6 panels) ════════════
def t_internals(s):
    if not s["rows"]:
        _empty("Belum ada data market.")
        return
    rows = s["rows"]
    b = bridge.breadth(rows)
    st.markdown("### Internals — healthy trend vs fragile trend")
    r1 = st.columns(3)
    r1[0].markdown(f'<div class="card"><div class="htitle">Breadth</div>'
                   f'<div style="font-size:1.6rem;font-weight:800">{b["health"]:.0f}</div>'
                   f'<small class="muted">% &gt;50d {b["pct_above_50"]:.0f} · % &gt;200d {b["pct_above_200"]:.0f}</small></div>', unsafe_allow_html=True)
    lead = bridge.leadership(rows, 5)
    r1[1].markdown('<div class="card"><div class="htitle">Leadership (RS)</div>'
                   + "".join(f'<div style="font-size:12px">{r["ticker"]} <small class="muted">{r["rs63"]:+.1f}</small></div>' for r in lead)
                   + '</div>', unsafe_allow_html=True)
    r1[2].markdown('<div class="locked"><div class="htitle">Credit</div>🔒 HY/IG OAS curve<br><small>FRED BAMLH0A0HYM2 — next</small></div>', unsafe_allow_html=True)
    r2 = st.columns(3)
    vol = b["bearish"]  # crude vol/fragility proxy
    r2[0].markdown(f'<div class="card"><div class="htitle">Volatility / fragility</div>'
                   f'<div style="font-size:1.6rem;font-weight:800">{s["regime"]["crash"]}</div>'
                   f'<small class="muted">crash proxy · bearish {b["bearish"]}/{b["n"]}</small></div>', unsafe_allow_html=True)
    nl = s.get("netliq")
    r2[1].markdown(f'<div class="card"><div class="htitle">Liquidity</div>'
                   f'<div style="font-size:1.4rem;font-weight:800">{("%.0f" % nl) if nl else "—"}</div>'
                   f'<small class="muted">Fed NetLiq $bn{(" · %+.0f wk" % s["nl_chg"]) if s.get("nl_chg") is not None else ""}</small></div>', unsafe_allow_html=True)
    r2[2].markdown('<div class="locked"><div class="htitle">Correlation</div>🔒 rolling 63/126/252d matrix<br><small>computable — next</small></div>', unsafe_allow_html=True)
    with st.expander("Per-market breadth"):
        st.dataframe(pd.DataFrame([{"market": bridge.MKT_LABEL[m], **v} for m, v in bridge.breadth_by_market(rows).items()]),
                     use_container_width=True, hide_index=True)


# ════════════ TAB 6 · EXECUTION ENGINE ════════════
def t_execution(s):
    if not s["rows"]:
        _empty("Belum ada data market.")
        return
    rows = s["rows"]
    st.markdown("### Execution — timing the Tier-1 names (Risk Range bands)")
    st.caption("Accumulation zone = LRR region. gamma walls / liquidity pockets / stop clusters = feed-gated.")
    t1 = [r for r in rows if r.get("tier") in ("highest_conviction", "watchlist")]
    if not t1:
        st.info("Ga ada nama conviction buat di-time sekarang.")
    cols = st.columns(2)
    for i, r in enumerate(sorted(t1, key=lambda x: -x["score"])[:8]):
        lrr, trr, close = r["lrr"], r["trr"], r["close"]
        half = max((trr - lrr) / 2, 1e-9)
        bull = r["formation"] == "BULLISH"
        if bull:
            entry, stop, t1p = (lrr if close > lrr else close), lrr - 0.5 * half, trr
            note = "buy/add at LRR (accumulation zone)"
        else:
            entry, stop, t1p = trr, trr + 0.5 * half, lrr
            note = "fade at TRR" if r["market"] not in bridge.LONG_ONLY else "wait (long-only)"
        rr = round(abs(t1p - entry) / max(abs(entry - stop), 1e-9), 2)
        with cols[i % 2]:
            gex = '<div class="locked" style="margin-top:8px">🔒 gamma walls / stop clusters (options feed — US)</div>' if r["market"] == "us" else ""
            st.markdown(f'<div class="card"><b style="font-size:16px">{r["ticker"]}</b> '
                        f'<small class="muted">{bridge.MKT_LABEL[r["market"]]} · {r["formation"]} · {r.get("tier")}</small>'
                        f'{_band(lrr, close, trr)}'
                        f'<div style="font-size:13px;margin-top:6px">entry <b>{round(entry,2)}</b> · stop <b>{round(stop,2)}</b> · T1 <b>{round(t1p,2)}</b> · R/R <b>{rr}</b></div>'
                        f'<small class="muted">{note} · RTA {r["rta"]}</small>{gex}</div>', unsafe_allow_html=True)


# ════════════ TAB 7 · RESEARCH LAB ════════════
def t_research(s):
    st.markdown("### Research Lab — validation (not the main workflow)")
    st.warning("Acceptance gate buat percaya sinyal: **perm_p < 0.05 AND Deflated Sharpe ≥ 0.95, else NOISE**. "
               "Walk-forward + Monte Carlo + feature importance dipasang di sini.")
    st.markdown("- Walk-forward IC > 0 OOS, permutation **p < 0.05**\n"
                "- **Deflated Sharpe ≥ 0.95** (koreksi multiple-testing)\n"
                "- Long-short decile spread positif lintas regime\n"
                "- Else → **NOISE**, jangan ditradein")
    st.caption("Next: wire full DSR + permutation harness + regime validation.")


# ── shell ──
st.markdown("## 🛰 MacroRegime War Room")
with st.spinner("Reading the tape…"):
    S = get_state()
reg = S.get("regime")
banner = (f"regime growth {reg['growth']:+.2f} · liquidity {reg['liquidity']:+.2f} · label {reg['label']} · "
          f"health {reg['health']:.0f}") if reg else "no data (deploy with feeds)"
st.caption(f"Decision war room · competitive ranking (3-5 conviction, not 60) · feeds locked never faked · {banner}")

tabs = st.tabs(["Command Center", "Opportunity Radar", "Bottleneck Map",
                "Flow & Positioning", "Market Internals", "Execution Engine", "Research Lab"])
with tabs[0]:
    t_command(S)
with tabs[1]:
    t_opportunity(S)
with tabs[2]:
    t_bottleneck(S)
with tabs[3]:
    t_flow(S)
with tabs[4]:
    t_internals(S)
with tabs[5]:
    t_execution(S)
with tabs[6]:
    t_research(S)
