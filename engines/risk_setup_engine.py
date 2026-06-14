"""risk_setup_engine.py — convert RR data to ticker_rows for display."""
def build_ticker_rows(rr_data, market_filter=None, action_filter=None):
    rows = []
    for t, rr in (rr_data or {}).items():
        if not isinstance(rr, dict): continue
        sig = rr.get("signals", {})
        trade = rr.get("trade", {})
        trend = rr.get("trend", {})
        row = {"ticker": t, "px": rr.get("px", 0),
               "trade_lrr": trade.get("lrr"), "trade_trr": trade.get("trr"),
               "trend_lrr": trend.get("lrr"), "trend_trr": trend.get("trr"),
               "action": sig.get("action", "N/A"),
               "quality": sig.get("quality", "C"),
               "formation": sig.get("formation", "NEUTRAL"),
               "phase": rr.get("phase", "NEUTRAL"),
               "trade_pos_pct": sig.get("trade_position_pct", 50),
               "rr_ratio": sig.get("rr_ratio", 1.0)}
        if action_filter and row["action"] != action_filter: continue
        rows.append(row)
    rows.sort(key=lambda r: (-(r["quality"] == "A+"), -(r["quality"] == "A"), -r["rr_ratio"]))
    return rows
