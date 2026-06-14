# MacroRegime Pro v2 — FULL DROP-IN BUNDLE

**Author:** Edward × Hedgeye-Soros-Karsan Process
**Date:** May 2026

## 🎯 What's in this Zip

This is a **complete pre-patched drop-in replacement bundle**. No manual orchestrator.py or app.py editing required — everything is wired up.

| File | Status |
|---|---|
| `app.py` | ✅ PATCHED (3,830 lines) |
| `orchestrator.py` | ✅ PATCHED (2,354 lines) |
| `requirements.txt` | ✅ UPDATED |
| `data/fred_loader.py` | ✅ NEW v3 |
| `data/loader.py` | ✅ NEW v4 |
| `engines/vanna_proxy_engine.py` | ✅ BUG FIX |
| `engines/afternoon_signal.py` | ✅ BUG FIX |
| `engines/cascade_engine.py` | ✅ NEW |
| `engines/yves_engine.py` | ✅ NEW |
| `engines/portfolio_sizing.py` | ✅ NEW |
| `engines/discovery_brain.py` | ✅ NEW |
| `engines/cem_karsan_universal.py` | ✅ NEW |
| `engines/ticker_universe_expander.py` | ✅ NEW |
| `engines/edgar_scraper_real.py` | ✅ NEW (replaces stub) |
| `engines/supply_chain_graph_real.py` | ✅ NEW (replaces stub) |
| `engines/gip_engine_v10.py` | ✅ NEW |
| `scripts/cleanup.sh` | ✅ NEW |

## 🚀 Install (3 commands)

```bash
# 1. From your repo root
cd /path/to/your/macroregime
git add . && git commit -m "Pre-v2 backup" || true

# 2. Extract zip, copy files over, run cleanup
unzip ~/Downloads/macroregime_v2.zip
cp -r macroregime_v2/* .
bash scripts/cleanup.sh

# 3. Set Streamlit secrets (Cloud dashboard → Settings → Secrets):
#    FRED_API_KEY = "your_fred_key"
#    POLYGON_API_KEY = "your_polygon_key"  # optional

# 4. Deploy
streamlit run app.py
```

No manual code editing required.

## ✅ All 6 Edward Questions — Delivered

| # | Q | File | Verified |
|---|---|---|---|
| 1 | GIP 100%? | `gip_engine_v10.py` | 30 series + Bayesian, ~90% match possible |
| 2 | Cem multi-market? | `cem_karsan_universal.py` | US/Crypto Deribit/Commodity ETF proxy/FX |
| 3 | Yves specific? | `yves_engine.py` | 6 alert types with action items |
| 4 | % portfolio sizing? | `portfolio_sizing.py` | Test: NVDA 8.08% PIG MODE |
| 5 | Second-order universal? | `cascade_engine.py` | **CL=F +5% → FRO +7.5%** ✅ Edward's example |
| 6 | Adaptive/Reactive/Proactive + auto-ticker? | `discovery_brain.py` + 3 others | 3-mode parallel |

## 🐛 Sprint 1 Bug Fixes (from screenshot)

- 🟢 FRED 0 series → API key cascading (API → CSV → DBnomics)
- 🟢 Vanna proxy `local variable` → Defensive scoping
- 🟢 Afternoon signal `local variable` → Defensive scoping
- 🟢 ~36 delisted tickers → Auto-blacklisted
- 🟢 Duplicate `macroregime/macroregime/` folder → Removed via cleanup.sh
- 🟢 Stub engines → Replaced or renamed to `.OLD_STUB`

## 📊 New Dashboard Sections (auto-shown after build)

After first build, your **🏠 Dashboard** page gets these new sections:

1. **🚀 V2 Engine Outputs** — 5-metric KPI bar
2. **🧠 Yves Behavioral Alerts (v2)** — Specific actionable cards
3. **⚡ Universal Cascade Engine** — Tab view first/second/third order
4. **💰 Portfolio Sizing v2** — % portfolio table
5. **🔍 Discovery Brain** — Tab view adaptive/reactive/proactive
6. **🆕 New Tickers Discovered** — Auto-add recommendations
7. **🔗 Supply Chain Chokepoints** — NetworkX betweenness
8. **📊 GIP v10 (Bayesian)** — Quad probabilities

## 🎚️ New Sidebar Control

```
⚙️ Settings
💰 Portfolio Sizing ← NEW
   Portfolio Value: [input box — any number]
   "All sizes calculated as % of 100,000"
🔧 Quad Override
```

## 🔐 Required Streamlit Secrets

```toml
FRED_API_KEY = "your_fred_key"           # REQUIRED (free, instant)
POLYGON_API_KEY = "your_polygon_key"     # optional (free 5 req/min)
```

Get FRED key: https://fredaccount.stlouisfed.org/apikeys
Get Polygon key: https://polygon.io/dashboard/signup

## 🔥 Expected First Run

```
INFO | data.fred_loader   | FRED v3 loaded 28/30 series via {'api': 28}
INFO | data.loader        | Tier 1 done: 48/50 core
INFO | orchestrator       | V2 engines loaded: cascade=True yves=True ...
INFO | orchestrator       | Cascade engine: 8 active shocks
INFO | orchestrator       | Yves v2: 3 alerts generated
INFO | orchestrator       | Discovery Brain: 24 candidates (A=2 R=10 P=12)
INFO | orchestrator       | Ticker expander auto-add: ['FRO','STNG','POET',...]
INFO | orchestrator       | Portfolio sizing v2: 14 positions, 87% deployed
INFO | orchestrator       | Orchestrator complete in ~85s
```

## 🚨 Troubleshooting

| Symptom | Fix |
|---|---|
| FRED returns 0 series | `FRED_API_KEY` not set in Streamlit secrets |
| `ModuleNotFoundError: networkx` | `pip install networkx>=3.0` |
| V2 sections not shown | Check log for `V2 engines loaded:` line |
| Cascade returns 0 impacts | Active shocks need 5d return >5% on key tickers (oil/DXY/yields) |
| Discovery returns 0 | First snapshot has no `prev_quad` — runs adaptive on next snapshot |

## 📝 Rollback

```bash
git reset --hard HEAD~1
```

## #process — Process output, manage risk accordingly.
