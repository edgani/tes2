"""warroom/app.py — MacroRegime War Room (5 tabs, war-room hierarchy).

Build step 3: visual hierarchy + de-duplicated tab roles.
  Command Center = WHAT MATTERS NOW (hero regime quadrant + risk thermometers +
    compact signal ribbon + hot-now) — NO trade cards (they live only in Opportunity).
  Opportunity & Execution = the trade detail (bubble map + full Risk Range cards).
  Market State = internals (breadth/leadership + measured-universe drilldowns + locked feed panels).
Everything from price/volume + FRED + verified engines. Feed-gated panels are shown
LOCKED (not blank, not faked). Per-market content differs. Not financial advice.

Run: pip install -r warroom/requirements.txt ; streamlit run warroom/app.py
"""
from __future__ import annotations
import os
import sys
from collections import defaultdict

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from warroom.engine_bridge import (UNIVERSE, LONG_ONLY, MKT_LABEL,  # noqa: E402
                                   build_rows, breadth, breadth_by_market, leadership,
                                   rr_backtest, regime_read, hot_now)
from gcfis.engines.asymmetric_discovery import run_discovery  # noqa: E402

st.set_page_config(page_title="MacroRegime War Room", page_icon="🛰", layout="wide",
                   initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap");
html, body, [class*="css"] { font-family:"Inter",sans-serif; }
.stApp { background:#0B0E11; }
.block-container { padding-top:0.5rem !important; max-width:1500px !important; }
[data-testid="stMetric"]{background:#12161C;border:1px solid rgba(255,255,255,.06);border-radius:10px;padding:8px 12px !important}
[data-testid="stMetricValue"]{font-size:1.3rem !important;font-weight:700 !important}
[data-testid="stMetricLabel"]{font-size:.6rem !important;letter-spacing:.6px;text-transform:uppercase;opacity:.55}
.stTabs [data-baseweb="tab"]{font-weight:600}
.desk-long{color:#3fb950;font-weight:700}.desk-short{color:#f85149;font-weight:700}.desk-trim{color:#d29922;font-weight:700}
.chip{display:inline-block;font-size:12px;padding:3px 9px;border-radius:7px;margin:2px 4px 2px 0;background:#161b22;border:1px solid #21262d}
.card{background:#12161C;border:1px solid rgba(255,255,255,.06);border-radius:12px;padding:14px 16px;margin-bottom:10px}
.hero{background:linear-gradient(180deg,#11161d,#0d1117);border:1px solid #21262d;border-radius:14px;padding:14px 16px}
.htitle{font-size:11px;letter-spacing:.7px;text-transform:uppercase;color:#8b949e;margin-bottom:8px}
.band{position:relative;height:10px;background:#1c2128;border-radius:5px;margin:8px 0}
.band-fill{position:absolute;top:0;bottom:0;left:0;background:#21323f;border-radius:5px}
.band-dot{position:absolute;top:-3px;width:4px;height:16px;background:#e6edf3;border-radius:2px}
.bar{display:inline-block;height:7px;border-radius:3px;vertical-align:middle}
.locked{background:#0d1117;border:1px dashed #30363d;border-radius:12px;padding:14px 16px;margin-bottom:10px;color:#6e7681}
small.muted{color:#8b949e}
</style>
""", unsafe_allow_html=True)


# ── cached loaders ──
@st.cache_data(ttl=3600, show_spinner=False)
def load_all(days=820):
    out = {}
    try:
        import yfinance as yf
    except Exception:
        return out
    for market, tickers in UNIVERSE.items():
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
def get_rows():
    return build_rows(load_all())


# ── html helpers ──
def _sidecls(side):
    return {"LONG": "desk-long", "SHORT": "desk-short", "TRIM": "desk-trim"}.get(side, "")


def _quadrant_html(growth, liquidity):
    x = (liquidity + 1) / 2 * 100
    y = (1 - (growth + 1) / 2) * 100
    return f'''<div style="position:relative;height:186px;background:#0d1117;border:1px solid #21262d;border-radius:10px">
      <div style="position:absolute;left:50%;top:6px;bottom:6px;width:1px;background:#21262d"></div>
      <div style="position:absolute;top:50%;left:6px;right:6px;height:1px;background:#21262d"></div>
      <span style="position:absolute;top:6px;right:8px;font-size:10px;color:#3fb950">risk-on · liquidity↑</span>
      <span style="position:absolute;top:6px;left:8px;font-size:10px;color:#8b949e">risk-on · liquidity↓</span>
      <span style="position:absolute;bottom:6px;right:8px;font-size:10px;color:#8b949e">risk-off · liquidity↑</span>
      <span style="position:absolute;bottom:6px;left:8px;font-size:10px;color:#f85149">risk-off · liquidity↓</span>
      <div style="position:absolute;left:calc({x:.0f}% - 8px);top:calc({y:.0f}% - 8px);width:16px;height:16px;border-radius:50%;background:#58a6ff;box-shadow:0 0 12px #58a6ff"></div>
    </div>'''


def _thermo(label, val, color):
    return (f'<div style="margin:7px 0"><div style="display:flex;justify-content:space-between;font-size:11px;color:#8b949e">'
            f'<span>{label}</span><span style="color:{color};font-weight:600">{val}</span></div>'
            f'<div style="height:9px;background:#1c2128;border-radius:5px;overflow:hidden">'
            f'<div style="width:{val}%;height:100%;background:{color}"></div></div></div>')


def _band(lrr, close, trr):
    rng = max(trr - lrr, 1e-9)
    pos = max(0.0, min(1.0, (close - lrr) / rng)) * 100.0
    return (f'<div class="band"><div class="band-fill" style="width:{pos:.0f}%"></div>'
            f'<div class="band-dot" style="left:calc({pos:.0f}% - 2px)"></div></div>'
            f'<small class="muted">LRR {lrr} · <b style="color:#e6edf3">close {close}</b> · TRR {trr}</small>')


def _sigbar(label, val, color):
    return (f'<div style="margin:2px 0"><small class="muted" style="display:inline-block;width:92px">{label}</small>'
            f'<span class="bar" style="width:{max(2,min(100,val))}px;background:{color}"></span> <small class="muted">{val:.0f}</small></div>')


def _locked(title, need):
    return f'<div class="locked"><b>🔒 {title}</b><br><small>needs live feed: {need}</small></div>'


def _empty(msg):
    st.info(msg + "  \n(Sandbox without market data → expected; runs fully on deploy with yfinance + FRED.)")


# ── TAB 1 · Command Center (overview only — no trade cards) ──
def render_command_center():
    netliq, nl_chg = load_netliq()
    with st.spinner("Reading the tape…"):
        rows = get_rows()
    if not rows:
        _empty("No market data loaded yet.")
        return
    reg = regime_read(rows, nl_chg)
    sig = [r for r in rows if r["signaling"]]
    nL = sum(1 for r in sig if r["side"] == "LONG")
    nS = sum(1 for r in sig if r["side"] == "SHORT")

    # HERO: regime quadrant (left) + risk thermometers (right)
    h1, h2 = st.columns([1.4, 1])
    with h1:
        st.markdown('<div class="hero"><div class="htitle">Regime read · internals + NetLiq</div>'
                    + _quadrant_html(reg["growth"], reg["liquidity"])
                    + '<small class="muted">risk-appetite (breadth/RS) × liquidity (NetLiq Δ). '
                      'Full GIP Growth×Inflation quad = feed-gated.</small></div>', unsafe_allow_html=True)
    with h2:
        st.markdown('<div class="hero"><div class="htitle">Risk state</div>'
                    + _thermo("crash risk", reg["crash"], "#f85149")
                    + _thermo("liquidity stress", reg["liq_stress"], "#f0883e")
                    + _thermo("positioning (short skew)", reg["positioning"], "#58a6ff")
                    + _thermo("breadth deterioration", reg["breadth_det"], "#d29922")
                    + f'<small class="muted">health {reg["health"]:.0f} · med vol-state {reg["med_vol"]}</small></div>',
                    unsafe_allow_html=True)

    # compact signal ribbon (NO cards — those live in Opportunity)
    chips = " ".join(f'<span class="chip"><span class="{_sidecls(r["side"])}">●</span> {r["ticker"]}</span>'
                     for r in sorted(sig, key=lambda x: -x["er"])[:12])
    st.markdown(f'<div class="card"><b>{len(sig)} signaling</b> <small class="muted">· {nL} long · {nS} short '
                f'— full setups in <b style="color:#58a6ff">Opportunity &amp; Execution →</b></small>'
                f'<div style="margin-top:8px">{chips or "<small class=muted>none right now — slim pickings</small>"}</div></div>',
                unsafe_allow_html=True)

    # hot now (computable notables)
    hot = hot_now(rows)
    def hchip(lbl, r, col, extra=""):
        return (f'<span class="chip"><small class="muted">{lbl}</small> <b style="color:{col}">{r["ticker"]}</b> '
                f'<small class="muted">{extra}</small></span>') if r else ""
    st.markdown('<div class="card"><div class="htitle">Hot now</div>'
                + hchip("RS leader", hot.get("leader"), "#3fb950", f'RS {hot.get("leader",{}).get("rs63","")}')
                + hchip("RS laggard", hot.get("laggard"), "#f85149", f'RS {hot.get("laggard",{}).get("rs63","")}')
                + hchip("most stretched", hot.get("stretched"), "#d29922", "near TRR")
                + hchip("best dip", hot.get("dip"), "#58a6ff", "near LRR · bull")
                + '</div>', unsafe_allow_html=True)
    st.caption("Next: 'what changed today' deltas (needs prior-session state) + cross-asset propagation graph.")


# ── TAB 2 · Opportunity & Execution (the ONLY home for trade cards) ──
def render_opportunity():
    rows = get_rows()
    if not rows:
        _empty("No market data loaded yet.")
        return
    st.markdown("### Opportunity map — crowding × relative strength")
    st.caption("Top-left = uncrowded leaders (sweet spot). Bubble size = volatility (ATR%). Colour = side.")
    dfm = pd.DataFrame([{"ticker": r["ticker"], "crowding": r["crowding"], "rs63": r["rs63"],
                         "atr_pct": max(r["atr_pct"], 0.3), "side": r["side"]}
                        for r in rows if r["rs63"] is not None])
    if len(dfm):
        st.scatter_chart(dfm, x="crowding", y="rs63", size="atr_pct", color="side", height=320)

    sig = [r for r in rows if r["signaling"]]
    st.markdown(f"### Trade cards — {len(sig)} signaling")
    if not sig:
        st.info("No actionable Risk Range setups right now.")
    cols = st.columns(2)
    for i, r in enumerate(sorted(sig, key=lambda x: -x["er"])):
        p = r["plan"]
        with cols[i % 2]:
            stack = (_sigbar("momentum", r["momentum"], "#3fb950") +
                     _sigbar("rel strength", max(0, min(100, 50 + (r["rs63"] or 0))), "#58a6ff") +
                     _sigbar("reflexivity", r["reflexivity"], "#d29922") +
                     _sigbar("crowding", r["crowding"], "#f0883e"))
            plan = (f'entry <b>{p["entry"]}</b> · stop <b>{p["stop"]}</b> · T1 <b>{p["t1"]}</b>'
                    f'{" · T2 " + str(p["t2"]) if p["t2"] else ""} · R/R <b>{p["rr"]}</b>') if p["entry"] else "—"
            gex = _locked("gamma walls (GEX)", "options chain — US only") if r["market"] == "us" else ""
            st.markdown(
                f'<div class="card"><span style="font-size:17px;font-weight:700">{r["ticker"]}</span> '
                f'<span class="{_sidecls(r["side"])}">{r["side"]}</span> '
                f'<small class="muted">· {MKT_LABEL[r["market"]]} · {r["formation"]}</small>'
                f'{_band(r["lrr"], r["close"], r["trr"])}'
                f'<div style="margin-top:8px">{stack}</div>'
                f'<div style="margin-top:8px;font-size:13px">{plan}</div>'
                f'<small class="muted">RTA {r["rta"]} · response {r["response"]} · ER {r["er"]} · {p["note"]}</small>'
                f'{gex}</div>', unsafe_allow_html=True)


# ── TAB 4 · Market State (internals + drilldowns + locked feed panels) ──
def render_market_state():
    rows = get_rows()
    netliq, nl_chg = load_netliq()
    if not rows:
        _empty("No market data loaded yet.")
        return
    b = breadth(rows)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Health", f"{b['health']:.0f}")
    c2.metric("% > 50d", f"{b['pct_above_50']:.0f}")
    c3.metric("% > 200d", f"{b['pct_above_200']:.0f}")
    c4.metric("Bull / Bear", f"{b['bullish']} / {b['bearish']}")
    c5.metric("NetLiq ($bn)", f"{netliq:,.0f}" if netliq is not None else "—",
              f"{nl_chg:+,.0f} wk" if nl_chg is not None else None)

    g1, g2 = st.columns(2)
    with g1:
        st.markdown("##### Breadth by market")
        st.dataframe(pd.DataFrame([{"market": MKT_LABEL[m], **v} for m, v in breadth_by_market(rows).items()]),
                     use_container_width=True, hide_index=True)
        st.markdown("##### Leadership — RS (uncrowded first)")
        st.dataframe(pd.DataFrame([{"ticker": r["ticker"], "mkt": MKT_LABEL[r["market"]], "rs63": r["rs63"],
                                    "ret63": r["ret63"], "crowd": r["crowding"]} for r in leadership(rows, 10)]),
                     use_container_width=True, hide_index=True)
    with g2:
        st.markdown("##### Internals not yet wired")
        st.markdown(_locked("Credit spreads (HY/IG OAS)", "FRED BAMLH0A0HYM2 — easy next") +
                    _locked("Correlation matrix", "rolling 63/126/252d — computable next") +
                    _locked("Dealer gamma / vanna", "options chain (US)") +
                    _locked("Foreign Type-F flow", "IDX GetStockSummary (IHSG)"), unsafe_allow_html=True)

    st.markdown("### Measured universe (per market)")
    for market in UNIVERSE:
        mr = [r for r in rows if r["market"] == market]
        if not mr:
            continue
        lo = " · long-only" if market in LONG_ONLY else ""
        with st.expander(f"{MKT_LABEL[market]} — {len(mr)} measured{lo}"):
            st.dataframe(pd.DataFrame(mr)[["ticker", "side", "rta", "formation", "response",
                                           "close", "lrr", "trr", "rs63", "crowding", "er"]],
                         use_container_width=True, hide_index=True)


# ── TAB 3 · Bottleneck & Moonshot ──
def render_bottleneck_moonshot():
    st.markdown("### Asymmetric / Moonshot Radar")
    st.warning("Research screen — **not advice**. Ranks the *structural* traits of past moonshots "
               "(bottleneck centrality · early adoption · under-coverage · small cap), not returns. "
               "Higher upside tier = lower base rate; tier-4/5 are lottery tickets and most go to zero. "
               "Cap / valuation / coverage need a live feed — neutral until wired (no fabrication).")
    out = run_discovery(min_asymmetry=0.0, top=80)
    s = out["summary"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Candidates", s["n"]); c2.metric("Hidden (layer 3-4)", s["hidden"]); c3.metric("Awaiting feed", f"{s['needs_feed']}/{s['n']}")
    tier_color = {1: "#8b949e", 2: "#58a6ff", 3: "#d29922", 4: "#f0883e", 5: "#f85149"}
    bydom = defaultdict(list)
    for r in out["candidates"]:
        bydom[r["domain"]].append(r)
    for dom, rs in bydom.items():
        with st.expander(f"{dom} — {len(rs)} · {rs[0]['framework']} ({rs[0]['source']})", expanded=False):
            for r in sorted(rs, key=lambda x: -x["asymmetry"]):
                tc = tier_color.get(r["tier"], "#8b949e")
                hid = '<span class="chip" style="color:#58a6ff">hidden</span>' if r["is_hidden"] else ""
                crd = '<span class="chip" style="color:#8b949e">crowded</span>' if r["is_crowded"] else ""
                st.markdown(
                    f'<div class="card"><b>{r["ticker"]}</b> {hid}{crd}'
                    f'<span style="float:right;color:{tc};font-weight:700">T{r["tier"]} · {r["upside_bucket"]} · base {r["base_rate"]}</span><br>'
                    f'<small class="muted">{r["node"]}</small><br><span style="font-size:13px">{r["scarcity"]}</span><br>'
                    f'<small class="muted">asymmetry {r["asymmetry"]} · stage {r["stage"]} · confidence {r["confidence"]}</small></div>',
                    unsafe_allow_html=True)
    st.markdown("#### What breaks the thesis")
    for f in out["failure_modes"]:
        st.markdown(f"- {f}")
    st.caption("Next: live cap/valuation/coverage feed · propagation network graph · tier-multiplier ladder.")


# ── TAB 5 · Research Lab ──
def render_research_lab():
    st.markdown("### Research Lab — validation")
    st.warning("The **honest harness**. Numbers below are a *diagnostic* of the Risk Range dip-buy signal "
               "on available history — overlapping windows, no costs, in-sample params. NOT the full OOS "
               "harness. A signal earns trust only via the acceptance gate: **perm_p < 0.05 AND DSR ≥ 0.95, else NOISE**.")
    with st.spinner("Backtesting the Risk Range dip-buy signal…"):
        bt = rr_backtest(load_all(), fwd=10)
    if not bt or bt.get("n", 0) == 0:
        _empty("Not enough data to run the diagnostic.")
    else:
        st.markdown("#### Risk Range dip-buy (close ≤ TRADE LRR, bullish formation) → 10-day forward")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Signals (n)", bt["n"]); c2.metric("Hit rate", f"{bt['hit']:.0f}%")
        c3.metric("Mean fwd", f"{bt['mean']:+.2f}%"); c4.metric("Median fwd", f"{bt['median']:+.2f}%")
        if bt.get("by_market"):
            st.dataframe(pd.DataFrame([{"market": MKT_LABEL.get(m, m), **v} for m, v in bt["by_market"].items()]),
                         use_container_width=True, hide_index=True)
    st.markdown("#### Acceptance gate")
    st.markdown("- Walk-forward IC > 0 OOS, permutation **p < 0.05**\n- **Deflated Sharpe ≥ 0.95**\n"
                "- Long-short decile spread positive across regimes\n- Else → **NOISE**, do not trade")
    st.caption("Next: wire gcfis/engines/backtest.py (full DSR + permutation) + Monte Carlo + feature IC.")


# ── shell ──
st.markdown("## 🛰 MacroRegime War Room")
st.caption("Command Center = what matters now · Opportunity = the trades · Bottleneck = asymmetric · "
           "Market State = internals · Research = validation. Feed-gated panels shown locked, never faked.")
t1, t2, t3, t4, t5 = st.tabs(["Command Center", "Opportunity & Execution",
                              "Bottleneck & Moonshot", "Market State", "Research Lab"])
with t1:
    render_command_center()
with t2:
    render_opportunity()
with t3:
    render_bottleneck_moonshot()
with t4:
    render_market_state()
with t5:
    render_research_lab()
