"""dashboard.py — Restored from tes.zip original v40 dashboard"""
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np

BG_DARK = "#0d1117"
CARD_BG = "#161b22"
BORDER = "#30363d"
TEXT_PRIMARY = "#c9d1d9"
TEXT_SECONDARY = "#8b949e"
GREEN = "#3FB950"
RED = "#F85149"
AMBER = "#D29922"
BLUE = "#58A6FF"
PURPLE = "#A371F7"

# Quad colors
QUAD_COLORS = {"Q1": "#3FB950", "Q2": "#D29922", "Q3": "#F85149", "Q4": "#A371F7"}

# Default layout template untuk semua Plotly charts
# NOTE: JANGAN tambahkan 'margin' di sini — setiap fungsi override sendiri
PLOTLY_TEMPLATE = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"color": "#c9d1d9", "family": "Inter, sans-serif", "size": 12},
}

import math

# ═══════════════════════════════════════════════════════════════════
# HELPERS FROM tes.zip ORIGINAL (required by dashboard functions)
# ═══════════════════════════════════════════════════════════════════
class _GipProxy:
    def __init__(self, data):
        self._is_dict = isinstance(data, dict)
        if self._is_dict: self._d = data
        else: self._obj = data
    def __getattr__(self, name):
        if self._is_dict: return self._d.get(name)
        return getattr(self._obj, name, None)


def _safe_float(v):
    if v is None: return None
    try:
        if isinstance(v, pd.Series): v = v.iloc[0] if len(v) > 0 else None
        if v is None: return None
        f = float(v)
        return f if math.isfinite(f) else None
    except: return None


def fp(v):
    try: return f"{float(v):.1%}" if v is not None and math.isfinite(float(v)) else "-"
    except: return "-"


def ff(v, d=2):
    try: return f"{float(v):,.{d}f}" if v is not None and math.isfinite(float(v)) else "-"
    except: return "-"


def sf(v, fmt=".2f"):
    try:
        if v is None: return "—"
        f = float(v)
        if not math.isfinite(f): return "—"
        return format(f, fmt)
    except:
        return "—"


def _price_ret(ticker, prices, days=21):
    if not prices: return None
    s = prices.get(ticker)
    if s is None: return None
    try:
        s = pd.to_numeric(pd.Series(s), errors="coerce").dropna()
    except: return None
    if len(s) < days + 1: return None
    try: return float(s.iloc[-1] / s.iloc[-(days+1)] - 1)
    except: return None


def _quad_color(q):
    return {"Q1":"#3FB950","Q2":"#D29922","Q3":"#F85149","Q4":"#A371F7"}.get(q, "#8B949E")


def _quad_name(q):
    return {"Q1":"Goldilocks","Q2":"Reflation","Q3":"Stagflation","Q4":"Deflation"}.get(q, q)


def _ret_color(r):
    if r is None: return "#8B949E"
    r = float(r)
    if r > 0.03: return "#3FB950"
    if r > 0: return "#2EA043"
    if r > -0.03: return "#F85149"
    return "#DA3633"


def _sparkline_html(series, width=80, height=24, bars=18):
    return ""


# ═══════════════════════════════════════════════════════════════════


def _plotly_risk_range_position(px, lrr, trr, entry, stop, target, height=140):
    """Visual gauge showing where price sits within Risk Range."""
    if not all(v is not None and math.isfinite(float(v)) for v in [px, lrr, trr]):
        return None
    px, lrr, trr = float(px), float(lrr), float(trr)
    fig = go.Figure()

    mid = entry if entry else (lrr + trr) / 2
    tp = target if target else trr

    fig.add_vrect(x0=lrr, x1=mid, fillcolor="rgba(63,185,80,0.12)", line_width=0, layer="below")
    fig.add_vrect(x0=mid, x1=tp, fillcolor="rgba(210,153,34,0.08)", line_width=0, layer="below")
    fig.add_vrect(x0=tp, x1=trr, fillcolor="rgba(248,81,73,0.12)", line_width=0, layer="below")

    fig.add_vline(x=lrr, line_color="#3FB950", line_dash="dash", line_width=1, annotation_text="LRR", annotation_position="top", annotation_font_size=9)
    fig.add_vline(x=trr, line_color="#F85149", line_dash="dash", line_width=1, annotation_text="TRR", annotation_position="top", annotation_font_size=9)
    if entry:
        fig.add_vline(x=entry, line_color="#58A6FF", line_width=2, annotation_text="Entry", annotation_position="bottom", annotation_font_size=9)
    if stop:
        fig.add_vline(x=stop, line_color="#F85149", line_width=2, annotation_text="SL", annotation_position="bottom", annotation_font_size=9)
    if target:
        fig.add_vline(x=target, line_color="#3FB950", line_width=2, annotation_text="TP1", annotation_position="bottom", annotation_font_size=9)

    fig.add_trace(go.Scatter(
        x=[px], y=[0],
        mode="markers+text",
        marker=dict(size=18, color="#E6EDF3", symbol="diamond", line=dict(color="#58A6FF", width=2)),
        text=[f"{px:.2f}"], textposition="top center", textfont=dict(color="#E6EDF3", size=11),
        showlegend=False,
        hovertemplate=f"Price: {px:.2f}<extra></extra>",
    ))

    fig.update_layout(
        height=height, showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#c9d1d9", size=10, family="Inter, sans-serif"),
        margin=dict(t=25, b=20, l=30, r=30),
        xaxis=dict(title="", showgrid=False, zeroline=False, tickfont=dict(size=9, color="#8b949e")),
        yaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
    )
    return fig



def _plotly_greeks_mini(opts, direction="LONG", height=140):
    """Mini bar chart for GEX, Vanna, Charm."""
    if not opts:
        return None
    greeks = {"GEX": opts.get("gex"), "Vanna": opts.get("vanna"), "Charm": opts.get("charm")}
    valid = {k: float(v) for k, v in greeks.items() if v is not None}
    if not valid:
        return None

    colors = []
    for k, v in valid.items():
        if k == "GEX":
            colors.append("#3FB950" if v > 0 else "#F85149")
        elif k == "Vanna":
            colors.append("#58A6FF" if v > 0 else "#D29922")
        else:
            colors.append("#A855F7" if v > 0 else "#F85149")

    fig = go.Figure(go.Bar(
        x=list(valid.keys()), y=list(valid.values()),
        marker_color=colors, text=[f"{v:+.2f}" for v in valid.values()],
        textposition="outside", textfont=dict(size=10, color="#E6EDF3"),
    ))
    fig.update_layout(
        height=height, showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#c9d1d9", size=10),
        margin=dict(t=10, b=10, l=30, r=10),
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="#21262d", zeroline=True, zerolinecolor="#30363d"),
    )
    return fig



def _plotly_expected_move(px, expected_move_pct, target, entry, height=120):
    """Show expected move cone vs target distance."""
    if not expected_move_pct or expected_move_pct <= 0 or not px or px <= 0:
        return None
    em = float(expected_move_pct)
    fig = go.Figure()

    fig.add_hrect(y0=-em*100, y1=em*100, fillcolor="rgba(210,153,34,0.12)", line_width=0, layer="below")
    fig.add_hrect(y0=-em*200, y1=em*200, fillcolor="rgba(248,81,73,0.06)", line_width=0, layer="below")

    if target and entry and entry > 0:
        dist = (target - entry) / entry * 100
        fig.add_hline(y=dist, line_color="#3FB950", line_dash="dash", line_width=2, annotation_text=f"Target +{dist:.1f}%", annotation_position="right")

    fig.add_trace(go.Scatter(x=[0, 1], y=[0, 0], mode="lines", line=dict(color="#E6EDF3", width=3), showlegend=False))

    fig.update_layout(
        height=height, showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#c9d1d9", size=10),
        margin=dict(t=10, b=10, l=40, r=80),
        xaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
        yaxis=dict(title="% Move", showgrid=True, gridcolor="#21262d", tickfont=dict(size=9)),
    )
    return fig


def _plotly_quad_probabilities(snap):
    """Buat horizontal bar chart untuk probabilitas 4 kuadran makro."""
    # Ambil probabilitas dari snap
    probs = {}
    for q in ["Q1", "Q2", "Q3", "Q4"]:
        p = snap.get("markov_v3", {}).get("forecast_1m", {}).get(q, 0) if isinstance(snap.get("markov_v3"), dict) else 0
        if p == 0:
            # Fallback: dari regime_compass data
            p = 25
        probs[q] = p * 100 if p <= 1 else p

    quad_names = {"Q1": "Goldilocks", "Q2": "Reflation", "Q3": "Stagflation", "Q4": "Deflation"}
    labels = [f"{q} — {quad_names.get(q,q)}" for q in ["Q1", "Q2", "Q3", "Q4"]]
    values = [probs.get(q, 25) for q in ["Q1", "Q2", "Q3", "Q4"]]
    colors = [QUAD_COLORS.get(q) for q in ["Q1", "Q2", "Q3", "Q4"]]

    fig = go.Figure()
    for i, (label, val, color) in enumerate(zip(labels, values, colors)):
        fig.add_trace(go.Bar(
            y=[label], x=[val], orientation="h",
            marker={"color": color, "opacity": 0.85},
            text=[f"{val:.0f}%"], textposition="outside",
            textfont={"color": TEXT_PRIMARY, "size": 12},
            hovertemplate=f"<b>%{{y}}</b><br>Probabilitas: %{{x:.1f}}%<extra></extra>",
        ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#c9d1d9", "family": "Inter, sans-serif", "size": 12},
        margin={"t": 40, "b": 30, "l": 40, "r": 20},
        title={"text": "Probabilitas 4 Kuadran Makro", "font": {"size": 14, "color": "#c9d1d9"}},
        xaxis={"title": "Probabilitas (%)", "range": [0, 60], "gridcolor": "#21262d", "tickfont": {"color": "#8b949e"}},
        yaxis={"gridcolor": "#21262d", "tickfont": {"color": "#c9d1d9", "size": 11}},
        barmode="group",
        showlegend=False,
        height=105,
    )
    return fig


def _regime_left_cards(snap, s_vals):
    """HTML card kiri: Structural / Monthly / Markov + dominance bar.
    v43: Fix GIP data access — pakai _GipProxy + getattr (gip adalah object, bukan dict).
    """
    gip_raw = snap.get("gip")
    if gip_raw is not None and not isinstance(gip_raw, dict):
        gip_obj = _GipProxy(gip_raw)
    elif isinstance(gip_raw, dict):
        gip_obj = _GipProxy(gip_raw)
    else:
        gip_obj = _GipProxy({})
    sq = str(getattr(gip_obj, "structural_quad", "Q3") or "Q3").upper()
    mq = str(getattr(gip_obj, "monthly_quad", "Q2") or "Q2").upper()
    sq_conf = float(getattr(gip_obj, "structural_confidence", 0) or 0)

    markov = snap.get("markov_v3") or {}
    if not isinstance(markov, dict):
        markov = {}
    mk_conf = float(markov.get("confidence", 0) or 0)
    mk_kelly = float(markov.get("kelly_fraction", 0.25) or 0.25)
    f1m = markov.get("forecast_1m") or {}
    mk_next_raw = str(markov.get("next_quad") or "").upper()
    # Strip label seperti "Q1_GOLDILOCKS" → "Q1"
    if "_" in mk_next_raw:
        mk_next = mk_next_raw.split("_")[0]
    elif mk_next_raw.startswith("Q") and len(mk_next_raw) >= 2 and mk_next_raw[1] in "1234":
        mk_next = mk_next_raw[:2]
    else:
        mk_next = mk_next_raw
    # Fallback: ambil highest forecast_1m yang bukan current quad
    if not mk_next and isinstance(f1m, dict):
        best_p, best_q = 0, ""
        for q, p in f1m.items():
            q_clean = str(q).upper()[:2]
            if q_clean in ["Q1", "Q2", "Q3", "Q4"] and isinstance(p, (int, float)) and p > best_p and q_clean != sq:
                best_p, best_q = p, q_clean
        mk_next = best_q

    # Quad colors (no names)
    qc = {"Q1": "#3FB950", "Q2": "#D29922", "Q3": "#F85149", "Q4": "#A371F7"}
    sq_c = qc.get(sq, "#8b949e")
    mq_c = qc.get(mq, "#8b949e")
    mk_c = qc.get(mk_next, "#8b949e") if mk_next else "#484f58"

    conf = max(sq_conf, mk_conf)
    conf_pct = int(conf * 100) if conf <= 1 else int(conf)

    # Mini sentiment bar (ganti dominance bar)
    behavioral = snap.get("behavioral_macro", {}) or {}
    bull = behavioral.get("bullish") or 30
    bear = behavioral.get("bearish") or 30
    neut = behavioral.get("neutral") or 40
    tot = bull + bear + neut or 1
    bp, np, bep = bull/tot*100, neut/tot*100, bear/tot*100
    cs = abs(bull - bear) / max(bull + bear, 1) * 100
    cs_c = "#3FB950" if cs < 30 else "#D29922" if cs < 60 else "#F85149"

    # ── TIER1ALPHA signals (merged into this same box — no separate panel) ──
    t1a = snap.get("tier1alpha", {}) or {}
    sigs = t1a.get("signals", {}) if isinstance(t1a, dict) else {}
    def _t1a_color(name, val):
        green = {"gamma_exposure": "Positive", "systematic_flow": "Bullish", "pv_band_rr": "Long", "strategic_allocation": "Risk On"}
        red = {"gamma_exposure": "Negative", "systematic_flow": "Bearish", "pv_band_rr": "Short", "strategic_allocation": "Risk Off"}
        if val == green.get(name): return "#1a7f37"
        if val == red.get(name): return "#cf222e"
        return "#bf8700"
    t1a_labels = {"gamma_exposure": "SPX Gamma", "systematic_flow": "Sys Flow", "pv_band_rr": "PV Band R/R", "strategic_allocation": "Strat Alloc"}
    t1a_html = ""
    if sigs:
        boxes = ""
        for k, lbl in t1a_labels.items():
            v = sigs.get(k, {}).get("value", "Neutral")
            c = _t1a_color(k, v)
            boxes += (f'<div style="flex:1;background:{c};border-radius:4px;padding:4px 2px;text-align:center;margin:0 1px;">'
                      f'<div style="font-size:0.55rem;color:#fff;font-weight:600;opacity:0.9;">{lbl}</div>'
                      f'<div style="font-size:0.72rem;color:#fff;font-weight:800;">{v}</div></div>')
        lv = t1a.get("spx_levels", {}) or {}
        lvl_line = ""
        if lv.get("last_price"):
            lvl_line = (f'<div style="display:flex;justify-content:space-between;font-size:0.66rem;color:#8b949e;margin-bottom:8px;padding:0 2px;">'
                        f'<span>SPX <b style="color:#c9d1d9;">{lv.get("last_price",0):,.0f}</b></span>'
                        f'<span>PV↑ <b style="color:#F85149;">{lv.get("upper_pv_band",0):,.0f}</b></span>'
                        f'<span>PV↓ <b style="color:#3FB950;">{lv.get("lower_pv_band",0):,.0f}</b></span></div>')
        t1a_html = (
            f'<div style="font-size:0.62rem;color:#8b949e;font-weight:700;letter-spacing:0.5px;margin-bottom:4px;">📐 MARKET STRUCTURE (Tier1Alpha)</div>'
            f'<div style="display:flex;gap:0;margin-bottom:6px;">{boxes}</div>'
            f'{lvl_line}'
            f'<div style="height:1px;background:#30363d;margin:3px 0 9px;"></div>'
        )

    # Global Quad as 4th column alongside Structural/Monthly/Markov
    gq = global_q_for_card(snap)
    gq_c = qc.get(gq, "#8b949e")

    html = (
        f'<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 14px;">'
        # ── Tier1Alpha block (merged at top) ──
        f'{t1a_html}'
        # (Quad row removed — Structural/Monthly/Global now live in the Quad Decoder block up top.)
        # Row 2: Conf + Kelly
        f'<div style="font-size:0.72rem;color:#8b949e;text-align:center;margin-bottom:8px;">'
        f'Conf {conf_pct}% · Kelly {int(mk_kelly*100)}%'
        f'</div>'
        # Row 3: Confidence bar
        f'<div style="position:relative;height:9px;background:#21262d;border-radius:3px;overflow:hidden;margin-bottom:8px;">'
        f'<div style="position:absolute;top:0;left:0;height:100%;width:{conf_pct}%;background:{sq_c};border-radius:3px;opacity:0.8;"></div></div>'
        # Row 4: Mini sentiment
        f'<div style="display:flex;height:12px;border-radius:3px;overflow:hidden;margin-bottom:8px;">'
        f'<div style="width:{bp:.0f}%;background:#3FB950;"></div>'
        f'<div style="width:{np:.0f}%;background:#8B949E;"></div>'
        f'<div style="width:{bep:.0f}%;background:#F85149;"></div></div>'
        f'<div style="display:flex;justify-content:space-between;font-size:0.72rem;color:#8b949e;">'
        f'<span>🐂 {bull:.0f}%</span><span>⚖ {neut:.0f}%</span><span>🐻 {bear:.0f}%</span></div>'
        f'<div style="font-size:0.72rem;color:{cs_c};margin-top:6px;text-align:center;">🎰 Casino Score: {cs:.0f}/100</div>'
        f'</div>'
    )
    return html


def global_q_for_card(snap):
    gip = snap.get("gip", {})
    if isinstance(gip, dict):
        return gip.get("global_quad") or gip.get("structural_quad") or snap.get("current_quad", "Q3")
    return getattr(gip, "global_quad", None) or getattr(gip, "structural_quad", None) or "Q3"


def _catalyst_monitor_v2(snap, sq="Q3", mq="Q2", next_q=None):
    """v44: Catalyst detail dengan proyeksi transisi + trigger ekonomi.
    Return: items + transition_projection dict."""
    items = []
    vix_val = (snap.get("vix", 20) or 20) if isinstance(snap, dict) else 20

    # 1. VIX
    if vix_val > 25:
        items.append(("VIX", f"{vix_val:.1f}", "🔴", "Panik", f"VIX>25 = flight to safety → {sq} ke Q3/Q4"))
    elif vix_val > 18:
        items.append(("VIX", f"{vix_val:.1f}", "🟡", "Waspada", f"VIX naik ke 25 = transisi {sq}→Q3"))
    else:
        items.append(("VIX", f"{vix_val:.1f}", "🟢", "Tenang", f"VIX rendah = {sq} stabil"))

    # 2. Yield Curve
    cm = snap.get("crash_meter") or {}
    yc = cm.get("yield_curve_score", 1) if isinstance(cm, dict) else 1
    yc_map = {1: ("🟢", "Normal", f"Yield OK = {sq} stabil"),
              2: ("🟡", "Flat", "Yield flat = monitor inflasi"),
              3: ("🟡", "Flat", "Yield flat = waspada Q3→Q4"),
              4: ("🔴", "Inverted", "⚠️ Yield inverted = Q4 Deflation dalam 6-18 bulan"),
              5: ("🔴", "Deep Inv", "🚨 CRASH SIGNAL — Q4 segera")}
    ec, ed, e_impact = yc_map.get(yc, ("🟢", "Normal", "OK"))
    items.append(("Yield Curve", f"sc{yc}", ec, ed, e_impact))

    # 3. Credit Spread
    cs = cm.get("credit_spread_score", 1) if isinstance(cm, dict) else 1
    cs_map = {1: ("🟢", "Tight", "Credit OK"),
              2: ("🟡", "Wide", "Credit melebar = waspada"),
              3: ("🟡", "Wide", "Credit melebar = Q3 risk"),
              4: ("🔴", "Extreme", "🚨 Credit crash = Q4 segera"),
              5: ("🔴", "Crisis", "🚨🚨 LIQUIDITY CRISIS")}
    ec2, ed2, e2_impact = cs_map.get(cs, ("🟢", "Tight", "OK"))
    items.append(("Credit Spread", f"sc{cs}", ec2, ed2, e2_impact))

    # 4. Inflasi trend
    gip = snap.get("gip") or {}
    trend = str(gip.get("inflation_trend", "") if isinstance(gip, dict) else "").lower()
    if "up" in trend or "naik" in trend:
        items.append(("Inflasi CPI", "—", "🔴", "Naik", f"📈 Inflasi naik = {sq}→Q3 Stagflation risk"))
    elif "down" in trend or "turun" in trend:
        items.append(("Inflasi CPI", "—", "🟢", "Turun", f"📉 Inflasi turun = {sq}→Q1 Goldilocks"))
    else:
        items.append(("Inflasi CPI", "—", "🟡", "Stabil", f"Inflasi flat = {sq} bertahan"))

    # 5. AAII Sentiment
    beh = snap.get("behavioral_macro") or {}
    bull = beh.get("bullish") if isinstance(beh, dict) else None
    bear = beh.get("bearish") if isinstance(beh, dict) else None
    if isinstance(bull, (int, float)) and bull > 50:
        items.append(("AAII Sentiment", f"Bull {bull:.0f}%", "🔴", "Extreme FOMO", "🎯 Contrarian SELL — top signal"))
    elif isinstance(bear, (int, float)) and bear > 45:
        items.append(("AAII Sentiment", f"Bear {bear:.0f}%", "🟢", "Extreme Fear", "🎯 Contrarian BUY — bottom signal"))
    elif isinstance(bull, (int, float)) and isinstance(bear, (int, float)):
        items.append(("AAII Sentiment", f"B{bull:.0f}/N{100-bull-bear:.0f}/B{bear:.0f}", "🟡", "Normal", f"Sentimen netral = {sq} stabil"))
    else:
        items.append(("AAII Sentiment", "—", "🟡", "No data", "Data belum tersedia"))

    # ── Transition Projection ──
    mk = snap.get("markov_v3") or {}
    f1m_local = (mk.get("forecast_1m") or {}) if isinstance(mk, dict) else {}
    proj = {"from": sq, "to": next_q or mq, "days": "", "triggers": []}
    if next_q and next_q != sq:
        # Estimasi hari berdasarkan probabilitas
        p1m_next = float(f1m_local.get(next_q, 0) or 0)
        if p1m_next > 0.3:
            proj["days"] = "~7-14 hari"
        elif p1m_next > 0.2:
            proj["days"] = "~14-30 hari"
        elif p1m_next > 0.1:
            proj["days"] = "~30-60 hari"
        else:
            proj["days"] = ">60 hari"

        # Trigger spesifik berdasarkan arah transisi
        pair = (sq, next_q)
        trigger_map = {
            ("Q3", "Q2"): ["📈 Growth recovery (PMI > 50)", "📉 Inflasi turun (CPI < 3%)", "🟢 VIX turun < 18"],
            ("Q3", "Q1"): ["🚀 GDP surprise +", "📉 CPI turun drastis", "🟢🟢 Risk-on kuat"],
            ("Q3", "Q4"): ["📉 GDP kontraksi", "📉 CPI turun tapi growth juga turun", "🔴 VIX > 30"],
            ("Q2", "Q1"): ["📉 Inflasi turun tanpa growth turun", "🟢 Soft landing confirmed"],
            ("Q2", "Q3"): ["📈 Inflasi spike", "📉 GDP turun", "🔴 Stagflation risk"],
            ("Q1", "Q2"): ["📈 Inflasi naik", "📈 Commodity rally", "🟡 Overheat signal"],
            ("Q1", "Q3"): ["📉 GDP turun tiba-tiba", "📈 Inflasi tetap naik", "🔴🔴 Stagflation shock"],
            ("Q4", "Q1"): ["🟢 Recovery signal", "📈 Leading indicators naik", "🟢 Dovish Fed"],
            ("Q4", "Q3"): ["📈 Inflasi naik saat growth lemah", "🔴🔴 Worst case"],
        }
        proj["triggers"] = trigger_map.get(pair, ["Monitor data ekonomi utama"])
    elif sq == mq:
        proj["days"] = "Stabil"
        proj["triggers"] = [f"{sq} konsisten Structural=Monthly", "Tidak ada transisi jangka pendek"]
    else:
        proj["days"] = "Transisi aktif"
        proj["triggers"] = [f"Structural={sq} vs Monthly={mq} — gap terbuka", f"Next: kemungkinan ke {mq}"]

    return items, proj


def _economic_calendar_mini(sq="Q3", mq="Q2"):
    """v49: Economic calendar mini — event minggu depan yang bisa trigger transisi.
    Hardcoded placeholder (bisa diganti dengan API real-time)."""
    # Event ekonomi penting (placeholder — update sesuai kalender real)
    events = [
        ("📅", "Fed Meeting", "19 Jun", "Rate decision — hawkish = Q3→Q4"),
        ("📊", "CPI Inflasi", "25 Jun", ">3.5% = Q2→Q3, <3% = Q3→Q1"),
        ("🏭", "PMI Manufaktur", "23 Jun", ">50 = Q3→Q2, <47 = Q4 risk"),
        ("💼", "Nonfarm Payroll", "6 Jul", ">250K = Q2 overheat, <100K = Q3"),
        ("🏦", "GDP Q2 Adv", "25 Jul", ">2% = Q3→Q2, negatif = Q4"),
    ]

    # Filter event yang relevan dengan transisi saat ini
    pair = (sq, mq)
    if sq != mq:
        title = f"📰 ECONOMIC CALENDAR — Transisi {sq}→{mq}"
    else:
        title = f"📰 ECONOMIC CALENDAR — Stabil {sq}"

    html = (
        f'<div style="background:#161b22;border:1px solid #58A6FF30;border-radius:5px;padding:14px 16px;margin-top:12px;">'
        f'<div style="font-size:0.68rem;color:#58A6FF;font-weight:600;letter-spacing:0.5px;margin-bottom:1px;">{title}</div>'
    )
    for emoji, name, date, impact in events[:3]:
        html += (
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:6px 0;border-bottom:1px solid #21262d;">'
            f'<div><span style="font-size:0.68rem;color:#c9d1d9;"><b>{name}</b></span>'
            f'<span style="font-size:0.65rem;color:#8b949e;margin-left:3px;">{date}</span></div>'
            f'<div style="font-size:0.65rem;color:#484f58;max-width:110px;text-align:right;">{impact}</div></div>'
        )
    html += (
        f'<div style="font-size:0.55rem;color:#484f58;margin-top:1px;text-align:center;">'
        f'📖 ForexFactory · Event bisa mengubah regime</div></div>'
    )
    return html


def _plotly_regime_dashboard(snap):
    """v43: Split layout — kiri cards, kanan horizontal bar.
    Fix: GIP data access via _GipProxy + getattr (gip adalah object, bukan dict).
    """
    gip_raw = snap.get("gip")
    if gip_raw is not None and not isinstance(gip_raw, dict):
        gip_obj = _GipProxy(gip_raw)
    elif isinstance(gip_raw, dict):
        gip_obj = _GipProxy(gip_raw)
    else:
        gip_obj = _GipProxy({})
    q_probs = getattr(gip_obj, "structural_probs", {}) or {}
    m_probs = getattr(gip_obj, "monthly_probs", {}) or {}
    sq = str(getattr(gip_obj, "structural_quad", "Q3") or "Q3").upper()
    mq = str(getattr(gip_obj, "monthly_quad", "Q2") or "Q2").upper()

    markov = snap.get("markov_v3") or {}
    if not isinstance(markov, dict):
        markov = {}
    mk_kelly = float(markov.get("kelly_fraction", 0.25) or 0.25)
    f1m = markov.get("forecast_1m") or {}
    f3m = markov.get("forecast_3m") or {}
    if not isinstance(f1m, dict): f1m = {}
    if not isinstance(f3m, dict): f3m = {}

    quads = ["Q1", "Q2", "Q3", "Q4"]
    quad_colors = {"Q1": "#3FB950", "Q2": "#D29922", "Q3": "#F85149", "Q4": "#A371F7"}

    s_vals = [float(q_probs.get(q, 0) or 0) for q in quads]
    mo_vals = [float(m_probs.get(q, 0) or 0) for q in quads]
    f1m_vals = [float(f1m.get(q, 0) or 0) for q in quads]

    has_real_data = any(v > 0 for v in s_vals + mo_vals + f1m_vals)

    for arr in [s_vals, mo_vals, f1m_vals]:
        total = sum(arr)
        if total == 0:
            arr[:] = [0.25, 0.25, 0.25, 0.25]
        elif abs(total - 1.0) > 0.01:
            arr[:] = [v / total for v in arr]

    # ── Next Quad Forecast ──
    next_q, next_prob, next_est = None, 0, ""
    for q in quads:
        if q == sq:
            continue
        p1m = float(f1m.get(q, 0) or 0)
        p3m = float(f3m.get(q, 0) or 0)
        p_combined = p1m * 0.6 + p3m * 0.4
        if p_combined > next_prob:
            next_prob = p_combined
            next_q = q
            if p1m > 0.25:
                next_est = f"~{max(7, int(30 * (1 - p1m) + 7))}hari"
            elif p1m > 0.15:
                next_est = f"~{max(14, int(45 * (1 - p1m)))}hari"
            elif p3m > 0.20:
                next_est = f"~{max(30, int(90 * (1 - p3m)))}hari"
            else:
                next_est = ">90hari"

    # ── Horizontal bar Q1-Q4: v49 — 1 bar Structural, Monthly/Forward jadi marker ──
    fig = go.Figure()
    labels = list(reversed(quads))  # Q4 di atas, Q1 di bawah
    label_colors = [quad_colors[q] for q in labels]
    quad_desc = {"Q1": "Growth↑ Inflasi↓", "Q2": "Growth↑ Inflasi↑",
                 "Q3": "Growth↓ Inflasi↑", "Q4": "Growth↓ Inflasi↓"}

    s_rev = list(reversed(s_vals))
    m_rev = list(reversed(mo_vals))
    f_rev = list(reversed(f1m_vals))

    # Hover: semua 3 data dalam 1 tooltip
    hover_texts = []
    for i, q in enumerate(labels):
        desc = quad_desc.get(q, "")
        hover_texts.append(
            f"<b>{q}</b> — {desc}<br>"
            f"📊 Structural: <b>{s_rev[i]*100:.0f}%</b><br>"
            f"📅 Monthly: <b>{m_rev[i]*100:.0f}%</b><br>"
            f"🔮 Forward 1M: <b>{f_rev[i]*100:.0f}%</b><extra></extra>"
        )

    # 1 Bar: Structural (solid, utama)
    fig.add_trace(go.Bar(
        y=labels, x=[v * 100 for v in s_rev], orientation="h",
        name="📊 Structural",
        marker={"color": label_colors, "opacity": 1.0, "line": {"width": 0}},
        text=[f"<b>{v*100:.0f}%</b>" for v in s_rev],
        textposition="outside",
        textfont={"size": 11, "color": "#c9d1d9", "weight": 700},
        hovertemplate=hover_texts,
        width=0.4,
    ))

    # Monthly: garis vertikal tipis di posisi monthly value
    fig.add_trace(go.Scatter(
        y=labels, x=[v * 100 for v in m_rev],
        mode="markers",
        name="📅 Monthly",
        marker={"symbol": "line-ns", "size": 16, "color": "#E6EDF3",
                "line": {"width": 2, "color": "#E6EDF3"}},
        hovertemplate=[f"📅 Monthly {q}: <b>{v*100:.0f}%</b><extra></extra>" for q, v in zip(labels, m_rev)],
    ))

    # Forward 1M: diamond marker di posisi forward value
    fig.add_trace(go.Scatter(
        y=labels, x=[v * 100 for v in f_rev],
        mode="markers",
        name="🔮 Forward 1M",
        marker={"symbol": "diamond", "size": 10, "color": label_colors,
                "line": {"width": 1.5, "color": "#E6EDF3"}},
        hovertemplate=[f"🔮 Forward 1M {q}: <b>{v*100:.0f}%</b><extra></extra>" for q, v in zip(labels, f_rev)],
    ))

    # Annotation transisi
    anno_text = ""
    if next_q:
        anno_text = f"🔮 Next: <b>{sq}→{next_q}</b> · {next_prob:.0%} · {next_est}"

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#c9d1d9", "family": "Inter, sans-serif", "size": 10},
        margin={"t": 28, "b": 20, "l": 35, "r": 50},
        height=180, barmode="relative",
        showlegend=True,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "center", "x": 0.5,
                "font": {"size": 9, "color": "#8b949e"}, "bgcolor": "rgba(0,0,0,0)"},
        yaxis={"tickfont": {"size": 11, "color": "#c9d1d9", "weight": 700},
               "gridcolor": "#21262d"},
        xaxis={"range": [0, 100], "tickformat": ".0f", "ticksuffix": "%",
               "gridcolor": "#21262d", "tickfont": {"size": 9, "color": "#8b949e"}},
        annotations=[{
            "text": anno_text,
            "x": 0.01, "y": -0.12, "xref": "paper", "yref": "paper",
            "showarrow": False,
            "font": {"size": 10, "color": "#58A6FF"},
            "align": "left",
        }] if anno_text else [],
    )
    if not has_real_data:
        fig.add_annotation(
            text="<span style='color:#8b949e;font-size:10px;'>📖 Data regime belum tersedia — equal-weight 25%</span>",
            x=0.5, y=0.5, xref="paper", yref="paper",
            showarrow=False,
        )

    return fig, sq, s_vals, next_q, next_prob, next_est


def _plotly_asset_pulse(snap, prices):
    """Buat horizontal bar chart untuk Asset Pulse 21D."""
    pulse_assets = [
        ("SPY", "US Eq"), ("QQQ", "Tech"), ("IWM", "Small"),
        ("GLD", "Gold"), ("TLT", "Bonds"), ("UUP", "DXY"),
        ("BTC-USD", "BTC"), ("ETH-USD", "ETH"),
    ]
    labels, values, colors = [], [], []
    for t, label in pulse_assets:
        ret = _price_ret(t, prices, 21)
        if ret is not None:
            labels.append(label)
            values.append(ret * 100)
            colors.append(GREEN if ret > 0.03 else "#2EA043" if ret > 0 else "#DA3633" if ret < -0.03 else RED if ret < 0 else AMBER)

    fig = go.Figure(go.Bar(
        y=labels, x=values, orientation="h",
        marker={"color": colors, "opacity": 0.85, "line": {"width": 0}},
        text=[f"{v:+.1f}%" for v in values],
        textposition="outside",
        textfont={"color": TEXT_PRIMARY, "size": 10},
        hovertemplate="<b>%{y}</b><br>Return 21D: %{x:.2f}%<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#c9d1d9", "family": "Inter, sans-serif", "size": 9},
        margin={"t": 10, "b": 8, "l": 28, "r": 40},
        xaxis={"gridcolor": "#21262d", "tickfont": {"size": 7, "color": "#8b949e"},
               "zeroline": True, "zerolinecolor": "#30363d", "zerolinewidth": 1},
        yaxis={"gridcolor": "#21262d", "tickfont": {"size": 8, "color": "#c9d1d9"}},
        showlegend=False, height=62,
    )
    return fig


def _plotly_behavioral_bar(snap):
    """AAII Sentiment — horizontal stacked bar dengan label jelas."""
    behavioral = snap.get("behavioral_macro", {}) or {}
    bullish = behavioral.get("bullish") or 30
    bearish = behavioral.get("bearish") or 30
    neutral = behavioral.get("neutral") or 40
    is_placeholder = (behavioral.get("bullish") is None)
    
    total = bullish + bearish + neutral or 1
    b_pct = bullish / total * 100
    n_pct = neutral / total * 100
    be_pct = bearish / total * 100
    
    # Status
    casino_score = min(100, max(0, (b_pct - 45) * 3))
    if is_placeholder:
        status_text, status_color = "⏳ Menunggu data AAII...", "#484f58"
    elif casino_score <= 30:
        status_text, status_color = "✅ Seimbang", "#3FB950"
    elif casino_score <= 60:
        status_text, status_color = f"⚠️ Waspada — raise {min(50, casino_score * 0.4):.0f}% cash", "#D29922"
    else:
        status_text, status_color = f"🚨 Casino — raise {min(50, casino_score * 0.4):.0f}% cash", "#F85149"

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Bullish", y=["Sentimen"], x=[b_pct], orientation="h",
        marker={"color": "#3FB950", "opacity": 0.9},
        text=[f"🐂 {bullish:.0f}%"], textposition="inside",
        textfont={"color": "#fff", "size": 13, "weight": 700},
        hovertemplate="Bullish: %{x:.0f}%<extra></extra>",
        width=0.5,
    ))
    fig.add_trace(go.Bar(
        name="Neutral", y=["Sentimen"], x=[n_pct], orientation="h",
        marker={"color": "#8B949E", "opacity": 0.7},
        text=[f"⚖ {neutral:.0f}%"], textposition="inside",
        textfont={"color": "#fff", "size": 13, "weight": 700},
        hovertemplate="Neutral: %{x:.0f}%<extra></extra>",
        width=0.5,
    ))
    fig.add_trace(go.Bar(
        name="Bearish", y=["Sentimen"], x=[be_pct], orientation="h",
        marker={"color": "#F85149", "opacity": 0.9},
        text=[f"🐻 {bearish:.0f}%"], textposition="inside",
        textfont={"color": "#fff", "size": 13, "weight": 700},
        hovertemplate="Bearish: %{x:.0f}%<extra></extra>",
        width=0.5,
    ))
    
    # ── Casino Score badge ──
    cs_html = f"🎰 Casino Score: {casino_score:.0f}/100"
    if casino_score <= 30:
        cs_color, cs_label = "#3FB950", "Seimbang"
    elif casino_score <= 60:
        cs_color, cs_label = "#D29922", f"Waspada — raise {min(50, casino_score * 0.4):.0f}% cash"
    else:
        cs_color, cs_label = "#F85149", f"🚨 Casino — raise {min(50, casino_score * 0.4):.0f}% cash"

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#c9d1d9", "family": "Inter, sans-serif", "size": 11},
        margin={"t": 22, "b": 18, "l": 55, "r": 18},
        xaxis={"range": [0, 100], "visible": False},
        yaxis={"visible": True, "tickfont": {"size": 10, "color": "#8b949e", "weight": 600}},
        barmode="stack", showlegend=True,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "center", "x": 0.5,
                "font": {"size": 10, "color": "#8b949e"}},
        height=100,
        annotations=[
            {
                "text": f"<span style='color:{cs_color};font-size:0.72rem;'>🎰 <b>Casino Score: {casino_score:.0f}/100</b> · {cs_label}</span>",
                "x": 0.5, "y": -0.18, "xref": "paper", "yref": "paper",
                "showarrow": False,
            },
            {
                "text": f"<span style='color:{status_color};font-size:0.62rem;'>{status_text}</span>",
                "x": 0.5, "y": -0.32, "xref": "paper", "yref": "paper",
                "showarrow": False,
            },
        ],
    )
    return fig

def _what_if_regime_html(structural_quad, monthly_quad):
    """Penjelasan 'What If' — apa yang terjadi kalau Structural=A tapi Monthly=B.
    Ini yang paling penting buat user ngerti regime makro.
    """
    if structural_quad == monthly_quad:
        # Sama — trend konsisten
        explain_map = {
            "Q1": "🟢 Trend kuat Goldilocks — growth naik, inflasi turun. Saham tech/growth naik paling kencang. Full deploy.",
            "Q2": "🟡 Trend kuat Reflation — growth naik, inflasi naik. Commodity, energy, cyclical naik. Full deploy.",
            "Q3": "🔴 Trend kuat Stagflation — growth turun, inflasi naik. Defensive (gold, bonds, utilities). Reduce equity.",
            "Q4": "🟣 Trend kuat Deflation — growth turun, inflasi turun. Cash/bonds aman. Avoid risky assets.",
        }
        return (
            f'<div style="padding:6px 10px;background:#161b22;border-left:3px solid #58A6FF;border-radius:0 6px 6px 0;margin:6px 0;">'
            f'<div style="font-size:0.65rem;color:#8b949e;">📖 <b>Structural = Monthly</b> = Trend konsisten, tidak ada transisi</div>'
            f'<div style="font-size:0.72rem;color:#c9d1d9;margin-top:2px;">{explain_map.get(structural_quad, "")}</div></div>'
        )

    # Beda — fase transisi
    pair = (structural_quad, monthly_quad)
    explain_map = {
        # Q3 → Q2 (yang paling umum sekarang)
        ("Q3", "Q2"): "🔴🟡 <b>Transisi: Stagflation → Reflation.</b> Growth mulai recovery (Monthly Q2) meski trend panjang masih Stagflation (Structural Q3). Inflasi masih tinggi tapi ekonomi mulai naik. <b>Strategi:</b> Rotate dari defensive ke cyclical. Commodity & energy masih ok, tapi mulai lirik growth.",
        # Q3 → Q1
        ("Q3", "Q1"): "🔴🟢 <b>Transisi cepat: Stagflation → Goldilocks.</b> Ekonomi recovery kencang, inflasi turun drastis. Ini fase paling bullish. <b>Strategi:</b> Full deploy ke saam growth/tech. Jangan sampai ketinggalan.",
        # Q3 → Q4
        ("Q3", "Q4"): "🔴🟣 <b>Bahaya: Stagflation → Deflation.</b> Growth turun, inflasi juga turun. Ini jalan ke crash/recession. <b>Strategi:</b> MAX DEFENSIVE. Cash, bonds, gold. Avoid equity.",
        # Q2 → Q1
        ("Q2", "Q1"): "🟡🟢 <b>Transisi: Reflation → Goldilocks.</b> Inflasi mulai turun, growth tetap kuat. Fase paling bullish. <b>Strategi:</b> Rotate dari commodity/energy ke tech/growth. Full deploy.",
        # Q2 → Q3
        ("Q2", "Q3"): "🟡🔴 <b>Bahaya: Reflation → Stagflation.</b> Growth turun tapi inflasi tetap naik. Stagflation = worst for stocks. <b>Strategi:</b> Defensive. Gold, bonds, utilities. Reduce equity.",
        # Q1 → Q2
        ("Q1", "Q2"): "🟢🟡 <b>Peringatan: Goldilocks → Reflation.</b> Growth tetap kuat tapi inflasi mulai naik lagi. Bisa jadi overheat. <b>Strategi:</b> Mulai rotate ke commodity/energy/infrastructure. Jangan terlalu tech-heavy.",
        # Q1 → Q3
        ("Q1", "Q3"): "🟢🔴 <b>Shock: Goldilocks → Stagflation.</b> Growth tiba-tiba turun, inflasi naik. Stagflation shock. <b>Strategi:</b> EMERGENCY defensive. Cash, gold, bonds. Cut equity exposure.",
        # Q4 → Q1
        ("Q4", "Q1"): "🟣🟢 <b>Recovery: Deflation → Goldilocks.</b> Ekonomi mulai recovery dari bottom. Ini fase awal bull market. <b>Strategi:</b> Accumulate slowly. DCA ke quality stocks. Jangan FOMO.",
        # Q4 → Q3
        ("Q4", "Q3"): "🟣🔴 <b>Bahaya: Deflation → Stagflation.</b> Inflasi naik tapi growth tetap lemah. Worst case. <b>Strategi:</b> MAX defensive. Cash is king.",
        # Q2 → Q4
        ("Q2", "Q4"): "🟡🟣 <b>Crash: Reflation → Deflation.</b> Growth dan inflasi turun bersama. Hard landing. <b>Strategi:</b> EMERGENCY. Cash, bonds, gold. Avoid cyclical.",
        # Q1 → Q4
        ("Q1", "Q4"): "🟢🟣 <b>Crash: Goldilocks → Deflation.</b> Bull market tiba-tiba crash. Black swan event. <b>Strategi:</b> PANIC MODE. Cash only. Wait for bottom.",
    }

    text = explain_map.get(pair, f"<b>Transisi: {structural_quad} → {monthly_quad}</b>. Watch for regime change signals.")
    color = "#D29922"  # default warning
    if "Bahaya" in text or "Crash" in text or "Shock" in text or "EMERGENCY" in text:
        color = "#F85149"
    elif "🟢" in text or "bullish" in text or "Full deploy" in text:
        color = "#3FB950"

    return (
        f'<div style="padding:6px 10px;background:#161b22;border-left:3px solid {color};border-radius:0 6px 6px 0;margin:6px 0;">'
        f'<div style="font-size:0.72rem;color:#c9d1d9;line-height:1.4;">{text}</div></div>'
    )

def _boombust_timeline_html(snap):
    """v50: Balik ke design attachment 4 — simple Boom-Bust Stage + progress bar.
    User ngerti: INCEPTION→ACCELERATION→EUPHORIA→CRISIS→AUCTION + Super Bubble Score.
    Jauh lebih intuitif dari 'SURVIVAL' yang membingungkan."""
    bb = snap.get("boom_bust", {}) or {}
    stage = bb.get("stage", "INCEPTION") if isinstance(bb, dict) else "INCEPTION"
    reflex = snap.get("reflexivity", {}) or {}
    score = reflex.get("super_bubble_score", 0) if isinstance(reflex, dict) else 0

    stages = ["INCEPTION", "ACCELERATION", "EUPHORIA", "CRISIS", "AUCTION"]
    idx = stages.index(stage) if stage in stages else 0

    # Stage warna + penjelasan 1 baris
    stage_info = {
        "INCEPTION":      ("#58A6FF", "💡 Awal tren naik — masih aman untuk masuk"),
        "ACCELERATION":   ("#D29922", "⚠️ Tren memanas — FOMO mulai, hati-hati beli"),
        "EUPHORIA":       ("#F85149", "🚨 Greed ekstrem — JANGAN BELI, siapkan cash"),
        "CRISIS":         ("#F85149", "💥 Panic selling — TUNGGU, jangan tangkap pisau jatuh"),
        "AUCTION":        ("#A371F7", "🔨 Capitulation — mulai pantau entry point"),
    }
    sc, sp = stage_info.get(stage, ("#8b949e", ""))

    # Timeline: dot + garis horizontal
    nodes = []
    for i, s in enumerate(stages):
        is_past = i < idx
        is_active = i == idx
        color = sc if is_active else ("#58A6FF" if is_past else "#30363d")
        size = "12px" if is_active else "9px"
        z = "2" if is_active else "1"
        nodes.append(
            f'<div style="display:flex;flex-direction:column;align-items:center;flex:1;position:relative;">'
            f'<div style="width:{size};height:{size};border-radius:50%;background:{color};'
            f'border:2px solid {"#E6EDF3" if is_active else color};z-index:{z};'
            f'box-shadow:{"0 0 5px " + color if is_active else "none"};"></div>'
            f'<div style="font-size:0.7rem;color:{color};margin-top:2px;font-weight:{"700" if is_active else "500"};">{s}</div></div>'
        )
    # Garis penghubung
    line_html = '<div style="position:absolute;top:4px;left:7%;right:7%;height:2px;background:#30363d;z-index:0;"></div>'

    # Progress bar warna
    bar_pct = min(100, score / 10 * 100)
    bar_color = "#3FB950" if score <= 3 else "#D29922" if score <= 6 else "#F85149"

    return (
        f'<div style="padding:14px 18px;background:#161b22;border:1px solid #30363d;border-radius:8px;">'
        # (inner "Boom-Bust Stage" header removed — the section header above already labels it; was a double header)
        # Timeline
        f'<div style="position:relative;display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px;">'
        f'{line_html}' + ''.join(nodes) + f'</div>'
        # Score + Progress bar
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:3px;">'
        f'<div><span style="font-size:0.9rem;color:{sc};font-weight:800;">Super Bubble Score: {score:.1f}</span><span style="font-size:0.6rem;color:#484f58;">/10</span></div>'
        f'<div style="font-size:0.7rem;color:{bar_color};font-weight:600;">{stage}</div></div>'
        # Progress bar
        f'<div style="height:16px;background:#21262d;border-radius:3px;overflow:hidden;margin-bottom:10px;">'
        f'<div style="width:{bar_pct:.0f}%;height:100%;background:{bar_color};border-radius:3px;transition:width 0.3s;"></div></div>'
        # Penjelasan 1 baris
        f'<div style="font-size:0.7rem;color:#8b949e;background:#0d1117;border-radius:4px;padding:3px 5px;">'
        f'{sp}</div>'
        # Skala
        f'<div style="font-size:0.7rem;color:#484f58;margin-top:3px;display:flex;justify-content:space-between;">'
        f'<span>0</span><span>2</span><span>4</span><span>6</span><span>8</span><span>10</span></div>'
        f'</div>'
    )


def _plotly_deep_technical(snap):
    """Buat subplot grid untuk Deep Technical section."""
    # CRI data
    cri = snap.get("cri_v2_data", {}) or {}
    cri_items = [(t, d.get("cri_v2", 0), d.get("velocity", ""))
                 for t, d in list(cri.items())[:5] if isinstance(d, dict)]

    # Squeeze data
    sq_scan = snap.get("squeeze_scanner", {}) or {}
    sq_items = [(i.get("ticker",""), i.get("squeeze_score",0))
                for i in sq_scan.get("imminent_squeezes", [])[:5] if isinstance(i, dict)]

    # VRP data
    vrp = snap.get("vrp_scanner", {}) or {}
    vrp_items = [(i.get("ticker",""), i.get("vrp_pct",0))
                 for i in vrp.get("high_vrp_sell_premium", [])[:5] if isinstance(i, dict)]

    if not cri_items and not sq_items and not vrp_items:
        return None

    fig = make_subplots(
        rows=1, cols=3,
        subplot_titles=("CRI v2 (Options Velocity)", "Squeeze Score", "VRP (Sell Premium)"),
        specs=[[{"type": "bar"}, {"type": "bar"}, {"type": "bar"}]],
    )

    if cri_items:
        cri_tickers, cri_vals, cri_vels = zip(*cri_items) if cri_items else ([], [], [])
        cri_colors = [RED if v == "EXTREME" else AMBER if v == "HIGH" else GREEN for v in cri_vels]
        fig.add_trace(go.Bar(
            x=list(cri_tickers), y=list(cri_vals),
            marker={"color": cri_colors, "opacity": 0.85},
            hovertemplate="%{x}: %{y:.2f}<extra></extra>",
            showlegend=False,
        ), row=1, col=1)

    if sq_items:
        sq_tickers, sq_vals = zip(*sq_items) if sq_items else ([], [])
        fig.add_trace(go.Bar(
            x=list(sq_tickers), y=list(sq_vals),
            marker={"color": AMBER, "opacity": 0.85},
            hovertemplate="%{x}: %{y:.0f}<extra></extra>",
            showlegend=False,
        ), row=1, col=2)

    if vrp_items:
        vrp_tickers, vrp_vals = zip(*vrp_items) if vrp_items else ([], [])
        fig.add_trace(go.Bar(
            x=list(vrp_tickers), y=list(vrp_vals),
            marker={"color": RED, "opacity": 0.7},
            hovertemplate="%{x}: %{y:.1f}%<extra></extra>",
            showlegend=False,
        ), row=1, col=3)

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#c9d1d9", "family": "Inter, sans-serif", "size": 10},
        margin={"t": 25, "b": 20, "l": 30, "r": 20},
        height=100,
        title={"text": "🔬 Deep Technical", "font": {"size": 11, "color": "#c9d1d9"}},
    )
    fig.add_annotation(
        text="<b>📖 Penjelasan:</b> CRI = options velocity (tinggi = ekstrem). Squeeze = kemungkinan short squeeze. VRP tinggi = jual premium.",
        x=0.5, y=-0.22, xref="paper", yref="paper",
        showarrow=False,
        font={"size": 10, "color": "#8b949e"},
    )
    return fig


def _kpi_grid_html(items):
    """Compact 2x2 HTML KPI grid — replaces plotly gauges (zero overlap, ~half the height).
    Each item: dict(value, label, color, pct, sub, sub2)."""
    cards = []
    for it in items:
        pct = max(0, min(100, float(it.get("pct", 0))))
        cards.append(
            f'<div style="background:#161b22;border:1px solid #30363d;border-radius:7px;padding:5px 9px;">'
            f'<div style="font-size:0.52rem;color:#8b949e;letter-spacing:0.6px;font-weight:700;">{it["label"]}</div>'
            f'<div style="font-size:1.2rem;color:{it["color"]};font-weight:800;line-height:1.15;">{it["value"]}</div>'
            f'<div style="height:4px;background:#21262d;border-radius:2px;overflow:hidden;margin:3px 0 3px;">'
            f'<div style="width:{pct:.0f}%;height:100%;background:{it["color"]};"></div></div>'
            f'<div style="font-size:0.52rem;font-weight:600;color:{it["color"]};">{it["sub"]} '
            f'<span style="color:#484f58;font-weight:400;">· {it["sub2"]}</span></div>'
            f'</div>'
        )
    return (f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">' + "".join(cards) + '</div>')


def _crash_meter_html(snap):
    """Crash Meter — 5 indicators as compact 5-segment HTML bars + total badge.
    Replaces the cramped plotly gauges (titles+numbers+annotation no longer collide)."""
    cm = snap.get("crash_meter", {}) if isinstance(snap.get("crash_meter"), dict) else {}
    inds = [("Yield Curve", "yield_curve_score"), ("Credit Spread", "credit_spread_score"),
            ("CAPE", "cape_score"), ("VIX %ile", "vix_percentile_score"), ("Margin Debt", "margin_score")]
    cells = []
    total = 0
    for name, key in inds:
        val = int(round(_safe_float(cm.get(key, 1)) or 1))
        val = max(0, min(5, val))
        total += val
        c = GREEN if val <= 1 else AMBER if val <= 2 else RED
        segs = "".join(
            f'<div style="flex:1;height:9px;border-radius:1px;background:{c if i < val else "#21262d"};"></div>'
            for i in range(5))
        cells.append(
            f'<div style="flex:1;text-align:center;min-width:0;">'
            f'<div style="font-size:0.56rem;color:#8b949e;line-height:1.1;min-height:2em;display:flex;'
            f'align-items:center;justify-content:center;">{name}</div>'
            f'<div style="display:flex;gap:2px;margin:2px 1px;">{segs}</div>'
            f'<div style="font-size:0.68rem;color:{c};font-weight:800;">{val}</div></div>'
        )
    oc = GREEN if total <= 7 else AMBER if total <= 12 else RED
    ol = "AMAN" if total <= 7 else "WASPADA" if total <= 12 else "KRITIS"
    return (
        f'<div style="background:#161b22;border:1px solid #30363d;border-radius:7px;padding:6px 8px;">'
        f'<div style="display:flex;gap:6px;align-items:flex-end;">' + "".join(cells) + '</div>'
        f'<div style="font-size:0.56rem;color:#8b949e;text-align:center;margin-top:4px;border-top:1px solid #21262d;padding-top:4px;">'
        f'🚨 <b>{total}/25 <span style="color:{oc};">{ol}</span></b> '
        f'<span style="color:#484f58;">· 1-2=AMAN · 3=WASPADA · 4-5=KRITIS</span></div>'
        f'</div>'
    )


def render(snap, prices=None, vix_now=20.0):
    """Macro Dashboard v40 — Full-height two-column layout. No empty gaps."""
    st.markdown("<div style='height:2px'></div>", unsafe_allow_html=True)

    # Extract mq safely
    gip_raw = snap.get("gip")
    if isinstance(gip_raw, dict):
        mq = gip_raw.get("monthly_quad", "Q2")
    elif gip_raw is not None:
        mq = getattr(gip_raw, "monthly_quad", "Q2")
    else:
        mq = "Q2"

    _, sq_current, s_vals, next_q, next_prob, next_est = _plotly_regime_dashboard(snap)
    catalysts, proj = _catalyst_monitor_v2(snap, sq=sq_current, mq=mq, next_q=next_q)

    r1_left, r1_right = st.columns([1, 1])

    # ═══════════════════════════════════════════════════════════
    # LEFT COLUMN: Regime + Proyeksi + Catalyst + Calendar (stretch to bottom)
    # ═══════════════════════════════════════════════════════════
    with r1_left:
        st.markdown(_regime_left_cards(snap, s_vals), unsafe_allow_html=True)

        # Proyeksi Transisi block removed — superseded by the Quad Decoder + Quad Map panel
        # (lower on the dashboard), which shows from→implied quad, ripeness stage, and triggers.

        # Block A: Asset Pulse merged directly under Market Structure (Tier1Alpha).
        # (Catalyst moved up into the Quad Decoder block; Economic Calendar moved to the right column.)
        st.markdown("<div style='font-size:0.65rem;color:#3FB950;font-weight:700;margin:8px 0 4px;'>⚡ ASSET PULSE (21D) — gerak aset 21 hari</div>", unsafe_allow_html=True)
        st.plotly_chart(_plotly_asset_pulse(snap, prices), width='stretch', config={"displayModeBar": False}, key="ap_v54")

        # Crash Meter moved HERE (below Asset Pulse, left col) — full width, no longer cramped/cut in right col
        st.markdown("<div style='font-size:0.62rem;color:#F85149;font-weight:700;margin:8px 0 4px;'>🚨 CRASH METER</div>", unsafe_allow_html=True)
        st.markdown(_crash_meter_html(snap), unsafe_allow_html=True)


    # ═══════════════════════════════════════════════════════════
    # RIGHT COLUMN: Gauges → Crash Meter → Bubble → Asset Pulse
    # ═══════════════════════════════════════════════════════════
    with r1_right:
        _mk = snap.get("markov_v3")
        markov_local = _mk if isinstance(_mk, dict) else {}
        health = snap.get("health", {}) or {}
        health_score = float(health.get("composite_score", 50)) if isinstance(health, dict) else 50
        kelly = float(markov_local.get("kelly_fraction", 0.25) or 0.25)
        n_alerts = len((snap.get("yves_v2", {}) or {}).get("alerts", [])) if isinstance(snap.get("yves_v2"), dict) else 0

        # ── Risk KPIs (HTML, compact, no overlap) — replaces plotly gauges ──
        vc = GREEN if vix_now < 18 else AMBER if vix_now < 25 else RED
        vix_cond = "Tenang" if vix_now < 18 else "Waspada" if vix_now < 25 else "Panik"
        hc = GREEN if health_score >= 70 else AMBER if health_score >= 50 else RED
        h_cond = "Kuat" if health_score >= 70 else "Sedang" if health_score >= 50 else "Lemah"
        kc = GREEN if kelly >= 0.5 else AMBER if kelly >= 0.25 else RED
        k_cond = "Agresif" if kelly >= 0.5 else "Normal" if kelly >= 0.25 else "Konservatif"
        ac = RED if n_alerts > 2 else AMBER if n_alerts > 0 else GREEN
        a_cond = "Aman" if n_alerts == 0 else "Waspada" if n_alerts <= 2 else "Bahaya"
        st.markdown(_kpi_grid_html([
            dict(value=f"{vix_now:.0f}", label="VIX", color=vc, pct=vix_now / 40 * 100, sub=vix_cond, sub2="Volatilitas"),
            dict(value=f"{health_score:.0f}%", label="HEALTH", color=hc, pct=health_score, sub=h_cond, sub2="Kesehatan Pasar"),
            dict(value=f"{kelly * 100:.0f}%", label="KELLY", color=kc, pct=kelly * 100, sub=k_cond, sub2="Taruhan Optimal"),
            dict(value=f"{n_alerts}", label="ALERTS", color=ac, pct=n_alerts * 10, sub=a_cond, sub2="Behavioral"),
        ]), unsafe_allow_html=True)

        # ── Boom-Bust (Crash Meter moved to left col below Asset Pulse for room) ──
        st.markdown("<div style='font-size:0.62rem;color:#A371F7;font-weight:700;margin:6px 0 3px;'>🌀 BOOM-BUST / SURVIVAL</div>", unsafe_allow_html=True)
        st.markdown(_boombust_timeline_html(snap), unsafe_allow_html=True)
        st.caption("Gauge atas = VIX/Health/Kelly/Alerts · Crash Meter (kiri) = 5 gauge tekanan pasar · "
                   "Boom-Bust = posisi siklus + Super Bubble Score. Semua = **risiko sistemik**.")
