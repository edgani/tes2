"""structure_quality.py — TRR width quality proxy."""
def run_structure_quality(rr_data):
    out = {}
    for t, rr in (rr_data or {}).items():
        if not isinstance(rr, dict): continue
        trade = rr.get("trade", {})
        width = trade.get("trr", 0) - trade.get("lrr", 0)
        px = rr.get("px", 1)
        if px > 0:
            width_pct = width / px * 100
            if width_pct < 3: quality = "TIGHT"
            elif width_pct < 7: quality = "NORMAL"
            else: quality = "WIDE"
            out[t] = {"width_pct": round(width_pct, 2), "quality": quality}
    return out
