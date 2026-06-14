"""warroom/app.py — MacroRegime War Room (5-tab shell).

Build step 1 MVP: Command Center driven by the new Hedgeye Risk Range engine
(risk_range_hedgeye). Measures the Risk Range for the whole multi-market universe,
then surfaces ONLY the names with a clear, formation-aligned signal — quality over
quantity, the Keith McCullough way ("X of N signaling"). Per-market columns differ
by available data (IDX is long-only; no greeks/on-chain faked anywhere).

Runs on deploy (yfinance + FRED, no API key). Tabs 2-5 are wired next.

Run:  streamlit run warroom/app.py
"""
from __future__ import annotations
import os
import sys
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from gcfis.engines.risk_range_hedgeye import compute_risk_range  # noqa: E402
from gcfis.engines.asymmetric_discovery import run_discovery  # noqa: E402
from collections import defaultdict  # noqa: E402

# ── universe per market (data availability differs — that's the point) ──
UNIVERSE = {
    "us":        ["SPY", "QQQ", "NVDA", "PLTR", "AAPL", "MSFT", "AMD", "META"],
    "crypto":    ["BTC-USD", "ETH-USD"],
    "fx":        ["EURUSD=X", "USDJPY=X", "GBPUSD=X"],
    "commodity": ["GC=F", "CL=F", "SI=F"],
    "idx":       ["BBCA.JK", "BBRI.JK", "BMRI.JK", "ASII.JK", "TLKM.JK"],
}
LONG_ONLY = {"idx"}
MKT_LABEL = {"us": "US equity", "crypto": "Crypto", "fx": "FX", "commodity": "Commodity", "idx": "IHSG"}

st.set_page_config(page_title="MacroRegime War Room", page_icon="🛰", layout="wide",
                   initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap");
html, body, [class*="css"] { font-family: "Inter", sans-serif; }
.stApp { background: #0B0E11; }
.block-container { padding-top: 0.6rem !important; max-width: 1500px !important; }
h1,h2,h3 { letter-spacing: -0.3px; }
[data-testid="stMetric"] { background:#12161C; border:1px solid rgba(255,255,255,0.06); border-radius:10px; padding:8px 12px !important; }
[data-testid="stMetricValue"] { font-size:1.4rem !important; font-weight:700 !important; }
[data-testid="stMetricLabel"] { font-size:0.62rem !important; letter-spacing:0.6px; text-transform:uppercase; opacity:0.55; }
.stTabs [data-baseweb="tab"] { font-weight:600; }
.desk-long { color:#3fb950; font-weight:700; }
.desk-short { color:#f85149; font-weight:700; }
.desk-trim { color:#d29922; font-weight:700; }
.chip { display:inline-block; font-size:11px; padding:2px 8px; border-radius:6px; margin-right:4px; }
.card { background:#12161C; border:1px solid rgba(255,255,255,0.06); border-radius:12px; padding:12px 16px; margin-bottom:10px; }
</style>
""", unsafe_allow_html=True)


# ── data ──
@st.cache_data(ttl=3600, show_spinner=False)
def load_ohlcv(tickers, days=820):
    """yfinance OHLCV → {ticker: DataFrame[open,high,low,close,volume]}. Graceful per-ticker."""
    out = {}
    try:
        import yfinance as yf
    except Exception:
        return out, "yfinance not installed"
    for t in tickers:
        try:
            d = yf.download(t, period=f"{days}d", interval="1d", progress=False, auto_adjust=True)
            if d is None or len(d) < 80:
                continue
            d.columns = [c[0] if isinstance(c, tuple) else c for c in d.columns]
            d = d.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].dropna()
            out[t] = d
        except Exception:
            continue
    return out, f"{len(out)}/{len(tickers)} loaded"


@st.cache_data(ttl=3600, show_spinner=False)
def load_netliq():
    """FRED NetLiq (no key). Returns ($bn latest, weekly Δ) or (None, None)."""
    try:
        from gcfis.feeds.fred_feed import fetch_fred
        ser, _status = fetch_fred()
        nl = ser.get("FEDLIQ")
        if nl is None or len(nl) < 10:
            return None, None
        return float(nl.iloc[-1]), float(nl.iloc[-1] - nl.iloc[-6])
    except Exception:
        return None, None


def run_universe():
    """Compute Risk Range for the whole universe → list of signal rows."""
    rows = []
    for market, tickers in UNIVERSE.items():
        data, _ = load_ohlcv(tickers)
        for t, df in data.items():
            try:
                rr = compute_risk_range(df, ticker=t)
            except Exception:
                continue
            rta = rr.get("rta", "—")
            form = rr.get("formation", "NEUTRAL")
            long_ok = rta in ("BUY", "ADD") and form == "BULLISH"
            short_ok = rta in ("SHORT",) and form == "BEARISH" and market not in LONG_ONLY
            trim_ok = rta in ("TRIM", "TRIM_RIP")
            signaling = long_ok or short_ok or trim_ok
            side = "LONG" if long_ok else "SHORT" if short_ok else "TRIM" if trim_ok else "—"
            rows.append({"ticker": t, "market": market, "side": side, "signaling": signaling,
                         "rta": rta, "formation": form, "response": rr.get("response", "MID"),
                         "close": rr["close"], "lrr": rr["trade"]["lrr"], "trr": rr["trade"]["trr"],
                         "trend_phase": rr["trend"]["phase"], "er": rr.get("efficiency_ratio", 0.0)})
    return rows


def _side_html(side):
    cls = {"LONG": "desk-long", "SHORT": "desk-short", "TRIM": "desk-trim"}.get(side, "")
    return f'<span class="{cls}">{side}</span>'


# ── Command Center ──
def render_command_center():
    netliq, nl_chg = load_netliq()
    with st.spinner("Measuring Risk Ranges across the universe…"):
        rows = run_universe()
    total = len(rows)
    signaling = [r for r in rows if r["signaling"]]
    longs = [r for r in signaling if r["side"] == "LONG"]
    shorts = [r for r in signaling if r["side"] == "SHORT"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Signaling", f"{len(signaling)} of {total}", help="Keith-style: measured all, only the clear few qualify")
    c2.metric("Longs", len(longs))
    c3.metric("Shorts", len(shorts))
    c4.metric("Fed NetLiq ($bn)", f"{netliq:,.0f}" if netliq is not None else "—",
              f"{nl_chg:+,.0f} wk" if nl_chg is not None else None)

    st.markdown("### Final Desk — quality over quantity")
    if not signaling:
        st.info("No clear Risk Range signal across the universe right now — slim pickings. "
                "No fabricated fills (this is the point).")
    else:
        order = {"LONG": 0, "SHORT": 1, "TRIM": 2}
        for r in sorted(signaling, key=lambda x: (order.get(x["side"], 9), -x["er"])):
            st.markdown(
                f'<div class="card">{_side_html(r["side"])} &nbsp; <b>{r["ticker"]}</b> '
                f'<span style="color:#8b949e">· {MKT_LABEL[r["market"]]}</span><br>'
                f'<span style="font-size:13px;color:#8b949e">RTA {r["rta"]} · formation {r["formation"]} '
                f'· {r["response"]} · ER {r["er"]}</span><br>'
                f'<span style="font-size:13px">close {r["close"]} · LRR {r["lrr"]} · TRR {r["trr"]}</span></div>',
                unsafe_allow_html=True)

    st.markdown("### Measured universe (per market)")
    for market in UNIVERSE:
        mr = [r for r in rows if r["market"] == market]
        if not mr:
            continue
        lo = " · long-only" if market in LONG_ONLY else ""
        with st.expander(f"{MKT_LABEL[market]} — {len(mr)} measured{lo}"):
            st.dataframe(pd.DataFrame(mr)[["ticker", "side", "rta", "formation", "response",
                                           "close", "lrr", "trr", "trend_phase", "er"]],
                         use_container_width=True, hide_index=True)


def _stub(title, bullets):
    st.markdown(f"### {title}")
    st.caption("Wired next — design locked.")
    for b in bullets:
        st.markdown(f"- {b}")


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
    for dom, rows in bydom.items():
        head = f"{dom} — {len(rows)} · {rows[0]['framework']} ({rows[0]['source']})"
        with st.expander(head, expanded=False):
            for r in sorted(rows, key=lambda x: -x["asymmetry"]):
                tc = tier_color.get(r["tier"], "#8b949e")
                hid = '<span class="chip" style="background:#1f6feb33;color:#58a6ff">hidden</span>' if r["is_hidden"] else ""
                crd = '<span class="chip" style="background:#6e768166;color:#8b949e">crowded</span>' if r["is_crowded"] else ""
                st.markdown(
                    f'<div class="card"><b>{r["ticker"]}</b> {hid}{crd}'
                    f'<span style="float:right;color:{tc};font-weight:700">T{r["tier"]} · {r["upside_bucket"]} · base {r["base_rate"]}</span><br>'
                    f'<span style="font-size:12px;color:#8b949e">{r["node"]}</span><br>'
                    f'<span style="font-size:13px">{r["scarcity"]}</span><br>'
                    f'<span style="font-size:12px;color:#8b949e">asymmetry {r["asymmetry"]} · stage {r["stage"]} · confidence {r["confidence"]}</span></div>',
                    unsafe_allow_html=True)
    st.markdown("#### What breaks the thesis")
    for f in out["failure_modes"]:
        st.markdown(f"- {f}")
    st.caption("Wired next: live cap/valuation/coverage feed · propagation network graph · tier-multiplier ladder · node detail sidebar.")


# ── shell ──
st.markdown("## 🛰 MacroRegime War Room")
t1, t2, t3, t4, t5 = st.tabs(["Command Center", "Opportunity & Execution",
                              "Bottleneck Map", "Market State", "Research Lab"])
with t1:
    render_command_center()
with t2:
    _stub("Opportunity & Execution", [
        "Bubble cluster map (crowding × pressure, size = reflexivity)",
        "Ticker cards: causal stack + Risk Range band + RTA + playbook + entry/stop/target/qty",
        "Per-market conditional panels (US greeks · crypto funding · IDX bandar)"])
with t3:
    render_bottleneck_moonshot()
with t4:
    _stub("Market State", [
        "Band A — internals (breadth/credit/liquidity/vol/correlation/leadership + divergence)",
        "Band B — flow & positioning (accumulation heatmap + per-market selector)"])
with t5:
    _stub("Research Lab", [
        "Walk-forward IC + permutation p + Deflated Sharpe + Monte Carlo",
        "Acceptance gate: perm_p<0.05 AND DSR≥0.95, else NOISE · bias guard"])
