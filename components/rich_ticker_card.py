"""rich_ticker_card.py — Comprehensive ticker rendering with narrative analysis

Per Edward's spec: setiap ticker card harus nampilin:
  • Ticker + harga saat ini
  • TRR/LRR (TRADE/TREND/TAIL)
  • **PHASE NARRATIVE** (trending bullish/bearish/sideways + reasoning)
  • **ENTRY ZONE** (di mana buy/short, take profit, R/R)
  • **OPTIONS + GREEKS narrative** (call/put walls, OI heatmap, MM positioning,
    expected move, volatility outlook, ACTIONABLE recommendation)
  • Market-specific layer (COT/on-chain/bandar) with NARRATIVE interpretation
"""
import streamlit as st


# ═══════════════════════════════════════════════════════════════════════════
# NARRATIVE GENERATORS
# ═══════════════════════════════════════════════════════════════════════════

def compute_signal_strength(rr: dict) -> dict:
    """Keith McCullough Signal Strength: HH across all 3 durations (TRADE/TREND/TAIL).
    HH = price breaking ABOVE the band (higher-high); LL = below the band (lower-low).
    For mid-range price, lean on MA trend (phase_code) so it stays CONSISTENT with Phase box.
    """
    if not rr:
        return {"score": 0, "label": "NEUTRAL", "detail": ""}
    px = rr.get("px", 0)
    phase_code = rr.get("phase_code", 0)
    hh = ll = 0
    states = []
    for d in ["trade", "trend", "tail"]:
        dd = rr.get(d, {})
        lrr = dd.get("lrr", 0) or 0
        trr = dd.get("trr", 0) or 0
        if trr and px >= trr:
            hh += 1; states.append("HH")
        elif lrr and px <= lrr:
            ll += 1; states.append("LL")
        else:
            states.append("mid")
    # Breakout extremes (Keith's true HH/LL across durations)
    if hh == 3:
        return {"score": 3, "label": "STRONGEST BULL", "detail": "Price > TRR on TRADE+TREND+TAIL - HH all 3 (Keith max strength)"}
    if ll == 3:
        return {"score": -3, "label": "STRONGEST BEAR", "detail": "Price < LRR on TRADE+TREND+TAIL - LL all 3 (max bearish)"}
    if hh >= 1 and ll == 0 and phase_code >= 0:
        return {"score": 2, "label": "STRONG BULL", "detail": f"Breaking out HH on {hh}/3 durations - bull trend intact"}
    if ll >= 1 and hh == 0 and phase_code <= 0:
        return {"score": -2, "label": "STRONG BEAR", "detail": f"Breaking down LL on {ll}/3 durations - bear trend"}
    # Mid-range: lean on MA trend so it agrees with the Phase box
    if phase_code == 1:
        return {"score": 1, "label": "BULL BIAS", "detail": "Mid-range, 21d>63d MA - bullish lean, wait for pullback/breakout"}
    if phase_code == -1:
        return {"score": -1, "label": "BEAR BIAS", "detail": "Mid-range, 21d<63d MA - bearish lean"}
    return {"score": 0, "label": "NEUTRAL", "detail": "Mid-range, no trend - no edge"}


def _cur_for(market_key=None, ticker=None):
    """Currency symbol for display: '' for forex (4-dp), 'Rp' for IHSG (.JK stocks),
    '$' otherwise. IHSG stocks trade in Rupiah — showing '$' was a bug."""
    if market_key == "forex":
        return ""
    if market_key == "ihsg" or (ticker and str(ticker).upper().endswith(".JK")):
        return "Rp"
    return "$"


def _directional_levels(px, direction, *, t_lrr=0, t_trr=0, tr_lrr=0, tr_trr=0,
                        tl_lrr=0, tl_trr=0, call_wall=None, put_wall=None, long_only=False):
    """Direction-aware entry/target/stop that ALWAYS stays on the correct side of price.

    long_only (IDX/spot equity): a SHORT is impossible, so a bearish read is degraded to a range/flat
    layout (target stays ABOVE entry) — never a 'short' whose target sits below entry on a buy-only name.

    Why this exists: after FIX-BASIS the TREND band is anchored to SMA63 and TAIL to SMA756, so a band
    can sit ENTIRELY above or below spot. A band edge is therefore only a valid target/stop if it's on
    the correct side of price — otherwise you get nonsense like a SHORT whose 'target' is +12% ABOVE
    entry (the MKR bug). We pick levels by SIDE, not by band name:
      LONG  → entry near TRADE LRR (support);    target = nearest level ABOVE px; stop = just below nearest support
      SHORT → entry near TRADE TRR (resistance);  target = nearest level BELOW px; stop = just above nearest resistance
    Returns {entry_lo, entry_hi, target, target2, stop} or {} if px invalid."""
    if long_only and direction == "short":
        direction = "flat"                          # buy-only market: no short layout, ever
    try:
        px = float(px)
    except (TypeError, ValueError):
        return {}
    if not px or px != px:
        return {}

    def _v(x):
        try:
            x = float(x)
            return x if (x == x and x > 0) else None
        except (TypeError, ValueError):
            return None

    b = {k: _v(v) for k, v in dict(t_lrr=t_lrr, t_trr=t_trr, tr_lrr=tr_lrr, tr_trr=tr_trr,
                                   tl_lrr=tl_lrr, tl_trr=tl_trr, cw=call_wall, pw=put_wall).items()}
    width = (b["t_trr"] - b["t_lrr"]) if (b["t_trr"] and b["t_lrr"] and b["t_trr"] > b["t_lrr"]) else px * 0.04
    UP = ("t_trr", "tr_trr", "tr_lrr", "tl_trr", "tl_lrr", "cw")     # any band edge / wall as a resistance
    DN = ("t_lrr", "tr_lrr", "tr_trr", "tl_lrr", "tl_trr", "pw")     # any band edge / wall as a support
    ups = sorted({b[k] for k in UP if b[k] and b[k] > px * 1.005})
    downs = sorted({b[k] for k in DN if b[k] and b[k] < px * 0.995}, reverse=True)

    if direction == "short":
        target = downs[0] if downs else px * 0.95
        target2 = downs[1] if len(downs) > 1 else px * 0.90
        stop = ups[0] * 1.005 if ups else px * 1.03            # just above nearest resistance
        e_hi = b["t_trr"] or px
        e_lo = e_hi - width * 0.30
        return {"entry_lo": e_lo, "entry_hi": e_hi, "target": target, "target2": target2, "stop": stop}
    if direction == "long":
        target = ups[0] if ups else px * 1.05
        target2 = ups[1] if len(ups) > 1 else px * 1.10
        stop = downs[0] * 0.995 if downs else px * 0.97         # just below nearest support
        e_lo = b["t_lrr"] or px
        e_hi = e_lo + width * 0.30
        return {"entry_lo": e_lo, "entry_hi": e_hi, "target": target, "target2": target2, "stop": stop}
    # range / flat — fade extremes
    return {"entry_lo": b["t_lrr"] or px * 0.98, "entry_hi": b["t_trr"] or px * 1.02,
            "target": b["t_trr"] or px * 1.03, "target2": None, "stop": b["t_lrr"] or px * 0.97}


def _gex_levels_chart(ticker, px, rr, opts, cur="$", show_walls=True, setup=None, long_only=False):
    """Unified DARK chart on a price x-axis: GEX-by-strike bars + aggregate gamma curve +
    put/call walls + gamma flip + max pain + TRADE/TREND/TAIL bands + Entry/Target/SL X-marks.
    show_walls=False (forex/commodity/IHSG = no listed options) → suppress all options-derived
    overlays (walls/max-pain/flip/GEX bars), leaving a pure Risk-Range chart. Returns a Figure or None."""
    import plotly.graph_objects as go
    import itertools
    try:
        px = float(px or 0)
    except (TypeError, ValueError):
        px = 0.0
    rr = rr or {}
    opts = opts or {}
    trade = rr.get("trade", {}) or {}; trend = rr.get("trend", {}) or {}; tail = rr.get("tail", {}) or {}

    def _f(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    strikes = opts.get("strikes") or []
    gexvals = opts.get("gex_by_strike") or []
    cw, pw = _f(opts.get("call_wall")), _f(opts.get("put_wall"))
    flip, mp = _f(opts.get("flip_level")), _f(opts.get("max_pain"))
    if not show_walls:
        # No listed options for this market → the walls/max-pain/flip/GEX bars are proxy/fake. Drop them.
        strikes, gexvals, cw, pw, flip, mp = [], [], None, None, None, None
    # sanitize price first → avoid "Last $nan" on the chart
    if not (isinstance(px, (int, float)) and px == px and px > 0):
        _tl0, _tt0 = _f(trade.get("lrr")), _f(trade.get("trr"))
        px = (((_tl0 or 0) + (_tt0 or 0)) / 2) or None
    # DIRECTION-AWARE entry/target/stop (was hardcoded as a LONG layout → short setups drew target
    # above entry). Derive direction from the risk-range phase; helper keeps levels on the right side.
    _long_only = bool(long_only) or str(ticker).upper().endswith(".JK")     # IDX = buy-only
    _pc = rr.get("phase_code", 0); _phs = rr.get("phase", "")
    _dir = "long" if (_phs == "BULL" or _pc == 1) else "short" if (_phs == "BEAR" or _pc == -1) else "flat"
    if _long_only and _dir == "short":
        _dir = "flat"                          # buy-only: bearish → range/fade-long, NEVER a short layout
    _lv = _directional_levels(px, _dir, t_lrr=trade.get("lrr"), t_trr=trade.get("trr"),
                              tr_lrr=trend.get("lrr"), tr_trr=trend.get("trr"),
                              tl_lrr=tail.get("lrr"), tl_trr=tail.get("trr"),
                              call_wall=cw, put_wall=pw, long_only=_long_only) if px else {}
    entry = _lv.get("entry_hi") if _dir == "short" else _lv.get("entry_lo")
    target = _lv.get("target"); stop = _lv.get("stop")
    # STALE GUARD: price has already moved past the entry zone → the setup is no longer actionable.
    _stale = False
    if px and entry:
        if _dir == "short" and px < entry * 0.97: _stale = True   # short entry is resistance ABOVE; price already dropped away
        elif _dir != "short" and stop and px < stop: _stale = True  # long support broke (price below stop)

    # Core extent = risk-range bands + price + entry/target/stop — always meaningful and tight.
    core = [v for v in [px, entry, target, stop,
                        _f(trade.get("lrr")), _f(trade.get("trr")),
                        _f(trend.get("lrr")), _f(trend.get("trr")),
                        _f(tail.get("lrr")), _f(tail.get("trr"))] if v and v > 0]
    if len(core) < 2:
        return None
    c_lo, c_hi = min(core), max(core)
    c_span = (c_hi - c_lo) or (px * 0.1) or 1.0
    # Walls / max-pain / flip / strikes: extend the axis ONLY if within 0.6×span of the core,
    # so a far-off Max Pain or deep-OTM strike can't squish the bands into a sliver (QQQ bug).
    extras = [cw, pw, mp, flip] + (list(strikes) if strikes else [])
    for v in extras:
        if v and v > 0 and (c_lo - 0.6 * c_span) <= v <= (c_hi + 0.6 * c_span):
            c_lo, c_hi = min(c_lo, v), max(c_hi, v)
    lo, hi = c_lo, c_hi
    pad = (hi - lo) * 0.06 or (px * 0.05) or 1.0
    x0, x1 = lo - pad, hi + pad

    fig = go.Figure()
    # positive / negative gamma shaded regions, split at the flip
    if flip:
        fig.add_vrect(x0=x0, x1=flip, fillcolor="rgba(248,81,73,0.06)", line_width=0)
        fig.add_vrect(x0=flip, x1=x1, fillcolor="rgba(63,185,80,0.06)", line_width=0)
    # TRR/LRR bands (wide→narrow so TRADE sits on top)
    for band, color, lbl in [(tail, "rgba(139,148,158,0.06)", "TAIL"),
                             (trend, "rgba(88,166,255,0.07)", "TREND"),
                             (trade, "rgba(210,153,34,0.12)", "TRADE")]:
        l, t = _f(band.get("lrr")), _f(band.get("trr"))
        if l and t:
            fig.add_vrect(x0=l, x1=t, fillcolor=color, line_width=0,
                          annotation_text=lbl, annotation_position="top left",
                          annotation_font={"size": 9, "color": "#8b949e"})
    # GEX bars only (per-strike). The cumulative "Aggregate GEX" line was removed — it rendered as
    # a confusing diagonal crossing the whole plot and added no actionable info over the bars.
    if strikes and gexvals and len(strikes) == len(gexvals):
        colors = ["#3FB950" if v >= 0 else "#F0883E" for v in gexvals]
        fig.add_trace(go.Bar(x=strikes, y=gexvals, marker_color=colors, opacity=0.55,
                             name="GEX by strike",
                             hovertemplate="Strike %{x}<br>GEX %{y:,.0f}<extra></extra>"))
    # vertical reference lines — labels staggered vertically (yshift) so they stay readable
    # even when two lines sit at nearly the same price (e.g. Last vs Call Wall).
    for x, color, lbl, dash, ysh in [(px, "#3FB950", f"Last {cur}{px:,.2f}", "solid", 0),
                                      (flip, "#F85149", "Gamma Flip", "dot", -13),
                                      (cw, "#A371F7", "Call Wall", "solid", -26),
                                      (pw, "#A371F7", "Put Wall", "solid", -39),
                                      (mp, "#8B949E", "Max Pain", "dot", -52)]:
        if x:
            fig.add_vline(x=x, line={"color": color, "width": 1.4, "dash": dash},
                          annotation_text=lbl, annotation_position="top",
                          annotation_yshift=ysh,
                          annotation_font={"size": 9, "color": color})
    # entry / target / stop as X markers on the baseline
    for x, color, lbl in [(entry, "#3FB950", "Entry"), (target, "#58A6FF", "Target"), (stop, "#F85149", "SL")]:
        if x:
            fig.add_trace(go.Scatter(x=[x], y=[0], mode="markers+text", text=[lbl],
                          textposition="bottom center", textfont={"size": 10, "color": color},
                          marker={"symbol": "x", "size": 13, "color": color, "line": {"width": 2, "color": color}},
                          showlegend=False, hovertemplate=f"{lbl} {cur}%{{x:,.2f}}<extra></extra>"))

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(13,17,23,0.5)",
        font={"color": "#c9d1d9", "family": "Inter, sans-serif", "size": 11},
        margin={"t": 34, "b": 38, "l": 52, "r": 52}, height=330,
        legend={"orientation": "h", "y": 1.14, "x": 0, "font": {"size": 9}, "bgcolor": "rgba(0,0,0,0)"},
        title={"text": f"{ticker} — {'GEX + ' if show_walls else ''}Risk Range + Entry/Target/SL"
                       + ("  ·  ⚠ harga sudah lewat entry (telat)" if _stale else "")
                       + ("  ·  buy-only" if _long_only else ""),
               "font": {"size": 13, "color": "#c9d1d9"}},
        xaxis={"title": {"text": f"Price ({cur})", "font": {"size": 10, "color": "#8b949e"}},
               "range": [x0, x1], "gridcolor": "#21262d", "tickfont": {"color": "#8b949e"}, "zeroline": False},
        yaxis={"title": {"text": "GEX by strike", "font": {"size": 10, "color": "#8b949e"}},
               "gridcolor": "#21262d", "tickfont": {"color": "#8b949e"}, "zeroline": True, "zerolinecolor": "#30363d"},
        yaxis2={"title": {"text": "Aggregate", "font": {"size": 10, "color": "#8b949e"}},
                "overlaying": "y", "side": "right", "showgrid": False, "tickfont": {"color": "#8b949e"}},
    )
    # ── Setup overlay INSIDE the plot — compact panels so they DON'T block the chart ──
    if setup:
        _hdr, _bar, _left, _right = setup
        # taller plot + suppress the redundant title (header annotation carries ticker/price/range)
        fig.update_layout(height=500, margin={"t": 26, "b": 26, "l": 50, "r": 16},
                          title={"text": ""})
        fig.add_annotation(xref="paper", yref="paper", x=0.0, y=1.0, xanchor="left", yanchor="bottom",
                           text=f"<b>{_hdr}</b>", showarrow=False, align="left",
                           font={"size": 9, "color": "#c9d1d9"})
        fig.add_annotation(xref="paper", yref="paper", x=0.004, y=0.995, xanchor="left", yanchor="top",
                           text=_left, showarrow=False, align="left",
                           font={"size": 8.5, "color": "#e6edf3"},
                           bgcolor="rgba(13,17,23,0.70)", bordercolor=_bar, borderwidth=1, borderpad=4)
        if _right:
            fig.add_annotation(xref="paper", yref="paper", x=0.996, y=0.995, xanchor="right", yanchor="top",
                               text=_right, showarrow=False, align="left",
                               font={"size": 8.5, "color": "#b9c2cc"},
                               bgcolor="rgba(13,17,23,0.70)", bordercolor="#30363d", borderwidth=1, borderpad=4)
    if not (strikes and gexvals and len(strikes) == len(gexvals)):
        # no options chain → render as a clean horizontal LEVEL LADDER instead of an empty GEX plane
        fig.update_layout(height=200, yaxis={"visible": False, "range": [-0.7, 0.7]})
        fig.add_annotation(xref="paper", yref="paper", x=1.0, y=1.05, xanchor="right",
                           text="level ladder — no options chain", showarrow=False,
                           font={"size": 9, "color": "#8b949e"})

    return fig


def _setup_text_cols(rr, snap, ticker, market_key="us_equity"):
    """Build (header, accent_color, left_html, right_html) for the in-chart setup overlay.
    Left = trade plan; right = entry styles + microstructure. None if no recommendation."""
    rec = build_options_recommendation(rr, snap, ticker, market_key)
    if not rec:
        return None
    f = rec["fmt"]
    bar = "#3FB950" if rec["direction"] == "long" else "#F85149" if rec["direction"] == "short" else "#8B949E"
    de = {"long": "🟢", "short": "🔴", "flat": "⚪"}.get(rec["direction"], "⚪")
    conv = " · ⚡ high-conviction" if rec["conviction"] == "high" else ""
    if rec["has_real_opts"]:
        src = "🟢 live options + greeks"
    elif market_key in ("commodity", "forex"):
        src = "TRR/LRR + COT"
    elif market_key == "ihsg":
        src = "TRR/LRR + bandar"
    else:
        src = "TRR/LRR (options N/A)"
    bits = [f"📋 <b>{rec['ticker']}</b>", f"{f(rec['px'])}", rec["sig_label"],
            f"TRADE {f(rec['trade_lrr'])}–{f(rec['trade_trr'])}"]
    if rec["has_real_opts"] and (rec["call_wall"] or rec["put_wall"]):
        w = []
        if rec["call_wall"]: w.append(f"CW {f(rec['call_wall'])}")
        if rec["put_wall"]: w.append(f"PW {f(rec['put_wall'])}")
        bits.append(" ".join(w))
    header = " · ".join(bits) + f"  ({src})"

    left = [f"{de} <b>Posisi:</b> {rec['instrument']}{conv}"]
    if rec["entry_zone"]: left.append(f"<b>Entry:</b> {rec['entry_zone']}")
    for c in rec["confluence"][:2]:
        left.append(f"↳ {c}")
    if rec["target"]: left.append(f"<b>Target:</b> {rec['target']} · <b>Stop:</b> {rec['stop']}")
    if rec["by_expiry"]: left.append(f"<b>Exp move:</b> {rec['by_expiry']}")
    if rec["breakout_up"]: left.append(f"📈 {rec['breakout_up']}")
    if rec["breakout_down"]: left.append(f"📉 {rec['breakout_down']}")

    right = []
    if rec.get("positions") and len(rec["positions"]) >= 2:
        right.append("<b>🎚️ Cara masuk:</b>")
        for p in rec["positions"]:
            right.append(f"{p['type']}: {p['detail']}")
    if rec["dealer"]: right.append(f"<b>Dealer:</b> {rec['dealer']}")
    if rec["vanna_charm"]: right.append(f"<b>Vanna/charm:</b> {rec['vanna_charm']}")
    if rec["dark_pool"]: right.append(rec["dark_pool"])
    if rec["cot"]: right.append(f"<b>COT:</b> {rec['cot']}")
    if rec.get("onchain"): right.append(f"<b>⛓️ On-chain:</b> {rec['onchain']}")
    if rec["keith"]: right.append(f"📌 {rec['keith']}")
    if rec.get("pcr") is not None: right.append(f"PCR {rec['pcr']:.2f}")

    return (header, bar, "<br>".join(left), "<br>".join(right))


def _bandarmetrics_chart(bm, ticker, cur="Rp"):
    """DARK chart in the real bandarmetrics.com style (attachment 4): candlesticks + LPM line
    overlay (secondary axis) / Intensity panel / Vol Rotation panel."""
    from plotly.subplots import make_subplots
    import plotly.graph_objects as go
    sr = (bm or {}).get("series_real")
    if sr and sr.get("index"):
        from plotly.subplots import make_subplots
        import plotly.graph_objects as go
        ix, cl = sr["index"], sr["close"]
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.58, 0.21, 0.21],
                            vertical_spacing=0.04, specs=[[{"secondary_y": True}], [{}], [{}]],
                            subplot_titles=(f"Price + LPM + Foreign Flow (REAL Type-F · Corr_F {bm.get('corr_f','—')} · Par_F {bm.get('par_f','—')})",
                                            "Intensity (trigger-only)", "Net Buy/Sell F (Rp)"))
        fig.add_trace(go.Scatter(x=ix, y=cl, mode="lines", name="Close",
                                 line={"color": "#c9d1d9", "width": 1.3}), row=1, col=1, secondary_y=False)
        fig.add_trace(go.Scatter(x=ix, y=sr["lpm"], mode="lines", name="LPM",
                                 line={"color": "#2dd4bf", "width": 1.4}), row=1, col=1, secondary_y=True)
        fig.add_trace(go.Scatter(x=ix, y=sr["ff_cum"], mode="lines", name="Foreign Flow (cum)",
                                 line={"color": "#58a6ff", "width": 1.2}), row=1, col=1, secondary_y=True)
        fig.add_trace(go.Bar(x=ix, y=sr["intensity"], marker_color="#a371f7", name="Intensity"), row=2, col=1)
        nf = sr["ff_net"]
        fig.add_trace(go.Bar(x=ix, y=nf, name="NetF",
                             marker_color=["#26a69a" if (v or 0) >= 0 else "#ef5350" for v in nf]), row=3, col=1)
        fig.update_layout(height=460, showlegend=True,
                          legend={"orientation": "h", "y": 1.06, "x": 0, "font": {"size": 9}},
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(13,17,23,0.6)",
                          font={"color": "#c9d1d9", "size": 10}, margin={"t": 42, "b": 18, "l": 50, "r": 50},
                          bargap=0.15)
        return fig
    s = (bm or {}).get("series") or {}
    idx = s.get("index"); o, h, l, c = s.get("open"), s.get("high"), s.get("low"), s.get("price")
    lpm, inten, rot = s.get("lpm"), s.get("intensity"), s.get("rotation")
    if not (idx and o and h and l and c) or len(idx) < 10:
        return None
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.74, 0.26],
                        vertical_spacing=0.04, specs=[[{"secondary_y": True}], [{}]],
                        subplot_titles=("Price + LPM (PROXY — Type-F absent; conditional)", "Intensity (trigger-only)"))
    # candlesticks
    fig.add_trace(go.Candlestick(x=idx, open=o, high=h, low=l, close=c, name="Price",
                                 increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
                                 increasing_fillcolor="#26a69a", decreasing_fillcolor="#ef5350",
                                 line={"width": 1}), row=1, col=1, secondary_y=False)
    # LPM line overlay on secondary axis (teal, like the real BM)
    if lpm:
        fig.add_trace(go.Scatter(x=idx, y=lpm, mode="lines", name="LPM",
                                 line={"color": "#2dd4bf", "width": 1.6}), row=1, col=1, secondary_y=True)
    # Intensity (purple bars)
    if inten:
        fig.add_trace(go.Bar(x=idx, y=inten, marker_color="#a371f7", name="Intensity"), row=2, col=1)
    fig.update_layout(height=420, showlegend=False, paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(13,17,23,0.6)", font={"color": "#c9d1d9", "size": 10},
                      margin={"t": 42, "b": 18, "l": 50, "r": 50}, bargap=0.15,
                      xaxis_rangeslider_visible=False,
                      title={"text": f"{ticker} — Bandarmetrics", "font": {"size": 13, "color": "#c9d1d9"}})
    fig.update_xaxes(gridcolor="#21262d", tickfont={"color": "#8b949e", "size": 8}, rangeslider_visible=False)
    fig.update_yaxes(gridcolor="#21262d", tickfont={"color": "#8b949e", "size": 8})
    fig.update_yaxes(showgrid=False, secondary_y=True, row=1, col=1, tickfont={"color": "#2dd4bf", "size": 8})
    for ann in fig.layout.annotations:
        ann.font.size = 10; ann.font.color = "#c9d1d9"
    return fig


def _ohlcv_from_snap(snap, ticker):
    """Best-effort OHLCV dict {Open,High,Low,Close,Volume} for a ticker from whatever the snap carries.
    Tries bandarmetrics series (IHSG + computed), then explicit ohlcv/price_data stores. None if absent."""
    snap = snap or {}
    bm = (snap.get("bandarmetrics", {}) or {}).get(ticker, {})
    ser = bm.get("series") if isinstance(bm, dict) else None
    if ser and ser.get("price"):
        try:
            p = ser["price"]
            return {"Open": ser.get("open") or p, "High": ser.get("high") or p,
                    "Low": ser.get("low") or p, "Close": p,
                    "Volume": ser.get("volume") or [0] * len(p)}
        except Exception:
            pass
    for key in ("ohlcv", "price_data", "ohlc", "prices"):
        store = snap.get(key)
        if isinstance(store, dict):
            d = store.get(ticker)
            if hasattr(d, "columns"):
                cols = {str(c).lower(): c for c in d.columns}
                if all(k in cols for k in ("open", "high", "low", "close")):
                    try:
                        return {"Open": d[cols["open"]].tolist(), "High": d[cols["high"]].tolist(),
                                "Low": d[cols["low"]].tolist(), "Close": d[cols["close"]].tolist(),
                                "Volume": d[cols["volume"]].tolist() if "volume" in cols else [0] * len(d)}
                    except Exception:
                        pass
            if isinstance(d, dict) and d.get("Close"):
                return d
    return None


def render_detail_charts(ticker, rr, snap, market_key="us_equity", px=None, part="all"):
    """Shared visual stack used by BOTH market-tab cards (render_rich_ticker) AND Alpha Center —
    so they never drift apart again. Renders inline: GEX+RiskRange+Entry/Target/SL chart, companion
    mini-charts (expected move / P/C OI / COT), and the IHSG bandarmetrics chart. px auto-derived.
    part='main' = only the main GEX chart; part='companions' = only companions+bandarmetrics;
    'all' = everything (lets the caller slot the setup box between the chart and the companions)."""
    import streamlit as st
    rr = rr or {}
    if px is None:
        for _k in ("prices", "price_history", "closes"):
            try:
                ph = (snap.get(_k) or {}).get(ticker)
                if ph is not None and len(ph):
                    px = float(ph.iloc[-1]); break
            except Exception:
                pass
    if px is None:
        _tr = rr.get("trade", {}) or {}
        try:
            px = ((float(_tr.get("lrr") or 0) + float(_tr.get("trr") or 0)) / 2) or None
        except (TypeError, ValueError):
            px = None
    _opts_c = (snap.get("yfinance_options", {}) or snap.get("options_data", {}) or {})
    _opts_c = _opts_c.get(ticker, {}) if isinstance(_opts_c, dict) else {}

    # unified DARK chart: GEX + Risk Range + Entry/Target/SL
    _walls = market_key not in ("forex", "commodity", "ihsg")
    if part in ("all", "main"):
      try:
        _setup = _setup_text_cols(rr, snap, ticker, market_key)
        _fig = _gex_levels_chart(ticker, px, rr, _opts_c, _cur_for(market_key, ticker), show_walls=_walls, setup=_setup,
                                 long_only=(market_key == "ihsg" or str(ticker).upper().endswith(".JK")))
        if _fig is not None:
            st.plotly_chart(_fig, width='stretch', config={"displayModeBar": False})
      except Exception:
        pass

    if part not in ("all", "companions"):
        return

    # NOTE: the expected-move / Put-Call-OI / COT mini-charts used to render here, but every number
    # they showed (expected move %, P/C ratio, COT net) is already in the setup box text above. They
    # were pure duplication, so they're merged into the setup box (removed here) per user request.

    # Bandarmetrics chart (candlestick + LPM + Intensity + Vol Rotation) — IHSG ONLY
    try:
        if market_key == "ihsg":
            _bm = (snap.get("bandarmetrics", {}) or {}).get(ticker, {})
            if _bm.get("ok"):
                _bfig = _bandarmetrics_chart(_bm, ticker, _cur_for(market_key, ticker))
                if _bfig is not None:
                    st.plotly_chart(_bfig, width='stretch', config={"displayModeBar": False})
                    _stl = _bm.get("stealth_accumulation") or {}
                    _stl_txt = (f" · 🤫 **HIDDEN ACCUMULATION ({_stl.get('score')})**" if _stl.get("is_stealth") else "")
                    _mk = _bm.get("markup_readiness") or {}
                    _mk_emoji = {"READY": "🟢", "BUILDING": "🟡", "EARLY": "⚪"}.get(_mk.get("verdict"), "")
                    _mk_txt = (f" · {_mk_emoji} **MM inventory: {_mk.get('verdict')}** "
                               f"({_mk.get('inventory_days')}d-vol terserap, coil {_mk.get('coil_ratio')}×, "
                               f"ruang {_mk.get('suppression_pct')}%)" if _mk.get("verdict") not in (None, "n/a") else "")
                    st.caption(
                        f"**LPM** (teal) = tekanan likuiditas bandar · **Intensity** = lonjakan aktivitas sebelum harga gerak · "
                        f"⚠️ Approx OHLCV; Foreign Flow butuh data Type-F IDX (gak ada di yfinance). Validasi: `validate_bandarmetrics.py`.")
    except Exception:
        pass

    # FX/COMMODITY driver bias (DXY/real-yield/GSR/oil-curve + COT + multi-TF confluence). Fully guarded:
    # renders nothing on any error or when no driver signal is present (degrades cleanly, never clutters).
    try:
        if market_key in ("forex", "commodity"):
            from engines import fx_commodity_driver_engine as _fx
            from engines.confluence_engine import multi_tf_confluence as _conf
            _peers = snap.get("metals_peers") or snap.get("peers")  # {'gold':px,'silver':px} if tab supplies it
            _ev = _fx.evaluate_from_snap(snap, ticker, peers=_peers)
            _drv = _ev.get("driver", {}) or {}
            _cot = _ev.get("cot", {}) or {}
            _gsr = _ev.get("gsr", {}) or {}
            _bits = []
            if _drv.get("bias"):
                _arrow = "🟢" if _drv["bias"] > 0 else "🔴"
                _bits.append(f"{_arrow} **{_drv.get('label')}** — {_drv.get('reason')}")
            if _gsr.get("favor") and _gsr.get("favor") != "n/a":
                _bits.append(f"⚖️ {_gsr.get('label')}")
            if _cot.get("bias"):
                _bits.append(f"📊 {_cot.get('label')} ({_cot.get('reason')})")
            _cf = _ev.get("confluence", {}) or {}
            if _cf.get("conviction") and _cf["conviction"] != "NONE":
                _bits.append(f"🎯 **Confluence {_cf['conviction']}** ({_cf.get('side')}) — {_cf.get('hold')}")
            if _bits:
                st.caption("**Driver:** " + " · ".join(_bits)
                           + "  \n_GYDI/DXY-dominant 2026; GSR mean-revert; oil curve. Butuh feed DXY/real-yield/curve lengkap buat sinyal penuh._")
    except Exception:
        pass

    # US-EQUITY driver (breakout + 52w-high proximity + relative-strength + dealer-gamma). Fully guarded.
    try:
        if market_key in ("us_equity", "us", "stocks"):
            from engines.equity_driver_engine import equity_driver as _eq
            from engines.confluence_engine import multi_tf_confluence as _conf
            _cs = None
            for _k in ("price_series", "closes", "prices"):
                _s = snap.get(_k)
                if isinstance(_s, (list, tuple)) and len(_s) > 62:
                    _cs = [float(x) for x in _s if isinstance(x, (int, float))]; break
            if _cs:
                _hi52 = snap.get("high_52w") or (max(_cs[-252:]) if len(_cs) >= 60 else None)
                _bench = snap.get("spy_ret_20d") or snap.get("bench_ret_20d")
                _ng = snap.get("net_gamma") or snap.get("net_dealer_gamma")
                _vr = snap.get("vol_ratio")
                _ed = _eq(_cs, bench_ret_20d=_bench, net_dealer_gamma=_ng, high_52w=_hi52, vol_ratio=_vr)
                _d = _ed.get("drivers", {})
                _eb = []
                _bo = _d.get("breakout", {})
                if _bo.get("label") and _bo["label"] != "breakout n/a":
                    _eb.append(("🟢" if _bo.get("bias", 0) > 0 else "🔴" if _bo.get("bias", 0) < 0 else "⚪") + f" {_bo.get('label')} — {_bo.get('reason')}")
                _dh = _d.get("distance_to_high", {})
                if _dh.get("label") and _dh["label"] != "ATH n/a":
                    _eb.append(f"📈 {_dh.get('label')} ({_dh.get('reason')})")
                _rs = _d.get("relative_strength", {})
                if _rs.get("bias"):
                    _eb.append(f"💪 {_rs.get('label')}")
                _ga = _d.get("gamma", {})
                if _ga.get("regime") not in (None, "n/a"):
                    _eb.append(f"🎰 {_ga.get('label')}")
                if _eb:
                    st.caption(f"**Driver ({_ed.get('verdict')}):** " + " · ".join(_eb)
                               + "  \n_RS/gamma muncul kalau data benchmark + GEX ada._")
    except Exception:
        pass

    # REAL buyer-vs-seller pressure (CVD proxy + absorption) — universal. Confirms long(real demand) /
    # short(real distribution); flags absorption (fake demand/supply). Fully guarded.
    try:
        from engines.real_flow_engine import real_flow as _rflow
        _df = _ohlcv_from_snap(snap, ticker)
        if _df:
            _rf = _rflow(_df, market=("crypto" if market_key == "crypto" else "generic"))
            if _rf.get("ok") and _rf["verdict"] != "BALANCED":
                _cf = ("✅ dukung LONG" if _rf["confirms_long"]
                       else "✅ dukung SHORT" if _rf["confirms_short"] else "")
                _wq = _rf.get("wash_quality", {}) or {}
                _wqt = (f" · ⚠️ volume quality suspect {_wq.get('suspect_frac'):.0%}"
                        if _wq.get("suspect_frac", 0) > 0.15 else "")
                st.caption(f"**Real flow:** {_rf['label']} · conf {_rf['confidence']:.0%}"
                           f"{(' · ' + _cf) if _cf else ''}{_wqt}  \n_{_rf['note']}_")
    except Exception:
        pass


def _render_oi_heatmap(snap, ticker, market_key):
    """OI heatmap (open interest by strike). ONLY renders when there's REAL OI data (commodity
    futures via ETF proxy). FX / no-data → renders NOTHING (no N/A caption clutter — positioning
    is already in the setup box via COT above)."""
    import streamlit as st
    if market_key == "forex":
        return  # no listed options → COT is in the setup box; skip empty N/A caption
    FUT_PROXY = {
        "CL=F": "USO", "GC=F": "GLD", "SI=F": "SLV", "NG=F": "UNG", "HG=F": "CPER",
        "RB=F": "UGA", "HO=F": "USO", "ZC=F": "CORN", "ZW=F": "WEAT", "ZS=F": "SOYB",
    }
    opts = (snap.get("options_data", {}) or {}).get(ticker, {})
    proxy = None
    if not opts:
        proxy = FUT_PROXY.get(ticker)
        if proxy:
            opts = (snap.get("options_data", {}) or {}).get(proxy, {})
    if opts and opts.get("total_call_oi"):
        tot_c = opts.get("total_call_oi", 0)
        tot_p = opts.get("total_put_oi", 0)
        pcr = (tot_p / tot_c) if tot_c else 0
        st.markdown("**📊 OI Heatmap (Open Interest by Strike)**")
        st.markdown(f"Call OI total: **{tot_c:,}** · Put OI total: **{tot_p:,}** · "
                    f"Put/Call OI ratio: **{pcr:.2f}**" + (f" (via {proxy} ETF proxy)" if proxy else ""))
        st.caption("Konsentrasi OI via ETF proxy (level absolut beda skala dari futures — pakai buat "
                   "lihat di mana OI numpuk + skew put/call, bukan 'wall' pasti). PCR >1 = put-heavy (hedging/bearish).")
    # else: no real OI data → render nothing (no N/A clutter below the setup box)


def _render_signal_boxes(rr, snap, market_key, show_options, ticker):
    """Tier1Alpha-style color-coded signal boxes per ticker."""
    import streamlit as st
    if not rr:
        return
    def _box(label, value, color):
        return (f"<div style='background:{color};color:white;padding:6px 4px;border-radius:6px;"
                f"text-align:center;font-weight:700;font-size:0.72rem;margin:2px 0;'>"
                f"{label}<br><span style='font-size:0.82rem;'>{value}</span></div>")
    GREEN, RED, AMBER, GREY = "#1a7f37", "#cf222e", "#bf8700", "#57606a"
    ss = compute_signal_strength(rr)
    ss_color = GREEN if ss["score"] > 0 else RED if ss["score"] < 0 else AMBER
    phase = rr.get("phase", "NEUTRAL")
    phase_color = GREEN if phase == "BULL" else RED if phase == "BEAR" else AMBER
    quality = rr.get("signals", {}).get("quality", "C")
    q_color = GREEN if quality.startswith("A") else RED if quality.startswith("short") else AMBER if quality == "B" else GREY
    hurst = rr.get("hurst", {}).get("interpretation", "RANDOM_WALK")
    hurst_short = {"TRENDING": "TREND", "MEAN_REVERTING": "MEAN-REV", "RANDOM_WALK": "RANDOM"}.get(hurst, "-")
    hurst_color = GREEN if hurst == "TRENDING" else AMBER if hurst == "MEAN_REVERTING" else GREY
    boxes = [
        _box("Signal Strength", ss["label"], ss_color),
        _box("Phase", phase, phase_color),
        _box("Quality", quality, q_color),
        _box("Hurst", hurst_short, hurst_color),
    ]
    if show_options:
        opts = (snap.get("options_data", {}) or {}).get(ticker, {})
        gex = opts.get("net_gex") or opts.get("gex")
        if gex is not None:
            try:
                g = float(gex)
                boxes.append(_box("Gamma", "LONG g" if g > 0 else "SHORT g", GREEN if g > 0 else RED))
            except (TypeError, ValueError):
                pass
    cols = st.columns(len(boxes))
    for c, b in zip(cols, boxes):
        c.markdown(b, unsafe_allow_html=True)
    if ss["detail"]:
        st.caption(f"Signal: {ss['detail']}")


def _phase_narrative(rr: dict) -> str:
    """Generate phase explanation in plain language."""
    if not rr:
        return "Phase data unavailable."

    phase = rr.get("phase", "NEUTRAL")
    formation = rr.get("signals", {}).get("formation", "NEUTRAL")
    trade_pos = rr.get("signals", {}).get("trade_position_pct", 50)
    hurst = rr.get("hurst", {}).get("interpretation", "RANDOM_WALK")

    parts = []

    # Trend direction
    if phase == "BULL":
        parts.append("**Trending BULLISH** (21d MA > 63d MA by +0.5%)")
    elif phase == "BEAR":
        parts.append("**Trending BEARISH** (21d MA < 63d MA by -0.5%)")
    else:
        parts.append("**Sideways** (21d MA ≈ 63d MA, no clear direction)")

    # Hurst behavior
    if hurst == "TRENDING":
        parts.append("Hurst > 0.6 → persistent trend regime, ride momentum")
    elif hurst == "MEAN_REVERTING":
        parts.append("Hurst < 0.4 → mean-reverting, fade extremes")
    else:
        parts.append("Hurst ≈ 0.5 → random walk, low signal")

    # Position in TRADE range
    if trade_pos < 25:
        parts.append(f"At **lower 25%** of TRADE range ({trade_pos:.0f}%) — kalo bullish → ADD zone")
    elif trade_pos > 75:
        parts.append(f"At **upper 25%** of TRADE range ({trade_pos:.0f}%) — kalo bullish → TRIM zone")
    else:
        parts.append(f"Mid TRADE range ({trade_pos:.0f}%) — no edge")

    # Formation
    if formation == "BULLISH":
        parts.append("Formation bullish (price > TREND TRR + TAIL TRR)")
    elif formation == "BEARISH":
        parts.append("Formation bearish (price < TREND LRR + TAIL LRR)")

    return " · ".join(parts)


def _entry_narrative(rr: dict) -> str:
    """Generate entry/exit zone explanation."""
    if not rr:
        return ""
    sig = rr.get("signals", {})
    action = sig.get("action", "HOLD")
    px = rr.get("px", 0)
    trade = rr.get("trade", {})
    trend = rr.get("trend", {})
    tail = rr.get("tail", {})

    trade_lrr = trade.get("lrr", 0) or 0
    trade_trr = trade.get("trr", 0) or 0
    trend_lrr = trend.get("lrr", 0) or 0
    trend_trr = trend.get("trr", 0) or 0
    rr_ratio = sig.get("rr_ratio", 0) or 0

    cur = _cur_for(None, rr.get("ticker"))
    def _m(v):
        return f"\\${(v or 0):.2f}" if cur == "$" else f"{cur}{(v or 0):.2f}"

    if action == "BUY_DIP":
        return (f"🎯 **BUY ZONE NOW** — price at LRR {_m(trade_lrr)}. "
                f"Take profit di TRR {_m(trade_trr)} (+{((trade_trr/px-1)*100):.1f}%). "
                f"Stop loss if breaks TAIL LRR {_m(tail.get('lrr', 0) or 0)}. R/R: {rr_ratio:.2f}")
    elif action == "ADD":
        return (f"🟢 **ADD ZONE** — lower 25% of TRADE range. "
                f"Entry up to {_m(trade_lrr + (trade_trr-trade_lrr)*0.25)}. "
                f"Trim di {_m(trade_trr)}. R/R: {rr_ratio:.2f}")
    elif action == "HOLD":
        return (f"⚪ **HOLD** — mid range. Wait. "
                f"Add jika turun ke {_m(trade_lrr)}, trim jika naik ke {_m(trade_trr)}.")
    elif action == "TRIM":
        return (f"🟡 **TRIM ZONE** — upper 25% of TRADE range. "
                f"Reduce exposure now. Re-add di {_m(trade_lrr)}.")
    elif action == "TRIM_RIP":
        return (f"🟠 **TAKE PROFIT** — price at/above TRR {_m(trade_trr)}. "
                f"Lock in gains. Wait pullback to {_m(trade_lrr)}.")
    elif action == "SHORT_RIP":
        return (f"🔴 **SHORT ZONE** — bearish trend, price at TRR {_m(trade_trr)}. "
                f"Cover di LRR {_m(trade_lrr)}. R/R: {rr_ratio:.2f}")
    elif action == "COVER":
        return (f"🟣 **COVER ZONE** — bearish, price at LRR {_m(trade_lrr)}. "
                f"Lock short gains.")
    elif action == "WATCH":
        return f"👀 **WATCH** — wait di sini. Setup unclear. LRR {_m(trade_lrr)} / TRR {_m(trade_trr)}"
    return ""


def _options_narrative(opts: dict, px: float, ticker: str) -> str:
    """Generate options + Greeks narrative."""
    if not opts:
        return ""

    parts = []

    # Walls
    call_wall = opts.get("call_wall") or opts.get("call_wall_strike")
    put_wall = opts.get("put_wall") or opts.get("put_wall_strike")
    max_pain = opts.get("max_pain")
    vol_trigger = opts.get("vol_trigger")
    gex = opts.get("gex") or opts.get("net_gex")

    if call_wall:
        dist_call = (float(call_wall) - px) / px * 100 if px else 0
        parts.append(f"**Call Wall \\${float(call_wall):.2f}** ({dist_call:+.1f}% away) — major resistance, MM short-gamma above")
    if put_wall:
        dist_put = (float(put_wall) - px) / px * 100 if px else 0
        parts.append(f"**Put Wall \\${float(put_wall):.2f}** ({dist_put:+.1f}% away) — major support, MM long-gamma below")
    if max_pain:
        parts.append(f"**Max Pain \\${float(max_pain):.2f}** — pinning target for OPEX week")
    if vol_trigger:
        dist_vt = (float(vol_trigger) - px) / px * 100 if px else 0
        parts.append(f"**Vol Trigger \\${float(vol_trigger):.2f}** ({dist_vt:+.1f}%) — gamma flip level")

    # GEX regime
    if gex is not None:
        try:
            gex_val = float(gex)
            if gex_val > 0:
                parts.append(f"GEX: **+\\${gex_val/1e9:.2f}B** (positive) → MM long gamma → **suppressed volatility**, mean-reverting")
            else:
                parts.append(f"GEX: **\\${gex_val/1e9:.2f}B** (negative) → MM short gamma → **amplified moves**, volatile breakouts")
        except (TypeError, ValueError):
            pass

    # IV
    iv_rank = opts.get("iv_rank")
    pc_ratio = opts.get("put_call_ratio") or opts.get("pc_ratio")
    if iv_rank is not None:
        try:
            ivr = float(iv_rank)
            if ivr > 70:
                parts.append(f"IV Rank **{ivr:.0f}** → vol expensive, sell premium")
            elif ivr < 30:
                parts.append(f"IV Rank **{ivr:.0f}** → vol cheap, buy options")
        except (TypeError, ValueError):
            pass
    if pc_ratio is not None:
        try:
            pc = float(pc_ratio)
            if pc > 1.0:
                parts.append(f"P/C ratio **{pc:.2f}** → put-heavy = hedging/bearish positioning")
            elif pc < 0.6:
                parts.append(f"P/C ratio **{pc:.2f}** → call-heavy = greed/squeeze risk")
        except (TypeError, ValueError):
            pass

    return "\n".join(f"• {p}" for p in parts) if parts else ""


def _mm_positioning(opts: dict, px: float) -> str:
    """Market maker positioning summary."""
    if not opts: return ""
    gex = opts.get("gex") or opts.get("net_gex")
    call_wall = opts.get("call_wall") or opts.get("call_wall_strike")
    put_wall = opts.get("put_wall") or opts.get("put_wall_strike")
    expected_move = opts.get("expected_move_pct") or opts.get("expected_move")

    summary_parts = []
    try:
        if gex is not None and float(gex) > 0 and call_wall and put_wall:
            summary_parts.append(
                f"**🟢 MM LONG GAMMA → BUY DIPS WORK.** Price kemungkinan pinball "
                f"antara Put Wall \\${float(put_wall):.2f} dan Call Wall \\${float(call_wall):.2f}. "
                f"Volatility supressed. Sell strangle/iron condor di range ini."
            )
        elif gex is not None and float(gex) < 0:
            summary_parts.append(
                f"**🔴 MM SHORT GAMMA → AMPLIFIED MOVES.** Break above Call Wall = "
                f"chase higher (MM buyback). Break below Put Wall = waterfall down. "
                f"Buy options, jangan sell premium."
            )
    except (TypeError, ValueError): pass

    if expected_move:
        try:
            em = float(expected_move)
            summary_parts.append(f"Expected move next week: **±{em:.2f}%** (implied by ATM straddle)")
        except (TypeError, ValueError): pass

    return "\n".join(summary_parts)


def _cot_pair_polarity(ticker: str) -> int:
    """+1 if a NET-LONG foreign-currency COT aligns with a LONG on this ticker, -1 if
    it inverts. CFTC FX futures are quoted USD-per-foreign → spec NET LONG = bullish the
    FOREIGN currency. For USD-BASE pairs (USDJPY/USDCAD/USDCHF) that is BEARISH the pair,
    so the COT must be inverted before comparing to a TRR/LRR bias on the pair itself.
    DXY/UUP track the dollar directly (+1). Commodities & foreign-base pairs: +1."""
    t = (ticker or "").upper().replace("=X", "")
    if t in ("DX-Y.NYB", "DXY", "UUP", "USD"):
        return 1
    if t.startswith("USD") and len(t) >= 6:   # USDJPY, USDCAD, USDCHF, ...
        return -1
    return 1


def _cot_narrative(cot: dict, ticker: str) -> str:
    """COT data interpretation for Forex/Commodities."""
    if not cot: return ""
    parts = []
    nc_net = cot.get("noncomm_net") or cot.get("non_commercial_net")
    nc_chg = cot.get("noncomm_change_wow") or cot.get("noncomm_change")
    extreme = cot.get("extreme_position") or cot.get("at_extreme")

    if nc_net is not None:
        try:
            nn = float(nc_net)
            pol = _cot_pair_polarity(ticker)
            raw = "NET LONG" if nn > 0 else "NET SHORT"
            specs = "bullish" if nn > 0 else "bearish"
            if pol < 0:
                pair_imp = "BEARISH" if nn > 0 else "BULLISH"
                parts.append(f"**Non-commercial {raw}: {nn:+,.0f}** (large specs {specs} the foreign ccy) "
                             f"→ {pair_imp} for {ticker} — USD-base pair, COT is on the quote ccy (inverted).")
            else:
                parts.append(f"**Non-commercial {raw}: {nn:+,.0f}** contracts (large specs {specs})")
        except (TypeError, ValueError): pass

    if nc_chg is not None:
        try:
            ncc = float(nc_chg)
            if abs(ncc) > 5000:
                direction = "added longs" if ncc > 0 else "added shorts" if ncc < 0 else "flat"
                parts.append(f"WoW change: {ncc:+,.0f} ({direction}) — momentum {'building' if abs(ncc) > 10000 else 'modest'}")
        except (TypeError, ValueError): pass

    if extreme:
        parts.append("⚠️ **EXTREME POSITIONING** (>2σ from 1yr avg) — contrarian setup, watch for reversal")

    return "\n".join(f"• {p}" for p in parts) if parts else ""


def _onchain_narrative(oc: dict, ticker: str) -> str:
    """On-chain accumulation/distribution narrative for Crypto."""
    if not oc: return ""
    parts = []
    whale_7d = oc.get("whale_accum_7d") or oc.get("whale_accum")
    funding = oc.get("funding_rate") or oc.get("funding_8h")
    oi_chg = oc.get("oi_change_7d") or oc.get("oi_chg")
    exch_outflow = oc.get("exchange_outflow_pct") or oc.get("exch_outflow")
    sig = oc.get("signal") or ""

    if whale_7d is not None:
        try:
            wa = float(whale_7d) * 100 if abs(float(whale_7d)) < 1 else float(whale_7d)
            if wa > 5:
                parts.append(f"**Whale ACCUMULATION** +{wa:.1f}% (7d) — top 100 wallets adding")
            elif wa < -5:
                parts.append(f"**Whale DISTRIBUTION** {wa:.1f}% (7d) — top wallets dumping")
        except (TypeError, ValueError): pass

    if funding is not None:
        try:
            f = float(funding) * 100 if abs(float(funding)) < 1 else float(funding)
            if f > 0.05:
                parts.append(f"Funding +{f:.3f}% → longs paying shorts = overheated, squeeze risk")
            elif f < -0.05:
                parts.append(f"Funding {f:.3f}% → shorts paying longs = bottom signal, short squeeze setup")
        except (TypeError, ValueError): pass

    if oi_chg is not None:
        try:
            oc_val = float(oi_chg) * 100 if abs(float(oi_chg)) < 1 else float(oi_chg)
            if abs(oc_val) > 10:
                parts.append(f"OI {oc_val:+.1f}% (7d) — {'leverage building' if oc_val > 0 else 'deleveraging'}")
        except (TypeError, ValueError): pass

    if exch_outflow is not None:
        try:
            eo = float(exch_outflow) * 100 if abs(float(exch_outflow)) < 1 else float(exch_outflow)
            if eo > 2:
                parts.append(f"Exchange outflow +{eo:.1f}% → coins moving to self-custody = bullish HODL")
            elif eo < -2:
                parts.append(f"Exchange inflow {eo:.1f}% → coins moving to exchanges = sell pressure")
        except (TypeError, ValueError): pass

    if sig:
        parts.append(f"**On-chain signal: {sig}**")

    return "\n".join(f"• {p}" for p in parts) if parts else ""


def _bandar_narrative(b: dict, ticker: str) -> str:
    """IHSG bandar (Indonesian market maker) detailed narrative.

    Based on Hengky Adinata methodology + bandarmologi research:
    - Cornering supply detection
    - 4-phase goreng cycle (akumulasi → corp action → liquiditas → euforia)
    - Foreign vs domestic broker classification
    - Cross-trade detection (same broker buying + selling = wash trade)
    - Konglomerat group flow (Bakrie, Salim, Barito, Astra, Lippo)
    """
    if not b: return ""
    parts = []

    flow_signal = b.get("flow_signal", "UNCLEAR")
    confidence = b.get("confidence", 0)

    signal_explanations = {
        "ACCUMULASI_ASLI": (
            "🟢 **AKUMULASI ASLI** — bandar lokal aktif kumpulin posisi. "
            "Pattern: bid-offer frequency tinggi di bid, broker dominan (BRPT, MNCS, dll) jadi top buyer "
            "berhari-hari, harga konsolidasi (volatility menurun). Setup goreng phase 1."
        ),
        "DISTRIBUSI_ASLI": (
            "🔴 **DISTRIBUSI ASLI** — bandar sedang exit posisi. "
            "Pattern: top sellers = broker yang sebelumnya top buyer, harga di range tinggi tapi volume menurun, "
            "bid-offer asymmetric (lebih banyak offer). EXIT NOW."
        ),
        "FAKE_AKUM": (
            "🟡 **FAKE AKUMULASI** — kelihatan akumulasi tapi cross-trade detected. "
            "Same broker code muncul di top buyer DAN top seller = wash trade. "
            "Mereka coba narik retail, jangan kena."
        ),
        "FAKE_DISTR": (
            "🟡 **FAKE DISTRIBUSI** — kelihatan distribusi tapi cross-trade detected. "
            "Bandar coba scare retail biar jual murah, mereka beli balik. Hold."
        ),
        "FORCED_SELL": (
            "🔴 **FORCED SELL / MARGIN CALL** — broker likuidasi posisi nasabah. "
            "Volume spike + price drop tajam + concentrated seller. "
            "Bisa jadi bottom signal kalo udah selesai."
        ),
        "WINDOW_DRESSING": (
            "🟣 **WINDOW DRESSING** — biasanya akhir bulan/kuartal/tahun. "
            "Bandar/MI naikin harga buat appearance NAV. Setelah period close = balik turun."
        ),
        "UNCLEAR": "⚪ Flow signal belum jelas — observasi lebih lanjut.",
    }
    parts.append(signal_explanations.get(flow_signal, signal_explanations["UNCLEAR"]))
    if confidence:
        try:
            parts.append(f"Confidence: **{float(confidence)*100:.0f}%** (broker concentration + cross-trade analysis)")
        except (TypeError, ValueError): pass

    # Top brokers
    top_buy = b.get("top_brokers_buy") or b.get("top_buyers") or []
    top_sell = b.get("top_brokers_sell") or b.get("top_sellers") or []
    if top_buy:
        broker_explanations = _broker_codes_explained(top_buy[:5], side="buy")
        parts.append(f"\n**🟢 Top Buyers:** {broker_explanations}")
    if top_sell:
        broker_explanations = _broker_codes_explained(top_sell[:5], side="sell")
        parts.append(f"**🔴 Top Sellers:** {broker_explanations}")

    # Cornering signal
    cornering = b.get("cornering_signal") or b.get("cornering") or {}
    if isinstance(cornering, dict) and cornering.get("detected"):
        thesis = cornering.get("thesis", "Floating shares mengecil drastis")
        parts.append(
            f"\n⚠️ **CORNERING SUPPLY DETECTED**\n"
            f"• Floating shares yang available di market mengecil drastis (kemungkinan <15% free float)\n"
            f"• {thesis}\n"
            f"• Implikasi: harga bisa lompat tajam ke atas karena tidak ada supply. "
            f"Tapi juga risiko: ketika bandar exit, harga collapse karena retail panic."
        )

    # Goreng phase
    goreng = b.get("goreng_phase")
    if goreng:
        phase_explanations = {
            "PHASE_1_AKUMULASI": (
                "📦 **PHASE 1 — AKUMULASI** (3-12 bulan): "
                "Bandar diam-diam beli di harga murah. Volume rendah, range sempit. "
                "Retail belum aware. Best entry point."
            ),
            "PHASE_2_CORP_ACTION": (
                "📰 **PHASE 2 — CORPORATE ACTION** (1-3 bulan): "
                "Berita keluar (right issue / akuisisi / spin-off / pembagian dividen besar). "
                "Volume mulai naik, harga break range akumulasi. Retail mulai notice."
            ),
            "PHASE_3_LIQUIDITAS": (
                "💧 **PHASE 3 — LIQUIDITAS** (1-2 bulan): "
                "Bandar marik retail dengan candle bullish yang nyolok. Volume tinggi. "
                "Influencer/media coverage mulai banyak. Bandar mulai distribute pelan-pelan."
            ),
            "PHASE_4_EUFORIA": (
                "🔥 **PHASE 4 — EUFORIA** (2-4 minggu): "
                "Harga parabolik. Retail FOMO. Volume sangat tinggi. "
                "Bandar sudah hampir habis distribusi. CRASH IMMINENT — EXIT NOW."
            ),
        }
        parts.append(f"\n{phase_explanations.get(goreng, goreng)}")

    # Konglomerat group flow
    konglo = b.get("konglomerat_group") or b.get("conglomerate")
    if konglo:
        parts.append(f"\n🏢 **Group: {konglo}** — coordinated flow detected. "
                    f"Watch cross-correlation dengan ticker satu grup.")

    return "\n".join(parts)


def compute_optimal_entry(rr: dict, snap: dict, market_key: str, ticker: str) -> dict:
    """Synthesize the OPTIMAL ENTRY using ONLY data appropriate to this market.

    Data by market (Edward's rule — never use options/greeks for IHSG/forex):
      • us_equity / crypto : TRR/LRR + options(GEX/walls/max-pain) + vanna/charm timing
      • forex              : TRR/LRR + COT positioning (NO options/greeks)
      • commodity          : TRR/LRR + COT + OI heatmap walls (NO options/greeks for futures)
      • ihsg               : TRR/LRR + bandar accumulation (NO options/greeks/COT)
    """
    if not rr:
        return {}
    px = rr.get("px", 0) or 0
    phase = rr.get("phase", "NEUTRAL")
    trade = rr.get("trade", {})
    lrr = trade.get("lrr", 0) or 0
    trr = trade.get("trr", 0) or 0
    width = trr - lrr if (trr and lrr) else 0
    pos = (px - lrr) / width if width > 0 else 0.5

    bull = phase == "BULL" or rr.get("phase_code", 0) == 1
    bear = phase == "BEAR" or rr.get("phase_code", 0) == -1

    # ── KEITH OVERRIDE: markets follow Keith's actual public calls ───────
    # If Keith says BEARISH TRADE on this name, don't chase even if our phase is bull.
    keith_note = None
    try:
        from engines.keith_signal_sync import resolve_direction
        dash_dir = "LONG" if bull else "SHORT" if bear else "NEUTRAL"
        kd = resolve_direction(ticker, dash_dir)
        if kd.get("override") or kd.get("keith_trade") not in (None, "NEUTRAL", ""):
            kt = kd.get("keith_trade", "NEUTRAL")
            ktr = kd.get("keith_trend", "NEUTRAL")
            keith_note = f"🎯 **Keith ({ticker}):** TRADE {kt} · TREND {ktr} — {kd.get('basis','')}"
            # If Keith TRADE bearish but we're bull → flip framing to 'wait/don't chase'
            if kt == "BEARISH" and bull:
                bull = False  # don't show 'buy now'; treat as wait
    except Exception:
        pass

    # Base entry zone from TRR/LRR (universal)
    parts = []
    if keith_note:
        parts.append(keith_note)
    is_fx = market_key == "forex"
    fmt = ".4f" if is_fx else ",.2f"
    cur = _cur_for(market_key, ticker)
    def _f(v): return f"{cur}{format(v, fmt)}"

    _long_only_ce = (market_key == "ihsg") or str(ticker).upper().endswith(".JK")
    _dirce = "long" if bull else ("flat" if _long_only_ce else "short") if bear else "flat"
    _lvce = _directional_levels(px, _dirce, t_lrr=lrr, t_trr=trr,
                                tr_lrr=rr.get("trend", {}).get("lrr", 0) or 0,
                                tr_trr=rr.get("trend", {}).get("trr", 0) or 0,
                                tl_lrr=rr.get("tail", {}).get("lrr", 0) or 0,
                                tl_trr=rr.get("tail", {}).get("trr", 0) or 0, long_only=_long_only_ce)
    if bull:
        stop = _lvce.get("stop", lrr - width * 0.30)
        target1 = _lvce.get("target", trr)
        target2 = _lvce.get("target2", trr)
        direction = "LONG"
        # Frame entry RELATIVE to current price (Keith daily-actionable style)
        if pos < 0.25:
            parts.append(f"🟢 **BUY ZONE SEKARANG** — harga {_f(px)} udah di lower TRADE band ({pos:.0%}). Entry di sini, ini level yang Keith sebut 'buy-able now'.")
        elif pos < 0.55:
            dip = lrr + width * 0.10
            parts.append(f"🟡 **Bisa mulai sekarang** ({_f(px)}, mid-low {pos:.0%}) — atau tunggu dip ke {_f(dip)} buat add lebih bagus.")
        elif pos < 0.80:
            zone_top = lrr + width * 0.15
            parts.append(f"🟠 **Mid-high ({pos:.0%})** — jangan chase. Tunggu pullback ke {_f(lrr)}–{_f(zone_top)} ({((zone_top/px-1)*100):+.1f}% s/d {((lrr/px-1)*100):+.1f}%) buat entry optimal.")
        else:
            parts.append(f"🔴 **Extended ({pos:.0%}, dekat TRR)** — JANGAN kejar. Trim kalau udah punya, atau tunggu reset ke {_f(lrr)} ({((lrr/px-1)*100):+.1f}%).")
        parts.append(f"**Stop:** < {_f(stop)} · **T1:** {_f(target1)} ({((target1/px-1)*100):+.1f}%) · **T2:** {_f(target2)} ({((target2/px-1)*100):+.1f}%)")
    elif bear:
        stop = _lvce.get("stop", trr + width * 0.30)
        target1 = _lvce.get("target", lrr)
        target2 = _lvce.get("target2", lrr)
        direction = "SHORT" if market_key != "ihsg" else "AVOID/WAIT"
        if market_key == "ihsg":
            parts.append(f"🔴 **IHSG buy-only — HINDARI.** Bearish ({_f(px)}). Tunggu reclaim {_f(lrr)} ({((lrr/px-1)*100):+.1f}%) sebelum mikir akumulasi.")
        else:
            if pos > 0.75:
                parts.append(f"🔴 **SHORT ZONE SEKARANG** — harga {_f(px)} di upper band ({pos:.0%}). Short di sini (Keith 'sell rip').")
            elif pos > 0.45:
                parts.append(f"🟠 **Mid-high ({pos:.0%})** — bisa short scale-in, atau tunggu rip ke {_f(trr)} ({((trr/px-1)*100):+.1f}%) buat entry lebih bagus.")
            else:
                parts.append(f"🟡 **Mid-low ({pos:.0%})** — udah turun jauh. Jangan short di bawah; tunggu bounce ke {_f(trr)} ({((trr/px-1)*100):+.1f}%).")
            parts.append(f"**Stop:** > {_f(stop)} · **T1:** {_f(target1)} ({((target1/px-1)*100):+.1f}%) · **T2:** {_f(target2)} ({((target2/px-1)*100):+.1f}%)")
    else:
        direction = "WAIT"
        parts.append(f"⚪ **Range-bound** ({_f(px)}, pos {pos:.0%}) — beli dekat {_f(lrr)}, jual dekat {_f(trr)}. No trend edge, fade extremes.")

    # ── Market-specific refinement (ONLY appropriate data) ───────────────
    if market_key in ("us_equity", "crypto"):
        opts = (snap.get("options_data", {}) or {}).get(ticker, {})
        if opts and opts.get("call_wall"):
            cw, pw, mp = opts.get("call_wall"), opts.get("put_wall"), opts.get("max_pain")
            gex = opts.get("net_gex")
            if bull and pw:
                parts.append(f"📊 **Options confirm:** Put Wall {_f(pw)} = dealer support (entry floor). "
                             f"Call Wall {_f(cw)} = upside magnet/T-zone. Max Pain {_f(mp)}.")
            elif bear and cw:
                parts.append(f"📊 **Options confirm:** Call Wall {_f(cw)} = dealer resistance (short ceiling). "
                             f"Put Wall {_f(pw)} = downside target.")
            if gex is not None:
                try:
                    g = float(gex)
                    parts.append(f"γ regime: {'LONG gamma (mean-revert, fade extremes)' if g > 0 else 'SHORT gamma (momentum, breakouts run)'}.")
                except (TypeError, ValueError):
                    pass
            # Vanna/charm timing
            try:
                from engines.options_greeks_engine import get_opex_calendar
                cal = get_opex_calendar()
                vcw = cal.get("vanna_charm_window", {}) if cal else {}
                status = vcw.get("status", "")
                if status in ("WINDOW_ACTIVE_BUILDING", "CHARM_MAX", "OPEX_DAY"):
                    parts.append(f"🗓️ **Timing terbaik:** vanna/charm window AKTIF ({status}) → {vcw.get('note', 'pin risk into OPEX')}. Charm-max ~{vcw.get('peak', '')}.")
                elif vcw.get("start"):
                    parts.append(f"🗓️ **Timing:** vanna/charm window buka {vcw.get('start')} → peak {vcw.get('peak')} (charm-max window = best entry buat pin move).")
            except Exception:
                pass
        else:
            parts.append("📊 Options belum ter-fetch — entry pakai TRR/LRR dulu. (Rebuild buat GEX/walls + vanna/charm timing.)")

    elif market_key == "forex":
        cot_map = (snap.get("cot_oi", {}) or {}).get("cot", {}) or snap.get("cot_data", {}) or {}
        cot = cot_map.get(ticker, {})
        if cot and cot.get("noncomm_net") is not None:
            net = cot.get("noncomm_net")
            chg = cot.get("noncomm_change_wow")
            pol = _cot_pair_polarity(ticker)
            eff = (net or 0) * pol               # pair-aligned net (inverts USD-base pairs)
            inv = " (inverted: USD-base pair)" if pol < 0 else ""
            align = ('Selaras sama long bias' if (bull and eff > 0)
                     else 'Selaras sama short bias' if (bear and eff < 0)
                     else 'Hati-hati: COT divergence dari TRR/LRR')
            parts.append(f"📋 **COT confirm:** non-comm net {net:+,.0f}{inv}"
                         + (f" (Δ {chg:+,.0f} WoW)" if chg is not None else "")
                         + f". {align}.")
        else:
            parts.append("📋 COT belum ter-fetch — entry pakai TRR/LRR. (COT confirm positioning saat live.)")

    elif market_key == "commodity":
        cot_map = (snap.get("cot_oi", {}) or {}).get("cot", {}) or snap.get("cot_data", {}) or {}
        cot = cot_map.get(ticker, {})
        if cot and cot.get("noncomm_net") is not None:
            net = cot.get("noncomm_net")
            parts.append(f"📋 **COT:** non-comm net {net:+,.0f} — {'managed money long' if (net or 0) > 0 else 'managed money short'}.")
        # OI walls via ETF proxy
        FUT_PROXY = {"CL=F": "USO", "GC=F": "GLD", "SI=F": "SLV", "NG=F": "UNG", "HG=F": "CPER", "RB=F": "UGA"}
        proxy = FUT_PROXY.get(ticker)
        opts = (snap.get("options_data", {}) or {}).get(proxy or ticker, {})
        if opts and opts.get("call_wall"):
            parts.append(f"📊 **OI walls (via {proxy or ticker}):** resistance {_f(opts.get('call_wall'))}, "
                         f"support {_f(opts.get('put_wall'))}, max-pain {_f(opts.get('max_pain'))}.")
        elif not cot:
            parts.append("📋 COT + OI belum ter-fetch — entry pakai TRR/LRR. (Saat live: COT + OI walls confirm.)")

    elif market_key == "ihsg":
        bandar_map = snap.get("ihsg_broker_proxy", {}) or snap.get("ihsg_broker_data", {}) or {}
        b = bandar_map.get(ticker, {})
        if b and b.get("phase"):
            parts.append(f"🏦 **Bandar:** {b.get('phase')} — {b.get('note', '')}")
        else:
            # Auto-compute bandar proxy from price/volume action (no manual!)
            bp = _auto_bandar_proxy(rr, snap, ticker)
            if bp:
                parts.append(f"🏦 **Bandar (auto-proxy):** {bp}")

    return {"direction": direction, "lines": parts}


def _auto_bandar_proxy(rr: dict, snap: dict, ticker: str) -> str:
    """Auto-derive bandar accumulation/distribution signal from price action + range position.
    Replaces 'manual check' — uses what we have (TRR/LRR position, phase, Hurst, BSI proxy)."""
    if not rr:
        return ""
    phase = rr.get("phase", "NEUTRAL")
    trade = rr.get("trade", {})
    px = rr.get("px", 0) or 0
    lrr = trade.get("lrr", 0) or 0
    trr = trade.get("trr", 0) or 0
    width = trr - lrr if (trr and lrr) else 0
    pos = (px - lrr) / width if width > 0 else 0.5
    hurst = rr.get("hurst", {}).get("value", 0.5) if isinstance(rr.get("hurst"), dict) else 0.5
    bsi = rr.get("bsi", {}) if isinstance(rr.get("bsi"), dict) else {}

    # Heuristic bandar phase from structure
    if phase == "BULL" and pos < 0.35:
        return ("ACCUMULATION (proxy) — harga di lower TRADE range + uptrend, "
                "pola bandar nyerap di bawah. Watch volume naik tanpa harga turun = akumulasi asli.")
    elif phase == "BULL" and pos > 0.75:
        return ("MARKUP/DISTRIBUSI awal (proxy) — harga di upper range + uptrend. "
                "Kalau volume spike tapi harga stuck = mulai distribusi.")
    elif phase == "BEAR" and pos > 0.65:
        return ("DISTRIBUTION (proxy) — harga di upper range + downtrend, bandar buang barang ke retail. "
                "Hindari FOMO di rip.")
    elif phase == "BEAR" and pos < 0.30:
        return ("MARKDOWN/FORCED SELL (proxy) — harga di lower range + downtrend. "
                "Tunggu basing sebelum akumulasi.")
    else:
        return (f"NETRAL (proxy) — range-bound, pos {pos:.0%}. "
                "Bandar belum nunjukin niat jelas. Pantau broker summary + bid-offer untuk konfirmasi.")


def _render_targets(rr: dict, px: float, market_key: str):
    """Render explicit nearest/mid/farthest target prices from TRR/LRR.

    Edward's request: di US stocks tab + front-run, kasih target terdekat + terjauh.
    Computed from TRR/LRR (TRADE/TREND/TAIL) — these ARE the system targets.
    """
    import streamlit as st
    if not rr: return
    trade = rr.get("trade", {})
    trend = rr.get("trend", {})
    tail = rr.get("tail", {})
    phase = rr.get("phase", "NEUTRAL")

    # For BULL/sideways: targets are upper TRR. For BEAR: targets are lower LRR.
    if phase == "BEAR":
        nearest = trade.get("lrr") or 0
        mid = trend.get("lrr") or 0
        farthest = tail.get("lrr") or 0
        label_n, label_m, label_f = "Target Terdekat (TRADE LRR)", "Target Mid (TREND LRR)", "Target Terjauh (TAIL LRR)"
        direction = "↓"
    else:
        nearest = trade.get("trr") or 0
        mid = trend.get("trr") or 0
        farthest = tail.get("trr") or 0
        label_n, label_m, label_f = "Target Terdekat (TRADE TRR)", "Target Mid (TREND TRR)", "Target Terjauh (TAIL TRR)"
        direction = "↑"

    is_fx = market_key == "forex"
    fmt = ".4f" if is_fx else ",.2f"
    cur_sym = "" if is_fx else ("Rp" if market_key == "ihsg" else "$")

    if nearest and px:
        d_near = (nearest/px - 1) * 100
        d_mid = (mid/px - 1) * 100 if mid else 0
        d_far = (farthest/px - 1) * 100 if farthest else 0
        st.markdown(
            f"**🎯 Target Prices** ({direction}): "
            f"Near **{cur_sym}{format(nearest, fmt)}** ({d_near:+.1f}%) · "
            f"Mid **{cur_sym}{format(mid, fmt)}** ({d_mid:+.1f}%) · "
            f"Far **{cur_sym}{format(farthest, fmt)}** ({d_far:+.1f}%)"
        )


def _broker_codes_explained(brokers: list, side="buy") -> str:
    # Common IHSG broker codes — classify foreign vs domestic + behavior
    FOREIGN_BROKERS = {"CS", "KZ", "MS", "AK", "BK", "DB", "GS", "ML", "DX", "RG", "UU"}  # CIMB Securities, Kim Eng (Maybank), Macquarie, etc.
    LOCAL_BANDAR_BROKERS = {"BR", "BNI", "DR", "FZ", "LG", "MQ", "MU", "NI", "RX", "PD", "PG", "YP", "YU", "YJ", "ZP", "BK"}  # local market makers
    RETAIL_BROKERS = {"AT", "AZ", "MG", "OD", "PC", "BQ", "EP", "II"}  # primarily retail flow

    results = []
    for code in brokers:
        c = str(code).upper().strip()
        if c in FOREIGN_BROKERS:
            results.append(f"`{c}` (foreign)")
        elif c in LOCAL_BANDAR_BROKERS:
            results.append(f"`{c}` (local bandar)")
        elif c in RETAIL_BROKERS:
            results.append(f"`{c}` (retail flow)")
        else:
            results.append(f"`{c}`")
    return " · ".join(results)


# ═══════════════════════════════════════════════════════════════════════════
# MAIN RENDER
# ═══════════════════════════════════════════════════════════════════════════

ACTION_COLORS = {
    "BUY_DIP": "#3FB950", "ADD": "#3FB950", "HOLD": "#D29922",
    "TRIM": "#D29922", "TRIM_RIP": "#FF8C00",
    "SHORT_RIP": "#F85149", "COVER": "#A371F7",
    "WATCH": "#8B949E", "NO_DATA": "#484F58",
}

# Per-card build marker — lets the user detect a STALE rich_ticker_card.py deploy
# (the sidebar stamp lives in app.py and can't catch a partially-pushed card file).
_CARD_BUILD = "s45"


def _render_greeks_panel(snap, ticker, market_key, px):
    """Compact-but-complete live greeks/options line for US + crypto. Renders ONLY when REAL options
    exist (source != proxy) — never shows fake greeks. Restores the net-GEX / γ-flip / max-pain / walls /
    P/C / expected-move / dark-pool readout that was lost when the setup box merge dropped the panel."""
    import streamlit as st
    if market_key not in ("us_equity", "crypto"):
        return
    od = (snap.get("options_data", {}) or snap.get("yfinance_options", {}) or {}).get(ticker, {})
    if not od or od.get("source") == "proxy":
        return
    _cur = _cur_for(market_key, ticker)
    def f(v):
        try:
            return f"{_cur}{float(v):,.2f}"
        except (TypeError, ValueError):
            return None
    bits = []
    gex = od.get("net_gex")
    if gex is not None:
        try:
            g = float(gex)
            bits.append(f"**Net GEX** {g:+,.0f} → {'LONG γ (pinned/mean-revert, fade extremes)' if g > 0 else 'SHORT γ (momentum, breakout/squeeze run)'}")
        except (TypeError, ValueError):
            pass
    gf = od.get("gamma_flip")
    if gf:
        _gx = f(gf)
        if _gx:
            bits.append(f"γ-flip {_gx}" + ((" (px di atas → dealer support)" if px and px > float(gf) else " (px di bawah → volatile)") if px else ""))
    mp = od.get("max_pain")
    if mp and f(mp): bits.append(f"Max-pain {f(mp)}")
    cw, pw = od.get("call_wall"), od.get("put_wall")
    if cw and f(cw): bits.append(f"Call wall {f(cw)}")
    if pw and f(pw): bits.append(f"Put wall {f(pw)}")
    pcr = od.get("put_call_ratio")
    if pcr is not None:
        try:
            _p = float(pcr); bits.append(f"P/C {_p:.2f} ({'bearish skew' if _p > 1 else 'bullish skew'})")
        except (TypeError, ValueError):
            pass
    em = od.get("expected_move_pct") or od.get("expected_move")
    if em is not None:
        try: bits.append(f"Exp move ±{float(em):.1f}%")
        except (TypeError, ValueError): pass
    dxn = od.get("net_dex") or od.get("dex")
    if dxn is not None:
        try:
            _d = float(dxn); bits.append(f"DEX {_d:+,.0f} ({'dealers longer delta' if _d > 0 else 'shorter delta'})")
        except (TypeError, ValueError): pass
    dp = od.get("dark_pool_sentiment") or ((od.get("dark_pool") or {}).get("net_sentiment"))
    if dp: bits.append(f"Dark-pool: {dp}")
    if bits:
        st.caption("🟢 **Greeks (live options):** " + " · ".join(bits))


def _render_block1_extras(rr, snap, ticker, market_key, show_options, show_onchain, px=None):
    """Compact extras folded INTO the single ticker block (no expander).
    Vanna/Charm OPEX timing + On-Chain are now MERGED into the setup box text above (no duplicate
    captions here). Only the forex/commodity OI heatmap remains — FX is honest N/A→COT, commodity
    uses real ETF-proxy OI, no fake call/put walls."""
    import streamlit as st
    # Live greeks/options panel (US + crypto, real options only) — restored compact readout
    if market_key in ("us_equity", "crypto") and show_options:
        try:
            _render_greeks_panel(snap, ticker, market_key, px)
        except Exception:
            pass
    # On-chain panel (crypto) — uses REAL DeFiLlama TVL flow; honest n/a for netflow/whale/MVRV (need feed)
    if market_key == "crypto" and show_onchain:
        try:
            from engines.onchain_engine import evaluate_from_snap as _oc
            _r = _oc(snap, ticker)
            if _r.get("available", 0) > 0:
                _e = "🟢" if _r["verdict"] > 0 else "🔴" if _r["verdict"] < 0 else "⚪"
                _bits = [p["reason"] for p in _r["parts"].values() if p.get("bias")]
                _tvl = _r.get("tvl_usd")
                _tvls = f" · TVL ${_tvl/1e9:.2f}B" if isinstance(_tvl, (int, float)) and _tvl else ""
                st.caption(f"⛓️ **On-chain:** {_e} {_r['label']}{_tvls}"
                           + (" · " + " · ".join(_bits) if _bits else "") + f"  \n_{_r['note']}_")
        except Exception:
            pass
    # OI heatmap for forex/commodities (per spec) — FX honest N/A→COT, commodity real ETF-proxy OI, no fake walls
    if market_key in ("forex", "commodity"):
        try:
            _render_oi_heatmap(snap, ticker, market_key)
        except Exception:
            pass


def render_rich_ticker(
    ticker: str, rr: dict, snap: dict, market_key: str = "us_equity",
    show_options: bool = False, show_cot: bool = False,
    show_onchain: bool = False, show_bandar: bool = False,
    is_frontrun: bool = False, frontrun_info: dict = None,
    show_oi: bool = False,
):
    """Render comprehensive ticker card with all narratives.

    Args:
        ticker: symbol
        rr: TRR/LRR dict from risk_range engine
        snap: full snapshot for data lookup
        market_key: us_equity/forex/commodity/crypto/ihsg
        show_*: which overlays to enable
        is_frontrun: True for front-run tab tickers
        frontrun_info: optional chain reaction context for front-run
    """
    if not rr or not isinstance(rr, dict):
        with st.container(border=True):
            st.markdown(f"### {ticker}  &nbsp; <span style='color:#8B949E;font-size:0.7rem;'>NO DATA</span>",
                       unsafe_allow_html=True)
            st.caption("Price/RR data unavailable for this ticker.")
        return

    px = rr.get("px") or 0
    phase = rr.get("phase", "NEUTRAL")
    sig = rr.get("signals", {})
    action = sig.get("action", "HOLD")
    quality = sig.get("quality", "C")

    # IHSG no-short rule
    if market_key == "ihsg" and action in ("SHORT_RIP", "COVER"):
        action = "WATCH"

    color = ACTION_COLORS.get(action, "#8B949E")

    with st.container(border=True):
        # ── HEADER: ticker, price, action ────────────────────────────────
        hc1, hc2, hc3 = st.columns([2.2, 1.2, 1.5])
        with hc1:
            head = f"### {ticker}"
            if is_frontrun:
                head += "  🔮"
            st.markdown(f"{head} <span style='font-size:0.5rem;color:#3FB950;vertical-align:super;'>card·{_CARD_BUILD}</span>",
                        unsafe_allow_html=True)
        with hc2:
            _cur = _cur_for(market_key, ticker)
            if market_key == "forex":
                _pv = f"{px:.4f}"
            elif _cur == "Rp":
                _pv = f"Rp{px:,.2f}"
            else:
                _pv = f"\\${px:,.2f}"
            st.metric("Price", _pv)
        with hc3:
            st.markdown(
                f"<div style='background:{color};color:#0D1117;padding:8px 12px;"
                f"border-radius:6px;text-align:center;font-weight:800;font-size:0.85rem;'>"
                f"{action}</div>",
                unsafe_allow_html=True,
            )

        # ── FRONT-RUN context (kalau di front-run tab) ────────────────────
        if is_frontrun and frontrun_info:
            driver = frontrun_info.get("driver", "?")
            shock = frontrun_info.get("shock_pct", 0)
            expected = frontrun_info.get("expected_pct", 0)
            lag = frontrun_info.get("lag_days", 0)
            thesis = frontrun_info.get("thesis", "")
            chain = frontrun_info.get("chain", "")
            readiness = frontrun_info.get("readiness", "")
            readiness_line = f"\n\n**Status: {readiness}**" if readiness else ""
            st.info(
                f"🔮 **Front-Run Setup:** Driver **{driver}** moved **{shock:+.2f}%** → "
                f"expected impact pada {ticker}: **{expected:+.2f}% within {lag} days**. "
                f"Chain: {chain}. {thesis}{readiness_line}"
            )

        # ── BLOCK 1 — main GEX/Risk-Range chart with the setup overlay INSIDE the plot ──
        # Setup (Posisi/Entry/Target/Stop/Cara-masuk/Dealer/Vanna/Dark-pool) is now rendered as
        # 2-column panels inside the chart itself (no separate text block below).
        render_detail_charts(ticker, rr, snap, market_key, px, part="main")

        # companion mini-charts (expected move / P/C OI / COT) + bandarmetrics, below the chart
        render_detail_charts(ticker, rr, snap, market_key, px, part="companions")

        # Compact extras folded into the SAME block (no expander)
        try:
            _render_block1_extras(rr, snap, ticker, market_key, show_options, show_onchain, px)
        except Exception:
            pass


def compute_accumulation_readiness(rr: dict, snap: dict, ticker: str) -> dict:
    """Detect if a name is being ACCUMULATED / setting up to rise, using options
    flow + greeks + dark pool. ONLY returns a signal if real data exists (else None).

    Methodology (from deep research):
      • Dark pool (Unusual Whales/scraped): prints BELOW spot + repeated + volume
        spike = institutions building BEFORE the public move ('front-run the rally').
      • Options flow: daily Vol >> OI = NEW positions; call-heavy + low PCR = bullish.
      • Gamma (GEX): price ABOVE gamma_flip = dealers long gamma (support); a large
        positive call_wall above = magnet/target; negative net GEX = explosive fuel.
      • DEX rising = dealers getting longer delta (bullish hedging flow).
    """
    od = (snap.get("options_data", {}) or {}).get(ticker, {})
    oc_check = (snap.get("onchain_data", {}) or {}).get(ticker, {})
    px_check = (snap.get("prices", {}) or {}).get(ticker)
    if not od and not oc_check and px_check is None:
        return None  # nothing to compute from

    px = rr.get("px", 0) or od.get("spot", 0) or 0
    score = 0
    signals = []
    has_any = False

    # ── GREEKS: gamma positioning (REAL options only — proxy GEX is unreliable) ──
    _real_opts = bool(od) and od.get("source") != "proxy"
    gex = od.get("net_gex") if _real_opts else None
    gflip = od.get("gamma_flip") if _real_opts else None
    cwall = od.get("call_wall") if _real_opts else None
    pwall = od.get("put_wall") if _real_opts else None
    if gflip and px:
        has_any = True
        if px > gflip:
            score += 1; signals.append(f"px>{gflip:,.0f} γ-flip → dealers long gamma (support)")
        else:
            signals.append(f"px<{gflip:,.0f} γ-flip → below flip (volatile/needs reclaim)")
    if gex is not None:
        has_any = True
        if gex < 0:
            score += 1; signals.append("net GEX negative → explosive-move fuel (squeeze risk up)")
        else:
            signals.append("net GEX positive → moves dampened/pinned")
    if cwall and px and cwall > px:
        signals.append(f"call wall {cwall:,.0f} = upside magnet/target ({(cwall/px-1)*100:+.0f}%)")

    # ── OPTIONS FLOW: PCR + new positioning ──
    pcr = od.get("put_call_ratio")
    if pcr is not None:
        has_any = True
        if pcr < 0.7:
            score += 1; signals.append(f"PCR {pcr:.2f} low → call-heavy (bullish flow)")
        elif pcr > 1.3:
            score -= 1; signals.append(f"PCR {pcr:.2f} high → put-heavy (hedging/bearish)")
    vol_oi = od.get("volume_oi_ratio")
    if vol_oi and vol_oi > 1.0:
        score += 1; signals.append(f"Vol/OI {vol_oi:.1f}× → NEW positions opening (fresh interest)")

    # ── DARK POOL (if present from scraped/UW) ──
    dp = od.get("dark_pool", {}) or {}
    dp_net = dp.get("net_sentiment") or od.get("dark_pool_sentiment")
    dp_below = dp.get("prints_below_pct") or od.get("dp_below_pct")
    if dp_net is not None or dp_below is not None:
        has_any = True
        if (dp_net and str(dp_net).lower() in ("bullish", "accumulation")) or (dp_below and dp_below > 60):
            score += 2; signals.append("🌑 Dark pool: net buying BELOW spot → institutions accumulating")
        elif (dp_net and str(dp_net).lower() in ("bearish", "distribution")) or (dp_below and dp_below < 40):
            score -= 2; signals.append("🌑 Dark pool: selling above spot → distribution")

    # ── FINRA off-exchange short volume — REAL free dark-pool signal (all US tickers) ──
    finra = (snap.get("finra_short", {}) or {}).get(ticker.upper(), {})
    if finra.get("signal"):
        has_any = True
        if finra["signal"] == "accumulation":
            score += 2; signals.append(f"🌑🟢 FINRA dark pool: {finra.get('note','')}")
        elif finra["signal"] == "distribution":
            score -= 2; signals.append(f"🌑🔴 FINRA dark pool: {finra.get('note','')}")
    dex = od.get("dex") or od.get("net_dex")
    if dex is not None:
        has_any = True
        if dex > 0:
            score += 1; signals.append("DEX positive → dealers long delta (supportive)")

    # ── ON-CHAIN (crypto): unusual TVL/volume/flow = quiet accumulation ──
    oc = (snap.get("onchain_data", {}) or {}).get(ticker, {})
    if oc:
        has_any = True
        tvl_chg = oc.get("tvl_change_7d") or oc.get("tvl_change_pct")
        vol_tvl = oc.get("volume_tvl_ratio")
        net_flow = oc.get("net_flow") or oc.get("netflow")
        if tvl_chg is not None:
            if tvl_chg > 10:
                score += 2; signals.append(f"⛓️ TVL +{tvl_chg:.0f}% → capital flowing IN (accumulation)")
            elif tvl_chg < -10:
                score -= 2; signals.append(f"⛓️ TVL {tvl_chg:.0f}% → capital leaving")
        if vol_tvl is not None and vol_tvl > 0.5:
            score += 1; signals.append(f"⛓️ Vol/TVL {vol_tvl:.2f} → unusual on-chain activity spike")
        if net_flow is not None:
            if net_flow > 0:
                score += 1; signals.append("⛓️ Net inflow positive → on-chain accumulation")
            else:
                score -= 1; signals.append("⛓️ Net outflow → on-chain distribution")

    # ── INSTITUTIONAL FLOW PROXY (price/vol-derived, works for ALL tickers) ──
    prices = snap.get("prices", {}) or {}
    if prices.get(ticker) is not None:
        try:
            from engines.institutional_proxy import analyze_institutional
            inst = analyze_institutional(ticker, prices, vix=snap.get("vix", 20.0) or 20.0)
            if inst.get("ok"):
                has_any = True
                fs = inst.get("flow_score", 0)
                bias = inst.get("bias", "NEUTRAL")
                if bias == "BULLISH" or fs > 0:
                    score += 1; signals.append(f"🏦 Institutional flow {bias} (score {fs}, price-based proxy)")
                elif bias == "BEARISH" or fs < 0:
                    score -= 1; signals.append(f"🏦 Institutional flow {bias} (score {fs})")
        except Exception:
            pass

    # ── 13F SMART MONEY (which famous funds hold + recent action = quiet accumulation) ──
    try:
        from engines.smart_money_tracker import get_ticker_smart_money
        sm = get_ticker_smart_money(ticker)
        if sm.get("smart_money_held") and sm.get("n_holders", 0) > 0:
            has_any = True
            act = sm.get("recent_action", "")
            top = sm.get("top_holder", "")
            n = sm.get("n_holders", 0)
            if "adding" in act.lower() or "🟢" in act:
                score += 2; signals.append(f"💎 {n} smart-money funds hold (top: {top}) — net ADDING (quiet accumulation)")
            elif "trim" in act.lower() or "🔴" in act:
                score -= 1; signals.append(f"💎 {n} smart-money funds hold but net trimming")
            else:
                score += 1; signals.append(f"💎 {n} smart-money funds hold (top: {top}) — {act}")
    except Exception:
        pass

    if not has_any:
        return None

    if score >= 4:
        label, emoji = "SIAP NAIK (strong accumulation)", "🟢🟢"
    elif score >= 2:
        label, emoji = "Ancang-ancang (building)", "🟢"
    elif score >= 0:
        label, emoji = "Netral / wait", "⚪"
    elif score >= -2:
        label, emoji = "Hati-hati (soft)", "🟡"
    else:
        label, emoji = "Distribution (avoid)", "🔴"

    # Flag data provenance so modeled proxy isn't mistaken for real dealer flow/dark pool
    src = od.get("source", "")
    if src == "proxy":
        signals.insert(0, "📐 PROXY (price-derived estimate — bukan real flow/dark pool)")
    elif od.get("dark_pool") or od.get("dark_pool_sentiment"):
        signals.insert(0, "🌑 REAL dark pool + options flow")

    return {"score": score, "label": label, "emoji": emoji, "signals": signals[:7], "source": src or "yfinance"}


def build_options_recommendation(rr: dict, snap: dict, ticker: str, market_key: str = "us_equity") -> dict:
    """Position report. TWO modes:
      • REAL options (yfinance live) → full dealer/walls/vanna/charm/dark-pool + TRR/LRR confluence
      • No real options (proxy/futures/ihsg) → TRR/LRR-based ONLY (entry=LRR, target=TRR,
        stop below LRR) + COT (futures) / institutional (stocks). NO fake gamma shown.
    Proxy GEX is SMA-derived & unreliable, so it is NEVER displayed as dealer positioning."""
    od = (snap.get("options_data", {}) or {}).get(ticker, {})
    px = rr.get("px", 0) or od.get("spot", 0) or 0
    if not px:
        return None
    has_real_opts = bool(od) and od.get("source") != "proxy"

    # TRR/LRR bands (always)
    trade = rr.get("trade", {}) or {}; trend = rr.get("trend", {}) or {}; tail = rr.get("tail", {}) or {}
    t_lrr, t_trr = trade.get("lrr", 0) or 0, trade.get("trr", 0) or 0
    tr_lrr, tr_trr = trend.get("lrr", 0) or 0, trend.get("trr", 0) or 0
    tl_lrr = tail.get("lrr", 0) or 0
    width = t_trr - t_lrr if (t_trr and t_lrr) else px * 0.04
    pos = (px - t_lrr) / width if width > 0 else 0.5

    # Greeks ONLY if real options
    gflip = od.get("gamma_flip") if has_real_opts else None
    gex = od.get("net_gex") if has_real_opts else None
    cwall = od.get("call_wall") if has_real_opts else None
    pwall = od.get("put_wall") if has_real_opts else None
    maxpain = od.get("max_pain") if has_real_opts else None
    pcr = od.get("put_call_ratio") if has_real_opts else None
    em = (od.get("expected_move_pct") or od.get("expected_move")) if has_real_opts else None
    above_flip = bool(gflip and px > gflip)
    short_gamma = has_real_opts and ((gex is not None and gex < 0) or (gflip and px < gflip))

    # sanity: walls must be on the right side (put<px<call); ignore if inverted (bad data)
    if pwall and pwall > px: pwall = None
    if cwall and cwall < px: cwall = None

    # Direction
    phase = rr.get("phase", "NEUTRAL"); pc = rr.get("phase_code", 0)
    bull = phase == "BULL" or pc == 1; bear = phase == "BEAR" or pc == -1
    keith_note = None; keith_flip = False
    try:
        from engines.keith_signal_sync import resolve_direction
        kd = resolve_direction(ticker, "LONG" if bull else "SHORT" if bear else "NEUTRAL")
        kt = kd.get("keith_trade", "NEUTRAL")
        if kt and kt != "NEUTRAL":
            keith_note = f"Keith TRADE {kt} / TREND {kd.get('keith_trend','NEUTRAL')}"
        if kt == "BEARISH" and bull:
            bull = False; keith_flip = True
    except Exception:
        pass

    # Dark pool (real only)
    dp = od.get("dark_pool", {}) or {} if has_real_opts else {}
    dp_acc = has_real_opts and ((str(dp.get("net_sentiment") or od.get("dark_pool_sentiment") or "").lower() in ("bullish","accumulation")) or ((dp.get("prints_below_pct") or od.get("dp_below_pct") or 0) > 60))
    dp_dist = has_real_opts and ((str(dp.get("net_sentiment") or od.get("dark_pool_sentiment") or "").lower() in ("bearish","distribution")) or (0 < (dp.get("prints_below_pct") or od.get("dp_below_pct") or 100) < 40))

    _cur = _cur_for(market_key, ticker)
    def f(v): return f"{_cur}{v:,.2f}"   # market-aware symbol; rendered inside HTML div
    def pct(v): return f"{(v/px-1)*100:+.1f}%"

    # ── INSTRUMENT + DIRECTION ──
    _long_only = (market_key == "ihsg") or str(ticker).upper().endswith(".JK")   # IDX/spot equity = buy-only
    instrument = None; direction = None; conviction = "medium"
    if _long_only:
        instrument, direction = (("AKUMULASI (beli spot bertahap)", "long") if bull
                                 else ("WAIT / hindari (buy-only)", "flat"))      # bearish buy-only → WAIT, NEVER short
    elif market_key in ("commodity", "forex"):
        instrument, direction = ("LONG FUTURES", "long") if bull else ("SHORT FUTURES", "short") if bear else ("WAIT (range)", "flat")
    else:  # us_equity / crypto
        if bull:
            if has_real_opts and (short_gamma or dp_acc):
                instrument, direction, conviction = "BUY CALL (leverage squeeze)", "long", "high"
            else:
                instrument, direction = "LONG SPOT/SHARES", "long"
        elif bear:
            if has_real_opts and (short_gamma or dp_dist):
                instrument, direction, conviction = "BUY PUT (leverage downside)", "short", "high"
            else:
                instrument, direction = "SHORT / SELL", "short"
        else:
            instrument, direction = ("WAIT — Keith bearish near-term (jangan chase)", "flat") if keith_flip else ("WAIT (range — fade extremes)", "flat")

    # ── ENTRY / TARGET / STOP (TRR/LRR base; walls refine if real) ──
    entry_zone = None; confluence = []; target = None; stop = None
    _lv = _directional_levels(px, direction, t_lrr=t_lrr, t_trr=t_trr, tr_lrr=tr_lrr, tr_trr=tr_trr,
                              tl_lrr=tl_lrr, tl_trr=(tail.get("trr", 0) or 0),
                              call_wall=cwall if has_real_opts else None,
                              put_wall=pwall if has_real_opts else None)
    if direction == "long" and _lv:
        e_lo, e_hi = _lv["entry_lo"], _lv["entry_hi"]
        entry_zone = f"{f(e_lo)}–{f(e_hi)}" + (" (beli sekarang, udah di support)" if px <= e_hi else " (tunggu pullback ke sini)")
        if has_real_opts and pwall:
            confluence.append(f"Put wall {f(pwall)} = support dealer ({pct(pwall)})")
            if abs(pwall - t_lrr) / px < 0.04:
                confluence[-1] = f"🎯 Put wall {f(pwall)} ≈ TRADE LRR {f(t_lrr)} → support confluence kuat"
        if has_real_opts and cwall and abs(cwall - _lv["target"]) / px < 0.05:
            confluence.append(f"🎯 Call wall {f(cwall)} ≈ target {f(_lv['target'])} → resistance confluence")
        target = f"{f(_lv['target'])} ({pct(_lv['target'])})"
        stop = f"< {f(_lv['stop'])} ({pct(_lv['stop'])})"
    elif direction == "short" and _lv:
        e_lo, e_hi = _lv["entry_lo"], _lv["entry_hi"]
        entry_zone = f"{f(e_lo)}–{f(e_hi)}" + (" (short sekarang, udah di resistance)" if px >= e_lo else " (tunggu rip ke sini)")
        if has_real_opts and cwall:
            confluence.append(f"Call wall {f(cwall)} = resistance dealer ({pct(cwall)})")
            if abs(cwall - t_trr) / px < 0.04:
                confluence[-1] = f"🎯 Call wall {f(cwall)} ≈ TRADE TRR {f(t_trr)} → resistance confluence"
        if has_real_opts and pwall and abs(pwall - _lv["target"]) / px < 0.05:
            confluence.append(f"🎯 Put wall {f(pwall)} ≈ target {f(_lv['target'])} → support confluence")
        target = f"{f(_lv['target'])} ({pct(_lv['target'])})"
        stop = f"> {f(_lv['stop'])} ({pct(_lv['stop'])})"
    else:
        entry_zone = f"{f(t_lrr)} (beli) / {f(t_trr)} (jual) — range, fade extremes"

    # ── Dealer + vanna/charm (REAL options only) ──
    dealer = None; vc = None
    if has_real_opts and (gflip or gex is not None):
        if above_flip:
            dealer = f"Long gamma (di atas γ-flip {f(gflip)}) → harga pinned/stabil, dealer jual rip beli dip"
        elif gflip:
            dealer = f"Short gamma (di bawah γ-flip {f(gflip)}) → gerakan diperbesar; reclaim {f(gflip)} = flip bullish"
        else:
            dealer = "Short gamma → explosive" if (gex or 0) < 0 else "Long gamma → teredam"
        try:
            from engines.options_greeks_engine import build_options_intelligence
            intel = build_options_intelligence(ticker, od, px, {})
            _oc_cal = intel.get("opex_calendar", {})
            vcw = _oc_cal.get("vanna_charm_window", {})
            dto = _oc_cal.get("days_to_opex")
            opx = _oc_cal.get("current_opex")
            stt = vcw.get("status", "")
            if stt == "WINDOW_ACTIVE_BUILDING": vc = f"Vanna tailwind aktif ({dto}d ke OPEX) → kalau vol turun dealer beli → drift bullish, pin ke call wall/max pain"
            elif stt == "CHARM_MAX": vc = f"Charm max ({dto}d ke OPEX) → pinning ke max pain {f(maxpain) if maxpain else ''}; gerakan terbatas s/d expiry"
            elif stt == "POST_OPEX": vc = "Post-OPEX → gamma reset, posisi unwinding → window gerakan baru (vol naik)"
            elif stt == "PRE_WINDOW": vc = f"Pre-vanna window ({dto}d ke OPEX) — efek vanna/charm belum dominan"
            if vc and opx: vc = f"{vc} · OPEX {opx}"
            if intel.get("expected_move_pct"): em = intel["expected_move_pct"]
        except Exception:
            pass

    # COT (futures)
    cot_note = None
    if market_key in ("commodity", "forex"):
        cot = (snap.get("cot_data", {}) or {}).get(ticker, {})
        nc = cot.get("noncommercial_net") or cot.get("net_position")
        if nc is not None:
            aligned = (nc > 0 and direction == "long") or (nc < 0 and direction == "short")
            cot_note = f"COT non-comm net {nc:+,.0f} — {'selaras' if aligned else 'divergence (hati-hati)'}"

    # On-chain (crypto) — compact, merged INTO the box (no separate caption below)
    onchain_note = None
    if market_key == "crypto":
        _ocd = (snap.get("crypto_tokens", {}) or snap.get("onchain_data", {}) or {}).get(ticker, {})
        if _ocd:
            try:
                _oc = _onchain_narrative(_ocd, ticker)
                if _oc:
                    onchain_note = " ".join(_oc.replace("\n", " ").split())
            except Exception:
                onchain_note = None

    dp_line = "🌑 Dark pool: akumulasi (institusi beli diam-diam)" if dp_acc else \
              "🌑 Dark pool: distribusi (institusi jual)" if dp_dist else None

    # FINRA off-exchange short volume — REAL free dark-pool signal (all US tickers,
    # independent of options). Overrides the (rarer) options dark_pool when present.
    finra = (snap.get("finra_short", {}) or {}).get(ticker.upper(), {})
    if finra.get("note"):
        sig = finra.get("signal")
        emoji = "🌑🟢" if sig == "accumulation" else "🌑🔴" if sig == "distribution" else "🌑"
        dp_line = f"{emoji} Dark pool (FINRA): {finra['note']}"
        if sig == "accumulation" and direction == "long":
            confluence.append(f"🌑 FINRA off-exch short {finra.get('short_pct',0):.0f}% → MM hedging dark-pool buys")

    # Expected move / breakout (REAL options only — needs real walls/IV)
    by_expiry = None; breakout_up = None; breakout_down = None
    if has_real_opts and em:
        lo = px * (1 - em/100); hi = px * (1 + em/100)
        by_expiry = f"{f(lo)} — {f(hi)} (±{em:.1f}%) s/d expiry"
    if has_real_opts and cwall:
        nxt = tr_trr if (tr_trr and tr_trr > cwall) else None
        breakout_up = f"break call wall {f(cwall)} → squeeze ke {f(nxt)} ({pct(nxt)})" if nxt else f"break call wall {f(cwall)} → gamma squeeze (dealer kejar)"
    if has_real_opts and pwall:
        nxt = tr_lrr if (tr_lrr and tr_lrr < pwall) else None
        breakout_down = f"break put wall {f(pwall)} → drop ke {f(nxt)} ({pct(nxt)})" if nxt else f"break put wall {f(pwall)} → support hilang, downside cepat"

    sig_label = "🟢 Bull" if bull else "🔴 Bear" if bear else "⚪ Netral"

    # ── MULTI-POSITIONING: how to express this trade via SPOT vs LEVERAGE ──
    # Only for markets with real long/short. IHSG = buy-only (spot only, no leverage section).
    positions = []
    if direction in ("long", "short"):
        is_long = direction == "long"
        e_txt = entry_zone or "—"
        # 1) SPOT / CASH (no leverage)
        if market_key == "ihsg":
            positions.append({"type": "💵 Spot (cash)", "detail":
                f"Akumulasi bertahap · size penuh, hold sampai fase berubah"})
        elif market_key in ("us_equity", "crypto"):
            lbl = "Long shares/spot" if is_long else "Short shares (borrow)"
            positions.append({"type": "💵 Spot (cash, no leverage)", "detail":
                f"{lbl} · size penuh · stop lebih longgar, hold lebih lama"})
        # 2) LEVERAGE via OPTIONS (real options + equity/crypto only)
        if has_real_opts and market_key in ("us_equity", "crypto"):
            if is_long:
                strike = gflip if (gflip and gflip <= px) else round(px, 2)
                fuel = "short-gamma = dealer kejar (gamma fuel) ✓" if short_gamma else "long-gamma = theta drag, pilih expiry ≥45d"
                positions.append({"type": "⚡ Leverage — BUY CALL", "detail":
                    f"Strike ~{f(strike)} (ATM/slightly-ITM), expiry ≥30-45d · risiko = premium (defined, ga kena likuidasi) · target call wall {f(cwall) if cwall else (target or '—')} · {fuel}"})
            else:
                strike = gflip if (gflip and gflip >= px) else round(px, 2)
                positions.append({"type": "⚡ Leverage — BUY PUT", "detail":
                    f"Strike ~{f(strike)} (ATM/slightly-ITM), expiry ≥30-45d · risiko = premium (defined) · target put wall {f(pwall) if pwall else (target or '—')}"})
        elif market_key in ("us_equity", "crypto"):
            # No real options → margin leverage is still available for the spot-vs-leverage choice
            positions.append({"type": "⚡ Leverage — Margin", "detail":
                f"{'Long' if is_long else 'Short'} margin 1.5-2x · stop lebih ketat dari spot · size lebih kecil, awas margin call"})
        # 3) LEVERAGE via FUTURES / PERP
        if market_key in ("commodity", "forex"):
            positions.append({"type": "⚡ Leverage — Futures", "detail":
                f"{'Long' if is_long else 'Short'} futures · stop di balik LRR/TRR · size kecil (margin), stop ketat krn likuidasi"})
        elif market_key == "crypto":
            positions.append({"type": "⚡ Leverage — Perp/Futures", "detail":
                f"{'Long' if is_long else 'Short'} perp 2-5x · awas funding rate + likuidasi, size kecil"})

    return {
        "ticker": ticker, "market": market_key, "px": px, "has_real_opts": has_real_opts,
        "instrument": instrument, "direction": direction, "conviction": conviction, "pos": pos,
        "entry_zone": entry_zone, "confluence": confluence, "target": target, "stop": stop,
        "dealer": dealer, "vanna_charm": vc, "dark_pool": dp_line, "cot": cot_note, "onchain": onchain_note, "keith": keith_note,
        "pcr": pcr, "expected_move": em, "by_expiry": by_expiry,
        "breakout_up": breakout_up, "breakout_down": breakout_down,
        "call_wall": cwall, "put_wall": pwall, "sig_label": sig_label, "positions": positions,
        "trade_lrr": t_lrr, "trade_trr": t_trr, "trend_lrr": tr_lrr, "trend_trr": tr_trr, "fmt": f,
    }


def render_options_recommendation(rr: dict, snap: dict, ticker: str, market_key: str = "us_equity"):
    """Clean scannable report. Plain $ inside HTML div (no LaTeX). TRR/LRR always shown.
    Options/greeks/dark-pool/vanna-charm ONLY when real options exist."""
    rec = build_options_recommendation(rr, snap, ticker, market_key)
    if not rec:
        return False
    f = rec["fmt"]
    bar = "#3FB950" if rec["direction"] == "long" else "#F85149" if rec["direction"] == "short" else "#8B949E"
    dir_emoji = {"long": "🟢", "short": "🔴", "flat": "⚪"}.get(rec["direction"], "⚪")
    conv = " · ⚡ high-conviction" if rec["conviction"] == "high" else ""
    if rec["has_real_opts"]:
        src = "🟢 live options + greeks"
    elif market_key in ("commodity", "forex"):
        src = "TRR/LRR + COT"
    elif market_key == "ihsg":
        src = "TRR/LRR + bandar"
    else:
        src = "TRR/LRR (options N/A)"

    # Header: TICKER · price · signal · TRR/LRR · walls(if real)
    bits = [f"📋 <b>{rec['ticker']}</b>", f"{f(rec['px'])}", rec["sig_label"],
            f"TRADE {f(rec['trade_lrr'])}–{f(rec['trade_trr'])}"]
    if rec["has_real_opts"] and (rec["call_wall"] or rec["put_wall"]):
        w = []
        if rec["call_wall"]: w.append(f"CW {f(rec['call_wall'])}")
        if rec["put_wall"]: w.append(f"PW {f(rec['put_wall'])}")
        bits.append(" ".join(w))
    header = " · ".join(bits) + f" <span style='opacity:0.55;font-size:0.82em'>({src})</span>"

    # LEFT column = the trade plan; RIGHT column = entry styles + microstructure/context.
    # (Was one narrow left strip leaving the right half empty — the thing circled across all markets.)
    left_rows = [f"{dir_emoji} <b>Posisi:</b> {rec['instrument']}{conv}"]
    if rec["entry_zone"]: left_rows.append(f"<b>Entry:</b> {rec['entry_zone']}")
    for c in rec["confluence"][:2]:
        left_rows.append(f"<span style='opacity:0.85'>&nbsp;&nbsp;↳ {c}</span>")
    if rec["target"]: left_rows.append(f"<b>Target:</b> {rec['target']}  ·  <b>Stop:</b> {rec['stop']}")
    if rec["by_expiry"]: left_rows.append(f"<b>Expected move:</b> {rec['by_expiry']}")
    if rec["breakout_up"]: left_rows.append(f"<span style='opacity:0.85'>📈 {rec['breakout_up']}</span>")
    if rec["breakout_down"]: left_rows.append(f"<span style='opacity:0.85'>📉 {rec['breakout_down']}</span>")

    right_rows = []
    if rec.get("positions") and len(rec["positions"]) >= 2:
        right_rows.append("<b>🎚️ Cara masuk (pilih sesuai gaya):</b>")
        for p in rec["positions"]:
            right_rows.append(f"<span style='opacity:0.9'>&nbsp;&nbsp;{p['type']}: {p['detail']}</span>")
    if rec["dealer"]: right_rows.append(f"<span style='opacity:0.8'><b>Dealer:</b> {rec['dealer']}</span>")
    if rec["vanna_charm"]: right_rows.append(f"<span style='opacity:0.8'><b>Vanna/charm:</b> {rec['vanna_charm']}</span>")
    if rec["dark_pool"]: right_rows.append(f"<span style='opacity:0.8'>{rec['dark_pool']}</span>")
    if rec["cot"]: right_rows.append(f"<span style='opacity:0.8'><b>COT:</b> {rec['cot']}</span>")
    if rec.get("onchain"): right_rows.append(f"<span style='opacity:0.8'><b>⛓️ On-chain:</b> {rec['onchain']}</span>")
    if rec["keith"]: right_rows.append(f"<span style='opacity:0.65'>📌 {rec['keith']}</span>")
    extras = []
    if rec.get("pcr") is not None: extras.append(f"PCR {rec['pcr']:.2f}")
    if extras: right_rows.append(f"<span style='opacity:0.6;font-size:0.85em'>{' · '.join(extras)}</span>")

    _left = "<br>".join(left_rows)
    _right = "<br>".join(right_rows) if right_rows else "<span style='opacity:0.35'>—</span>"
    # Borderless → MERGED into the main ticker card block (no nested box-in-box). Keeps the
    # 2-column layout so the width is used; just a left accent bar for direction.
    st.markdown(
        f"<div style='border-left:3px solid {bar};padding:2px 0 4px 12px;margin:4px 0 6px;"
        f"font-size:0.85rem;line-height:1.65;'>"
        f"<div style='font-weight:600;margin-bottom:7px;'>{header}</div>"
        f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:6px 22px;'>"
        f"<div>{_left}</div><div>{_right}</div></div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    return True
