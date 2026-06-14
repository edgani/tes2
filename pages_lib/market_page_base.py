"""market_page_base.py — Generic 2-tab market page v40.3 (Picks + Front-Run)

Per Edward's strict spec:
  • Tab 1: Picks (Hedgeye-style) — ticker rekomendasi dengan TRR/LRR + phase + entry zone + 
    options/Greeks/MM positioning (or COT/on-chain/bandar tergantung market)
  • Tab 2: Front-Run — ticker yang sedang di-setup untuk front-running based on chain reactions

Used by US Stocks, Forex, Commodities, Crypto, IHSG with their specific overlays:
  • US: show_options=True
  • Forex: show_cot=True
  • Commodities: show_options=True + show_cot=True
  • Crypto: show_onchain=True (+ optional options)
  • IHSG: show_bandar=True (NO options/greeks per Edward)
"""
import streamlit as st
from components.rich_ticker_card import render_rich_ticker


COMMODITY_ETFS = {"USO", "GLD", "SLV", "UNG", "CPER", "DBC", "XOP", "OIH", "GDX", "GDXJ",
                  "USL", "BNO", "UGA", "DBA", "CORN", "WEAT", "PALL", "PPLT", "IAU", "SIVR"}
FOREX_PROXIES = {"DX-Y.NYB", "UUP", "FXE", "FXY", "FXB", "UDN", "FXA", "FXC", "FXF", "CYB"}


def _market_match(ticker: str, market_key: str) -> bool:
    """Filter tickers belonging to this market. Specific markets checked before us_equity."""
    t = ticker.upper()
    is_jk = ".JK" in t or t in ("^JKSE", "EIDO")
    is_fx = "=X" in t or t in FOREX_PROXIES
    is_comm = "=F" in t or t in COMMODITY_ETFS
    is_crypto = "-USD" in t and t.split("-")[0] not in ("DX",)
    is_index = t.startswith("^") and t not in ("^JKSE",)

    if market_key == "forex":
        return is_fx
    elif market_key == "commodity":
        return is_comm
    elif market_key == "crypto":
        return is_crypto
    elif market_key == "ihsg":
        return is_jk
    elif market_key == "us_equity":
        # us_equity = NOT any other market, and not a raw index symbol
        return not (is_jk or is_fx or is_comm or is_crypto or is_index)
    return False


def render_market_page(
    snap: dict,
    market_key: str,
    title: str,
    icon: str,
    show_options: bool = False,
    show_cot: bool = False,
    show_onchain: bool = False,
    show_bandar: bool = False,
    show_oi: bool = False,
):
    st.title(f"{icon} {title}")

    rr_data = snap.get("risk_range", {}).get("asset_ranges", {}) if isinstance(snap.get("risk_range"), dict) else {}

    # Build rows for THIS market only
    market_tickers = [t for t in rr_data.keys() if _market_match(t, market_key)]
    market_rrs = {t: rr_data[t] for t in market_tickers if isinstance(rr_data[t], dict)}

    if not market_rrs:
        st.warning(f"No {market_key} tickers with TRR/LRR data in current snapshot. Click Rebuild.")
        return

    # ── KPI summary ──────────────────────────────────────────────────────
    actions = [rr.get("signals", {}).get("action", "HOLD") for rr in market_rrs.values()]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tickers", len(market_rrs))
    c2.metric("BUY/ADD", sum(1 for a in actions if a in ("BUY_DIP", "ADD")))
    c3.metric("TRIM", sum(1 for a in actions if a in ("TRIM", "TRIM_RIP")))
    c4.metric("A-grade", sum(1 for rr in market_rrs.values() if rr.get("signals", {}).get("quality", "C").startswith("A")))

    st.divider()

    # ── 2 TABS: Picks + Front-Run ────────────────────────────────────────
    tab1, tab2 = st.tabs(["🎯 Picks (Hedgeye-style)", "🔮 Front-Run (Pre-positioning)"])

    with tab1:
        _render_picks_tab(market_rrs, snap, market_key, show_options, show_cot, show_onchain, show_bandar, show_oi)

    with tab2:
        _render_frontrun_tab(market_rrs, snap, market_key, show_options, show_cot, show_onchain, show_bandar, show_oi)


# ═══════════════════════════════════════════════════════════════════════════
# TAB 1: PICKS
# ═══════════════════════════════════════════════════════════════════════════

def _render_picks_tab(market_rrs, snap, market_key, show_options, show_cot, show_onchain, show_bandar, show_oi=False):
    """Hedgeye-style picks — sorted by R/R, grouped by long/short/monitor."""

    # Convert to sortable list
    items = []
    for t, rr in market_rrs.items():
        sig = rr.get("signals", {})
        items.append({
            "ticker": t, "rr": rr, "action": sig.get("action", "HOLD"),
            "quality": sig.get("quality", "C"),
            "rr_ratio": sig.get("rr_ratio", 0) or 0,
            "dist_to_lrr": sig.get("distance_to_lrr_pct", 0) or 0,
        })

    # ── ELEVATION: regime-gated confluence score (quad-fit × structure × timing ×
    # overlays, with hard vetoes). Fully optional — any failure leaves items unscored
    # and the page falls back to the existing R/R sort (non-regressive). ──
    try:
        from engines.confluence_scorer import score_ticker
        _sm = snap.get("summary", {}) if isinstance(snap, dict) else {}
        _q = _sm.get("structural_quad", "Q3")
        _qm = _sm.get("monthly_quad") or _sm.get("monthly", "Q2")
        _vix = (snap.get("vix", 20.0) or 20.0) if isinstance(snap, dict) else 20.0
        _gexmap = snap.get("gex", {}) if isinstance(snap, dict) else {}
        for it in items:
            try:
                sc = score_ticker(it["ticker"], _q, _qm, _vix,
                                  rr=it["rr"], gex=_gexmap.get(it["ticker"]))
                it["confluence"] = sc["score"]
                it["confluence_verdict"] = sc["verdict"]
            except Exception:
                it["confluence"] = None
            # All markets: fold bandarmetrics accumulation/stealth into the rank (±12 pts) + tag stealth
            try:
                from engines.bandarmetrics_engine import signal_adjustment
                _bm = (snap.get("bandarmetrics", {}) or {}).get(it["ticker"], {})
                if _bm.get("ok"):
                    _adj = signal_adjustment(_bm) * 12.0
                    it["confluence"] = (it.get("confluence") if it.get("confluence") is not None else 50.0) + _adj
                    it["bandarmetrics_adj"] = round(_adj, 1)
                    it["bandarmetrics_div"] = _bm.get("divergence")
                    _stl = _bm.get("stealth_accumulation") or {}
                    it["stealth_score"] = _stl.get("score", 0)
                    it["is_stealth"] = _stl.get("is_stealth", False)
                    it["ignition"] = (_bm.get("ignition") or {}).get("ignition", False)
            except Exception:
                pass
    except Exception:
        pass

    # Sort options
    sort_by = st.selectbox(
        "Sort", ["🎯 Confluence (regime-gated)", "🤫 Hidden Accumulation", "Best R/R",
                 "Distance to LRR (closest first)", "Quality (A+ first)"],
        key=f"sort_picks_{market_key}",
    )
    if sort_by == "🤫 Hidden Accumulation":
        items.sort(key=lambda x: -(x.get("stealth_score") or 0))
    if sort_by == "🎯 Confluence (regime-gated)":
        items.sort(key=lambda x: -(x.get("confluence") if x.get("confluence") is not None else -1))
    elif sort_by == "Best R/R":
        items.sort(key=lambda x: -x["rr_ratio"])
    elif sort_by == "Distance to LRR (closest first)":
        items.sort(key=lambda x: abs(x["dist_to_lrr"]))
    else:
        q_rank = {"A+": 0, "A": 1, "short_A+": 1.5, "short_A": 2, "B": 3, "C": 4}
        items.sort(key=lambda x: q_rank.get(x["quality"], 5))

    # IHSG-only rule: convert SHORT to WATCH
    is_ihsg = market_key == "ihsg"
    if is_ihsg:
        for it in items:
            if it["action"] in ("SHORT_RIP", "COVER"):
                it["action"] = "WATCH"

    # Group by DIRECTIONAL BIAS (not just immediate timing action), so a bull-trend
    # ticker at mid-range still shows as a Long candidate (timing = HOLD) instead of
    # vanishing into Monitor. Bias from phase + formation.
    def _bias(it):
        rr = it["rr"]
        phase = rr.get("phase", "NEUTRAL")
        formation = rr.get("signals", {}).get("formation", "NEUTRAL")
        action = it["action"]
        if action in ("BUY_DIP", "ADD"):
            return "long"
        if action in ("SHORT_RIP", "COVER"):
            return "short"
        # Directional bias fallback
        if phase == "BULL" or formation == "BULLISH":
            return "long"
        if phase == "BEAR" or formation == "BEARISH":
            return "short" if not is_ihsg else "monitor"
        return "monitor"

    longs = [it for it in items if _bias(it) == "long"]
    shorts = [] if is_ihsg else [it for it in items if _bias(it) == "short"]
    monitor = [it for it in items if _bias(it) == "monitor"]

    # Sub-tabs — IHSG uses "Akumulasi" instead of "Long" (buy-only market)
    # Sort longs by signal strength (strongest bull first), shorts by strongest bear
    # ── KEITH ENTRY-QUALITY SORT (Hedgeye methodology) ──────────────────
    # Keith: BUY at the LOW end of the range (LRR), SELL/TRIM at the top (TRR).
    # "Ride the trend, but DON'T chase overbought names." So the most ACTIONABLE
    # longs = bullish names pulled back toward LRR (low range position), NOT the
    # ones breaking out to new highs (HH = overbought = trim, don't chase).
    def _range_pos(it):
        rr = it.get("rr", {})
        t = rr.get("trade", {}) or {}
        lrr = t.get("lrr", 0) or 0; trr = t.get("trr", 0) or 0; px = rr.get("px", 0) or 0
        w = trr - lrr
        return (px - lrr) / w if w > 0 else 0.5  # 0 = at LRR (best buy), 1 = at TRR (don't chase)
    def _phase(it):
        return it.get("rr", {}).get("phase_code", 0)
    # Longs: actionable BUYS first → low range pos (near LRR), bullish trend as tiebreak.
    # Overbought longs (high pos, "don't chase") sink to the bottom.
    longs.sort(key=lambda it: (_range_pos(it), -_phase(it)))
    # Shorts: best SHORTS first → high range pos (ripped to TRR = sell-the-rip).
    shorts.sort(key=lambda it: (-_range_pos(it), _phase(it)))

    # ── KEITH QUALITY FILTER (avoid 100 garbage ideas) ───────────────────
    # Keith: cleanest signal = Bullish TRADE+TREND + Higher Highs + Higher Lows.
    # Our quality grade A/A+ = bull_form (px>TREND TRR & px>TAIL TRR = HH across
    # durations) + bull trend. short_A/short_A+ = the bearish mirror. Default ON.
    def _qual(it):
        return (it.get("rr", {}).get("signals", {}) or {}).get("quality", "C")
    quality_only = st.checkbox(
        "✅ Quality only — Keith-grade setups (Bullish TRADE+TREND + Higher-Highs/Lows). "
        "Matiin buat liat semua.", value=True, key=f"qual_{market_key}")
    if quality_only:
        longs_q = [it for it in longs if _qual(it) in ("A+", "A")]
        shorts_q = [it for it in shorts if _qual(it) in ("short_A+", "short_A")]
        # If filter empties a bucket, fall back to B-grade so it's not blank
        longs = longs_q or [it for it in longs if _qual(it) in ("A+", "A", "B")]
        shorts = shorts_q or [it for it in shorts if _qual(it) in ("short_A+", "short_A", "B")]
        st.caption(f"🎯 Quality filter ON: {len(longs)} long · {len(shorts)} short "
                   f"(A/A+ Keith-grade). Sisanya disembunyiin.")

    long_label = "🟢 Akumulasi" if is_ihsg else "🟢 Long"
    if is_ihsg:
        sub_long, sub_mon = st.tabs([f"{long_label} ({len(longs)})", f"🟡 Monitor ({len(monitor)})"])
        with sub_long:
            st.caption("📋 Saham di bullish TREND (Keith-style inventory). Timing entry per-card (BUY_DIP/ADD/HOLD). Diurutkan dari signal strength terkuat.")
            if not longs:
                st.caption("Belum ada saham di zona akumulasi sekarang.")
            for it in longs[:25]:
                render_rich_ticker(it["ticker"], it["rr"], snap, market_key,
                                   show_options=show_options, show_cot=show_cot,
                                   show_onchain=show_onchain, show_bandar=show_bandar, show_oi=show_oi)
        with sub_mon:
            for it in monitor[:30]:
                render_rich_ticker(it["ticker"], it["rr"], snap, market_key,
                                   show_options=show_options, show_cot=show_cot,
                                   show_onchain=show_onchain, show_bandar=show_bandar, show_oi=show_oi)
        return

    sub_long, sub_short, sub_mon = st.tabs(
        [f"{long_label} ({len(longs)})", f"🔴 Short ({len(shorts)})", f"🟡 Monitor ({len(monitor)})"]
    )
    with sub_long:
        st.caption("📋 Names di bullish TREND (Keith-style inventory). Per Keith: kalau cuma sedikit signal bearish, 'slim pickings on short side' → wajar banyak long. Timing per-card. Diurutkan signal strength terkuat dulu.")
        if not longs:
            st.caption("No long picks active right now.")
        for it in longs[:25]:
            render_rich_ticker(it["ticker"], it["rr"], snap, market_key,
                               show_options=show_options, show_cot=show_cot,
                               show_onchain=show_onchain, show_bandar=show_bandar, show_oi=show_oi)
    with sub_short:
        if not shorts:
            st.caption("No short picks active right now.")
        for it in shorts[:25]:
            render_rich_ticker(it["ticker"], it["rr"], snap, market_key,
                               show_options=show_options, show_cot=show_cot,
                               show_onchain=show_onchain, show_bandar=show_bandar, show_oi=show_oi)
    with sub_mon:
        for it in monitor[:30]:
            render_rich_ticker(it["ticker"], it["rr"], snap, market_key,
                               show_options=show_options, show_cot=show_cot,
                               show_onchain=show_onchain, show_bandar=show_bandar, show_oi=show_oi)


# ═══════════════════════════════════════════════════════════════════════════
# TAB 2: FRONT-RUN
# ═══════════════════════════════════════════════════════════════════════════

def _render_frontrun_tab(market_rrs, snap, market_key, show_options, show_cot, show_onchain, show_bandar, show_oi=False):
    """Front-Run tab — tickers being set up for front-running based on:
       (a) Active chain reactions (driver shocks → impact on this market)
       (b) Quad transition setups (tickers favored by NEXT quad)
    """
    st.markdown("### 🔮 Front-Run Candidates")
    st.caption(
        "Front-Run = ticker yang sedang di-set up untuk move karena: "
        "(1) chain reaction dari driver shock, ATAU (2) quad transition akan benefit ticker ini."
    )

    market_tickers = set(market_rrs.keys())

    # ── (A) Active chain reaction transmissions ───────────────────────────
    transmissions = snap.get("transmissions", {})
    active = transmissions.get("active_transmissions", []) if isinstance(transmissions, dict) else []

    chain_candidates = []
    try:
        from engines.chain_reaction_v2 import get_chain_engine
        cre = get_chain_engine()
    except Exception:
        cre = None

    for t_active in active:
        driver = t_active.get("shock_ticker") or t_active.get("driver") or ""
        shock = t_active.get("shock_pct", 0)
        cascade = t_active.get("cascade", {})
        for impact_list in (cascade.get("first_order", []), cascade.get("second_order", [])):
            for impact in impact_list:
                tic = impact.get("ticker")
                if tic in market_tickers:
                    chain_candidates.append({
                        "ticker": tic, "driver": driver, "shock_pct": shock,
                        "expected_pct": impact.get("expected_pct", 0),
                        "lag_days": impact.get("lag_days", 0),
                        "thesis": impact.get("thesis", ""),
                        "chain": impact.get("chain", ""),
                    })

    # Sort by expected impact magnitude
    chain_candidates.sort(key=lambda x: abs(x["expected_pct"]), reverse=True)

    # ── (B) Quad transition front-run candidates ──────────────────────────
    gip = snap.get("gip", {})
    if isinstance(gip, dict):
        current_q = gip.get("monthly_quad") or gip.get("structural_quad") or "Q3"
    else:
        current_q = getattr(gip, "monthly_quad", None) or getattr(gip, "structural_quad", None) or "Q3"
    regime_trans = snap.get("regime_transition", {})
    next_q = regime_trans.get("to") if isinstance(regime_trans, dict) else None

    quad_candidates = []
    if next_q and next_q != current_q:
        try:
            from engines.hedgeye_position_sizing import QUAD_SECTOR_FIT
            great_in_next = set(QUAD_SECTOR_FIT.get(next_q, {}).get("GREAT", []))
            good_in_next = set(QUAD_SECTOR_FIT.get(next_q, {}).get("GOOD", []))
            for t in market_tickers:
                if t in great_in_next:
                    quad_candidates.append({"ticker": t, "fit": "GREAT", "next_quad": next_q})
                elif t in good_in_next:
                    quad_candidates.append({"ticker": t, "fit": "GOOD", "next_quad": next_q})
        except Exception:
            pass

    # ── RENDER ─────────────────────────────────────────────────────────────
    if not chain_candidates and not quad_candidates:
        st.info(
            "No active front-run setups for this market right now. "
            "Front-run triggers when (a) major driver moves >2% in last day OR "
            "(b) regime transition probability >40%."
        )
        # Show all available chains as reference
        if cre is not None:
            with st.expander("📚 Available Chain Drivers (reference)"):
                for ticker in list(market_tickers)[:25]:
                    parents = cre.find_parents_of(ticker)
                    if parents:
                        st.markdown(f"**{ticker}** — driven by:")
                        for p in parents[:3]:
                            st.caption(f"• {p['parent']} β={p.get('beta', 0):.2f} lag {p.get('lag_days', 0)}d — {p.get('thesis', '')}")
        return

    # Chain-driven candidates
    if chain_candidates:
        st.markdown(f"#### 🔗 Chain Reaction Setups ({len(chain_candidates)})")
        st.caption("Driver shocks already triggered, downstream tickers expected to follow.")

        seen = set()
        for fr in chain_candidates[:15]:
            if fr["ticker"] in seen:
                continue
            seen.add(fr["ticker"])
            rr = market_rrs.get(fr["ticker"], {})
            # Readiness: "udah siap" if price near entry zone, "siap-siap" if still forming
            sig = rr.get("signals", {}) if rr else {}
            trade_pos = sig.get("trade_position_pct", 50)
            action = sig.get("action", "")
            if action in ("BUY_DIP", "ADD") or trade_pos < 30:
                fr["readiness"] = "🟢 UDAH SIAP (entry zone aktif)"
            elif abs(fr.get("expected_pct", 0)) > 3 and fr.get("lag_days", 0) <= 2:
                fr["readiness"] = "🟡 SIAP-SIAP (driver baru gerak, impact incoming)"
            else:
                fr["readiness"] = "⚪ SEDANG DISIAPKAN (watch, belum entry)"
            render_rich_ticker(
                fr["ticker"], rr, snap, market_key,
                show_options=show_options, show_cot=show_cot,
                show_onchain=show_onchain, show_bandar=show_bandar,
                is_frontrun=True, frontrun_info=fr,
            )

    # Quad transition candidates
    if quad_candidates:
        st.markdown(f"#### 🔄 Quad Transition Setups ({len(quad_candidates)})")
        st.caption(f"Regime expected to transition {current_q} → **{next_q}**. These tickers favored in {next_q}.")

        for qc in quad_candidates[:15]:
            rr = market_rrs.get(qc["ticker"], {})
            fr_info = {
                "driver": f"QUAD {current_q}→{next_q}",
                "shock_pct": 0,
                "expected_pct": 0,
                "lag_days": 30,
                "thesis": f"{qc['fit']} fit dalam {qc['next_quad']} (per Hedgeye book).",
                "chain": f"quad_{qc['next_quad']}_rotation",
            }
            render_rich_ticker(
                qc["ticker"], rr, snap, market_key,
                show_options=show_options, show_cot=show_cot,
                show_onchain=show_onchain, show_bandar=show_bandar,
                is_frontrun=True, frontrun_info=fr_info,
            )
