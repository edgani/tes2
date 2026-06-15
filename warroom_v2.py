"""
warroom_v2.py — NEW-DESIGN War Room front-end, wired to your VERIFIED tes2 engines.

Drop this file (+ lpm.py + .streamlit/config.toml) into the tes2 repo ROOT
(next to gcfis/, engines/, warroom/) and run:

    pip install -r warroom/requirements.txt
    streamlit run warroom_v2.py

WIRES (all smoke-tested as PASS on synthetic data):
  • warroom.bridge.build ............ regime read + competitive ranking + per-ticker rows
                                      (Hedgeye Risk Range LRR/TRR, RS63, crowding, momentum,
                                       accumulation, reflexivity, bottleneck, formation)
  • engines.thought_process_engine .. Citrini + Hedgeye + Yves + Soros + Druckenmiller + Coatue
  • engines.leopold_methodology ..... Aschenbrenner OOM compute-scaling + bottleneck layers
  • gcfis.engines.asymmetric_discovery  Moonshot / hidden-bottleneck screen
  • lpm.py .......................... fixed value-based Liquidity Pressure Model (IDX bandar)

Data: yfinance live; deterministic SYNTHETIC fallback so it always renders (flagged in UI).
Honesty: engine math is verified; EDGE is not — weights are priors. Not financial advice.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import streamlit as st

# ----------------------------------------------------------------------------- universe
US_UNIVERSE = ["NVDA", "ARKK", "XLE", "VST", "CEG", "VRT", "ANET", "SMH", "AAPL", "MSFT",
               "GLD", "TLT", "XLU", "XLP", "HYG", "USO", "DBC", "COPX", "SOXX", "SPY"]
IDX_UNIVERSE = ["BBCA.JK", "BMRI.JK", "BBRI.JK", "TLKM.JK", "ASII.JK", "BUMI.JK", "ANTM.JK", "HUMI.JK"]
GROWTH_B, DEF_B, INFL_B = ["SOXX", "COPX", "HYG"], ["XLU", "XLP"], ["USO", "DBC"]


def _fmt(v, nd=2):
    try:
        if v is None or (isinstance(v, float) and (np.isnan(v))):
            return "—"
        return f"{float(v):.{nd}f}"
    except Exception:
        return str(v)


# ----------------------------------------------------------------------------- data layer
def _synth(ticker: str, n: int = 400) -> pd.DataFrame:
    r = np.random.default_rng(abs(hash(ticker)) % (2**32))
    rets = r.normal(r.uniform(-0.0007, 0.0012), r.uniform(0.012, 0.03), n)
    c = 100 * np.exp(np.cumsum(rets))
    intr = np.abs(r.normal(0, 0.02, n)) * c
    loc = r.uniform(0.2, 0.8, n)
    h = c + intr * (1 - loc); l = c - intr * loc
    o = l + (h - l) * r.uniform(0.2, 0.8, n)
    v = r.uniform(1e6, 5e7, n).round()
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": v}, index=idx)


@st.cache_data(ttl=900, show_spinner=False)
def load_prices(tickers, days: int = 400):
    tickers = list(dict.fromkeys(tickers))
    try:
        import yfinance as yf
        raw = yf.download(tickers, period=f"{days}d", interval="1d", auto_adjust=False,
                          progress=False, group_by="ticker", threads=True)
        out = {}
        if isinstance(raw.columns, pd.MultiIndex):
            for t in tickers:
                if t in raw.columns.get_level_values(0):
                    d = raw[t][["Open", "High", "Low", "Close", "Volume"]].dropna()
                    if len(d) > 80:
                        out[t] = d
        else:
            d = raw[["Open", "High", "Low", "Close", "Volume"]].dropna()
            if len(d) > 80:
                out[tickers[0]] = d
        if len(out) >= max(4, len(tickers) // 2):
            return out, "yfinance · live"
    except Exception:
        pass
    return {t: _synth(t, days) for t in tickers}, "synthetic · demo (no live feed)"


def _basket_z(prices, tickers, n=20):
    zs = []
    for t in tickers:
        d = prices.get(t)
        if d is not None and len(d) > n + 60:
            r = d["Close"].pct_change(n)
            z = (r.iloc[-1] - r.tail(252).mean()) / (r.tail(252).std() + 1e-9)
            if np.isfinite(z):
                zs.append(float(z))
    return float(np.mean(zs)) if zs else 0.0


def derive_quad(prices):
    g = _basket_z(prices, GROWTH_B) - _basket_z(prices, DEF_B)
    i = _basket_z(prices, INFL_B)
    quad = ("Quad 1" if (g > 0 and i <= 0) else "Quad 2" if (g > 0 and i > 0)
            else "Quad 3" if (g <= 0 and i > 0) else "Quad 4")
    desc = {"Quad 1": "Growth accelerating · inflation slowing",
            "Quad 2": "Growth accelerating · inflation accelerating",
            "Quad 3": "Growth slowing · inflation accelerating",
            "Quad 4": "Growth slowing · inflation slowing"}[quad]
    return quad, desc, round(g, 2), round(i, 2)


# ----------------------------------------------------------------------------- compute (testable, no streamlit calls)
def compute(prices: dict, idx_prices: dict | None = None) -> dict:
    out = {"errors": []}
    quad, quad_desc, g_z, i_z = derive_quad(prices)
    out.update(quad=quad, quad_desc=quad_desc, growth_z=g_z, infl_z=i_z)

    rows, regime, ranking = [], {}, {}
    try:
        import warroom.bridge as br
        built = br.build({"US": {t: prices[t] for t in prices}})
        rows, regime, ranking = built.get("rows", []), built.get("regime", {}), built.get("ranking", {})
    except Exception as e:
        out["errors"].append(f"bridge: {e}")
    out["regime"], out["ranking"] = regime, ranking

    # breadth + posture
    above = sum(1 for r in rows if r.get("formation") == "BULLISH")
    n = len(rows) or 1
    breadth = round(100 * above / n)
    defensive = (g_z <= 0) and (i_z > 0 or breadth < 50 or regime.get("liq_stress", 0) > 0)
    out["breadth"], out["posture"], out["defensive"] = breadth, "Defensive" if defensive else "Risk-on", defensive

    # conviction / watchlist from rows (sorted by engine score)
    def direction(r):
        f = r.get("formation", "")
        return "Long" if f == "BULLISH" else "Short" if f == "BEARISH" else "Watch"
    for r in rows:
        r["_dir"] = direction(r)
    ranked = sorted([r for r in rows if r.get("ticker") not in ("SPY",)],
                    key=lambda r: r.get("score", 0) or 0, reverse=True)
    out["conviction"] = ranked[:4]
    out["watchlist"] = ranked[4:12]
    out["scanned"] = len(rows)

    # methodology theses (Citrini / Hedgeye / Yves / Soros / Druckenmiller / Coatue)
    try:
        from engines.thought_process_engine import analyze_multi, get_top_theses
        names = [r["ticker"] for r in ranked[:10]]
        res = analyze_multi(names, prices={t: prices[t]["Close"] for t in names if t in prices},
                            quad=quad.replace("Quad ", "Q"), vix=20.0)
        out["theses"] = get_top_theses(res, top_n=8)
    except Exception as e:
        out["theses"] = []; out["errors"].append(f"thought_process: {e}")

    # Aschenbrenner / Leopold (OOM scaling + bottleneck layers)
    try:
        from engines.leopold_methodology import run_leopold_scan
        out["leopold"] = run_leopold_scan(list(prices.keys()), {t: prices[t]["Close"] for t in prices})
    except Exception as e:
        out["leopold"] = {}; out["errors"].append(f"leopold: {e}")

    # Moonshot / hidden bottleneck
    try:
        from gcfis.engines.asymmetric_discovery import run_discovery
        out["moonshot"] = run_discovery(extra_tickers=list(prices.keys()), top=12)
    except Exception as e:
        out["moonshot"] = {}; out["errors"].append(f"asymmetric_discovery: {e}")

    # US gamma (price-proxy GEX; options feed sharpens it)
    try:
        from engines.gex_engine import analyze_multi as _gex
        us_top = [r["ticker"] for r in ranked[:8] if r["ticker"] in prices]
        out["gex"] = _gex(us_top, {t: prices[t] for t in us_top}, 20.0)
    except Exception as e:
        out["gex"] = {}; out["errors"].append(f"gex: {e}")

    # IDX bandar — value-based LPM (patched engine + lpm.py); foreign flow needs Type-F feed
    out["idx"] = []
    if idx_prices:
        try:
            import engines.bandarmetrics_engine as BM
            import lpm as LPM
            for t, df in idx_prices.items():
                try:
                    bm = BM.compute(df) or {}
                    lf = LPM.lpm_features(df, scaling="value_typical", span=20)
                    out["idx"].append({"ticker": t, "lpm": lf.get("lpm"), "state": lf.get("state"),
                                       "cmf": bm.get("cmf"), "cmf_state": bm.get("cmf_state"),
                                       "adl_rising": bm.get("adl_rising")})
                except Exception:
                    continue
        except Exception as e:
            out["errors"].append(f"idx: {e}")

    # market state — breadth + leadership
    try:
        import warroom.bridge as _br2
        out["market_breadth"] = _br2.breadth(rows)
        out["leaders"] = _br2.leadership(rows, top=8)
    except Exception as e:
        out["market_breadth"], out["leaders"] = {}, []
        out["errors"].append(f"market_state: {e}")

    return out


# ----------------------------------------------------------------------------- design system (CSS)
CSS = """
<style>
.stApp { background:#0d1015; }
section.main > div { padding-top: 1rem; }
.wr-mono { font-family: 'SF Mono','Roboto Mono',ui-monospace,monospace; }
.wr-hero { border:0.5px solid #2a3038; border-radius:14px; padding:16px 20px; background:#12161d; margin-bottom:14px; }
.wr-quad { font-size:26px; font-weight:600; color:#e8edf2; line-height:1; }
.wr-sub { font-size:13px; color:#9aa6b2; }
.wr-lbl { font-size:11px; color:#6b7682; margin:0 0 7px 2px; }
.wr-badge { font-size:11px; font-weight:600; padding:4px 11px; border-radius:8px; white-space:nowrap; }
.b-red{color:#f0a0a0;background:#3a1f22;} .b-grn{color:#9adcc0;background:#15332a;}
.b-amb{color:#e7c389;background:#33280f;} .b-inf{color:#9cc3e7;background:#13283a;}
.wr-tile { background:#161b22; border-radius:8px; padding:10px 12px; }
.wr-tk { font-size:11px; color:#6b7682; margin-bottom:4px; }
.wr-tv { font-size:18px; font-weight:600; color:#e8edf2; line-height:1.1; }
.wr-card { background:#12161d; border:0.5px solid #232a32; border-radius:8px; padding:10px 12px; margin-bottom:8px; }
.wr-why { font-size:12px; color:#9aa6b2; line-height:1.55; }
.wr-why .k { color:#6b7682; }
.wr-row { display:flex; align-items:center; gap:10px; padding:9px 12px; border-bottom:0.5px solid #1d242c; font-size:12px; }
.wr-pill { font-size:12px; padding:4px 10px; border-radius:8px; border:0.5px solid #2a3038; color:#cdd5dd; }
small.note{color:#6b7682;font-size:11px;}
</style>
"""


def _dir_badge(d):
    cls = {"Long": "b-grn", "Short": "b-red", "Watch": "b-amb"}.get(d, "b-inf")
    return f"<span class='wr-badge {cls}'>{d}</span>"


def _causal(r):
    rs = r.get("rs63", 0)
    pos = "above" if r.get("close", 0) >= r.get("lrr", 0) else "below"
    acc = r.get("accumulation", 0)
    inval = ("loses TRR / RS turns negative" if r["_dir"] == "Long"
             else "reclaims TRR / RS turns positive" if r["_dir"] == "Short"
             else "needs formation + RS confirmation")
    return (f"<span class='k'>Why:</span> RS {'+' if rs>=0 else ''}{rs:.0f}% vs SPY, "
            f"{r.get('formation','').lower()} formation, accumulation {acc}. "
            f"<span class='k'>Invalidates:</span> {inval}.")


# ----------------------------------------------------------------------------- renderers
def render_command_center(d, source):
    posture_cls = "b-red" if d["defensive"] else "b-grn"
    st.markdown(
        f"<div class='wr-hero'><div style='display:flex;justify-content:space-between;align-items:flex-start;gap:12px;'>"
        f"<div><div class='wr-sub'>Regime — US equities</div>"
        f"<div style='display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;'>"
        f"<span class='wr-quad'>{d['quad']}</span><span class='wr-sub'>{d['quad_desc']}</span></div></div>"
        f"<span class='wr-badge {posture_cls}'>Posture · {d['posture']}</span></div></div>",
        unsafe_allow_html=True)

    st.markdown("<div class='wr-lbl'>Why — regime drivers</div>", unsafe_allow_html=True)
    tiles = [("Growth z", f"{d['growth_z']:+.2f}σ"), ("Inflation z", f"{d['infl_z']:+.2f}σ"),
             ("Breadth", f"{d['breadth']}%"), ("Crowding", f"{d['regime'].get('crowding','—')}"),
             ("Fragility", f"{d['regime'].get('fragility','—')}"), ("Crash press", f"{d['regime'].get('crash','—')}")]
    cols = st.columns(len(tiles))
    for c, (k, v) in zip(cols, tiles):
        c.markdown(f"<div class='wr-tile'><div class='wr-tk'>{k}</div><div class='wr-tv wr-mono'>{v}</div></div>",
                   unsafe_allow_html=True)

    st.markdown("<div class='wr-lbl' style='margin-top:14px;'>What to do — highest conviction</div>", unsafe_allow_html=True)
    for r in d["conviction"]:
        st.markdown(
            f"<div class='wr-card'><div style='display:flex;align-items:center;gap:8px;margin-bottom:6px;'>"
            f"{_dir_badge(r['_dir'])}<span class='wr-mono' style='font-size:15px;font-weight:600;color:#e8edf2;'>{r['ticker']}</span>"
            f"<span class='wr-sub'>RR {r.get('lrr',0):.1f}–{r.get('trr',0):.1f}</span>"
            f"<span class='wr-mono' style='margin-left:auto;font-weight:600;color:#e8edf2;'>{r.get('score',0):.1f}</span></div>"
            f"<div class='wr-why'>{_causal(r)}</div></div>", unsafe_allow_html=True)
    st.markdown(f"<small class='note'>Data: {source} · risk range = Hedgeye TRADE/TREND/TAIL · engine math verified, edge is prior — not advice.</small>",
                unsafe_allow_html=True)


def render_alpha(d):
    s = d.get("ranking", {}).get("summary", {})
    scanned = d.get("scanned", 0)
    surv = len(d["conviction"]) + len(d["watchlist"])
    cols = st.columns(4)
    for c, (k, v) in zip(cols, [("Scanned", scanned), ("Survived", surv),
                                ("Conviction", len(d["conviction"])), ("Watchlist", len(d["watchlist"]))]):
        c.markdown(f"<div class='wr-tile'><div class='wr-tk'>{k}</div><div class='wr-tv wr-mono'>{v}</div></div>",
                   unsafe_allow_html=True)
    by_t = {t["ticker"]: t for t in d.get("theses", [])}

    st.markdown("<div class='wr-lbl' style='margin-top:14px;'>Highest conviction</div>", unsafe_allow_html=True)
    for r in d["conviction"]:
        th = by_t.get(r["ticker"])
        extra = ""
        if th and th.get("matched_frameworks"):
            fw = ", ".join(th["matched_frameworks"][:4])
            extra = f"<div class='wr-sub' style='margin-top:4px;'>frameworks: {fw}</div>"
        st.markdown(
            f"<div class='wr-card'><div style='display:flex;align-items:center;gap:8px;margin-bottom:6px;'>"
            f"{_dir_badge(r['_dir'])}<span class='wr-mono' style='font-size:15px;font-weight:600;color:#e8edf2;'>{r['ticker']}</span>"
            f"<span class='wr-mono' style='margin-left:auto;font-weight:600;color:#e8edf2;'>{r.get('score',0):.1f}</span></div>"
            f"<div class='wr-why'>{_causal(r)}</div>{extra}</div>", unsafe_allow_html=True)

    st.markdown("<div class='wr-lbl' style='margin-top:6px;'>Watchlist</div>", unsafe_allow_html=True)
    html = "<div class='wr-card' style='padding:0;'>"
    for r in d["watchlist"]:
        html += (f"<div class='wr-row'><span class='wr-mono' style='font-weight:600;min-width:54px;'>{r['ticker']}</span>"
                 f"{_dir_badge(r['_dir'])}<span class='wr-mono' style='color:#9aa6b2;'>{r.get('score',0):.1f}</span>"
                 f"<span style='color:#9aa6b2;'>RS {r.get('rs63',0):+.0f}% · accum {r.get('accumulation',0)}</span></div>")
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def render_bottleneck(d):
    lp = d.get("leopold", {}) or {}
    oom = lp.get("oom_trajectory", {}) or {}
    st.markdown("<div class='wr-lbl'>Aschenbrenner — compute scaling (orders of magnitude)</div>", unsafe_allow_html=True)
    tiles = [("Annual OOMs", oom.get("annual_ooms", "—")),
             ("Annual ×", f"{oom.get('annual_multiplier',0):.0f}×" if oom.get("annual_multiplier") else "—"),
             ("4yr OOMs", oom.get("4yr_cumulative_ooms", "—"))]
    cols = st.columns(len(tiles))
    for c, (k, v) in zip(cols, tiles):
        c.markdown(f"<div class='wr-tile'><div class='wr-tk'>{k}</div><div class='wr-tv wr-mono'>{v}</div></div>",
                   unsafe_allow_html=True)

    st.markdown("<div class='wr-lbl' style='margin-top:14px;'>Bottleneck layers (Citrini / Leopold) — picks by layer</div>",
                unsafe_allow_html=True)
    picks = lp.get("top_picks_by_layer", {}) or {}
    if picks:
        for layer, names in picks.items():
            chips = "".join(
                f"<span class='wr-pill wr-mono' style='margin-right:6px;'>{p.get('ticker')} · {p.get('score',0):.0f}</span>"
                for p in (names or [])) or "<span class='wr-sub'>—</span>"
            st.markdown(f"<div class='wr-card'><div class='wr-sub' style='margin-bottom:6px;'>{layer}</div>{chips}</div>",
                        unsafe_allow_html=True)
    else:
        st.markdown("<small class='note'>No layer picks in this universe.</small>", unsafe_allow_html=True)

    setups = lp.get("asymmetry_setups", []) or []
    if setups:
        st.markdown("<div class='wr-lbl' style='margin-top:6px;'>Asymmetry setups (written-off → recovering)</div>",
                    unsafe_allow_html=True)
        for s in setups[:6]:
            t = s.get("ticker", "?")
            st.markdown(f"<div class='wr-row' style='border:0.5px solid #232a32;border-radius:8px;margin-bottom:6px;'>"
                        f"<span class='wr-mono' style='font-weight:600;'>{t}</span>"
                        f"<span class='wr-sub'>{s.get('label', s.get('rationale',''))[:90]}</span></div>",
                        unsafe_allow_html=True)
    st.markdown("<small class='note'>Moonshot/bottleneck = structural screen, not a return forecast. Tier-4/5 = lottery.</small>",
                unsafe_allow_html=True)


def render_us_gamma(d):
    gex = d.get("gex", {}) or {}
    st.markdown("<div class='wr-lbl'>Dealer gamma — price-proxy GEX (real chain via options feed sharpens this)</div>",
                unsafe_allow_html=True)
    if not gex:
        st.markdown("<small class='note'>GEX engine returned nothing for this universe.</small>", unsafe_allow_html=True); return
    html = "<div class='wr-card' style='padding:0;'>"
    for t, g in list(gex.items())[:8]:
        if not isinstance(g, dict):
            continue
        reg = g.get("regime") or g.get("gamma_regime") or g.get("state") or "—"
        num = ""
        for k in ("net_gex", "gex", "total_gex", "zero_gamma", "gamma_flip", "flip"):
            if isinstance(g.get(k), (int, float)):
                num = f"{k} {g[k]:,.0f}"; break
        html += (f"<div class='wr-row'><span class='wr-mono' style='font-weight:600;min-width:54px;'>{t}</span>"
                 f"<span class='wr-pill'>{reg}</span><span class='wr-sub'>{num}</span></div>")
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)
    st.markdown("<small class='note'>Proxy from price/vol. Real dealer GEX needs an options chain (engines/yfinance_options or a paid feed).</small>",
                unsafe_allow_html=True)


def render_idx_bandar(d):
    idx = d.get("idx", []) or []
    st.markdown("<div class='wr-lbl'>IDX bandar — value-based LPM (fixed) + accumulation. Foreign flow needs Type-F feed.</div>",
                unsafe_allow_html=True)
    if not idx:
        st.markdown("<small class='note'>No IDX data loaded.</small>", unsafe_allow_html=True); return
    html = "<div class='wr-card' style='padding:0;'>"
    for r in idx:
        stt = r.get("state", "n/a")
        cls = {"accumulation": "b-grn", "distribution": "b-red"}.get(stt, "b-amb")
        rising = "A/D ↑" if r.get("adl_rising") else "A/D ↓"
        html += (f"<div class='wr-row'><span class='wr-mono' style='font-weight:600;min-width:78px;'>{r['ticker']}</span>"
                 f"<span class='wr-badge {cls}'>{stt}</span>"
                 f"<span class='wr-sub'>{rising} · CMF {_fmt(r.get('cmf'))} ({r.get('cmf_state','—')})</span></div>")
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)
    st.markdown("<small class='note'>LPM = value-based CLV×Vol×Price (calibrate_lpm.py locks it to BandarMetrics). Foreign Flow / Corr_F / Par_F require IDX broker Type-F data.</small>",
                unsafe_allow_html=True)


def render_market_state(d):
    b = d.get("market_breadth", {}) or {}
    st.markdown("<div class='wr-lbl'>Market state — breadth & leadership</div>", unsafe_allow_html=True)
    tiles = [("% &gt; 50d", b.get("pct_above_50")), ("% &gt; 200d", b.get("pct_above_200")),
             ("Bullish", b.get("bullish")), ("Bearish", b.get("bearish"))]
    cols = st.columns(len(tiles))
    for c, (k, v) in zip(cols, tiles):
        c.markdown(f"<div class='wr-tile'><div class='wr-tk'>{k}</div><div class='wr-tv wr-mono'>{_fmt(v,0)}</div></div>",
                   unsafe_allow_html=True)
    leaders = d.get("leaders", []) or []
    st.markdown("<div class='wr-lbl' style='margin-top:14px;'>RS leadership</div>", unsafe_allow_html=True)
    html = "<div class='wr-card' style='padding:0;'>"
    for r in leaders:
        html += (f"<div class='wr-row'><span class='wr-mono' style='font-weight:600;min-width:54px;'>{r.get('ticker','?')}</span>"
                 f"<span class='wr-sub'>RS {r.get('rs63',0):+.0f}% · {r.get('formation','')}</span></div>")
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


# ----------------------------------------------------------------------------- app
def main():
    st.set_page_config(page_title="War Room v2", layout="wide", initial_sidebar_state="collapsed")
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown("<div style='display:flex;align-items:center;gap:8px;margin-bottom:4px;'>"
                "<span style='font-size:14px;font-weight:600;color:#e8edf2;'>War Room</span>"
                "<span class='wr-sub'>v2 · verified-engine wiring</span></div>", unsafe_allow_html=True)
    with st.spinner("Loading prices + running engines…"):
        prices, source = load_prices(US_UNIVERSE)
        idx_prices, _ = load_prices(IDX_UNIVERSE)
        data = compute(prices, idx_prices)
    if data["errors"]:
        st.caption("engine notes: " + " | ".join(data["errors"]))
    tabs = st.tabs(["Command Center", "Alpha Center", "US Gamma", "IDX Bandar",
                    "Market State", "Bottleneck & Moonshot"])
    with tabs[0]:
        render_command_center(data, source)
    with tabs[1]:
        render_alpha(data)
    with tabs[2]:
        render_us_gamma(data)
    with tabs[3]:
        render_idx_bandar(data)
    with tabs[4]:
        render_market_state(data)
    with tabs[5]:
        render_bottleneck(data)


if __name__ == "__main__":
    main()
