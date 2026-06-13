"""visuals.py — the VISUAL layer (hybrid: v40's proven visuals + v2 real data/engines).

Ports v40's Hedgeye 2×2 quad map (plotly) and adds compact visual primitives (stacked stress
bars, regime chips) so Mission Control reads as a war-room, not a wall of text. The quad position
is computed from the LIVE price universe via forward_macro (market-implied growth/inflation RoC),
so it's real-data-driven, not decorative.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

_QM_CENTER = {"Q1": (-0.5, 0.5), "Q2": (0.5, 0.5), "Q3": (0.5, -0.5), "Q4": (-0.5, -0.5)}
_QM_FILL = {"Q1": "rgba(63,185,80,0.16)", "Q2": "rgba(210,153,34,0.16)",
            "Q3": "rgba(248,81,73,0.15)", "Q4": "rgba(88,166,255,0.15)"}
_QM_NAME = {"Q1": "Q1 · Goldilocks", "Q2": "Q2 · Reflation", "Q3": "Q3 · Stagflation", "Q4": "Q4 · Deflation"}
_NAMES = {"Q1": "Goldilocks", "Q2": "Reflation", "Q3": "Stagflation", "Q4": "Deflation"}


def _norm_series(parts: list[pd.Series]) -> pd.Series | None:
    """Average of rolling-z-normalized component series → a single composite series."""
    zs = []
    for s in parts:
        s = pd.to_numeric(s, errors="coerce").dropna()
        if len(s) < 40:
            continue
        m = s.rolling(60, min_periods=20).mean(); sd = s.rolling(60, min_periods=20).std()
        zs.append(((s - m) / sd.replace(0, np.nan)).clip(-3, 3))
    if not zs:
        return None
    df = pd.concat(zs, axis=1)
    return df.mean(axis=1).dropna()


# Hedgeye reference (external, dated — update via search; app can't fetch paywalled Hedgeye live).
HEDGEYE_REF = {"quad": "Q3", "name": "Stagflation", "next": "Q4 (Nov)",
              "as_of": "Apr 2026", "note": "growth slowing + oil-shock inflation; gold #1 allocation"}


def compute_quad(prices: dict, macro: dict | None = None) -> dict:
    """Hedgeye-style GIP: QUARTERLY quad (climate, ~63d RoC) + MONTHLY quad (weather, ~21d RoC),
    genuinely distinct windows. x=inflation RoC, y=growth RoC. Market-implied (labeled) — shown
    alongside the Hedgeye economic-nowcast reference so divergence is visible, not hidden."""
    macro = macro or {}

    def px(t):
        df = prices.get(t)
        return pd.to_numeric(df["Close"], errors="coerce").dropna() if (df is not None and "Close" in df) else None

    nvda, xlu, smr, gold, oil, tlt = (px(t) for t in ("NVDA", "XLU", "SMR", "XAUUSD", "USOIL", "TLT"))
    # growth proxy series: cyclical-vs-defensive RS + oil demand + curve(FRED) + (−)real-yield level
    g_parts, i_parts = [], []
    if smr is not None and gold is not None:
        g_parts.append((smr / gold))
    if nvda is not None and xlu is not None:
        g_parts.append((nvda / xlu))
    if oil is not None:
        g_parts.append(oil); i_parts.append(oil)
    if gold is not None:
        i_parts.append(gold)
    if macro.get("curve_10y2y", {}).get("series") is not None:
        g_parts.append(macro["curve_10y2y"]["series"])
    if macro.get("real_yield_10y", {}).get("series") is not None:
        i_parts.append(-macro["real_yield_10y"]["series"])   # lower real yield ~ inflation pressure

    G = _norm_series(g_parts); I = _norm_series(i_parts)

    def roc(series, w):
        if series is None or len(series) <= w:
            return 0.0
        d = series.diff(w).dropna()
        if len(d) < 5:
            return 0.0
        sd = d.tail(120).std() or 1.0
        return float(np.tanh((d.iloc[-1] / sd)))          # −1..1, RoC strength

    groc_q, iroc_q = roc(G, 63), roc(I, 63)               # quarterly = climate
    groc_m, iroc_m = roc(G, 21), roc(I, 21)               # monthly  = weather

    def to_quad(g, i):
        return ("Q2" if g >= 0 and i >= 0 else "Q1" if g >= 0 and i < 0
                else "Q3" if g < 0 and i >= 0 else "Q4")
    names = {"Q1": "Goldilocks", "Q2": "Reflation", "Q3": "Stagflation", "Q4": "Deflation"}
    q_quad, m_quad = to_quad(groc_q, iroc_q), to_quad(groc_m, iroc_m)

    # implied-next: monthly (fast) leads the quarterly (slow) → where the climate is heading
    nq = m_quad if m_quad != q_quad else q_quad

    return {"quarterly_quad": q_quad, "quarterly_name": names[q_quad],
            "monthly_quad": m_quad, "monthly_name": names[m_quad],
            "structural_quad": q_quad, "structural_name": names[q_quad],   # back-compat
            "GROC": round(groc_q, 2), "IROC": round(iroc_q, 2),
            "q_pos": (round(iroc_q, 2), round(groc_q, 2)), "m_pos": (round(iroc_m, 2), round(groc_m, 2)),
            "where_it_goes": {"implied_next": nq},
            "hedgeye_ref": HEDGEYE_REF,
            "provenance": "market-implied RoC (forward proxies + FRED where REAL) — differs from Hedgeye GDP/CPI nowcast"}


def quad_map_figure(qe: dict, explanation: str | None = None):
    """2×2 Hedgeye GIP map (x=inflation RoC, y=growth RoC). Highlights the ACTIVE (quarterly) quad,
    plots Quarterly (climate) + Monthly (weather) markers at their real RoC positions (clamped to
    stay readable), and the transition arrow. No more off-screen markers / fake duplicate horizons."""
    import plotly.graph_objects as go

    def _c(v, lo=-0.82, hi=0.82):
        return max(lo, min(hi, float(v)))

    qq = qe.get("quarterly_quad", qe.get("structural_quad", "Q3"))
    mq = qe.get("monthly_quad", qq)
    nq = (qe.get("where_it_goes", {}) or {}).get("implied_next", qq)
    qx, qy = (_c(qe.get("q_pos", (0, 0))[0]), _c(qe.get("q_pos", (0, 0))[1]))
    mx, my = (_c(qe.get("m_pos", (0, 0))[0]), _c(qe.get("m_pos", (0, 0))[1]))

    fig = go.Figure()
    rects = {"Q1": (-1, 0, 0, 1), "Q2": (0, 1, 0, 1), "Q3": (0, 1, -1, 0), "Q4": (-1, 0, -1, 0)}
    for q, (x0, x1, y0, y1) in rects.items():
        active = (q == qq)
        fig.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
                      line={"width": 2.5, "color": "#f0b429"} if active else {"width": 0},
                      fillcolor=(_QM_FILL[q].replace("0.16", "0.42").replace("0.15", "0.40")
                                 if active else _QM_FILL[q]), layer="below")
        _nx, _ny = {"Q1": (-0.5, 0.9), "Q2": (0.5, 0.9), "Q3": (0.5, -0.1), "Q4": (-0.5, -0.1)}[q]
        fig.add_annotation(x=_nx, y=_ny, text=(f"● {_QM_NAME[q]}" if active else _QM_NAME[q]),
                           showarrow=False, font={"size": 12 if active else 10,
                                                  "color": "#f0b429" if active else "#8b949e"})
    fig.add_shape(type="line", x0=0, x1=0, y0=-1, y1=1, line={"color": "#30363d", "width": 1})
    fig.add_shape(type="line", x0=-1, x1=1, y0=0, y1=0, line={"color": "#30363d", "width": 1})

    # transition arrow quarterly → implied-next quad center
    if nq != qq:
        nx, ny = _QM_CENTER.get(nq, (mx, my))
        fig.add_annotation(x=nx * 0.6, y=ny * 0.6, ax=qx, ay=qy, xref="x", yref="y", axref="x", ayref="y",
                           showarrow=True, arrowhead=2, arrowsize=1.3, arrowwidth=2, arrowcolor="#f0b429", opacity=0.8)
    # markers: Quarterly (climate) solid, Monthly (weather) hollow — at real, clamped positions
    fig.add_trace(go.Scatter(x=[qx], y=[qy], mode="markers+text", text=["Quarterly"], textposition="bottom center",
                             textfont={"color": "#e6edf3", "size": 11},
                             marker={"symbol": "circle", "size": 22, "color": "#e6edf3", "line": {"color": "#0d1117", "width": 2}},
                             hovertemplate=f"Quarterly (climate): {qq}<extra></extra>", showlegend=False))
    fig.add_trace(go.Scatter(x=[mx], y=[my], mode="markers+text", text=["Monthly"], textposition="top center",
                             textfont={"color": "#39d0d8", "size": 11},
                             marker={"symbol": "x", "size": 18, "color": "#39d0d8", "line": {"color": "#39d0d8", "width": 2}},
                             hovertemplate=f"Monthly (weather): {mq}<extra></extra>", showlegend=False))
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font={"color": "#c9d1d9", "family": "Inter, sans-serif"},
                      margin={"t": 10, "b": 32, "l": 48, "r": 12}, height=320, showlegend=False,
                      xaxis={"title": {"text": "← Disinflation     Inflation (RoC)     Inflation ↑ →",
                                       "font": {"size": 10, "color": "#8b949e"}}, "range": [-1, 1],
                             "zeroline": False, "showgrid": False, "tickvals": []},
                      yaxis={"title": {"text": "← Growth ↓     Growth (RoC)     Growth ↑ →",
                                       "font": {"size": 10, "color": "#8b949e"}}, "range": [-1, 1],
                             "zeroline": False, "showgrid": False, "tickvals": []})
    return fig


def stress_bar_html(label: str, value: float, provenance: str = "") -> str:
    """A single stacked stress bar (0-100) — replaces the text 'credit_stress: 0.50' lines."""
    v = max(0.0, min(100.0, float(value)))
    col = "#3fb950" if v < 40 else "#d29922" if v < 65 else "#f85149"
    prov = f"<span style='color:#6e7681;font-size:10px'> · {provenance}</span>" if provenance else ""
    return (f"<div style='margin:7px 0'>"
            f"<div style='display:flex;justify-content:space-between;font-size:11px;color:#c9d1d9'>"
            f"<span>{label}{prov}</span><span style='font-weight:700;color:{col}'>{v:.0f}</span></div>"
            f"<div style='background:#21262d;border-radius:4px;height:7px;margin-top:2px'>"
            f"<div style='width:{v}%;background:{col};height:7px;border-radius:4px'></div></div></div>")


def big_metric_html(label: str, value, sub: str = "", color: str = "#e6edf3") -> str:
    return (f"<div style='background:#12161c;border:1px solid rgba(255,255,255,0.06);border-radius:12px;"
            f"padding:14px 16px'><div style='font-size:11px;color:#8b949e;text-transform:uppercase;"
            f"letter-spacing:.5px'>{label}</div>"
            f"<div style='font-size:34px;font-weight:700;color:{color};line-height:1.1;margin-top:2px'>{value}</div>"
            f"<div style='font-size:11px;color:#8b949e;margin-top:2px'>{sub}</div></div>")
