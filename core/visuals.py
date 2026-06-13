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


def _rs(a: pd.Series, b: pd.Series, n: int = 63):
    """relative-strength ratio z-ish change (a vs b), as a forward_macro growth input."""
    r = (a / a.shift(n)) / (b / b.shift(n))
    return r.dropna()


def compute_quad(prices: dict, macro: dict | None = None) -> dict:
    """Build the Hedgeye quad (structural/monthly/global) from the LIVE universe + FRED macro.
    Growth inputs: copper/gold (XLU defensive vs SMR/cyclical proxy), SOX (NVDA), small-cap, curve.
    Inflation inputs: commodities (oil, gold), breakeven (real-yield inverse from FRED if present).
    Returns the qe dict the quad map + explainer consume. Honest: market-implied proxy, labeled."""
    from engines.forward_macro import run_forward_macro

    def px(t):
        df = prices.get(t)
        if df is None:
            return None
        return pd.to_numeric(df["Close"], errors="coerce").dropna() if "Close" in df else None

    nvda, xlu, smr, gold, oil, tlt, btc = (px(t) for t in
                                           ("NVDA", "XLU", "SMR", "XAUUSD", "USOIL", "TLT", "BTCUSD"))
    g_in, i_in = {}, {}
    if smr is not None and gold is not None:
        g_in["copper_gold"] = _rs(smr, gold)               # cyclical vs gold = growth proxy
    if nvda is not None and xlu is not None:
        g_in["sox"] = _rs(nvda, xlu)                       # semis vs utility = growth proxy
    if oil is not None:
        g_in["oil"] = oil.pct_change().rolling(20).mean().dropna()
        i_in["commodities"] = oil.pct_change(20).dropna()
    if gold is not None:
        i_in["breakeven"] = gold.pct_change(20).dropna()
    # FRED-real inputs when present
    macro = macro or {}
    if macro.get("curve_10y2y", {}).get("series") is not None:
        g_in["curve_10_2"] = macro["curve_10y2y"]["series"]
    if macro.get("real_yield_10y", {}).get("series") is not None:
        i_in["wage_proxy"] = -macro["real_yield_10y"]["series"]   # inverse real yield ~ infl pressure

    fm = run_forward_macro(g_in, i_in)
    q = fm["forward_quad"]
    groc, iroc = fm["GROC"], fm["IROC"]
    # implied-next: nudge by RoC momentum sign
    nq = q
    if q == "Q3" and groc > -0.1:
        nq = "Q2"
    elif q == "Q2" and iroc < 0:
        nq = "Q1"
    elif q == "Q4" and groc > 0:
        nq = "Q1"
    return {"structural_quad": q, "structural_name": _NAMES[q],
            "monthly_quad": q, "monthly_name": _NAMES[q],
            "global_quad": q, "global_name": _NAMES[q],
            "GROC": groc, "IROC": iroc, "MIFG": fm["MIFG"], "MII": fm["MII"],
            "growth_components": fm["growth_components"], "infl_components": fm["infl_components"],
            "where_it_goes": {"implied_next": nq},
            "provenance": "market-implied (forward_macro) + FRED curve/real-yield where REAL"}


def quad_map_figure(qe: dict, explanation: str | None = None):
    """v40's 2×2 Hedgeye GIP map (x=inflation RoC, y=growth RoC) + transition arrow. Real position
    from GROC/IROC when available."""
    import plotly.graph_objects as go
    sq = qe.get("structural_quad", "Q3"); mq = qe.get("monthly_quad", sq)
    gq = qe.get("global_quad", sq); nq = (qe.get("where_it_goes", {}) or {}).get("implied_next", sq)
    groc, iroc = qe.get("GROC"), qe.get("IROC")

    fig = go.Figure()
    rects = {"Q1": (-1, 0, 0, 1), "Q2": (0, 1, 0, 1), "Q3": (0, 1, -1, 0), "Q4": (-1, 0, -1, 0)}
    for q, (x0, x1, y0, y1) in rects.items():
        fig.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1, line={"width": 0},
                      fillcolor=_QM_FILL[q], layer="below")
        _nx, _ny = {"Q1": (-0.5, 0.88), "Q2": (0.5, 0.88), "Q3": (0.5, -0.12), "Q4": (-0.5, -0.12)}[q]
        fig.add_annotation(x=_nx, y=_ny, text=_QM_NAME[q], showarrow=False, font={"size": 11, "color": "#8b949e"})
    fig.add_shape(type="line", x0=0, x1=0, y0=-1, y1=1, line={"color": "#30363d", "width": 1})
    fig.add_shape(type="line", x0=-1, x1=1, y0=0, y1=0, line={"color": "#30363d", "width": 1})

    # live position from RoC if present, else quad centers
    if groc is not None and iroc is not None and (abs(groc) + abs(iroc)) > 1e-6:
        live = (float(np.clip(iroc, -0.9, 0.9)), float(np.clip(groc, -0.9, 0.9)))
        base = {"S": live, "M": live, "G": _QM_CENTER.get(gq, live)}
    else:
        base = {"S": _QM_CENTER.get(sq, (0.5, -0.5)), "M": _QM_CENTER.get(mq, (0.5, -0.5)),
                "G": _QM_CENTER.get(gq, (0.5, -0.5))}
    offs = {"S": (-0.14, -0.11), "M": (0.14, 0.11), "G": (0.14, -0.11)}
    pos = {k: (base[k][0] + offs[k][0], base[k][1] + offs[k][1]) for k in base}
    if nq != sq:
        nx, ny = _QM_CENTER.get(nq, pos["M"]); sx, sy = pos["S"]
        fig.add_annotation(x=nx, y=ny, ax=sx, ay=sy, xref="x", yref="y", axref="x", ayref="y",
                           showarrow=True, arrowhead=2, arrowsize=1.2, arrowwidth=2,
                           arrowcolor="#f0b429", opacity=0.85)
    for k, sym, col, lbl, q in [("S", "circle-open", "#e6edf3", "Structural", sq),
                                ("M", "x", "#39d0d8", "Monthly", mq),
                                ("G", "diamond-open", "#f0b429", "Global", gq)]:
        px_, py_ = pos[k]
        fig.add_trace(go.Scatter(x=[px_], y=[py_], mode="markers+text", text=[lbl],
                                 textposition="bottom center", textfont={"color": col, "size": 10},
                                 marker={"symbol": sym, "size": 20, "color": col, "line": {"color": col, "width": 3}},
                                 hovertemplate=f"{lbl}: {q}<extra></extra>", showlegend=False))
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font={"color": "#c9d1d9", "family": "Inter, sans-serif"},
                      margin={"t": 8, "b": 30, "l": 46, "r": 10}, height=300, showlegend=False,
                      xaxis={"title": {"text": "← Disinflation   Inflation (RoC)   Inflation ↑ →",
                                       "font": {"size": 10, "color": "#8b949e"}}, "range": [-1, 1],
                             "zeroline": False, "showgrid": False, "tickvals": []},
                      yaxis={"title": {"text": "← Growth ↓   Growth (RoC)   Growth ↑ →",
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
