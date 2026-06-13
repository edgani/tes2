"""options_layer.py — Options market structure component (SpotGamma + Tier1Alpha style)"""
import streamlit as st


def render_options_layer(ticker: str, options_data: dict = None):
    """Render Call Wall, Put Wall, GEX, Vol Trigger for a ticker.
    
    options_data structure (from unified_greeks_engine / spotgamma_gex_engine):
    {
      'call_wall': 950.0,
      'put_wall': 850.0,
      'vol_trigger': 880.0,
      'zero_gamma': 870.0,
      'gex': 2.3e9,
      'dex': -1.2e9,
      'iv_rank': 65.0,
      'iv_percentile': 70.0,
      'put_call_ratio': 0.65,
      'max_pain': 900.0,
    }
    """
    if not options_data:
        st.caption("No options data available")
        return
    
    od = options_data
    
    # Top metrics row
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        cw = od.get("call_wall")
        st.metric("Call Wall", f"${cw:.2f}" if cw else "—", help="Largest call gamma — resistance")
    with c2:
        pw = od.get("put_wall")
        st.metric("Put Wall", f"${pw:.2f}" if pw else "—", help="Largest put gamma — support")
    with c3:
        vt = od.get("vol_trigger")
        st.metric("Vol Trigger", f"${vt:.2f}" if vt else "—", help="Gamma flip — above = stable, below = vol expansion")
    with c4:
        mp = od.get("max_pain")
        st.metric("Max Pain", f"${mp:.2f}" if mp else "—", help="OPEX gravitational center")
    
    # GEX + DEX
    c1, c2, c3 = st.columns(3)
    with c1:
        gex = od.get("gex", 0)
        gex_color = "#3FB950" if gex > 0 else "#F85149"
        gex_label = "POSITIVE GAMMA" if gex > 0 else "NEGATIVE GAMMA"
        gex_meaning = "MM stabilize moves" if gex > 0 else "MM amplify moves"
        st.markdown(f"""<div style='background:#161B22;border:1px solid {gex_color};border-radius:6px;padding:8px;'>
            <div style='font-size:0.55rem;color:#8B949E;text-transform:uppercase;font-weight:600;'>GEX</div>
            <div style='font-size:0.9rem;font-weight:700;color:{gex_color};'>{gex_label}</div>
            <div style='font-size:0.7rem;color:#E6EDF3;'>${gex/1e9:+.2f}B</div>
            <div style='font-size:0.6rem;color:#8B949E;margin-top:2px;'>{gex_meaning}</div>
            </div>""", unsafe_allow_html=True)
    with c2:
        ivr = od.get("iv_rank", 0)
        ivp = od.get("iv_percentile", 0)
        iv_color = "#F85149" if ivr > 70 else "#D29922" if ivr > 40 else "#3FB950"
        st.markdown(f"""<div style='background:#161B22;border:1px solid #30363D;border-radius:6px;padding:8px;'>
            <div style='font-size:0.55rem;color:#8B949E;text-transform:uppercase;font-weight:600;'>IV Rank</div>
            <div style='font-size:0.9rem;font-weight:700;color:{iv_color};'>{ivr:.0f}%</div>
            <div style='font-size:0.6rem;color:#8B949E;margin-top:2px;'>{'ELEVATED — sell premium' if ivr>70 else 'CHEAP — buy premium' if ivr<30 else 'NORMAL'}</div>
            </div>""", unsafe_allow_html=True)
    with c3:
        pcr = od.get("put_call_ratio", 1.0)
        pcr_color = "#3FB950" if pcr < 0.8 else "#F85149" if pcr > 1.2 else "#8B949E"
        st.markdown(f"""<div style='background:#161B22;border:1px solid #30363D;border-radius:6px;padding:8px;'>
            <div style='font-size:0.55rem;color:#8B949E;text-transform:uppercase;font-weight:600;'>Put/Call</div>
            <div style='font-size:0.9rem;font-weight:700;color:{pcr_color};'>{pcr:.2f}</div>
            <div style='font-size:0.6rem;color:#8B949E;margin-top:2px;'>{'Bullish skew' if pcr<0.8 else 'Bearish skew' if pcr>1.2 else 'Balanced'}</div>
            </div>""", unsafe_allow_html=True)
    
    # MM positioning interpretation
    if od.get("call_wall") and od.get("put_wall"):
        cw, pw = od["call_wall"], od["put_wall"]
        st.caption(f"📊 **MM Positioning:** Range bound between Put Wall ${pw:.2f} (support) and Call Wall ${cw:.2f} (resistance). "
                   f"Above Vol Trigger ${(od.get('vol_trigger') or 0):.2f} = stable regime.")


def render_oi_heatmap(strikes_data: list):
    """Render simple OI bar visualization."""
    if not strikes_data:
        return
    st.markdown("**📊 OI Heatmap (Top 8 Strikes)**")
    max_oi = max(s.get("oi", 0) for s in strikes_data) if strikes_data else 1
    for s in strikes_data[:8]:
        oi = s.get("oi", 0)
        pct = (oi / max_oi * 100) if max_oi > 0 else 0
        side = s.get("type", "C")
        color = "#3FB950" if side == "C" else "#F85149"
        st.markdown(f"""<div style='display:flex;gap:6px;align-items:center;margin:2px 0;'>
            <span style='font-size:0.65rem;width:65px;color:#8B949E;font-weight:600;'>${(s.get('strike') or 0):.0f} {side}</span>
            <div style='flex:1;height:10px;background:#21262D;border-radius:2px;overflow:hidden;'>
                <div style='height:100%;width:{pct}%;background:{color};opacity:0.8;'></div>
            </div>
            <span style='font-size:0.65rem;width:55px;text-align:right;color:#E6EDF3;font-weight:700;'>{oi:,.0f}</span>
        </div>""", unsafe_allow_html=True)
