"""engines/volga_proxy.py — Volga (VIX Gamma) Proxy
Detects when VIX options gamma creates secondary SPX hedging flows.
"""
import math


def analyze_volga(ticker, prices, vix_prices, vix=20.0):
    """Detect volga activity from VIX behavior."""
    if vix < 20:
        return {
            "ok": True,
            "status": "INACTIVE",
            "erratic_risk": "LOW",
            "zigzag_probability": 0.1,
            "note": "VIX low — volga dormant",
            "source": "PROXY",
        }

    # Proxy: high VIX + recent spike = volga active
    vix_s = vix_prices.get("^VIX") if isinstance(vix_prices, dict) else None
    if vix_s is not None and len(vix_s) >= 6:
        try:
            import pandas as pd
            vix_clean = pd.to_numeric(vix_s, errors="coerce").dropna()
            vix_5d_ago = float(vix_clean.iloc[-6])
            vix_change = (vix - vix_5d_ago) / vix_5d_ago if vix_5d_ago > 0 else 0
        except Exception:
            vix_change = 0
    else:
        vix_change = 0

    if vix > 25 and abs(vix_change) > 0.2:
        status = "ACTIVE"
        erratic = "HIGH"
        zigzag = 0.6
        note = f"VIX spiked {vix_change:+.0%} — volga creating erratic SPX flows"
    elif vix > 25:
        status = "ACTIVE"
        erratic = "MEDIUM"
        zigzag = 0.4
        note = "VIX elevated — volga moderate impact"
    else:
        status = "INACTIVE"
        erratic = "LOW"
        zigzag = 0.2
        note = "VIX normal — volga low impact"

    return {
        "ok": True,
        "status": status,
        "erratic_risk": erratic,
        "zigzag_probability": round(zigzag, 2),
        "vix_change_5d": round(vix_change, 4),
        "note": note,
        "source": "PROXY",
    }
