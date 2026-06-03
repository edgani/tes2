"""market_panels.py — COT, on-chain crypto, IHSG bandar widgets"""
import streamlit as st


def render_cot_panel(ticker: str, cot_data: dict = None):
    """Render COT positioning panel for Forex/Commodities."""
    if not cot_data:
        st.caption("COT data unavailable for this ticker")
        return
    
    c1, c2, c3 = st.columns(3)
    with c1:
        nc_long = cot_data.get("noncomm_long", 0)
        nc_short = cot_data.get("noncomm_short", 0)
        net = nc_long - nc_short
        net_color = "#3FB950" if net > 0 else "#F85149"
        st.markdown(f"""<div style='background:#161B22;border:1px solid #30363D;border-radius:6px;padding:8px;'>
            <div style='font-size:0.55rem;color:#8B949E;text-transform:uppercase;font-weight:600;'>Non-Comm Net</div>
            <div style='font-size:0.9rem;font-weight:700;color:{net_color};'>{net:+,.0f} contracts</div>
            <div style='font-size:0.6rem;color:#8B949E;margin-top:2px;'>L:{nc_long:,.0f} S:{nc_short:,.0f}</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        pct = cot_data.get("net_pct_oi", 0)
        pct_color = "#3FB950" if pct > 0 else "#F85149"
        st.markdown(f"""<div style='background:#161B22;border:1px solid #30363D;border-radius:6px;padding:8px;'>
            <div style='font-size:0.55rem;color:#8B949E;text-transform:uppercase;font-weight:600;'>Net % OI</div>
            <div style='font-size:0.9rem;font-weight:700;color:{pct_color};'>{pct:+.1f}%</div>
            <div style='font-size:0.6rem;color:#8B949E;margin-top:2px;'>Extreme: ±25%</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        chg = cot_data.get("week_chg", 0)
        chg_color = "#3FB950" if chg > 0 else "#F85149"
        st.markdown(f"""<div style='background:#161B22;border:1px solid #30363D;border-radius:6px;padding:8px;'>
            <div style='font-size:0.55rem;color:#8B949E;text-transform:uppercase;font-weight:600;'>Weekly Chg</div>
            <div style='font-size:0.9rem;font-weight:700;color:{chg_color};'>{chg:+,.0f}</div>
            <div style='font-size:0.6rem;color:#8B949E;margin-top:2px;'>Direction</div>
        </div>""", unsafe_allow_html=True)
    
    # Interpretation
    extreme = ""
    if pct > 25:
        extreme = "⚠️ **CROWDED LONG** — contrarian short signal"
    elif pct < -25:
        extreme = "⚠️ **CROWDED SHORT** — contrarian long signal"
    else:
        extreme = f"📊 Positioning normal ({pct:+.1f}% net)"
    st.caption(extreme)


def render_onchain_panel(ticker: str, onchain_data: dict = None):
    """Render on-chain analytics for crypto."""
    if not onchain_data:
        st.caption("On-chain data unavailable")
        return
    
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        whale = onchain_data.get("whale_accumulation_pct", 0)
        whale_color = "#3FB950" if whale > 0 else "#F85149"
        st.markdown(f"""<div style='background:#161B22;border:1px solid #30363D;border-radius:6px;padding:8px;'>
            <div style='font-size:0.55rem;color:#8B949E;text-transform:uppercase;'>Whale Accum (7d)</div>
            <div style='font-size:0.9rem;font-weight:700;color:{whale_color};'>{whale:+.1f}%</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        funding = onchain_data.get("funding_rate", 0)
        funding_color = "#F85149" if funding > 0.05 else "#3FB950" if funding < -0.02 else "#8B949E"
        st.markdown(f"""<div style='background:#161B22;border:1px solid #30363D;border-radius:6px;padding:8px;'>
            <div style='font-size:0.55rem;color:#8B949E;text-transform:uppercase;'>Funding 8h</div>
            <div style='font-size:0.9rem;font-weight:700;color:{funding_color};'>{funding:+.3f}%</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        oi = onchain_data.get("oi_change_7d", 0)
        st.markdown(f"""<div style='background:#161B22;border:1px solid #30363D;border-radius:6px;padding:8px;'>
            <div style='font-size:0.55rem;color:#8B949E;text-transform:uppercase;'>OI Chg 7d</div>
            <div style='font-size:0.9rem;font-weight:700;color:#E6EDF3;'>{oi:+.1f}%</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        ex_balance = onchain_data.get("exchange_balance_change", 0)
        ex_color = "#3FB950" if ex_balance < 0 else "#F85149"
        st.markdown(f"""<div style='background:#161B22;border:1px solid #30363D;border-radius:6px;padding:8px;'>
            <div style='font-size:0.55rem;color:#8B949E;text-transform:uppercase;'>Exch Outflow</div>
            <div style='font-size:0.9rem;font-weight:700;color:{ex_color};'>{-ex_balance:+.1f}%</div>
            <div style='font-size:0.55rem;color:#8B949E;'>+ = bullish HODL</div>
        </div>""", unsafe_allow_html=True)
    
    # Signal synthesis
    bullish_signals = sum([
        whale > 1,
        funding < 0.02,
        ex_balance < 0,
        oi > 5,
    ])
    if bullish_signals >= 3:
        st.success(f"✅ **ON-CHAIN BULLISH** ({bullish_signals}/4 signals)")
    elif bullish_signals <= 1:
        st.error(f"❌ **ON-CHAIN BEARISH** ({bullish_signals}/4 signals)")
    else:
        st.info(f"📊 On-chain mixed ({bullish_signals}/4 signals)")
    
    unlocks = onchain_data.get("upcoming_unlocks", [])
    if unlocks:
        st.caption(f"⏰ **Upcoming Unlocks:** {', '.join([str(u) for u in unlocks[:3]])}")


def render_bandar_panel(ticker: str, bandar_data: dict = None):
    """Render IHSG broker flow / bandar panel."""
    if not bandar_data:
        st.caption("Bandar data unavailable")
        return
    
    flow_signal = bandar_data.get("flow_signal", "UNCLEAR")
    confidence = bandar_data.get("confidence", 0)
    
    # Color coding
    sig_colors = {
        "ACCUMULASI_ASLI": "#3FB950",
        "DISTRIBUSI_ASLI": "#F85149",
        "FAKE_AKUM": "#D29922",
        "FAKE_DISTR": "#D29922",
        "FORCED_SELL": "#F85149",
        "WINDOW_DRESSING": "#A855F7",
        "UNCLEAR": "#8B949E",
    }
    color = sig_colors.get(flow_signal, "#8B949E")
    
    st.markdown(f"""<div style='background:#161B22;border:1px solid {color};border-radius:6px;padding:10px;margin:6px 0;'>
        <div style='font-size:0.6rem;color:#8B949E;text-transform:uppercase;font-weight:600;'>Broker Flow Signal</div>
        <div style='font-size:1rem;font-weight:800;color:{color};margin:4px 0;'>{flow_signal.replace('_', ' ')}</div>
        <div style='font-size:0.7rem;color:#E6EDF3;'>Confidence: {confidence:.0%}</div>
        <div style='font-size:0.65rem;color:#8B949E;margin-top:4px;'>{bandar_data.get('explanation', '')}</div>
    </div>""", unsafe_allow_html=True)
    
    # Top brokers
    top_buy = bandar_data.get("top_brokers_buy", [])
    top_sell = bandar_data.get("top_brokers_sell", [])
    if top_buy or top_sell:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Top Buyers**")
            for b in top_buy[:3]:
                st.caption(f"🟢 {b}")
        with c2:
            st.markdown("**Top Sellers**")
            for b in top_sell[:3]:
                st.caption(f"🔴 {b}")
    
    # Cornering signal
    cornering = bandar_data.get("cornering_signal", {})
    if cornering and cornering.get("detected"):
        st.warning(f"⚠️ **CORNERING DETECTED** — {cornering.get('thesis', '')}")
    
    # Goreng phase
    goreng = bandar_data.get("goreng_phase")
    if goreng:
        phase_colors = {
            "PHASE_1_AKUMULASI": "#3FB950",
            "PHASE_2_CORP_ACTION": "#58A6FF",
            "PHASE_3_LIQUIDITAS": "#D29922",
            "PHASE_4_EUFORIA": "#F85149",
        }
        pcolor = phase_colors.get(goreng, "#8B949E")
        st.markdown(f"<span style='background:rgba(168,85,247,0.12);color:{pcolor};padding:2px 8px;border-radius:10px;font-size:0.7rem;font-weight:700;'>🎯 {goreng.replace('_', ' ')}</span>", unsafe_allow_html=True)


def render_chain_reaction_panel(ticker: str, chain_data: dict = None):
    """Render correlation chain / front-run path."""
    if not chain_data:
        st.caption("No chain mapping")
        return
    
    parent_chains = chain_data.get("parent_chains", [])
    if parent_chains:
        st.markdown("**🔗 Correlation Drivers**")
        for ch in parent_chains[:3]:
            beta = ch.get("beta", 0)
            color = "#3FB950" if beta > 0 else "#F85149"
            direction = "↗" if ch.get("direction") == "SAME" else "↙"
            st.markdown(f"""<div style='background:#0D1117;border-left:3px solid {color};padding:6px 10px;margin:3px 0;border-radius:4px;'>
                <span style='font-weight:700;color:#E6EDF3;'>{ch.get('parent', '?')}</span>
                <span style='color:#8B949E;'>{direction} β={beta:.2f}, lag {ch.get('lag_days', 0)}d</span>
                <div style='font-size:0.65rem;color:#8B949E;margin-top:2px;'>{ch.get('thesis', '')}</div>
            </div>""", unsafe_allow_html=True)
