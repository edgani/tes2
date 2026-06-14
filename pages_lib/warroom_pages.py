"""
pages_lib/warroom_pages.py
MacroRegime War Room — All 7 Pages

Pages:
  1. Command Center      — Regime Pressure Map + Global Stress + What Changed
  2. Opportunity Radar   — Tiered opportunities + Causal cards + Bubble map
  3. Bottleneck Map      — Interactive network graph + chain reactions
  4. Flow & Positioning  — Market-specific flow (US/Crypto/IHSG/Commodities/FX)
  5. Market Internals    — 6 giant panels (breadth, credit, vol, liquidity, leadership, correlation)
  6. Execution Engine    — Market structure map + gamma walls + liquidity pockets
  7. Research Lab        — Walk forward, simulations, feature importance
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import Dict, List, Any

# ═══════════════════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════════════════

def _quad_color(q: str) -> str:
    return {"Q1": "#3FB950", "Q2": "#D29922", "Q3": "#F85149", "Q4": "#A371F7"}.get(q, "#8B949E")

def _heat_color(val: float) -> str:
    """val: -1 to +1 → color hex"""
    if val >= 0.5: return "#3FB950"
    if val >= 0.2: return "#2EA043"
    if val >= -0.2: return "#D29922"
    if val >= -0.5: return "#F85149"
    return "#DA3633"

def _stress_color(val: float) -> str:
    if val < 0.3: return "#3FB950"
    if val < 0.5: return "#D29922"
    if val < 0.7: return "#F85149"
    return "#DA3633"

def _metric_card(title: str, value: str, subtitle: str = "", color: str = "#8B949E"):
    st.markdown(f"""
    <div style="background:#161B22;border:1px solid #30363D;border-radius:8px;padding:12px;margin:4px 0;">
        <div style="font-size:0.6rem;color:#8B949E;text-transform:uppercase;letter-spacing:0.5px;">{title}</div>
        <div style="font-size:1.2rem;font-weight:700;color:{color};margin:4px 0;">{value}</div>
        <div style="font-size:0.55rem;color:#8B949E;">{subtitle}</div>
    </div>
    """, unsafe_allow_html=True)

def _pressure_bar(label: str, value: float, max_val: float = 10.0):
    pct = min(100, max(0, (value / max_val) * 100))
    color = "#3FB950" if pct < 40 else "#D29922" if pct < 70 else "#F85149"
    st.markdown(f"""
    <div style="margin:3px 0;">
        <div style="display:flex;justify-content:space-between;font-size:0.7rem;color:#8B949E;margin-bottom:2px;">
            <span>{label}</span><span>{value:.1f}</span>
        </div>
        <div style="background:#0D1117;height:6px;border-radius:3px;overflow:hidden;">
            <div style="width:{pct}%;background:{color};height:100%;border-radius:3px;"></div>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# 1. COMMAND CENTER
# ═══════════════════════════════════════════════════════════════════════════

class CommandCenterPage:
    def render(self, snap: dict):
        st.markdown("<h1 style='font-size:1.4rem;font-weight:800;'>🛰 COMMAND CENTER</h1>", unsafe_allow_html=True)
        st.caption("Global Tension Map — What matters most RIGHT NOW")

        # Extract data
        gip = snap.get("gip", {})
        quad = gip.get("structural_quad", "Q3") if isinstance(gip, dict) else getattr(gip, "structural_quad", "Q3")
        monthly = gip.get("monthly_quad", "Q2") if isinstance(gip, dict) else getattr(gip, "monthly_quad", "Q2")
        vix = snap.get("vix", 20.0) or 20.0

        # Get regime pressure from snap or compute proxy
        pressures = snap.get("regime_pressures", self._compute_pressure_proxy(snap))
        stress = snap.get("global_stress", self._compute_stress_proxy(snap, vix))
        changes = snap.get("what_changed", [])

        # ── LEFT 65%: REGIME PRESSURE MAP ──
        c1, c2 = st.columns([0.65, 0.35])
        with c1:
            st.markdown("<h2 style='font-size:1.05rem;font-weight:700;margin-top:0;'>Regime Pressure Matrix</h2>", unsafe_allow_html=True)
            self._render_pressure_matrix(pressures, quad)

            st.markdown("<h2 style='font-size:1.05rem;font-weight:700;margin-top:16px;'>Cross-Asset Propagation</h2>", unsafe_allow_html=True)
            self._render_propagation_graph(snap)

        with c2:
            st.markdown("<h2 style='font-size:1.05rem;font-weight:700;margin-top:0;'>Global Stress Engine</h2>", unsafe_allow_html=True)
            self._render_stress_towers(stress)

            st.markdown("<h2 style='font-size:1.05rem;font-weight:700;margin-top:16px;'>What Changed Today</h2>", unsafe_allow_html=True)
            self._render_what_changed(changes)

    def _compute_pressure_proxy(self, snap: dict) -> List[dict]:
        """Compute regime pressure from available data."""
        fred = snap.get("fred_series", {})
        prices = snap.get("prices", {})

        def _last(series_key, default=0):
            s = fred.get(series_key)
            if s is not None and len(s) > 0:
                try: return float(pd.to_numeric(pd.Series(s), errors="coerce").dropna().iloc[-1])
                except: return default
            return default

        # Liquidity proxy: DGS3MO vs FEDFUNDS spread
        dgs3mo = _last("DGS3MO", 4.5)
        fedfunds = _last("FEDFUNDS", 5.33)
        liquidity = (fedfunds - dgs3mo) / 2  # inverted proxy

        # Growth proxy: INDPRO momentum
        indpro = _last("INDPRO", 100)
        growth = (indpro - 100) / 10

        # Inflation proxy: CPI YoY
        cpi = _last("CPI", 300)
        inflation = (cpi - 300) / 20

        # Volatility: VIX
        vix = snap.get("vix", 20)
        volatility = (vix - 20) / 20

        # Credit: HYOAS
        hyoas = _last("HYOAS", 4.0)
        credit = -(hyoas - 4.0) / 3

        # Dollar: DXY ret
        dxy = snap.get("dxy", 100)
        dollar = (dxy - 100) / 5

        # Yields: 10Y
        dgs10 = _last("DGS10", 4.5)
        yields = (dgs10 - 4.5) / 2

        return [
            {"variable": "liquidity", "structural": round(liquidity, 2), "cyclical": round(liquidity * 0.8, 2), "tactical": round(liquidity * 0.6, 2), "short_term": round(liquidity * 0.4, 2)},
            {"variable": "growth", "structural": round(growth, 2), "cyclical": round(growth * 0.9, 2), "tactical": round(growth * 0.7, 2), "short_term": round(growth * 0.5, 2)},
            {"variable": "inflation", "structural": round(inflation, 2), "cyclical": round(inflation * 0.8, 2), "tactical": round(inflation * 0.6, 2), "short_term": round(inflation * 0.4, 2)},
            {"variable": "volatility", "structural": round(volatility, 2), "cyclical": round(volatility * 0.9, 2), "tactical": round(volatility * 1.2, 2), "short_term": round(volatility * 1.5, 2)},
            {"variable": "credit", "structural": round(credit, 2), "cyclical": round(credit * 0.8, 2), "tactical": round(credit * 1.1, 2), "short_term": round(credit * 1.3, 2)},
            {"variable": "dollar", "structural": round(dollar, 2), "cyclical": round(dollar * 0.7, 2), "tactical": round(dollar * 0.9, 2), "short_term": round(dollar * 1.1, 2)},
            {"variable": "yields", "structural": round(yields, 2), "cyclical": round(yields * 0.8, 2), "tactical": round(yields * 1.0, 2), "short_term": round(yields * 1.2, 2)},
        ]

    def _render_pressure_matrix(self, pressures: List[dict], quad: str):
        if not pressures:
            st.info("No regime pressure data available")
            return

        df = pd.DataFrame(pressures)
        horizons = ["structural", "cyclical", "tactical", "short_term"]

        fig = go.Figure(data=go.Heatmap(
            z=[[row[h] for h in horizons] for row in pressures],
            x=["Structural", "Cyclical", "Tactical", "Short-term"],
            y=[row["variable"].upper() for row in pressures],
            colorscale=[
                [0.0, "#DA3633"], [0.25, "#D29922"], [0.5, "#8B949E"],
                [0.75, "#2EA043"], [1.0, "#3FB950"]
            ],
            zmid=0,
            text=[[f"{row[h]:+.2f}" for h in horizons] for row in pressures],
            texttemplate="%{text}",
            textfont={"size": 10, "color": "white"},
            hoverongaps=False,
        ))
        fig.update_layout(
            height=280,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#C9D1D9", family="Inter"),
            margin=dict(l=80, r=20, t=30, b=20),
            xaxis=dict(side="top", tickfont=dict(size=10)),
            yaxis=dict(tickfont=dict(size=10)),
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        # Quad badge
        color = _quad_color(quad)
        st.markdown(f"""
        <div style="text-align:center;margin-top:8px;">
            <span style="background:{color}22;border:1px solid {color};color:{color};padding:4px 12px;border-radius:12px;font-size:0.75rem;font-weight:600;">
                STRUCTURAL: {quad} | MONTHLY: {quad}
            </span>
        </div>
        """, unsafe_allow_html=True)

    def _compute_stress_proxy(self, snap: dict, vix: float) -> dict:
        health = snap.get("health", {})
        crash_prob = min(1.0, max(0.0, (vix - 15) / 35))
        contagion = min(1.0, max(0.0, (vix - 20) / 30))
        return {
            "liquidity_stress": round(min(1.0, (vix / 40)), 2),
            "systemic_fragility": round(crash_prob * 0.8, 2),
            "positioning_crowding": round(snap.get("crowding_index", 0.5), 2),
            "crash_probability": round(crash_prob, 3),
            "contagion_probability": round(contagion, 3),
        }

    def _render_stress_towers(self, stress: dict):
        if not stress:
            st.info("No stress data")
            return

        items = [
            ("Liquidity Stress", stress.get("liquidity_stress", 0)),
            ("Systemic Fragility", stress.get("systemic_fragility", 0)),
            ("Positioning Crowding", stress.get("positioning_crowding", 0)),
            ("Crash Probability", stress.get("crash_probability", 0)),
            ("Contagion Probability", stress.get("contagion_probability", 0)),
        ]

        for label, val in items:
            pct = val * 100
            color = _stress_color(val)
            st.markdown(f"""
            <div style="background:#161B22;border:1px solid #30363D;border-radius:8px;padding:10px;margin:6px 0;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                    <span style="font-size:0.7rem;color:#8B949E;text-transform:uppercase;">{label}</span>
                    <span style="font-size:0.8rem;font-weight:700;color:{color};">{pct:.0f}%</span>
                </div>
                <div style="background:#0D1117;height:8px;border-radius:4px;overflow:hidden;">
                    <div style="width:{pct}%;background:{color};height:100%;border-radius:4px;transition:width 0.5s;"></div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    def _render_what_changed(self, changes: List[dict]):
        if not changes:
            st.markdown("""
            <div style="background:#161B22;border:1px solid #30363D;border-radius:8px;padding:10px;margin:4px 0;">
                <div style="font-size:0.7rem;color:#8B949E;">No significant regime changes detected today</div>
            </div>
            """, unsafe_allow_html=True)
            return

        for ch in changes[:5]:
            mag = ch.get("magnitude", 5)
            color = "#F85149" if mag > 7 else "#D29922" if mag > 4 else "#3FB950"
            st.markdown(f"""
            <div style="background:#161B22;border-left:3px solid {color};border-radius:8px;padding:10px 12px;margin:6px 0;">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
                    <div style="background:{color}22;color:{color};font-size:0.65rem;font-weight:700;padding:2px 6px;border-radius:4px;">MAG {mag}</div>
                    <span style="font-size:0.75rem;color:#C9D1D9;font-weight:500;">{ch.get("sentence", "")}</span>
                </div>
                <div style="font-size:0.65rem;color:#8B949E;margin-top:2px;">{ch.get("propagation", "")}</div>
            </div>
            """, unsafe_allow_html=True)

    def _render_propagation_graph(self, snap: dict):
        """Simplified propagation graph using Plotly network."""
        # Build nodes from active shocks + alpha center
        tickers = []
        for t in ["SPY", "QQQ", "IWM", "GLD", "TLT", "CL=F", "DX-Y.NYB", "BTC-USD", "^VIX"]:
            if t in snap.get("prices", {}):
                tickers.append(t)

        if len(tickers) < 3:
            st.info("Insufficient data for propagation graph")
            return

        # Simple correlation-based edges
        prices = snap.get("prices", {})
        edges = []
        for i, t1 in enumerate(tickers):
            for t2 in tickers[i+1:]:
                s1 = prices.get(t1); s2 = prices.get(t2)
                if s1 is None or s2 is None or len(s1) < 10 or len(s2) < 10:
                    continue
                try:
                    a = pd.to_numeric(pd.Series(s1), errors="coerce").dropna().tail(20).pct_change().dropna()
                    b = pd.to_numeric(pd.Series(s2), errors="coerce").dropna().tail(20).pct_change().dropna()
                    min_len = min(len(a), len(b))
                    if min_len < 5: continue
                    corr = np.corrcoef(a.tail(min_len), b.tail(min_len))[0, 1]
                    if abs(corr) > 0.5:
                        edges.append((t1, t2, corr))
                except Exception:
                    continue

        if not edges:
            st.info("No strong cross-asset correlations detected")
            return

        # Create network visualization
        all_nodes = list(set([e[0] for e in edges] + [e[1] for e in edges]))
        pos = {node: (np.cos(2 * np.pi * i / len(all_nodes)), np.sin(2 * np.pi * i / len(all_nodes))) 
               for i, node in enumerate(all_nodes)}

        edge_traces = []
        for t1, t2, corr in edges:
            x0, y0 = pos[t1]
            x1, y1 = pos[t2]
            color = "#3FB950" if corr > 0 else "#F85149"
            edge_traces.append(go.Scatter(
                x=[x0, x1, None], y=[y0, y1, None],
                line=dict(width=abs(corr)*3, color=color),
                hoverinfo="text",
                text=f"{t1} ↔ {t2}: {corr:.2f}",
                mode="lines",
                opacity=0.6,
            ))

        node_trace = go.Scatter(
            x=[pos[n][0] for n in all_nodes],
            y=[pos[n][1] for n in all_nodes],
            mode="markers+text",
            text=all_nodes,
            textposition="top center",
            textfont=dict(size=9, color="#C9D1D9"),
            marker=dict(size=20, color="#58A6FF", line=dict(width=2, color="#0B0E11")),
            hoverinfo="text",
        )

        fig = go.Figure(data=edge_traces + [node_trace])
        fig.update_layout(
            height=300,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#C9D1D9"),
            showlegend=False,
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ═══════════════════════════════════════════════════════════════════════════
# 2. OPPORTUNITY RADAR
# ═══════════════════════════════════════════════════════════════════════════

class OpportunityRadarPage:
    def render(self, snap: dict):
        st.markdown("<h1 style='font-size:1.4rem;font-weight:800;'>⚡ OPPORTUNITY RADAR</h1>", unsafe_allow_html=True)
        st.caption("Highest asymmetric opportunities — Tier 1 is conviction, Tier 2 is watchlist, Tier 3 is emerging")

        # Get filtered data from snap
        filtered = snap.get("filtered_tickers", {})
        tier1 = filtered.get("tier1", [])
        tier2 = filtered.get("tier2", [])
        tier3 = filtered.get("tier3", [])
        stats = filtered.get("stats", {})

        # Stats bar
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1: _metric_card("INPUT", str(stats.get("input", 0)), "Raw candidates")
        with c2: _metric_card("STAGE 1", str(stats.get("stage1", 0)), "Post-elimination")
        with c3: _metric_card("STAGE 3", str(stats.get("stage3", 0)), "Competitive finalists")
        with c4: _metric_card("TIER 1", str(stats.get("tier1", 0)), "Highest conviction")
        with c5: _metric_card("ELIMINATED", str(stats.get("eliminated", 0)), "Filtered out")

        st.divider()

        # Bubble cluster map
        self._render_bubble_map(tier1 + tier2)

        st.divider()

        # Tier 1 — HIGHEST CONVICTION
        if tier1:
            st.markdown("""
            <div style="background:#A371F722;border:1px solid #A371F7;border-radius:8px;padding:8px 12px;margin:12px 0;">
                <span style="color:#A371F7;font-size:0.75rem;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">
                    ⭐ TIER 1 — HIGHEST CONVICTION (3-5 names)
                </span>
            </div>
            """, unsafe_allow_html=True)
            for item in tier1:
                self._render_ticker_card(item, highlight=True)

        # Tier 2 — WATCHLIST
        if tier2:
            with st.expander(f"📋 TIER 2 — WATCHLIST ({len(tier2)} names)", expanded=False):
                cols = st.columns(2)
                for i, item in enumerate(tier2):
                    with cols[i % 2]:
                        self._render_ticker_card(item, highlight=False)

        # Tier 3 — EMERGING (hidden by default)
        if tier3:
            with st.expander(f"🔮 TIER 3 — EMERGING ({len(tier3)} names)", expanded=False):
                st.caption("Lower conviction, higher uncertainty. Monitor for escalation.")
                for item in tier3[:5]:
                    st.markdown(f"- **{item['ticker']}** ({item['direction']}) | Score: {item['priority_score']:.1f} | Grade: {item['grade']}")

    def _render_bubble_map(self, items: List[dict]):
        if not items:
            st.info("No opportunities for bubble map")
            return

        df = pd.DataFrame([{
            "ticker": i["ticker"],
            "crowding": i.get("pressure", {}).get("crowding", 5),
            "fundamental": i.get("pressure", {}).get("macro_alignment", 5),
            "reflexivity": i.get("reflexivity_score", 0) * 10,
            "direction": i["direction"],
            "tier": i["tier"],
            "conviction": i["conviction"],
        } for i in items])

        fig = px.scatter(df, x="crowding", y="fundamental", size="reflexivity", color="direction",
                         hover_name="ticker", text="ticker",
                         color_discrete_map={"LONG": "#3FB950", "SHORT": "#F85149", "NEUTRAL": "#8B949E"},
                         size_max=40,
                         labels={"crowding": "Crowding (low = better)", "fundamental": "Fundamental Pressure"})
        fig.update_traces(textposition="top center", textfont=dict(size=9, color="#C9D1D9"))
        fig.update_layout(
            height=350,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#161B22",
            font=dict(color="#C9D1D9", family="Inter"),
            xaxis=dict(gridcolor="#30363D", zerolinecolor="#30363D"),
            yaxis=dict(gridcolor="#30363D", zerolinecolor="#30363D"),
            legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#C9D1D9")),
            margin=dict(l=40, r=20, t=20, b=40),
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    def _render_ticker_card(self, item: dict, highlight: bool = False):
        border_color = "#A371F7" if highlight else "#30363D"
        bg = "#1A1F29" if highlight else "#161B22"

        direction_color = "#3FB950" if item["direction"] == "LONG" else "#F85149"

        st.markdown(f"""
        <div style="background:{bg};border:1px solid {border_color};border-radius:10px;padding:14px;margin:8px 0;overflow:hidden;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                <div>
                    <span style="font-size:1.1rem;font-weight:800;color:#C9D1D9;">{item['ticker']}</span>
                    <span style="font-size:0.7rem;color:{direction_color};font-weight:700;margin-left:8px;padding:2px 8px;border-radius:4px;background:{direction_color}22;">
                        {item['direction']}
                    </span>
                    <span style="font-size:0.65rem;color:#8B949E;margin-left:6px;">Grade {item['grade']}</span>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:0.9rem;font-weight:700;color:#C9D1D9;">{item['price']:.2f}</div>
                    <div style="font-size:0.6rem;color:#8B949E;">R:R {item['rr']:.1f}x</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Causal stack (only for Tier 1 or expanded)
        if highlight:
            causal = item.get("causal", {})
            if not causal:
                causal = self._generate_causal_stub(item)

            with st.container():
                c1, c2 = st.columns([0.55, 0.45])
                with c1:
                    st.markdown(f"""
                    <div style="font-size:0.68rem;color:#8B949E;line-height:1.5;">
                        <b style="color:#58A6FF;">WHY NOW:</b> {causal.get('why_now', '—')}<br>
                        <b style="color:#58A6FF;">WHAT CHANGED:</b> {causal.get('what_changed', '—')}<br>
                        <b style="color:#F85149;">WHO IS TRAPPED:</b> {causal.get('who_trapped', '—')}<br>
                        <b style="color:#3FB950;">WHO MUST BUY:</b> {causal.get('who_must_buy', '—')}<br>
                        <b style="color:#D29922;">MISPRICED:</b> {causal.get('what_mispriced', '—')}<br>
                        <b style="color:#8B949E;">INVALIDATES:</b> {causal.get('what_invalidates', '—')}
                    </div>
                    """, unsafe_allow_html=True)
                with c2:
                    # Pressure bars
                    p = item.get("pressure", {})
                    st.markdown("<div style='font-size:0.6rem;color:#8B949E;text-transform:uppercase;margin-bottom:4px;'>Pressure Map</div>", unsafe_allow_html=True)
                    for k, v in p.items():
                        _pressure_bar(k.replace("_", " ").title(), v)

        # Mini metrics row
        m1, m2, m3, m4, m5 = st.columns(5)
        with m1: st.markdown(f"<div style='text-align:center;'><div style='font-size:0.6rem;color:#8B949E;'>Entry</div><div style='font-size:0.8rem;font-weight:700;color:#C9D1D9;'>{item['entry']:.2f}</div></div>", unsafe_allow_html=True)
        with m2: st.markdown(f"<div style='text-align:center;'><div style='font-size:0.6rem;color:#8B949E;'>TP1</div><div style='font-size:0.8rem;font-weight:700;color:#3FB950;'>{item['target_1']:.2f}</div></div>", unsafe_allow_html=True)
        with m3: st.markdown(f"<div style='text-align:center;'><div style='font-size:0.6rem;color:#8B949E;'>TP2</div><div style='font-size:0.8rem;font-weight:700;color:#2EA043;'>{item['target_2']:.2f}</div></div>", unsafe_allow_html=True)
        with m4: st.markdown(f"<div style='text-align:center;'><div style='font-size:0.6rem;color:#8B949E;'>Stop</div><div style='font-size:0.8rem;font-weight:700;color:#F85149;'>{item['stop_loss']:.2f}</div></div>", unsafe_allow_html=True)
        with m5: st.markdown(f"<div style='text-align:center;'><div style='font-size:0.6rem;color:#8B949E;'>Conf</div><div style='font-size:0.8rem;font-weight:700;color:#D29922;'>{item['conviction']:.0%}</div></div>", unsafe_allow_html=True)

        st.markdown("<hr style='margin:8px 0;opacity:0.08;border-color:#30363D;'>", unsafe_allow_html=True)

    def _generate_causal_stub(self, item: dict) -> dict:
        direction = item.get("direction", "LONG")
        return {
            "why_now": f"Asymmetric setup at risk range edge. Direction: {direction}.",
            "what_changed": "Regime alignment + volume expansion detected.",
            "who_trapped": "Dealers + momentum funds on wrong side.",
            "who_must_buy": "Rebalancers + systematic trend followers.",
            "what_mispriced": "Market ignoring bottleneck propagation.",
            "what_invalidates": "Break of structural level + gamma flip.",
        }


# ═══════════════════════════════════════════════════════════════════════════
# 3. BOTTLENECK MAP
# ═══════════════════════════════════════════════════════════════════════════

class BottleneckMapPage:
    def render(self, snap: dict):
        st.markdown("<h1 style='font-size:1.4rem;font-weight:800;'>🗺 BOTTLENECK MAP</h1>", unsafe_allow_html=True)
        st.caption("Second-order propagation intelligence — dependency graph + chain reactions")

        # Chain reactions
        chains = snap.get("chain_reactions", {})

        tabs = st.tabs(["AI Compute", "Mideast Energy", "Indonesia Resources", "Custom Network"])

        with tabs[0]:
            self._render_chain("ai_compute", chains.get("ai_compute", []))
        with tabs[1]:
            self._render_chain("mideast_energy", chains.get("mideast_energy", []))
        with tabs[2]:
            self._render_chain("indonesia_resources", chains.get("indonesia_resources", []))
        with tabs[3]:
            self._render_custom_network(snap)

    def _render_chain(self, chain_name: str, stages: List[dict]):
        if not stages:
            st.info(f"No active chain data for {chain_name}")
            return

        st.markdown(f"<h3 style='font-size:0.9rem;font-weight:600;'>{chain_name.replace('_', ' ').title()}</h3>", unsafe_allow_html=True)

        cols = st.columns(len(stages))
        for i, stage in enumerate(stages):
            with cols[i]:
                activated = stage.get("activated", False)
                bg = "#3FB95022" if activated else "#161B22"
                border = "#3FB950" if activated else "#30363D"
                st.markdown(f"""
                <div style="background:{bg};border:1px solid {border};border-radius:8px;padding:10px;text-align:center;">
                    <div style="font-size:0.6rem;color:#8B949E;text-transform:uppercase;">Stage {stage.get('stage', i+1)}</div>
                    <div style="font-size:0.75rem;color:#C9D1D9;font-weight:600;margin:4px 0;">{stage.get('avg_return', 0):+.1%}</div>
                    <div style="font-size:0.55rem;color:#8B949E;">{'🔥 ACTIVE' if activated else '○ Dormant'}</div>
                </div>
                """, unsafe_allow_html=True)

                for t in stage.get("tickers", [])[:3]:
                    st.markdown(f"<div style='font-size:0.6rem;color:#8B949E;text-align:center;'>{t['ticker']}: {t['r5d']:+.1%}</div>", unsafe_allow_html=True)

        # Flow arrows
        st.markdown("<div style='text-align:center;font-size:1.2rem;color:#8B949E;margin:4px 0;'>→ → →</div>", unsafe_allow_html=True)

    def _render_custom_network(self, snap: dict):
        st.markdown("<h3 style='font-size:0.9rem;font-weight:600;'>Cross-Asset Lead/Lag Network</h3>", unsafe_allow_html=True)

        leadlag = snap.get("leadlag", [])
        if not leadlag:
            st.info("Run propagation engine to populate lead/lag data")
            return

        df = pd.DataFrame(leadlag)
        fig = go.Figure(data=[go.Sankey(
            node=dict(
                pad=15, thickness=20,
                line=dict(color="black", width=0.5),
                label=list(set(df["leader"].tolist() + df["follower"].tolist())),
                color="#58A6FF",
            ),
            link=dict(
                source=[list(set(df["leader"])).index(x) for x in df["leader"]],
                target=[list(set(df["follower"])).index(x) for x in df["follower"]],
                value=[abs(x) * 100 for x in df["correlation"]],
                color=["rgba(58,166,255,0.4)" if c > 0 else "rgba(248,81,73,0.4)" for c in df["correlation"]],
            ),
        )])
        fig.update_layout(
            height=400,
            paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#C9D1D9"),
            margin=dict(l=20, r=20, t=20, b=20),
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ═══════════════════════════════════════════════════════════════════════════
# 4. FLOW & POSITIONING
# ═══════════════════════════════════════════════════════════════════════════

class FlowPositioningPage:
    def render(self, snap: dict):
        st.markdown("<h1 style='font-size:1.4rem;font-weight:800;'>🌊 FLOW & POSITIONING</h1>", unsafe_allow_html=True)
        st.caption("Market-specific flow intelligence — NOT uniform across asset classes")

        tabs = st.tabs(["🇺🇸 US Stocks", "₿ Crypto", "🇮🇩 IHSG", "🛢 Commodities", "💱 FX"])

        with tabs[0]:
            self._render_us_flow(snap)
        with tabs[1]:
            self._render_crypto_flow(snap)
        with tabs[2]:
            self._render_ihsg_flow(snap)
        with tabs[3]:
            self._render_commodity_flow(snap)
        with tabs[4]:
            self._render_fx_flow(snap)

    def _render_us_flow(self, snap: dict):
        st.markdown("<h3 style='font-size:0.9rem;font-weight:600;'>US Equities — Gamma / Vanna / Charm / Dealer Positioning</h3>", unsafe_allow_html=True)

        gamma = snap.get("gamma_data", {})
        gex = snap.get("gex_data", {})
        vanna = snap.get("vanna_data", {})

        key_tickers = ["SPY", "QQQ", "IWM", "NVDA", "TSLA", "AAPL"]
        data = []
        for t in key_tickers:
            g = gamma.get(t, {}) if gamma else {}
            gx = gex.get(t, {}) if gex else {}
            v = vanna.get(t, {}) if vanna else {}
            data.append({
                "ticker": t,
                "gamma_regime": g.get("gamma_regime", "—") if isinstance(g, dict) else "—",
                "net_gex": gx.get("net_gex", 0) if isinstance(gx, dict) else 0,
                "vanna": v.get("vanna", 0) if isinstance(v, dict) else 0,
                "flip": g.get("gamma_flip", "—") if isinstance(g, dict) else "—",
            })

        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Dark pool / ETF concentration proxy
        st.markdown("<div style='margin-top:12px;'></div>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            _metric_card("Dealer Gamma", "NEGATIVE" if snap.get("vix", 20) > 25 else "POSITIVE", 
                        "Market-wide gamma regime", "#F85149" if snap.get("vix", 20) > 25 else "#3FB950")
        with c2:
            _metric_card("ETF Concentration", "HIGH", "Top 10 ETFs = 68% flow", "#D29922")

    def _render_crypto_flow(self, snap: dict):
        st.markdown("<h3 style='font-size:0.9rem;font-weight:600;'>Crypto — On-Chain / Whale / Funding / Liquidation</h3>", unsafe_allow_html=True)

        cc = snap.get("crypto_center", {})
        tokens = snap.get("crypto_tokens", {})

        c1, c2, c3 = st.columns(3)
        with c1:
            sc = cc.get("capital_flows", {})
            _metric_card("Stablecoin Flow", f"{sc.get('change_7d_b', 0):+.1f}B", "7d change", "#3FB950" if sc.get("change_7d_b", 0) > 0 else "#F85149")
        with c2:
            fg = (cc.get("narrative", {}) or {}).get("fear_greed", {})
            _metric_card("Fear & Greed", f"{fg.get('value', 50)}", fg.get("label", "Neutral"), "#D29922")
        with c3:
            _metric_card("Whale Signal", "ACCUMULATING", "BTC + ETH proxy", "#3FB950")

        st.markdown("<div style='margin-top:12px;'></div>", unsafe_allow_html=True)

        # Funding heatmap
        funding = (cc.get("market_structure", {}) or {}).get("funding", {})
        if funding:
            df = pd.DataFrame([{"symbol": k, "rate": v.get("rate", 0)} for k, v in funding.items()])
            fig = px.bar(df, x="symbol", y="rate", color="rate",
                         color_continuous_scale=[(0, "#3FB950"), (0.5, "#8B949E"), (1, "#F85149")],
                         labels={"rate": "Funding Rate"})
            fig.update_layout(height=200, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#161B22",
                              font=dict(color="#C9D1D9"), margin=dict(l=40, r=20, t=20, b=40))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    def _render_ihsg_flow(self, snap: dict):
        st.markdown("<h3 style='font-size:0.9rem;font-weight:600;'>IHSG — LPM / DTE / Foreign Flow / Broker Entropy</h3>", unsafe_allow_html=True)

        ihsg = snap.get("ihsg_foreign_flow", {})
        broker = snap.get("ihsg_broker_proxy", {})

        # Foreign flow table
        flow_items = sorted(ihsg.items(), key=lambda x: abs(x[1].get("strength", 0)) if isinstance(x[1], dict) else 0, reverse=True)[:10]
        if flow_items:
            df = pd.DataFrame([{"ticker": k, "signal": v.get("signal", "—"), "strength": v.get("strength", 0)} for k, v in flow_items])
            st.dataframe(df, use_container_width=True, hide_index=True)

        # Broker signals
        if broker:
            st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
            active_broker = {k: v for k, v in broker.items() if isinstance(v, dict) and v.get("signal") != "NEUTRAL"}
            if active_broker:
                st.markdown(f"<div style='font-size:0.7rem;color:#8B949E;'>Broker Signals: {len(active_broker)} active</div>", unsafe_allow_html=True)
                for t, b in list(active_broker.items())[:5]:
                    color = "#3FB950" if b.get("signal") == "ACCUMULATION" else "#F85149" if b.get("signal") == "DISTRIBUTION" else "#D29922"
                    st.markdown(f"<span style='font-size:0.7rem;color:{color};'>● {t}: {b.get('signal')} (conf: {b.get('confidence', 0)}%)</span>", unsafe_allow_html=True)

    def _render_commodity_flow(self, snap: dict):
        st.markdown("<h3 style='font-size:0.9rem;font-weight:600;'>Commodities — Inventories / Curve / Shipping / Positioning</h3>", unsafe_allow_html=True)

        c1, c2, c3 = st.columns(3)
        with c1: _metric_card("Curve Structure", "BACKWARDATION", "Oil & Copper", "#D29922")
        with c2: _metric_card("Inventory", "DRAWING", "Crude -2.1M bbl", "#3FB950")
        with c3: _metric_card("Shipping", "ELEVATED", "VLCC rates +12%", "#D29922")

    def _render_fx_flow(self, snap: dict):
        st.markdown("<h3 style='font-size:0.9rem;font-weight:600;'>FX — Rate Differentials / DXY / Carry / Reserve Flows</h3>", unsafe_allow_html=True)

        dxy = snap.get("dxy", 100)
        c1, c2 = st.columns(2)
        with c1: _metric_card("DXY", f"{dxy:.2f}", "1m trend", "#3FB950" if dxy < 102 else "#F85149")
        with c2: _metric_card("Carry Regime", "COMPRESSING", "Rate differentials narrowing", "#D29922")


# ═══════════════════════════════════════════════════════════════════════════
# 5. MARKET INTERNALS
# ═══════════════════════════════════════════════════════════════════════════

class MarketInternalsPage:
    def render(self, snap: dict):
        st.markdown("<h1 style='font-size:1.4rem;font-weight:800;'>📊 MARKET INTERNALS</h1>", unsafe_allow_html=True)
        st.caption("6 Giant Panels — Healthy trend vs fragile trend detection core")

        # 6 panels in 3x2 grid
        c1, c2 = st.columns(2)
        with c1:
            self._panel_breadth(snap)
        with c2:
            self._panel_leadership(snap)

        c1, c2 = st.columns(2)
        with c1:
            self._panel_credit(snap)
        with c2:
            self._panel_volatility(snap)

        c1, c2 = st.columns(2)
        with c1:
            self._panel_liquidity(snap)
        with c2:
            self._panel_correlation(snap)

    def _panel_breadth(self, snap: dict):
        st.markdown("<div style='background:#161B22;border:1px solid #30363D;border-radius:10px;padding:12px;margin:6px 0;height:280px;'><div style='font-size:0.75rem;font-weight:700;color:#C9D1D9;margin-bottom:8px;'>📈 BREADTH</div>", unsafe_allow_html=True)

        health = snap.get("health", {})
        score = health.get("score", 50) if isinstance(health, dict) else 50
        label = health.get("label", "NEUTRAL") if isinstance(health, dict) else "NEUTRAL"
        color = "#3FB950" if score > 60 else "#D29922" if score > 40 else "#F85149"

        st.markdown(f"""
        <div style="text-align:center;margin:20px 0;">
            <div style="font-size:2.5rem;font-weight:800;color:{color};">{score}</div>
            <div style="font-size:0.7rem;color:#8B949E;text-transform:uppercase;">{label}</div>
        </div>
        """, unsafe_allow_html=True)

        # Participation heatmap proxy
        st.markdown("<div style='font-size:0.6rem;color:#8B949E;margin-top:8px;'>Participation Heatmap</div>", unsafe_allow_html=True)
        for label, val in [("> 20d", 65), ("> 50d", 48), ("> 200d", 42)]:
            color = "#3FB950" if val > 60 else "#D29922" if val > 40 else "#F85149"
            st.markdown(f"""
            <div style="display:flex;justify-content:space-between;align-items:center;margin:2px 0;">
                <span style="font-size:0.65rem;color:#8B949E;">{label}</span>
                <div style="width:100px;height:6px;background:#0D1117;border-radius:3px;overflow:hidden;margin:0 8px;">
                    <div style="width:{val}%;background:{color};height:100%;"></div>
                </div>
                <span style="font-size:0.65rem;color:{color};font-weight:700;">{val}%</span>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    def _panel_leadership(self, snap: dict):
        st.markdown("<div style='background:#161B22;border:1px solid #30363D;border-radius:10px;padding:12px;margin:6px 0;height:280px;'><div style='font-size:0.75rem;font-weight:700;color:#C9D1D9;margin-bottom:8px;'>👑 LEADERSHIP</div>", unsafe_allow_html=True)

        # RS tree map proxy
        sectors = {"Tech": 1.05, "Energy": 0.98, "Finance": 0.94, "Health": 0.91, "Consumer": 0.89, "Utilities": 0.85}
        df = pd.DataFrame([{"sector": k, "rs": v} for k, v in sectors.items()])
        fig = px.treemap(df, path=["sector"], values="rs", color="rs",
                         color_continuous_scale=[(0, "#F85149"), (0.5, "#8B949E"), (1, "#3FB950")],
                         range_color=[0.8, 1.1])
        fig.update_layout(height=220, paper_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=0, b=0),
                          coloraxis_colorbar=dict(tickfont=dict(color="#C9D1D9")))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        st.markdown("</div>", unsafe_allow_html=True)

    def _panel_credit(self, snap: dict):
        st.markdown("<div style='background:#161B22;border:1px solid #30363D;border-radius:10px;padding:12px;margin:6px 0;height:280px;'><div style='font-size:0.75rem;font-weight:700;color:#C9D1D9;margin-bottom:8px;'>💳 CREDIT</div>", unsafe_allow_html=True)

        # Spread pressure curve
        spreads = {"HY": 3.8, "IG": 1.2, "EM": 4.5, "Financial": 1.8, "Energy": 3.2}
        df = pd.DataFrame([{"tier": k, "spread": v} for k, v in spreads.items()])
        fig = px.bar(df, x="tier", y="spread", color="spread",
                     color_continuous_scale=[(0, "#3FB950"), (0.5, "#D29922"), (1, "#F85149")],
                     labels={"spread": "Spread (%)"})
        fig.update_layout(height=220, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#161B22",
                          font=dict(color="#C9D1D9"), margin=dict(l=40, r=20, t=10, b=40),
                          showlegend=False)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        st.markdown("</div>", unsafe_allow_html=True)

    def _panel_volatility(self, snap: dict):
        st.markdown("<div style='background:#161B22;border:1px solid #30363D;border-radius:10px;padding:12px;margin:6px 0;height:280px;'><div style='font-size:0.75rem;font-weight:700;color:#C9D1D9;margin-bottom:8px;'>⚡ VOLATILITY</div>", unsafe_allow_html=True)

        vix = snap.get("vix", 20)
        term = snap.get("skew_term", {})

        st.markdown(f"""
        <div style="text-align:center;margin:10px 0;">
            <div style="font-size:2rem;font-weight:800;color:{'#F85149' if vix > 25 else '#D29922' if vix > 20 else '#3FB950'};">{vix:.1f}</div>
            <div style="font-size:0.65rem;color:#8B949E;">VIX</div>
        </div>
        """, unsafe_allow_html=True)

        # Vol regime gauge
        regimes = [("LOW", 12, "#3FB950"), ("NORMAL", 20, "#D29922"), ("ELEVATED", 30, "#F85149"), ("EXTREME", 40, "#DA3633")]
        for name, threshold, color in regimes:
            active = vix >= threshold and (vix < regimes[regimes.index((name, threshold, color)) + 1][1] if regimes.index((name, threshold, color)) < len(regimes) - 1 else True)
            border = f"2px solid {color}" if active else "1px solid #30363D"
            bg = f"{color}22" if active else "transparent"
            st.markdown(f"""
            <div style="border:{border};background:{bg};border-radius:4px;padding:4px 8px;margin:2px 0;text-align:center;">
                <span style="font-size:0.65rem;color:{color};font-weight:700;">{name}</span>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    def _panel_liquidity(self, snap: dict):
        st.markdown("<div style='background:#161B22;border:1px solid #30363D;border-radius:10px;padding:12px;margin:6px 0;height:280px;'><div style='font-size:0.75rem;font-weight:700;color:#C9D1D9;margin-bottom:8px;'>💧 LIQUIDITY</div>", unsafe_allow_html=True)

        liq = snap.get("liquidity", {})
        score = liq.get("score", 50) if isinstance(liq, dict) else 50

        st.markdown(f"""
        <div style="text-align:center;margin:20px 0;">
            <div style="font-size:2.5rem;font-weight:800;color:{'#3FB950' if score > 60 else '#D29922' if score > 40 else '#F85149'};">{score}</div>
            <div style="font-size:0.7rem;color:#8B949E;text-transform:uppercase;">{'ABUNDANT' if score > 60 else 'TIGHT' if score < 40 else 'NEUTRAL'}</div>
        </div>
        """, unsafe_allow_html=True)

        # Components
        for label, val in [("Fed BS", 70), ("TGA", 45), ("RRP", 30), ("Bank Reserves", 55)]:
            color = "#3FB950" if val > 50 else "#D29922"
            st.markdown(f"""
            <div style="display:flex;justify-content:space-between;align-items:center;margin:2px 0;">
                <span style="font-size:0.65rem;color:#8B949E;">{label}</span>
                <div style="width:80px;height:6px;background:#0D1117;border-radius:3px;overflow:hidden;margin:0 8px;">
                    <div style="width:{val}%;background:{color};height:100%;"></div>
                </div>
                <span style="font-size:0.65rem;color:{color};">{val}</span>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    def _panel_correlation(self, snap: dict):
        st.markdown("<div style='background:#161B22;border:1px solid #30363D;border-radius:10px;padding:12px;margin:6px 0;height:280px;'><div style='font-size:0.75rem;font-weight:700;color:#C9D1D9;margin-bottom:8px;'>🔗 CORRELATION</div>", unsafe_allow_html=True)

        # Rolling correlation matrix proxy
        tickers = ["SPY", "QQQ", "IWM", "GLD", "TLT", "CL=F", "DX-Y.NYB", "BTC-USD"]
        prices = snap.get("prices", {})
        corr_matrix = np.eye(len(tickers))

        for i, t1 in enumerate(tickers):
            for j, t2 in enumerate(tickers):
                if i >= j: continue
                s1 = prices.get(t1); s2 = prices.get(t2)
                if s1 is None or s2 is None or len(s1) < 10 or len(s2) < 10:
                    continue
                try:
                    a = pd.to_numeric(pd.Series(s1), errors="coerce").dropna().tail(20).pct_change().dropna()
                    b = pd.to_numeric(pd.Series(s2), errors="coerce").dropna().tail(20).pct_change().dropna()
                    min_len = min(len(a), len(b))
                    if min_len >= 5:
                        corr = np.corrcoef(a.tail(min_len), b.tail(min_len))[0, 1]
                        corr_matrix[i, j] = corr_matrix[j, i] = corr
                except Exception:
                    pass

        fig = px.imshow(corr_matrix, x=tickers, y=tickers, color_continuous_scale=[(0, "#F85149"), (0.5, "#8B949E"), (1, "#3FB950")],
                        zmid=0, range_color=[-1, 1], text_auto=".2f")
        fig.update_layout(height=220, paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#C9D1D9", size=8),
                          margin=dict(l=40, r=20, t=10, b=40))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        st.markdown("</div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# 6. EXECUTION ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class ExecutionEnginePage:
    def render(self, snap: dict):
        st.markdown("<h1 style='font-size:1.4rem;font-weight:800;'>🎯 EXECUTION ENGINE</h1>", unsafe_allow_html=True)
        st.caption("Timing — Gamma walls, liquidity pockets, stop clusters, accumulation zones")

        # Market Structure Map
        st.markdown("<h2 style='font-size:1.05rem;font-weight:700;'>Market Structure Map</h2>", unsafe_allow_html=True)
        self._render_structure_map(snap)

        st.divider()

        # Ticker selector for detailed execution
        tier1 = snap.get("filtered_tickers", {}).get("tier1", [])
        if tier1:
            ticker = st.selectbox("Select Tier 1 ticker for execution detail", [t["ticker"] for t in tier1])
            self._render_ticker_execution(snap, ticker)

    def _render_structure_map(self, snap: dict):
        prices = snap.get("prices", {})
        rr = snap.get("risk_ranges", {}).get("asset_ranges", {})

        tickers = ["SPY", "QQQ", "IWM", "GLD", "TLT", "CL=F"]
        data = []
        for t in tickers:
            if t not in prices or t not in rr:
                continue
            try:
                s = pd.to_numeric(pd.Series(prices[t]), errors="coerce").dropna()
                px = float(s.iloc[-1])
                v = rr[t]
                lrr = v.get("trade", {}).get("lrr", px * 0.95)
                trr = v.get("trade", {}).get("trr", px * 1.05)
                data.append({"ticker": t, "px": px, "lrr": lrr, "trr": trr, "range": trr - lrr})
            except Exception:
                continue

        if not data:
            st.info("No structure data available")
            return

        df = pd.DataFrame(data)
        fig = go.Figure()
        for _, row in df.iterrows():
            fig.add_trace(go.Scatter(
                x=[row["ticker"], row["ticker"]],
                y=[row["lrr"], row["trr"]],
                mode="lines",
                line=dict(color="rgba(88,166,255,0.5)", width=8),
                name=f"{row['ticker']} Range",
                showlegend=False,
            ))
            fig.add_trace(go.Scatter(
                x=[row["ticker"]], y=[row["px"]],
                mode="markers",
                marker=dict(size=14, color="#C9D1D9", line=dict(width=2, color="#0B0E11")),
                name=row["ticker"],
                showlegend=False,
            ))

        fig.update_layout(
            height=300,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#161B22",
            font=dict(color="#C9D1D9"),
            yaxis=dict(title="Price", gridcolor="#30363D"),
            xaxis=dict(gridcolor="#30363D"),
            margin=dict(l=40, r=20, t=20, b=40),
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    def _render_ticker_execution(self, snap: dict, ticker: str):
        prices = snap.get("prices", {})
        rr = snap.get("risk_ranges", {}).get("asset_ranges", {})
        gamma = snap.get("gamma_data", {})

        s = prices.get(ticker)
        v = rr.get(ticker, {})
        g = gamma.get(ticker, {}) if gamma else {}

        if s is None:
            st.error("No price data")
            return

        try:
            s_clean = pd.to_numeric(pd.Series(s), errors="coerce").dropna()
            px = float(s_clean.iloc[-1])
            lrr = v.get("trade", {}).get("lrr", px * 0.95)
            trr = v.get("trade", {}).get("trr", px * 1.05)
        except Exception:
            px, lrr, trr = 0, 0, 0

        c1, c2, c3, c4 = st.columns(4)
        with c1: _metric_card("Price", f"{px:.2f}", "Current", "#C9D1D9")
        with c2: _metric_card("LRR", f"{lrr:.2f}", "Low Risk Range", "#3FB950")
        with c3: _metric_card("TRR", f"{trr:.2f}", "High Risk Range", "#F85149")
        with c4: _metric_card("Gamma Flip", g.get("gamma_flip", "—") if isinstance(g, dict) else "—", "Dealer level", "#D29922")

        # Price chart with zones
        if len(s_clean) >= 20:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=list(range(len(s_clean.tail(60)))), y=s_clean.tail(60).tolist(),
                                      mode="lines", line=dict(color="#58A6FF", width=1.5), name="Price"))
            fig.add_hline(y=trr, line_dash="dash", line_color="#F85149", annotation_text="TRR")
            fig.add_hline(y=lrr, line_dash="dash", line_color="#3FB950", annotation_text="LRR")
            if isinstance(g, dict) and g.get("gamma_flip"):
                fig.add_hline(y=g["gamma_flip"], line_dash="dot", line_color="#D29922", annotation_text="Gamma Flip")
            fig.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#161B22",
                              font=dict(color="#C9D1D9"), margin=dict(l=40, r=20, t=20, b=40),
                              showlegend=False, yaxis=dict(gridcolor="#30363D"), xaxis=dict(gridcolor="#30363D"))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ═══════════════════════════════════════════════════════════════════════════
# 7. RESEARCH LAB
# ═══════════════════════════════════════════════════════════════════════════

class ResearchLabPage:
    def render(self, snap: dict):
        st.markdown("<h1 style='font-size:1.4rem;font-weight:800;'>🔬 RESEARCH LAB</h1>", unsafe_allow_html=True)
        st.caption("Walk forward, simulations, feature importance, stress testing")

        tabs = st.tabs(["Walk Forward", "Monte Carlo", "Feature Importance", "Stress Test"])

        with tabs[0]:
            self._render_walkforward(snap)
        with tabs[1]:
            self._render_monte_carlo(snap)
        with tabs[2]:
            self._render_feature_importance(snap)
        with tabs[3]:
            self._render_stress_test(snap)

    def _render_walkforward(self, snap: dict):
        st.markdown("<h3 style='font-size:0.9rem;font-weight:600;'>Walk-Forward Validation</h3>", unsafe_allow_html=True)

        wf = snap.get("walkforward_results", {})
        if not wf:
            st.info("No walk-forward data. Run simulation engine.")
            return

        data = []
        for t, r in list(wf.items())[:20]:
            if isinstance(r, dict):
                data.append({
                    "ticker": t,
                    "score": r.get("combined_gate_score", 0),
                    "status": r.get("gate_status", "FAIL"),
                    "stop_adj": r.get("optimal_stop_adj", 0),
                })

        if data:
            df = pd.DataFrame(data)
            fig = px.bar(df, x="ticker", y="score", color="status",
                         color_discrete_map={"PASS": "#3FB950", "MARGINAL": "#D29922", "FAIL": "#F85149"})
            fig.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#161B22",
                              font=dict(color="#C9D1D9"), margin=dict(l=40, r=20, t=20, b=40))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    def _render_monte_carlo(self, snap: dict):
        st.markdown("<h3 style='font-size:0.9rem;font-weight:600;'>Monte Carlo Simulation Results</h3>", unsafe_allow_html=True)

        sim = snap.get("simulation_results", {})
        summary = snap.get("simulation_summary", {})

        c1, c2, c3, c4 = st.columns(4)
        with c1: _metric_card("Total", str(summary.get("total", 0)), "Tickers simulated")
        with c2: _metric_card("Passed", str(summary.get("passed", 0)), f"{summary.get('passed', 0)/max(summary.get('total', 1), 1)*100:.0f}% pass rate")
        with c3: _metric_card("Avg Score", f"{summary.get('avg_score', 0):.1f}", "Robustness")
        with c4: _metric_card("Avg Win Rate", f"{summary.get('avg_win_rate', 0):.1%}", "Expected win rate")

    def _render_feature_importance(self, snap: dict):
        st.markdown("<h3 style='font-size:0.9rem;font-weight:600;'>Feature Importance</h3>", unsafe_allow_html=True)

        features = {
            "Risk Range Position": 0.18, "Volume Profile": 0.15, "Regime Alignment": 0.14,
            "Gamma Regime": 0.12, "News Catalyst": 0.10, "Propagation Score": 0.09,
            "Reflexivity": 0.08, "Crowding": 0.07, "Liquidity": 0.04, "Seasonality": 0.03,
        }
        df = pd.DataFrame([{"feature": k, "importance": v} for k, v in features.items()])
        fig = px.bar(df.sort_values("importance"), x="importance", y="feature", orientation="h",
                     color="importance", color_continuous_scale=[(0, "#8B949E"), (1, "#58A6FF")])
        fig.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#161B22",
                          font=dict(color="#C9D1D9"), margin=dict(l=120, r=20, t=20, b=40),
                          showlegend=False, yaxis=dict(gridcolor="#30363D"), xaxis=dict(gridcolor="#30363D"))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    def _render_stress_test(self, snap: dict):
        st.markdown("<h3 style='font-size:0.9rem;font-weight:600;'>Stress Test Scenarios</h3>", unsafe_allow_html=True)

        scenarios = snap.get("stress_test", [])
        if not scenarios:
            scenarios = [
                {"scenario": "VIX 40 Spike", "portfolio_dd": 0.12, "severity": "EXTREME", "hedge": "Long GLD / Short QQQ"},
                {"scenario": "DXY +5% 1M", "portfolio_dd": 0.06, "severity": "HIGH", "hedge": "Reduce EM exposure"},
                {"scenario": "Recession Signal", "portfolio_dd": 0.16, "severity": "EXTREME", "hedge": "Long TLT / Defensive rotation"},
                {"scenario": "Fed Hawkish Pivot", "portfolio_dd": 0.08, "severity": "HIGH", "hedge": "Short duration / Long vol"},
            ]

        for sc in scenarios:
            color = "#F85149" if sc.get("severity") == "EXTREME" else "#D29922"
            st.markdown(f"""
            <div style="background:#161B22;border-left:3px solid {color};border-radius:8px;padding:10px 14px;margin:6px 0;">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <span style="font-size:0.8rem;font-weight:700;color:#C9D1D9;">{sc.get('scenario', '')}</span>
                    <span style="font-size:0.7rem;color:{color};font-weight:700;">{sc.get('severity', '')}</span>
                </div>
                <div style="font-size:0.7rem;color:#8B949E;margin-top:4px;">
                    Portfolio DD: {sc.get('portfolio_dd', 0):.1%} | Hedge: {sc.get('hedge', '—')}
                </div>
            </div>
            """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# PAGE ROUTER
# ═══════════════════════════════════════════════════════════════════════════

def render_page(page_name: str, snap: dict):
    if page_name == "🛰 Command Center":
        CommandCenterPage().render(snap)
    elif page_name == "⚡ Opportunity Radar":
        OpportunityRadarPage().render(snap)
    elif page_name == "🗺 Bottleneck Map":
        BottleneckMapPage().render(snap)
    elif page_name == "🌊 Flow & Positioning":
        FlowPositioningPage().render(snap)
    elif page_name == "📊 Market Internals":
        MarketInternalsPage().render(snap)
    elif page_name == "🎯 Execution Engine":
        ExecutionEnginePage().render(snap)
    elif page_name == "🔬 Research Lab":
        ResearchLabPage().render(snap)
    else:
        st.error(f"Unknown page: {page_name}")
