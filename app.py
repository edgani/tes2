"""
app.py — MacroRegime War Room v40 (Redesigned Multi-Page Architecture)

Pages:
  🛰 Command Center      — Regime Pressure Map + Global Stress + What Changed
  ⚡ Opportunity Radar   — Tiered opportunities + Causal cards + Bubble map
  🗺 Bottleneck Map      — Interactive network graph + chain reactions
  🌊 Flow & Positioning  — Market-specific flow (US/Crypto/IHSG/Commodities/FX)
  📊 Market Internals   — 6 giant panels (breadth, credit, vol, liquidity, leadership, correlation)
  🎯 Execution Engine    — Market structure map + gamma walls + liquidity pockets
  🔬 Research Lab        — Walk forward, simulations, feature importance

Version: v40-WARROOM — Multi-Stage Filter + Tier System + Causal Intelligence
"""
import streamlit as st
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

st.set_page_config(
    page_title="MacroRegime War Room v40",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ═══════════════════════════════════════════════════════════════════
# GLOBAL CSS — Dark War Room Theme
# ═══════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Geist:wght@400;500;600;700&display=swap");
html, body, [class*="css"] { font-family: "Inter", "Geist", sans-serif; }
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
[data-testid="stVerticalBlockBorderWrapper"] { margin-bottom: 16px !important; }
[data-testid="stVerticalBlockBorderWrapper"] p { line-height: 1.5 !important; margin: 3px 0 !important; }
[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stCaptionContainer"] { margin: 2px 0 !important; line-height: 1.45 !important; }
[data-testid="stSidebar"] .block-container { padding-top: 0.6rem !important; }
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
    st.session_state.page = "🛰 Command Center"

# ═══════════════════════════════════════════════════════════════════
# SIDEBAR — Navigation + Controls
# ═══════════════════════════════════════════════════════════════════
def _quad_color(q):
    return {"Q1": "#3FB950", "Q2": "#D29922", "Q3": "#F85149", "Q4": "#A371F7"}.get(q, "#8B949E")

with st.sidebar:
    st.markdown("## 🎯 MacroRegime War Room")
    st.caption("v40-WARROOM · Probabilistic Battlefield Awareness")
    st.divider()

    page = st.radio("Navigation", [
        "🛰 Command Center",
        "⚡ Opportunity Radar",
        "🗺 Bottleneck Map",
        "🌊 Flow & Positioning",
        "📊 Market Internals",
        "🎯 Execution Engine",
        "🔬 Research Lab",
    ], label_visibility="collapsed", key="page_radio")
    st.session_state.page = page

    st.divider()

    try:
        from data.loader import snapshot_age_str
        st.caption(f"Last update: {snapshot_age_str()}")
    except Exception:
        st.caption("Last update: unknown")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔄 Update", use_container_width=True):
            st.session_state.loading = True
    with c2:
        if st.button("⚡ Rebuild", use_container_width=True):
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
        quad = snap.get("quad", "—")
        monthly = snap.get("monthly_quad", "—")
        color = _quad_color(quad)

        # Tier counts
        ft = snap.get("filtered_tickers", {})
        t1 = len(ft.get("tier1", []))
        t2 = len(ft.get("tier2", []))

        st.markdown(f"""
        <div style='background:#161B22;border:1px solid #30363D;border-radius:8px;padding:10px;text-align:center;margin-bottom:8px;'>
            <div style='font-size:0.6rem;color:#8B949E;text-transform:uppercase;letter-spacing:0.5px;'>REGIME</div>
            <div style='font-size:1rem;font-weight:700;color:{color};margin:4px 0;'>{quad} / {monthly}</div>
            <div style='font-size:0.55rem;color:#8B949E;'>Structural / Monthly</div>
        </div>
        <div style='display:flex;gap:4px;justify-content:center;'>
            <div style='background:#A371F722;border:1px solid #A371F7;border-radius:4px;padding:2px 6px;'>
                <span style='font-size:0.6rem;color:#A371F7;font-weight:700;'>T1: {t1}</span>
            </div>
            <div style='background:#58A6FF22;border:1px solid #58A6FF;border-radius:4px;padding:2px 6px;'>
                <span style='font-size:0.6rem;color:#58A6FF;font-weight:700;'>T2: {t2}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.caption("⏳ No snapshot yet — click Rebuild")

# ═══════════════════════════════════════════════════════════════════
# LOADING / ORCHESTRATOR HOOK
# ═══════════════════════════════════════════════════════════════════
def _load_snapshot():
    """Run orchestrator to build fresh snapshot."""
    try:
        from orchestrator import build_snapshot_v40
        progress_bar = st.progress(0, text="Initializing War Room...")

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
    except ImportError as e:
        st.error(f"Orchestrator import failed: {e}")
        return {"ok": False, "error": str(e)}
    except Exception as e:
        st.error(f"Failed to build snapshot: {e}")
        return {"ok": False, "error": str(e)}

if st.session_state.loading or st.session_state.snap is None:
    with st.spinner("Building War Room snapshot..."):
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
        from pages_lib.warroom_pages import render_page
        render_page(page, snap)
    except Exception as e:
        st.error(f"Page error: {e}")
        import traceback
        st.code(traceback.format_exc())
