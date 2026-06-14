# MacroRegime Pro v2 — Orchestrator Integration Patches

**Apply these changes to your existing `orchestrator.py` after dropping in the new files.**

All new engines are designed to be backwards-compatible. Old engines stay in place; new engines added next to them. Orchestrator imports get updated to point to new versions for the upgraded flows.

---

## Step 1 — Run cleanup script

```bash
cd <your-repo-root>
bash scripts/cleanup.sh
```

This will:
- Remove the nested duplicate `macroregime/macroregime/` folder
- Remove the literal-named `{config,data,engines,ui` folder  
- Rename stub engines to `.OLD_STUB` (preserved as backup)
- Clear `__pycache__` and stale snapshots

---

## Step 2 — Drop new files into repo

Place files at these paths (preserving directory structure):

```
data/fred_loader.py                    ← REPLACES existing
data/loader.py                          ← REPLACES existing
engines/vanna_proxy_engine.py           ← REPLACES existing (bug fix)
engines/afternoon_signal.py             ← REPLACES existing (bug fix)
engines/cascade_engine.py               ← NEW
engines/yves_engine.py                  ← NEW
engines/portfolio_sizing.py             ← NEW (extends conviction_sizing.py)
engines/discovery_brain.py              ← NEW (extends auto_discovery_engine_v3.py)
engines/cem_karsan_universal.py         ← NEW
engines/ticker_universe_expander.py     ← NEW
engines/edgar_scraper_real.py           ← REPLACES stub
engines/supply_chain_graph_real.py      ← REPLACES stub
engines/gip_engine_v10.py               ← NEW (keep gip_engine.py as fallback)
```

---

## Step 3 — Update `orchestrator.py` imports

### 3a. Add imports near the top of orchestrator.py (around line 90-230 with other engine imports):

```python
# ═══ Sprint 1-4 New Engines ═══
try:
    from engines.cascade_engine import run_cascade_from_shock, run_all_cascades, bottleneck_full_cascade
except Exception as e:
    logger.error(f"Failed to import cascade_engine: {e}")
    def run_cascade_from_shock(*a, **k): return {}
    def run_all_cascades(*a, **k): return {}
    def bottleneck_full_cascade(*a, **k): return {}

try:
    from engines.yves_engine import run_yves_v2
except Exception as e:
    logger.error(f"Failed to import yves_engine: {e}")
    def run_yves_v2(*a, **k): return {"alerts": [], "summary": {}}

try:
    from engines.portfolio_sizing import run_portfolio_sizing
except Exception as e:
    logger.error(f"Failed to import portfolio_sizing: {e}")
    def run_portfolio_sizing(*a, **k): return {"positions": [], "total_deployed_pct": 0}

try:
    from engines.discovery_brain import run_discovery_brain
except Exception as e:
    logger.error(f"Failed to import discovery_brain: {e}")
    def run_discovery_brain(*a, **k): return {"by_mode": {}, "top_10": []}

try:
    from engines.cem_karsan_universal import analyze_multi as cem_universal_multi
except Exception as e:
    logger.error(f"Failed to import cem_karsan_universal: {e}")
    def cem_universal_multi(*a, **k): return {}

try:
    from engines.ticker_universe_expander import run_ticker_expander
except Exception as e:
    logger.error(f"Failed to import ticker_universe_expander: {e}")
    def run_ticker_expander(*a, **k): return {"new_tickers": [], "candidates": []}

try:
    from engines.edgar_scraper_real import scan_multi_tickers as edgar_scan_multi
except Exception as e:
    logger.error(f"Failed to import edgar_scraper_real: {e}")
    def edgar_scan_multi(*a, **k): return {}

try:
    from engines.supply_chain_graph_real import run_supply_chain_analysis
except Exception as e:
    logger.error(f"Failed to import supply_chain_graph_real: {e}")
    def run_supply_chain_analysis(*a, **k): return {"chokepoints": [], "propagation": {}}

try:
    from engines.gip_engine_v10 import gip_engine_v10 as gip_v10
    GIP_V10_AVAILABLE = True
except Exception as e:
    logger.error(f"Failed to import gip_engine_v10: {e}")
    GIP_V10_AVAILABLE = False
```

### 3b. In `build_snapshot()` after the existing GIP call, add v10 layer:

Find the section that runs `gip = gip_engine(...)`. After that block, add:

```python
# Sprint 4: Upgrade to v10 if available
if GIP_V10_AVAILABLE:
    try:
        v10 = gip_v10(fred, vix_last=vix_last)
        result["gip_v10"] = {
            "structural_quad": v10.structural_quad,
            "monthly_quad": v10.monthly_quad,
            "structural_confidence": v10.structural_confidence,
            "monthly_confidence": v10.monthly_confidence,
            "growth_momentum": v10.growth_momentum,
            "inflation_momentum": v10.inflation_momentum,
            "nowcast_growth_adj": v10.nowcast_growth_adj,
            "nowcast_inflation_adj": v10.nowcast_inflation_adj,
            "quad_probabilities": v10.quad_probabilities,
            "features": v10.features,
            "n_series_loaded": v10.features.get("n_series_loaded", 0),
        }
    except Exception as e:
        logger.warning(f"GIP v10 failed: {e}")
        result["errors"].append(f"gip_v10: {e}")
```

### 3c. Add cascade engine call (replaces interconnect-only):

Find the section where `interconnect_engine` is called. After it, add:

```python
# Sprint 2: Universal Cascade Engine
try:
    cascade = run_all_cascades(prices)
    result["cascade_analysis"] = cascade
except Exception as e:
    logger.warning(f"Cascade engine failed: {e}")
    result["errors"].append(f"cascade: {e}")
```

### 3d. Add Yves v2:

After the existing AAII / behavioral macro call:

```python
# Sprint 2: Yves Alerts v2 (specific actionable)
try:
    yves_v2 = run_yves_v2(
        aaii=aaii_data,
        vix=vix_last,
        real_yield=real_yield,
        put_call=put_call_ratio if "put_call_ratio" in dir() else 1.0,
        prices=prices,
        fred=fred,
    )
    result["yves_v2"] = yves_v2
except Exception as e:
    logger.warning(f"Yves v2 failed: {e}")
```

### 3e. Add Cem Universal:

Replace the limited (3-ticker) yfinance options call with universal:

```python
# Sprint 3: Cem Karsan Universal Multi-Market
try:
    cem_targets = ["SPY", "QQQ", "IWM", "GLD", "TLT", "BTC-USD", "ETH-USD",
                   "USO", "UNG", "FXE", "EEM"]
    cem_universal_data = cem_universal_multi(cem_targets, prices, vix_last, max_yfinance=8)
    result["cem_karsan_universal"] = cem_universal_data
except Exception as e:
    logger.warning(f"Cem Karsan Universal failed: {e}")
```

### 3f. Add Discovery Brain (replaces auto_discovery):

```python
# Sprint 3: Discovery Brain (Adaptive + Reactive + Proactive)
try:
    prev_quad = (cache_get_last_quad() or None)  # implement based on your cache
    discovery = run_discovery_brain(
        prices=prices,
        news_analysis=news_analysis,
        gip_features=result.get("gip", {}).get("features", {}),
        current_quad=result.get("gip", {}).get("structural_quad", "Q3"),
        monthly_quad=result.get("gip", {}).get("monthly_quad", "Q3"),
        prev_quad=prev_quad,
        cot_data=result.get("cot_data"),
        bottleneck_ref=bottleneck_reference,
    )
    result["discovery_brain"] = discovery
except Exception as e:
    logger.warning(f"Discovery Brain failed: {e}")
```

### 3g. Add Ticker Universe Expander:

```python
# Sprint 3: Auto-discover new tickers not in universe
try:
    current_universe = list(prices.keys())
    expansion = run_ticker_expander(
        prices=prices,
        news_analysis=news_analysis,
        current_universe=current_universe,
        cascade_results=result.get("cascade_analysis"),
        bottleneck_ref=bottleneck_reference,
    )
    result["ticker_universe_expansion"] = expansion
    
    # Optional: auto-add high-confidence new tickers to next snapshot
    auto_add = expansion.get("auto_add_recommended", [])
    if auto_add:
        result["auto_add_tickers_next_run"] = auto_add
        logger.info(f"Auto-add recommended for next run: {auto_add[:10]}")
except Exception as e:
    logger.warning(f"Ticker expander failed: {e}")
```

### 3h. Add Portfolio Sizing v2:

After alpha generation, replace `conviction_sizing.run_sizing(...)`:

```python
# Sprint 2: Portfolio Sizing v2 (% of portfolio, Kelly, sector caps)
try:
    portfolio_value = result.get("portfolio_value", 100_000)  # User input from UI
    sized = run_portfolio_sizing(
        alpha_items=alpha_ideas,
        portfolio_value=portfolio_value,
        quad=result.get("gip", {}).get("structural_quad", "Q3"),
        stage=result.get("boom_bust", {}).get("stage", "INCEPTION"),
        gamma_data=result.get("gamma_data"),
        greeks_data=result.get("greeks_data"),
        reflexivity=result.get("reflexivity"),
        current_positions=result.get("current_positions", {}),
    )
    result["portfolio_sizing_v2"] = sized
except Exception as e:
    logger.warning(f"Portfolio sizing v2 failed: {e}")
```

---

## Step 4 — `app.py` UI additions

Add to your sidebar in `app.py`:

```python
# Portfolio size input (any value — user choice)
portfolio_value = st.sidebar.number_input(
    "💰 Portfolio Value (any unit)",
    min_value=1000,
    max_value=1_000_000_000,
    value=100_000,
    step=10_000,
    help="Sizes are output as % of this. Currency doesn't matter."
)
st.session_state["portfolio_value"] = portfolio_value
```

Then in the orchestrator call, pass `portfolio_value` through.

For displaying new tabs/sections, add:

```python
# Cascade Tab
if "cascade_analysis" in snap:
    with st.expander("⚡ Cascade Analysis (Second-Order Mapping)"):
        cascade = snap["cascade_analysis"]
        st.write(f"Active shocks: {cascade.get('active_shocks')}")
        for shock, data in cascade.get("cascades", {}).items():
            st.subheader(f"Shock: {shock}")
            tabs = st.tabs(["First Order", "Second Order", "Third Order"])
            for i, key in enumerate(("first_order", "second_order", "third_order")):
                with tabs[i]:
                    rows = data.get(key, [])
                    if rows:
                        st.dataframe(pd.DataFrame(rows))

# Yves V2 Tab  
if "yves_v2" in snap:
    with st.expander("🧠 Yves Behavioral Alerts (v2 — Specific Actionable)"):
        for alert in snap["yves_v2"].get("alerts", []):
            color = {"CRITICAL": "🔴", "OPPORTUNITY": "🟢", "WARNING": "🟡",
                     "CAUTION": "🟠", "NEUTRAL": "⚪"}.get(alert["level"], "⚪")
            st.markdown(f"### {color} {alert['title']}")
            st.write(f"**Specifics:** {alert['specifics']}")
            st.write("**Actions:**")
            for action in alert.get("action", []):
                st.write(f"  • {action}")
            st.caption(f"**Invalidation:** {alert.get('invalidation', '—')}")
            st.caption(f"**Time horizon:** {alert.get('time_horizon', '—')}")

# Portfolio Sizing v2 Tab
if "portfolio_sizing_v2" in snap:
    with st.expander("💰 Portfolio Sizing v2 (% of Portfolio)"):
        sized = snap["portfolio_sizing_v2"]
        st.metric("Total Deployed", f"{sized['total_deployed_pct']:.1%}")
        st.metric("Cash %", f"{sized['cash_pct']:.1%}")
        st.dataframe(pd.DataFrame(sized["positions"]))

# Discovery Brain Tab
if "discovery_brain" in snap:
    with st.expander("🔍 Discovery Brain (Adaptive / Reactive / Proactive)"):
        disc = snap["discovery_brain"]
        tabs = st.tabs(["Adaptive", "Reactive", "Proactive"])
        for i, mode in enumerate(("adaptive", "reactive", "proactive")):
            with tabs[i]:
                items = disc.get("by_mode", {}).get(mode, [])
                for item in items[:10]:
                    st.markdown(f"**{item['name']}** (confidence: {item['confidence']:.0%})")
                    st.write(item['thesis'])
                    if item.get("beneficiary_tickers"):
                        st.write(f"**Long:** {', '.join(item['beneficiary_tickers'][:5])}")
                    if item.get("fade_tickers"):
                        st.write(f"**Fade:** {', '.join(item['fade_tickers'][:5])}")

# Ticker Universe Expansion Tab
if "ticker_universe_expansion" in snap:
    with st.expander("🆕 New Tickers Discovered"):
        exp = snap["ticker_universe_expansion"]
        st.write(f"**{exp['summary']}**")
        if exp.get("auto_add_recommended"):
            st.success(f"Auto-add recommended: {', '.join(exp['auto_add_recommended'])}")
        st.dataframe(pd.DataFrame(exp["candidates"][:30]))
```

---

## Step 5 — Add Streamlit Secrets

In Streamlit Cloud → Settings → Secrets, add:

```toml
FRED_API_KEY = "your_fred_api_key_here"
POLYGON_API_KEY = "your_polygon_key_here"  # optional, free tier OK
```

Get FRED key: https://fredaccount.stlouisfed.org/apikeys (free, instant)
Get Polygon key: https://polygon.io/dashboard/signup (free tier 5 req/min)

---

## Step 6 — Verify Deployment

```bash
streamlit run app.py
```

Expected log output (success):
```
INFO  | data.fred_loader | FRED v3 loaded 28/30 series via {'api': 28}
INFO  | data.loader      | Tier 1 done: 48/50 core
INFO  | data.loader      | Tier 2 done: 142/200 secondary
INFO  | orchestrator     | Cascade engine: 8 active shocks detected
INFO  | orchestrator     | Yves v2: 3 alerts generated
INFO  | orchestrator     | Discovery Brain: 24 candidates (adaptive=2, reactive=10, proactive=12)
INFO  | orchestrator     | Ticker expander: 18 new candidates discovered
INFO  | orchestrator     | Portfolio sizing v2: 14 positions, 87% deployed
INFO  | orchestrator     | Orchestrator complete in ~90s
```

If FRED still returns 0 series → FRED_API_KEY not properly set in secrets.

---

## Rollback Plan

If anything breaks, restore old files from your git history:

```bash
git checkout HEAD~1 -- data/fred_loader.py data/loader.py engines/vanna_proxy_engine.py engines/afternoon_signal.py
```

Then disable new imports by adding at the top of orchestrator.py:

```python
DISABLE_V2_ENGINES = True  # emergency rollback
```

And gate each new try/except block with `if not DISABLE_V2_ENGINES:`.
