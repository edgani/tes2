"""app.py — MacroRegime Pro v40 (Clean Multi-Page Architecture)

Replaces legacy monolithic 412KB app.py with router pattern.

Pages:
  🏠 Dashboard         — KPIs, regime compass, Quad probs, news pulse
  ⚡ Alpha Center       — Curated surge candidates (5-layer filter)
  🇺🇸 US Stocks         — Tab1: Picks | Tab2: Front-Run
  💱 Forex             — Tab1: Picks (+COT) | Tab2: Front-Run
  🛢️ Commodities       — Tab1: Picks (+COT) | Tab2: Front-Run
  ₿ Crypto             — Tab1: Picks (+on-chain) | Tab2: Front-Run
  🇮🇩 IHSG              — Tab1: Picks (+bandar) | Tab2: Front-Run (+cornering)
  📖 Themes            — Scenario narratives + active themes
  📊 Portfolio Stress  — Stress test scenarios

Version: v40 — TRR/LRR v20.3b core
"""
import streamlit as st
import sys
import os

# Make sure local modules are importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

st.set_page_config(
    page_title="MacroRegime Pro v40",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ═══════════════════════════════════════════════════════════════════
# GLOBAL CSS — Dark Hedgeye theme
# ═══════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap");
html, body, [class*="css"] { font-family: "Inter", sans-serif; }
.block-container { padding-top: 0.5rem !important; padding-bottom: 0.5rem !important; padding-left: 1rem !important; padding-right: 1rem !important; max-width: 1500px !important; }
h1 { font-size: 1.4rem !important; margin: 0.2rem 0 0.3rem !important; font-weight: 800 !important; letter-spacing: -0.5px; }
h2 { font-size: 1.05rem !important; margin: 0.4rem 0 0.2rem !important; font-weight: 700 !important; }
h3 { font-size: 0.9rem !important; margin: 0.3rem 0 0.15rem !important; font-weight: 600 !important; }
hr { margin: 0.4rem 0 !important; opacity: 0.08; border-color: #30363D; }
[data-testid="stMetric"] { background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius: 6px; padding: 5px 8px !important; }
[data-testid="stMetricLabel"] { font-size: 0.58rem !important; font-weight: 600 !important; letter-spacing: 0.6px; text-transform: uppercase; opacity: 0.55; }
[data-testid="stMetricValue"] { font-size: 1.05rem !important; font-weight: 700 !important; }
.stTabs [data-baseweb="tab-list"] { gap: 2px !important; margin-bottom: 5px !important; }
.stTabs [data-baseweb="tab"] { padding: 4px 10px !important; font-size: 0.78rem !important; font-weight: 600 !important; border-radius: 6px 6px 0 0 !important; }
[data-testid="stExpander"] { border: 1px solid #30363D !important; border-radius: 8px !important; margin-bottom: 5px !important; }
[data-testid="stExpander"] > details > summary { padding: 7px 10px !important; font-size: 0.78rem !important; font-weight: 600 !important; }
/* Card spacing — prevent cramped/numpuk ticker cards across ALL tabs */
[data-testid="stVerticalBlockBorderWrapper"] { margin-bottom: 16px !important; }
[data-testid="stVerticalBlockBorderWrapper"] p { line-height: 1.5 !important; margin: 3px 0 !important; }
[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stCaptionContainer"] { margin: 2px 0 !important; line-height: 1.45 !important; }
[data-testid="stSidebar"] .block-container { padding-top: 0.6rem !important; }
.hy-card { background: #161B22; border: 1px solid #30363D; border-radius: 10px; margin: 4px 0; overflow: hidden; }
.metric-card { background: #161B22; border: 1px solid #30363D; border-radius: 8px; padding: 10px 12px; }
.narrative-card { background: #161B22; border-left: 3px solid #58A6FF; border-radius: 8px; padding: 10px 14px; margin: 6px 0; }
.alpha-card { background: #161B22; border-left: 3px solid #A855F7; border-radius: 8px; padding: 10px 14px; margin: 4px 0; }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════
# SESSION STATE INIT
# ═══════════════════════════════════════════════════════════════════
if "snap" not in st.session_state:
    st.session_state.snap = None
if "loading" not in st.session_state:
    st.session_state.loading = False
if "portfolio_value" not in st.session_state:
    st.session_state.portfolio_value = 100_000
if "mq_override" not in st.session_state:
    st.session_state.mq_override = "Auto"
if "page" not in st.session_state:
    st.session_state.page = "🏠 Dashboard"

# ═══════════════════════════════════════════════════════════════════
# SIDEBAR — Navigation + Controls
# ═══════════════════════════════════════════════════════════════════
def _quad_color(q):
    return {"Q1": "#3FB950", "Q2": "#D29922", "Q3": "#F85149", "Q4": "#A371F7"}.get(q, "#8B949E")


with st.sidebar:
    st.markdown("## 📊 MacroRegime Pro")
    st.caption("v40 · build s59 — real feeds (Type-F IDX + FRED NetLiq)")
    st.divider()
    
    page = st.radio("Navigation", [
        "🛰 Mission Control", "🌐 Regime & Flow", "⚡ Opportunity",
        "🗺 Market Intelligence", "🔬 Ticker Intelligence", "📊 Portfolio & Scenario",
    ], label_visibility="collapsed", key="page_radio")
    st.session_state.page = page
    
    st.divider()
    
    # Snapshot timestamp
    try:
        from data.loader import snapshot_age_str
        st.caption(f"Last update: {snapshot_age_str()}")
    except Exception:
        st.caption("Last update: unknown")
    
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔄 Update", width='stretch'):
            st.session_state.loading = True
    with c2:
        if st.button("⚡ Rebuild", width='stretch'):
            st.session_state.loading = True
            st.session_state.snap = None
    
    with st.expander("⚙️ Markets", expanded=False):
        st.checkbox("US Stocks", True, key="inc_us")
        st.checkbox("Forex", True, key="inc_fx")
        st.checkbox("Commodities", True, key="inc_comm")
        st.checkbox("Crypto", True, key="inc_cryp")
        st.checkbox("Indonesia", True, key="inc_ihsg")
    
    with st.expander("💰 Portfolio", expanded=False):
        pv = st.number_input("Value (USD)", min_value=1000, max_value=1_000_000_000,
                            value=int(st.session_state.portfolio_value), step=10_000, key="pv_input")
        st.session_state.portfolio_value = pv
    
    with st.expander("🔧 Quad Override", expanded=False):
        mq_ov = st.selectbox("Monthly Quad", ["Auto", "Q1", "Q2", "Q3", "Q4"],
                            index=["Auto", "Q1", "Q2", "Q3", "Q4"].index(st.session_state.mq_override))
        st.session_state.mq_override = mq_ov
    
    st.divider()
    
    # Current regime mini-display
    snap = st.session_state.snap
    if snap and snap.get("ok"):
        gip = snap.get("gip")
        if gip is not None:
            if isinstance(gip, dict):
                sq = gip.get("structural_quad", "—")
                mq = gip.get("monthly_quad", "—")
            else:
                sq = getattr(gip, "structural_quad", "—")
                mq = getattr(gip, "monthly_quad", "—")
            color = _quad_color(sq)
            st.markdown(f"""<div style='background:#161B22;border:1px solid #30363D;border-radius:8px;padding:10px;text-align:center;'>
                <div style='font-size:0.6rem;color:#8B949E;text-transform:uppercase;letter-spacing:0.5px;'>REGIME</div>
                <div style='font-size:1rem;font-weight:700;color:{color};margin:4px 0;'>{sq} / {mq}</div>
                <div style='font-size:0.55rem;color:#8B949E;'>Structural / Monthly</div>
            </div>""", unsafe_allow_html=True)
    else:
        st.caption("⏳ No snapshot yet — click Rebuild")

# ═══════════════════════════════════════════════════════════════════
# LOADING / ORCHESTRATOR HOOK
# ═══════════════════════════════════════════════════════════════════
def _load_snapshot():
    """Run orchestrator to build fresh snapshot."""
    try:
        from orchestrator import build_snapshot_v40
        progress_bar = st.progress(0, text="Initializing orchestrator…")
        
        def _cb(msg, pct):
            try:
                progress_bar.progress(min(int(pct), 100), text=msg)
            except Exception:
                pass
        
        snap = build_snapshot_v40(
            portfolio_value=st.session_state.portfolio_value,
            quad_override=st.session_state.mq_override,
            progress_cb=_cb,
        )
        progress_bar.empty()
        return snap
    except ImportError:
        # Fallback to legacy orchestrator
        try:
            from orchestrator import build_snapshot
            return build_snapshot(progress_cb=lambda m, p: None)
        except Exception as e:
            st.error(f"Failed to load orchestrator: {e}")
            return {"ok": False, "error": str(e)}

if st.session_state.loading or st.session_state.snap is None:
    with st.spinner("Building snapshot…"):
        st.session_state.snap = _load_snapshot()
        st.session_state.loading = False

snap = st.session_state.snap or {"ok": False}

# ═══════════════════════════════════════════════════════════════════
# PAGE ROUTER
# ═══════════════════════════════════════════════════════════════════
if not snap.get("ok"):
    st.error("⚠️ Snapshot build failed. Check logs and click Rebuild.")
    st.json(snap)
else:
    try:
        if page == "🛰 Mission Control":
            from pages_lib import mission_control
            mission_control.render(snap)
        elif page == "🌐 Regime & Flow":
            from pages_lib import regime_flow
            regime_flow.render(snap)
        elif page == "⚡ Opportunity":
            from pages_lib import opportunity
            opportunity.render(snap)
        elif page == "🗺 Market Intelligence":
            from pages_lib import market_intel
            market_intel.render(snap)
        elif page == "🔬 Ticker Intelligence":
            from pages_lib import ticker_intel
            ticker_intel.render(snap)
        elif page == "📊 Portfolio & Scenario":
            from pages_lib import portfolio_scenario
            portfolio_scenario.render(snap)
    except Exception as e:
        st.error(f"Page error: {e}")
        import traceback
        st.code(traceback.format_exc())
