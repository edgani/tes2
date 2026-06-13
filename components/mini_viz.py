"""mini_viz.py — tiny guarded plotly helpers so EVERY new tab has real visuals.
All fall back silently (return False) so callers can print text instead."""
from __future__ import annotations

def hbar(st, title, labels, values, colors=None, height=None, fmt="{:.2f}"):
    try:
        import plotly.graph_objects as go
        vals = [float(v) for v in values]
        cols = colors or ["#3fb950" if v >= 0 else "#f85149" for v in vals]
        fig = go.Figure(go.Bar(x=vals, y=list(labels), orientation="h", marker_color=cols,
                               text=[fmt.format(v) for v in vals], textposition="outside",
                               cliponaxis=False))
        fig.update_layout(title={"text": title, "font": {"size": 12, "color": "#c9d1d9"}},
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(13,17,23,0.5)",
                          font={"color": "#8b949e", "size": 10},
                          height=height or (56 + 26 * len(vals)), showlegend=False,
                          margin={"t": 30, "b": 8, "l": 8, "r": 40},
                          xaxis={"gridcolor": "#21262d", "zerolinecolor": "#30363d"},
                          yaxis={"autorange": "reversed"})
        st.plotly_chart(fig, use_container_width=True)
        return True
    except Exception:
        return False
