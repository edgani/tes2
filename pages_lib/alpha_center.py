"""alpha_center.py — Bottleneck + Surge Potential UI v40.2

Renders Edward's enriched curator (alpha_center_curator.py) with full thesis details:
  • Ticker, current price (if available), thesis, bottleneck_reason
  • Correlations (NVDA↔AMKR, AVGO↔CoWoS etc.)
  • Potential upside (multi-bag indicator)
  • Risk + Source attribution
  • Sortable, filterable by tier, market, upside potential
"""
import streamlit as st


def _parse_conviction_upside(upside_str: str) -> float:
    """Extract MAX upside % from the thesis string (e.g. '+300-1000%' → 1000)."""
    import re
    if not upside_str:
        return 0.0
    nums = re.findall(r'(\d+)', upside_str.replace(",", ""))
    if not nums:
        return 0.0
    return max(float(n) for n in nums)


def _alpha_score(cand: dict, rr: dict = None) -> dict:
    """Operationalizes the bottleneck/Citrini methodology to surface REAL alpha
    (next SNDK / next PLTR) — ideally BEFORE consensus. Synthesized from:
      • Citrini: 'investing in the technology bottleneck is extremely profitable';
        find bottleneck-owners EARLY (NVDA/CRDO before crowd); asymmetric.
      • King Yuan/Mawer: monopoly on a mission-critical chokepoint + inflection
        (proprietary tech, pricing power, ROIC inflection).
      • Solo Capitalist: physical bottleneck REAL & VERIFIABLE (order book past 2027)
        + positioning NOT yet crowded; conviction to hold through 30% drawdown.
    Returns score + the factors that earned it (transparent 'why')."""
    score = 0.0
    factors = []
    tags = [t.lower() for t in cand.get("tags", [])]
    text = " ".join([
        str(cand.get("bottleneck_reason", "")), str(cand.get("monopoly_strength", "")),
        str(cand.get("thesis", "")), str(cand.get("catalysts_2026", "")),
    ]).lower()

    # 1) BOTTLENECK ownership — the core of the methodology
    if "bottleneck" in tags or "bottleneck" in text or "chokepoint" in text:
        score += 25; factors.append("🔬 Bottleneck")
    # 2) MONOPOLY / pricing power on a mission-critical node
    ms = str(cand.get("monopoly_strength", "")).lower()
    if "monopol" in ms or "monopol" in tags or "monopol" in text:
        score += 22; factors.append("👑 Monopoly")
    elif any(k in ms or k in text for k in ["oligopol", "duopol", "triopol", "near-monopol"]):
        score += 14; factors.append("👑 Oligopoly")
    # 3) ASYMMETRY / multi-bag headroom (conviction upside)
    conv = _parse_conviction_upside(cand.get("potential_upside", ""))
    score += min(conv / 20.0, 45)  # 1000% → +45 (capped)
    if conv >= 300: factors.append(f"🚀 {conv:.0f}% upside")
    # 4) SMALL/MID-CAP headroom — room to 10x (mega-cap = capped appreciation)
    if "small-cap" in tags or "multi-bag" in tags or "small cap" in text:
        score += 20; factors.append("📈 Cap headroom")
    # 5) NOT-YET-CROWDED / EARLY — find it before consensus (Solo Capitalist filter 2)
    stage = None
    if rr:
        tl = rr.get("tail", {}) or {}
        tlrr = tl.get("lrr", 0) or 0; ttrr = tl.get("trr", 0) or 0; px = rr.get("px", 0) or 0
        w = ttrr - tlrr
        tail_pos = (px - tlrr) / w if w > 0 else 0.5
        if tail_pos < 0.35:
            stage = "EARLY"; score += 18; factors.append("🌱 Early (not crowded)")
        elif tail_pos > 0.80:
            stage = "LATE"; score -= 12; factors.append("⏰ Late (extended)")
        else:
            stage = "MID"
    # 6) CATALYST / inflection (M&A target, contract, validation, capacity)
    if "m&a-target" in tags or any(k in text for k in ["m&a", "acquisition", "buyout", "inflection", "order book", "offtake", "contract win"]):
        score += 12; factors.append("⚡ Catalyst")
    # 6b) VERIFIABLE SHORTAGE — the strongest bottleneck proof (HyperTechInvest/Solo Cap):
    #     capacity reserved/prepaid/booked through future years = real, not narrative.
    if any(k in text for k in ["reserved", "prepay", "pre-pay", "sold out", "booked through",
                                "through 2027", "through 2028", "capacity locked", "multi-year supply",
                                "two to three year", "2-3 year", "lead time"]):
        score += 15; factors.append("✅ Verifiable shortage")
    # 6c) PURE-PLAY / direct exposure (SIVE pattern): the bottleneck IS the whole small-cap,
    #     not one line in a giant's portfolio → far more asymmetric.
    if any(k in text for k in ["pure-play", "pure play", "direct exposure", "only public", "sole",
                                "whole company", "entire business"]):
        score += 12; factors.append("🎯 Pure-play")
    # 7) PENALTY — large-cap low-conviction = appreciation, NOT moonshot alpha
    if conv < 100 and "multi-bag" not in tags and "small-cap" not in tags:
        score -= 25; factors.append("⚠️ Mega-cap (low asym)")

    return {"score": round(score, 1), "factors": factors, "stage": stage, "conviction": conv}


def _calc_upside_metrics(rr: dict) -> dict:
    """Compute thesis-progress metrics: TAIL position, distance to TRR, TARGET PRICES."""
    if not rr or not isinstance(rr, dict):
        return {}
    px = rr.get("px", 0) or 0
    trade = rr.get("trade", {}) or {}
    trend = rr.get("trend", {}) or {}
    tail = rr.get("tail", {}) or {}
    tail_lrr = tail.get("lrr", 0) or 0
    tail_trr = tail.get("trr", 0) or 0
    trade_trr = trade.get("trr", 0) or 0
    trend_trr = trend.get("trr", 0) or 0
    tail_pos = None
    if tail_trr > tail_lrr > 0 and px > 0:
        tail_pos = max(0, min(100, (px - tail_lrr) / (tail_trr - tail_lrr) * 100))
    upside_trade = ((trade_trr - px) / px * 100) if px > 0 else 0
    upside_trend = ((trend_trr - px) / px * 100) if px > 0 else 0
    upside_tail = ((tail_trr - px) / px * 100) if px > 0 and tail_trr > 0 else 0
    if tail_pos is None:
        thesis_stage = "—"
    elif tail_pos < 25:
        thesis_stage = "🟢 EARLY (banyak ruang surge)"
    elif tail_pos < 50:
        thesis_stage = "🟡 MID (masih ada upside)"
    elif tail_pos < 75:
        thesis_stage = "🟠 LATE-MID (hati-hati)"
    else:
        thesis_stage = "🔴 LATE (sebagian besar move udah jalan)"
    return {
        "tail_position_pct": tail_pos,
        "upside_to_trade_trr_pct": round(upside_trade, 2),
        "upside_to_trend_trr_pct": round(upside_trend, 2),
        "upside_to_tail_trr_pct": round(upside_tail, 2),
        "thesis_stage": thesis_stage,
        # TARGET PRICES (Edward request: bukan cuma %)
        "target_near": round(trade_trr, 2),     # nearest target = TRADE TRR
        "target_mid": round(trend_trr, 2),       # mid target = TREND TRR
        "target_far": round(tail_trr, 2),        # farthest target = TAIL TRR
        "current_px": round(px, 2),
    }


def _stars_html(n: int) -> str:
    return "⭐" * int(n or 0)


def render(snap: dict):
    st.title("⚡ Alpha Center — Asymmetric Moonshots")
    # ── Card spacing + consistent typography (fix cramped/numpuk cards) ──
    st.markdown("""<style>
    [data-testid="stVerticalBlockBorderWrapper"] { margin-bottom: 18px !important; padding: 4px 6px !important; }
    [data-testid="stVerticalBlockBorderWrapper"] h4 { margin: 2px 0 4px !important; font-size: 1.05rem !important; }
    [data-testid="stVerticalBlockBorderWrapper"] p { margin: 3px 0 !important; line-height: 1.4 !important; }
    [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stCaptionContainer"] { margin: 2px 0 !important; }
    </style>""", unsafe_allow_html=True)
    st.caption("**Tempat nyari ALPHA sejati**, bukan trade 5%. Buruan buat nangkep "
               "**the next SNDK ($30→$1,500), SIVE, early PLTR** — small/mid-cap dengan thesis "
               "bottleneck/monopoly/M&A yang bisa **3x–50x** kalau theses-nya jalan. "
               "Asymmetric: downside terbatas, upside gila. Ride the wave, jangan scalp.")

    try:
        from engines.alpha_center_curator import get_curator
        curator = get_curator()
    except Exception as e:
        st.error(f"Alpha Center curator unavailable: {e}")
        return

    keith_signals = snap.get("keith_signals", {}) or {}
    wf_results = snap.get("walkforward_results", {}) or snap.get("walkforward_results_v40", {}) or {}
    gip = snap.get("gip", {})
    if isinstance(gip, dict):
        current_quad = gip.get("monthly_quad") or gip.get("structural_quad") or "Q3"
    else:
        current_quad = getattr(gip, "monthly_quad", None) or getattr(gip, "structural_quad", None) or "Q3"

    result = curator.filter_universe(
        keith_signals=keith_signals, wf_results=wf_results,
        current_quad=current_quad, min_stars=1,
    )
    passed = result["passed"]
    rejected = result["rejected"]

    # ── TOP KPIs ─────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Passed", len(passed))
    multi_bag = sum(1 for p in passed if "MULTI-BAG" in p["candidate"].get("tags", []))
    c2.metric("🚀 Multi-bag candidates", multi_bag)
    ma_targets = sum(1 for p in passed if "M&A-Target" in p["candidate"].get("tags", []))
    c3.metric("🎯 M&A targets", ma_targets)
    c4.metric("Current Quad", current_quad)

    st.divider()

    # ── FILTERS ──────────────────────────────────────────────────────────
    f1, f2, f3 = st.columns([1, 1.4, 1])
    with f1:
        tier_filter = st.radio("Tier", ["All", "5★", "4★+", "3★+", "1-2★ (HRHR)"], horizontal=False)
    with f2:
        market_filter = st.multiselect(
            "Market", ["us_equity", "ihsg", "crypto", "forex", "commodity"],
            default=["us_equity", "ihsg", "crypto"],
        )
    with f3:
        tag_filter = st.multiselect(
            "Tag focus",
            ["Bottleneck", "MULTI-BAG", "M&A-Target", "AI", "Citrini", "Energy",
             "Materials", "Crypto", "IHSG", "Bandar", "Optical", "Memory",
             "Power", "Storage", "SMR", "Speculative"],
        )

    min_upside_str = st.select_slider(
        "Min upside ke TAIL TRR (% — di bawah ini = late stage, hide)",
        options=["No filter", "0%", "20%", "50%", "100%", "200%"],
        value="0%",
        help="Edward's rule: Alpha Center = potensi surging, BUKAN udah surging. >100% = true multi-bag.",
    )
    min_upside = {"No filter": -1e9, "0%": 0, "20%": 20, "50%": 50, "100%": 100, "200%": 200}.get(min_upside_str, 0)

    # Defensive: never let a None filter crash the page (real Streamlit returns lists,
    # but guard anyway so a single odd state can't blank the whole Alpha Center)
    if not market_filter:
        market_filter = ["us_equity", "ihsg", "crypto", "forex", "commodity"]
    tag_filter = tag_filter or []
    tier_filter = tier_filter or "All"

    def _tier_ok(c):
        s = c["candidate"].get("stars", 0)
        if tier_filter == "All": return True
        if tier_filter == "5★": return s == 5
        if tier_filter == "4★+": return s >= 4
        if tier_filter == "3★+": return s >= 3
        if tier_filter == "1-2★ (HRHR)": return s <= 2
        return True

    def _tag_ok(c):
        if not tag_filter: return True
        tags = c["candidate"].get("tags", [])
        return any(t in tags for t in tag_filter)

    filtered = [c for c in passed
                if _tier_ok(c) and _tag_ok(c)
                and c["candidate"].get("market") in market_filter]

    # Upside filter (if RR data available)
    rr_data = snap.get("risk_range", {}).get("asset_ranges", {}) if isinstance(snap.get("risk_range"), dict) else {}

    if min_upside > -1e9:
        filtered_pre = filtered
        filtered = []
        for e in filtered_pre:
            rr = rr_data.get(e["ticker"], {})
            if not rr:
                # No RR data — keep (don't punish for missing data)
                filtered.append(e)
                continue
            um = _calc_upside_metrics(rr)
            tu = um.get("upside_to_tail_trr_pct")
            if tu is None or tu >= min_upside:
                filtered.append(e)

    # Sort by ALPHA SCORE (bottleneck methodology): bottleneck + monopoly + early +
    # cap headroom + catalyst + asymmetry. Surfaces real alpha (next SNDK/PLTR) first.
    def _sort_key(e):
        cand = e["candidate"]
        rr = rr_data.get(e["ticker"], {})
        a = _alpha_score(cand, rr)
        return (-a["score"], -a["conviction"], e["ticker"])
    filtered.sort(key=_sort_key)

    # Split into HAS_DATA and NO_DATA — hide NO_DATA from main list (Edward fix)
    has_data = [e for e in filtered if rr_data.get(e["ticker"], {}).get("px")]
    no_data = [e for e in filtered if not rr_data.get(e["ticker"], {}).get("px")]
    filtered = has_data

    st.caption(f"📊 **{len(filtered)}** candidates dengan price data (sorted: Alpha Score — bottleneck + monopoly + early + asymmetry)"
               + (f" · ⚠️ {len(no_data)} pending (no price data — di bawah)" if no_data else ""))
    st.divider()

    # ── RENDER CARDS — native Streamlit (no HTML escape issues) ──────────
    for entry in filtered:
        ticker = entry["ticker"]
        cand = entry["candidate"]
        stars = _stars_html(cand.get("stars", 0))
        market = cand.get("market", "?").upper()
        tags = cand.get("tags", [])
        rr = rr_data.get(ticker, {})
        upside = _calc_upside_metrics(rr)

        # IHSG no-short
        action = rr.get("signals", {}).get("action", "WATCH") if rr else "NO_DATA"
        if market == "IHSG" and action in ("SHORT_RIP", "COVER"):
            action = "WATCH"
        action_emoji = {"BUY_DIP": "🟢", "ADD": "🟢", "HOLD": "⚪", "WATCH": "⚪",
                        "TRIM": "🟡", "TRIM_RIP": "🟠", "SHORT_RIP": "🔴",
                        "COVER": "🟣", "NO_DATA": "⚫"}.get(action, "⚪")

        # Compute SURGE flags
        tail_upside_val = upside.get("upside_to_tail_trr_pct") or 0
        is_multi_bag = "MULTI-BAG" in tags
        is_ma_target = "M&A-Target" in tags

        with st.container(border=True):
            # ── Header row (consistent typography: h4 title, uniform captions) ──
            hc1, hc2, hc3 = st.columns([2.6, 1.0, 1.3])
            with hc1:
                badges = ""
                if is_multi_bag: badges += " \U0001f680"
                if is_ma_target: badges += " \U0001f3af"
                st.markdown(f"#### {ticker}{badges}")
            with hc2:
                px_str = f"\\${(rr.get('px') or 0):.2f}" if rr.get('px') else "\u2014"
                st.metric("Price", px_str)
            with hc3:
                st.caption(f"{action_emoji} **{action}**")

            # ── BLOCK 1 per spec: ONE block — main chart → setup → companions → extras ──
            _mkt = cand.get("market", "us_equity")
            try:
                from components.rich_ticker_card import render_detail_charts
                render_detail_charts(ticker, rr, snap, _mkt, part="main")  # main GEX/RR chart only
            except Exception:
                pass

            # setup details folded immediately UNDER the chart (Posisi/Entry/Target/Stop/Cara-masuk/Dealer/Vanna/Dark-pool)
            try:
                from components.rich_ticker_card import render_options_recommendation
                render_options_recommendation(rr, snap, ticker, _mkt)
            except Exception:
                pass

            # companions (expected move / P/C OI / COT) below the setup
            try:
                from components.rich_ticker_card import render_detail_charts
                render_detail_charts(ticker, rr, snap, _mkt, part="companions")
            except Exception:
                pass

            # ── Vanna/Charm OPEX window + on-chain extras (block-1 per spec) ──
            try:
                from components.rich_ticker_card import _render_block1_extras
                _render_block1_extras(rr, snap, ticker, _mkt, show_options=True,
                                      show_onchain=(_mkt == "crypto"), px=rr.get("px"))
            except Exception:
                pass

            # ── Thesis ───────────────────────────────────────────────────
            st.markdown(f"**💡 Thesis:** {cand.get('thesis', '')}")

            # ── Bottleneck reason ────────────────────────────────────────
            br = cand.get("bottleneck_reason")
            if br:
                st.markdown(f"**🔒 Why bottleneck:** {br}")

            # ── Correlations + Catalysts + Risk ──────────────────────────
            with st.expander("🔍 Detail — correlations, catalysts, RR, filters"):
                dc1, dc2 = st.columns(2)
                with dc1:
                    corr = cand.get("correlations", {})
                    if corr:
                        st.markdown("**🔗 Correlations**")
                        for parent, val in corr.items():
                            st.caption(f"  • **{parent}** — β/note: {val}")
                    cats = cand.get("catalysts_2026", [])
                    if cats:
                        st.markdown("**📌 Catalysts 2026**")
                        for cat in cats:
                            st.caption(f"  • {cat}")
                with dc2:
                    risk = cand.get("risk")
                    if risk:
                        st.warning(f"⚠️ **Risk:** {risk}")
                    rn = cand.get("risk_notes")
                    if rn:
                        st.warning(f"⚠️ {rn}")
                st.markdown("**✅ 5-Layer Filter Pass:**")
                for layer_name, check in entry["checks"].items():
                    icon = "✅" if check["pass"] else "❌"
                    st.caption(f"{icon} {layer_name}: {check['msg']}")

    if not filtered:
        st.info("No candidates match current filters. Loosen the filter to see more.")

    # ── Rejected list (compact) ──────────────────────────────────────────
    if rejected:
        with st.expander(f"❌ Rejected ({len(rejected)})"):
            for entry in rejected:
                fail_reasons = [f"{ln.replace('L', 'Layer ').replace('_', ': ')}: {ch['msg']}"
                                for ln, ch in entry["checks"].items() if not ch["pass"]]
                st.caption(f"**{entry['ticker']}** — {' · '.join(fail_reasons)}")
