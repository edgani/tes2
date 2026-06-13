"""causal_map.py — doc-16 'most important visual': directed propagation graph.
Chains are RESEARCHED templates (market_drivers corpus); node intensity = LIVE |z| where a feed
exists, else dim (honest: no fake animation of dead nodes). Guarded — returns False on any failure."""
from __future__ import annotations

CHAINS = [
    ("LIQUIDITY",  ["Fed NetLiq Δ", "Risk appetite", "Tech / Crypto", "Small caps"],
     [("us", "FEDLIQ"), None, None, None]),
    ("OIL SHOCK",  ["Hormuz / geopol", "Oil", "Shipping", "Inflation", "Rates", "Consumer"],
     [("oil", "GEOPOL"), ("oil", "EIA_CRUDE_INV"), None, None, ("us", "TIPS10Y"), None]),
    ("AI CAPEX",   ["AI capex", "Power demand", "Grid / transformers", "Utilities", "Copper"],
     [None, None, None, None, None]),
    ("IDX FLOW",   ["DXY / Fed", "USDIDR", "Foreign flow", "Banks (≈51%)", "IHSG"],
     [("fx", "DXY"), ("idx", "USDIDR"), ("idx", "FFLOW_IDX"), None, None]),
]

def _z(out, key):
    if not key:
        return None
    mkt, sid = key
    for r in ((out.get("drivers") or {}).get(mkt) or {}).get("readings", []) or []:
        if r.get("series") == sid or sid in str(r.get("factor", "")):
            return r.get("reading_z")
    return None

def render_causal_map(st, out, height=340):
    try:
        import plotly.graph_objects as go
        fig = go.Figure()
        crash_hot = float((out.get("crash") or {}).get("pressure", 0) or 0) >= 60
        for row, (name, nodes, keys) in enumerate(CHAINS):
            y = -row
            for i, label in enumerate(nodes):
                z = _z(out, keys[i] if i < len(keys) else None)
                live = z is not None
                mag = min(abs(float(z)), 3.0) if live else 0.0
                col = ("#3fb950" if (z or 0) > 0.3 else "#f85149" if (z or 0) < -0.3 else "#8b949e") if live else "#444c56"
                border = "#f85149" if (crash_hot and i == len(nodes) - 1) else col
                fig.add_trace(go.Scatter(x=[i], y=[y], mode="markers+text",
                    text=[label + (f"<br>z {z:+.2f}" if live else "")], textposition="bottom center",
                    textfont={"size": 9, "color": "#c9d1d9" if live else "#6e7681"},
                    marker={"size": 16 + 7 * mag, "color": col,
                            "line": {"width": 2, "color": border}},
                    hovertemplate=f"{name}: {label}" + (f"<br>z {z:+.2f}" if live else "<br>feed seam") + "<extra></extra>",
                    showlegend=False))
                if i:
                    fig.add_annotation(x=i - 0.18, y=y, ax=i - 0.82, ay=y, xref="x", yref="y",
                                       axref="x", ayref="y", showarrow=True, arrowhead=2,
                                       arrowwidth=1.4, arrowcolor="#58a6ff", opacity=0.7)
            fig.add_annotation(x=-0.55, y=y, text=f"<b>{name}</b>", showarrow=False,
                               font={"size": 10, "color": "#58a6ff"}, xanchor="right")
        fig.update_layout(height=height, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(13,17,23,0.5)",
                          margin={"t": 14, "b": 8, "l": 110, "r": 12},
                          xaxis={"visible": False, "range": [-0.8, 6.0]},
                          yaxis={"visible": False, "range": [-len(CHAINS) + 0.4, 0.7]})
        st.plotly_chart(fig, use_container_width=True)
        st.caption("node size/brightness = live |z| from feeds · dim = feed seam (not faked) · red end-node border = crash pressure ≥60")
        return True
    except Exception:
        return False
