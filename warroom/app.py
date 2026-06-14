"""warroom/app.py — MacroRegime War Room (5 tabs, all live).

Build step 2: all five tabs render. Everything is derived from price/volume (yfinance)
+ FRED + the verified Risk Range / asymmetric engines. Feed-gated enrichments
(GEX/greeks, on-chain, COT, fundamentals) are absent and flagged — never fabricated.
Per-market content differs (IDX long-only; no greeks/on-chain faked). Not financial advice.

Run:  pip install -r warroom/requirements.txt ; streamlit run warroom/app.py
"""
from __future__ import annotations
import os
import sys
from collections import defaultdict

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from warroom.engine_bridge import (UNIVERSE, LONG_ONLY, MKT_LABEL, BENCH,  # noqa: E402
                                   build_rows, breadth, breadth_by_market, leadership, rr_backtest)
from gcfis.engines.asymmetric_discovery import run_discovery  # noqa: E402

st.set_page_config(page_title="MacroRegime War Room", page_icon="🛰", layout="wide",
                   initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap");
html, body, [class*="css"] { font-family: "Inter", sans-serif; }
.stApp { background: #0B0E11; }
.block-container { padding-top: 0.6rem !important; max-width: 1500px !important; }
[data-testid="stMetric"] { background:#12161C; border:1px solid rgba(255,255,255,0.06); border-radius:10px; padding:8px 12px !important; }
[data-testid="stMetricValue"] { font-size:1.35rem !important; font-weight:700 !important; }
[data-testid="stMetricLabel"] { font-size:0.62rem !important; letter-spacing:0.6px; text-transform:uppercase; opacity:0.55; }
.stTabs [data-baseweb="tab"] { font-weight:600; }
.desk-long{color:#3fb950;font-weight:700} .desk-short{color:#f85149;font-weight:700} .desk-trim{color:#d29922;font-weight:700}
.chip{display:inline-block;font-size:11px;padding:2px 8px;border-radius:6px;margin-right:4px}
.card{background:#12161C;border:1px solid rgba(255,255,255,0.06);border-radius:12px;padding:12px 16px;margin-bottom:10px}
.band{position:relative;height:10px;background:#1c2128;border-radius:5px;margin:8px 0}
.band-fill{position:absolute;top:0;bottom:0;left:0;background:#21323f;border-radius:5px}
.band-dot{position:absolute;top:-3px;width:4px;height:16px;background:#e6edf3;border-radius:2px}
.bar{display:inline-block;height:7px;border-radius:3px;vertical-align:middle}
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


def _side_html(side):
    cls = {"LONG": "desk-long", "SHORT": "desk-short", "TRIM": "desk-trim"}.get(side, "")
    return f'<span class="{cls}">{side}</span>'


def _band_html(lrr, close, trr):
    rng = max(trr - lrr, 1e-9)
    pos = max(0.0, min(1.0, (close - lrr) / rng)) * 100.0
    return (f'<div class="band"><div class="band-fill" style="width:{pos:.0f}%"></div>'
            f'<div class="band-dot" style="left:calc({pos:.0f}% - 2px)"></div></div>'
            f'<small class="muted">LRR {lrr} · <b style="color:#e6edf3">close {close}</b> · TRR {trr}</small>')


def _sigbar(label, val, color):
    w = max(2, min(100, val))
    return (f'<div style="margin:2px 0"><small class="muted" style="display:inline-block;width:92px">{label}</small>'
            f'<span class="bar" style="width:{w}px;background:{color}"></span> <small class="muted">{val:.0f}</small></div>')


def _empty(msg):
    st.info(msg + "  \n(In a sandbox without market data this is expected; runs fully on deploy with yfinance + FRED.)")


# ── TAB 1 · Command Center ──
def render_command_center():
    netliq, nl_chg = load_netliq()
    with st.spinner("Measuring Risk Ranges across the universe…"):
        rows = get_rows()
    if not rows:
        _empty("No market data loaded yet.")
        return
    sig = [r for r in rows if r["signaling"]]
    longs = [r for r in sig if r["side"] == "LONG"]
    shorts = [r for r in sig if r["side"] == "SHORT"]
    b = breadth(rows)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Signaling", f"{len(sig)} of {len(rows)}", help="Measured all; only clear signals qualify (Keith-style)")
    c2.metric("Longs", len(longs))
    c3.metric("Shorts", len(shorts))
    c4.metric("Breadth health", f"{b['health']:.0f}")
    c5.metric("Fed NetLiq ($bn)", f"{netliq:,.0f}" if netliq is not None else "—",
              f"{nl_chg:+,.0f} wk" if nl_chg is not None else None)

    st.markdown("### Final Desk — quality over quantity")
    if not sig:
        st.info("No clear Risk Range signal right now — slim pickings. No fabricated fills.")
    else:
        order = {"LONG": 0, "SHORT": 1, "TRIM": 2}
        for r in sorted(sig, key=lambda x: (order.get(x["side"], 9), -x["er"])):
            p = r["plan"]
            plan = (f' · entry {p["entry"]} · stop {p["stop"]} · T1 {p["t1"]}'
                    f'{" · T2 " + str(p["t2"]) if p["t2"] else ""} · R/R {p["rr"]}') if p["entry"] else ""
            st.markdown(
                f'<div class="card">{_side_html(r["side"])} &nbsp;<b>{r["ticker"]}</b> '
                f'<small class="muted">· {MKT_LABEL[r["market"]]} · RTA {r["rta"]} · {r["formation"]} · {r["response"]}</small>'
                f'{_band_html(r["lrr"], r["close"], r["trr"])}'
                f'<small class="muted">{plan}</small></div>', unsafe_allow_html=True)

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


# ── TAB 2 · Opportunity & Execution ──
def render_opportunity():
    rows = get_rows()
    if not rows:
        _empty("No market data loaded yet.")
        return
    st.markdown("### Opportunity map — crowding × relative strength")
    st.caption("Top-left = uncrowded leaders (the sweet spot). Bubble size = volatility (ATR%). Colour = side.")
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
            st.markdown(
                f'<div class="card"><span style="font-size:17px;font-weight:700">{r["ticker"]}</span> '
                f'{_side_html(r["side"])} <small class="muted">· {MKT_LABEL[r["market"]]} · {r["formation"]}</small>'
                f'{_band_html(r["lrr"], r["close"], r["trr"])}'
                f'<div style="margin-top:8px">{stack}</div>'
                f'<div style="margin-top:8px;font-size:13px">{plan}</div>'
                f'<small class="muted">RTA {r["rta"]} · response {r["response"]} · ER {r["er"]} · {p["note"]}</small></div>',
                unsafe_allow_html=True)
    st.caption("Next: GEX/greeks gamma walls (US) overlaid on the band — feed-gated, not faked.")


# ── TAB 4 · Market State ──
def render_market_state():
    rows = get_rows()
    netliq, nl_chg = load_netliq()
    if not rows:
        _empty("No market data loaded yet.")
        return
    b = breadth(rows)
    st.markdown("### Market health (internals)")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Health", f"{b['health']:.0f}")
    c2.metric("% > 50d", f"{b['pct_above_50']:.0f}")
    c3.metric("% > 200d", f"{b['pct_above_200']:.0f}")
    c4.metric("Bull / Bear", f"{b['bullish']} / {b['bearish']}")
    c5.metric("NetLiq ($bn)", f"{netliq:,.0f}" if netliq is not None else "—",
              f"{nl_chg:+,.0f} wk" if nl_chg is not None else None)

    st.markdown("### Breadth by market")
    bm = breadth_by_market(rows)
    st.dataframe(pd.DataFrame([{"market": MKT_LABEL[m], **v} for m, v in bm.items()]),
                 use_container_width=True, hide_index=True)

    st.markdown("### Leadership — relative strength (uncrowded first)")
    lead = leadership(rows, top=10)
    st.dataframe(pd.DataFrame([{"ticker": r["ticker"], "market": MKT_LABEL[r["market"]], "rs63": r["rs63"],
                                "ret63": r["ret63"], "crowding": r["crowding"], "formation": r["formation"]}
                               for r in lead]), use_container_width=True, hide_index=True)
    st.caption("Next (feed-gated): credit spreads (HY/IG OAS), correlation matrix, dealer gamma, foreign Type-F flow.")


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
    c1.metric("Candidates", s["n"])
    c2.metric("Hidden (layer 3-4)", s["hidden"])
    c3.metric("Awaiting feed", f"{s['needs_feed']}/{s['n']}")
    tier_color = {1: "#8b949e", 2: "#58a6ff", 3: "#d29922", 4: "#f0883e", 5: "#f85149"}
    bydom = defaultdict(list)
    for r in out["candidates"]:
        bydom[r["domain"]].append(r)
    for dom, rs in bydom.items():
        with st.expander(f"{dom} — {len(rs)} · {rs[0]['framework']} ({rs[0]['source']})", expanded=False):
            for r in sorted(rs, key=lambda x: -x["asymmetry"]):
                tc = tier_color.get(r["tier"], "#8b949e")
                hid = '<span class="chip" style="background:#1f6feb33;color:#58a6ff">hidden</span>' if r["is_hidden"] else ""
                crd = '<span class="chip" style="background:#6e768166;color:#8b949e">crowded</span>' if r["is_crowded"] else ""
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
    st.warning("This is the **honest harness**. Numbers below are a *diagnostic* of the Risk Range "
               "dip-buy signal on available history — overlapping windows, no costs, in-sample params. "
               "It is NOT the full out-of-sample harness. A live signal only earns trust through the "
               "acceptance gate: **perm_p < 0.05 AND Deflated Sharpe ≥ 0.95, else NOISE**.")
    with st.spinner("Backtesting the Risk Range dip-buy signal…"):
        bt = rr_backtest(load_all(), fwd=10)
    if not bt or bt.get("n", 0) == 0:
        _empty("Not enough data to run the diagnostic.")
    else:
        st.markdown("#### Risk Range dip-buy (close ≤ TRADE LRR, bullish formation) → 10-day forward")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Signals (n)", bt["n"])
        c2.metric("Hit rate", f"{bt['hit']:.0f}%")
        c3.metric("Mean fwd", f"{bt['mean']:+.2f}%")
        c4.metric("Median fwd", f"{bt['median']:+.2f}%")
        if bt.get("by_market"):
            st.dataframe(pd.DataFrame([{"market": MKT_LABEL.get(m, m), **v} for m, v in bt["by_market"].items()]),
                         use_container_width=True, hide_index=True)
    st.markdown("#### Acceptance gate (what makes a signal trustworthy)")
    st.markdown("- **Walk-forward IC** > 0 out-of-sample, with permutation **p < 0.05**\n"
                "- **Deflated Sharpe Ratio ≥ 0.95** (corrects for multiple testing / selection)\n"
                "- Long-short decile spread positive across regimes\n"
                "- Else → label **NOISE** and do not trade")
    st.caption("Next: wire gcfis/engines/backtest.py (full DSR + permutation) + Monte Carlo + feature IC.")


# ── shell ──
st.markdown("## 🛰 MacroRegime War Room")
st.caption("All five tabs live. Price/volume + FRED + verified Risk Range/asymmetric engines. "
           "Feed-gated enrichments flagged, never faked. Not financial advice.")
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
