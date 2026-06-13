"""ticker_card.py — Reusable Hedgeye-style ticker card v40"""
import streamlit as st


def render_triple_rr_bar(rr: dict, height: int = 14) -> str:
    """Render TRADE/TREND/TAIL stacked range visual."""
    if not rr or "px" not in rr:
        return ""
    px = rr["px"]
    trade = rr.get("trade", {})
    trend = rr.get("trend", {})
    tail = rr.get("tail", {})

    # Use TAIL as outer bounds
    if not tail.get("lrr") or not tail.get("trr"):
        lo, hi = trend.get("lrr", px * 0.95), trend.get("trr", px * 1.05)
    else:
        lo, hi = tail["lrr"], tail["trr"]

    if hi <= lo:
        return ""

    def pos(v):
        return max(0, min(100, (v - lo) / (hi - lo) * 100))

    px_pos = pos(px)
    t_lrr = pos(trade.get("lrr", lo))
    t_trr = pos(trade.get("trr", hi))
    tr_lrr = pos(trend.get("lrr", lo))
    tr_trr = pos(trend.get("trr", hi))

    return f"""
<div style="margin:8px 0;">
  <div style="position:relative;height:{height}px;background:#21262D;border-radius:4px;overflow:hidden;">
    <div style="position:absolute;left:{tr_lrr}%;width:{tr_trr-tr_lrr}%;top:0;bottom:0;background:rgba(88,166,255,0.18);"></div>
    <div style="position:absolute;left:{t_lrr}%;width:{t_trr-t_lrr}%;top:2px;bottom:2px;background:rgba(255,196,0,0.30);border-radius:2px;"></div>
    <div style="position:absolute;left:{px_pos}%;top:50%;transform:translate(-50%,-50%);width:8px;height:8px;background:#fff;border:2px solid #58A6FF;border-radius:50%;z-index:10;"></div>
  </div>
  <div style="display:flex;justify-content:space-between;font-size:0.55rem;color:#8B949E;margin-top:1px;">
    <span>TAIL {lo:.2f}</span>
    <span>TRADE</span>
    <span>TAIL {hi:.2f}</span>
  </div>
</div>
"""


def render_ticker_card(row: dict, expanded: bool = False, show_options: bool = True,
                       show_cot: bool = False, show_onchain: bool = False, show_bandar: bool = False):
    """Main ticker card renderer. Pass row dict from risk_setup_engine.build_ticker_rows."""
    ticker = row.get("ticker", "?")
    px = row.get("px")
    try:
        px_str = f"{float(px):.2f}" if px not in (None, "", 0) else "—"
    except (TypeError, ValueError):
        px_str = "—"
    rec_pct = row.get("recommended_pct")
    try:
        rec_pct_str = f"{float(rec_pct):.2f}%" if rec_pct not in (None, "") else "—"
    except (TypeError, ValueError):
        rec_pct_str = "—"
    action = row.get("action", "HOLD")
    quality = row.get("quality", "C")
    phase = row.get("phase", "NEUTRAL")
    formation = row.get("formation", "NEUTRAL")

    # Color logic
    action_colors = {
        "BUY_DIP": "#3FB950", "ADD": "#3FB950", "HOLD": "#8B949E",
        "WATCH": "#D29922", "TRIM": "#D29922", "TRIM_RIP": "#D29922",
        "SHORT_RIP": "#F85149", "COVER": "#3FB950",
    }
    action_color = action_colors.get(action, "#8B949E")

    phase_color = {"BULL": "#3FB950", "BEAR": "#F85149", "NEUTRAL": "#8B949E"}.get(phase, "#8B949E")

    quality_color = "#3FB950" if quality.startswith("A") else "#D29922" if quality.startswith("B") else "#8B949E"

    keith_trade = row.get("keith_trade")
    keith_badge = ""
    if keith_trade:
        kc = {"BULLISH": "#3FB950", "BEARISH": "#F85149", "NEUTRAL": "#8B949E"}.get(keith_trade, "#8B949E")
        keith_badge = f'<span style="background:rgba(168,85,247,0.12);color:#A855F7;border:1px solid rgba(168,85,247,0.3);padding:1px 5px;border-radius:10px;font-size:0.6rem;font-weight:700;">KEITH-{keith_trade[:4]}</span>'

    # Header card
    html = f"""
<div style="background:#161B22;border:1px solid #30363D;border-radius:10px;margin:6px 0;overflow:hidden;">
  <div style="display:flex;align-items:center;gap:8px;padding:8px 12px;border-bottom:1px solid #21262D;">
    <span style="font-weight:800;font-size:1.0rem;color:#E6EDF3;min-width:80px;">{ticker}</span>
    <span style="font-weight:700;font-size:0.85rem;color:#E6EDF3;min-width:60px;">{px_str}</span>
    <span style="background:rgba(34,197,94,0.12);color:{action_color};border:1px solid {action_color};padding:2px 8px;border-radius:12px;font-size:0.65rem;font-weight:700;">{action}</span>
    <span style="color:{quality_color};font-weight:700;font-size:0.7rem;">{quality}</span>
    <span style="color:{phase_color};font-weight:600;font-size:0.7rem;">{phase}</span>
    {keith_badge}
  </div>
  <div style="padding:6px 12px;">
    {render_triple_rr_bar({"px": px, "trade": {"lrr": row.get("trade_lrr"), "trr": row.get("trade_trr")},
                          "trend": {"lrr": row.get("trend_lrr"), "trr": row.get("trend_trr")},
                          "tail": {"lrr": row.get("tail_lrr"), "trr": row.get("tail_trr")}})}
  </div>
  <div style="display:flex;gap:10px;padding:4px 12px 8px;font-size:0.68rem;color:#8B949E;">
    <span>TRADE: <b style="color:#E6EDF3;">{(row.get('trade_lrr') or 0):.2f} - {(row.get('trade_trr') or 0):.2f}</b></span>
    <span>R/R: <b style="color:#E6EDF3;">{(row.get('rr_ratio') or 0):.2f}</b></span>
    <span>Size: <b style="color:#E6EDF3;">{rec_pct_str}</b></span>
    <span>Quad: <b style="color:#E6EDF3;">{row.get('quad_fit', '?')}</b></span>
  </div>
</div>
"""
    st.markdown(html, unsafe_allow_html=True)

    if expanded:
        with st.expander(f"📊 {ticker} — Detail", expanded=False):
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("**TRADE (3w)**")
                st.metric("LRR", f"{(row.get('trade_lrr') or 0):.2f}")
                st.metric("TRR", f"{(row.get('trade_trr') or 0):.2f}")
            with c2:
                st.markdown("**TREND (3m)**")
                st.metric("LRR", f"{(row.get('trend_lrr') or 0):.2f}")
                st.metric("TRR", f"{(row.get('trend_trr') or 0):.2f}")
            with c3:
                st.markdown("**TAIL (3y)**")
                if row.get("tail_lrr"):
                    st.metric("LRR", f"{(row.get('tail_lrr') or 0):.2f}")
                    st.metric("TRR", f"{(row.get('tail_trr') or 0):.2f}")
                else:
                    st.caption("Need full history")


def render_ticker_cards(rows: list, max_rows: int = 30, sort_by: str = "rr_ratio"):
    """Render list of ticker cards with sorting."""
    if not rows:
        st.info("No tickers to display.")
        return
    # Sort
    if sort_by and rows and isinstance(rows[0], dict):
        try:
            rows = sorted(rows, key=lambda x: -(x.get(sort_by, 0) or 0))
        except Exception:
            pass
    for row in rows[:max_rows]:
        if isinstance(row, dict):
            render_ticker_card(row)


def render_action_filter(rows: list) -> list:
    """Filter pills + return filtered rows."""
    if not rows:
        return rows
    actions = sorted(set(r.get("action", "HOLD") for r in rows if isinstance(r, dict)))
    selected = st.multiselect("Filter Action", actions, default=actions, key=f"action_filter_{len(rows)}")
    return [r for r in rows if isinstance(r, dict) and r.get("action") in selected]
