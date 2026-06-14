"""portfolio_stress.py — Portfolio stress test scenarios"""
import streamlit as st

def render(snap):
    st.title("📊 Portfolio Stress Test")
    st.caption("Apply shock scenarios to your portfolio.")
    
    pv = st.session_state.get("portfolio_value", 100_000)
    st.metric("Portfolio Value", f"${pv:,.0f}")
    
    st.divider()
    
    st.subheader("🎯 Shock Scenarios")
    
    scenarios = [
        ("Oil +10%", "CL=F", 10.0, "Iran/OPEC supply shock"),
        ("Oil -10%", "CL=F", -10.0, "Demand crash / SPR release"),
        ("NVDA -15%", "NVDA", -15.0, "AI capex disappointment"),
        ("BTC +20%", "BTC-USD", 20.0, "ETF inflow + halving + risk-on"),
        ("BTC -25%", "BTC-USD", -25.0, "Macro liquidity crunch"),
        ("DXY +3%", "DX-Y.NYB", 3.0, "Fed hawkish surprise"),
        ("TLT -5%", "TLT", -5.0, "Term premium spike"),
        ("VIX → 35", "VIX", 35.0, "Vol regime change to F-bucket"),
    ]
    
    try:
        from engines.chain_reaction_v2 import get_chain_engine
        cre = get_chain_engine()
    except Exception:
        cre = None
    
    quad = snap.get("gip", {}).get("structural_quad", "Q3") if isinstance(snap.get("gip"), dict) else "Q3"
    
    selected = st.selectbox("Select scenario", [s[0] for s in scenarios])
    sc = next(s for s in scenarios if s[0] == selected)
    
    st.markdown(f"### Scenario: {sc[0]}")
    st.caption(sc[3])
    
    if cre and sc[1] not in ("VIX",):
        cascade = cre.calculate_cascade(sc[1], sc[2], current_quad=quad)
        
        st.markdown("#### 🌊 First Order Impact")
        first = cascade.get("first_order", [])
        if first:
            for item in first[:10]:
                pct = item.get("expected_pct", 0)
                color = "#3FB950" if pct > 0 else "#F85149"
                st.markdown(f"""<div style='background:#161B22;border-left:2px solid {color};padding:6px 10px;margin:3px 0;border-radius:4px;'>
                    <div style='display:flex;justify-content:space-between;'>
                        <span style='font-weight:700;color:#E6EDF3;'>{item['ticker']}</span>
                        <span style='color:{color};font-weight:700;'>{pct:+.2f}%</span>
                    </div>
                    <div style='font-size:0.65rem;color:#8B949E;'>{item.get('thesis', '')[:120]}</div>
                </div>""", unsafe_allow_html=True)
        
        if cascade.get("second_order"):
            with st.expander(f"🌊🌊 Second Order ({len(cascade['second_order'])} tickers)"):
                for item in cascade["second_order"][:15]:
                    pct = item.get("expected_pct", 0)
                    st.caption(f"{item['ticker']}: {pct:+.2f}% — {item.get('thesis', '')[:80]}")
        
        if cascade.get("third_order"):
            with st.expander(f"🌊🌊🌊 Third Order ({len(cascade['third_order'])} tickers)"):
                for item in cascade["third_order"][:10]:
                    pct = item.get("expected_pct", 0)
                    st.caption(f"{item['ticker']}: {pct:+.2f}%")
    elif sc[1] == "VIX":
        st.markdown("#### 🔥 VIX Spike Impact")
        from engines.hedgeye_position_sizing import classify_vix_bucket
        vb = classify_vix_bucket(sc[2])
        st.warning(f"⚠️ VIX → {sc[2]} → **{vb['bucket']} BUCKET** ({vb['label']})")
        st.write(f"Position size multiplier: **{vb['multiplier']}x**")
        st.write(f"Max single position: **{vb['max_position_pct']}%**")
