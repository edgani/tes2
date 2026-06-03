"""engines/spotgamma_levels.py — SpotGamma Structural Levels Proxy v1.0
Calculates Volatility Trigger™, Risk Pivot, and Structural Zone from price action + options proxy.
No external API needed. Pure math.
"""
import math
from typing import Dict, Any
import pandas as pd

def _safe_float(v, default=0.0):
    if v is None:
        return default
    try:
        f = float(v)
        return f if math.isfinite(f) else default
    except:
        return default

def compute_structural_levels(px, sma20, std20, max_pain=None, call_wall=None, put_wall=None):
    """
    SpotGamma-style structural levels from price action.

    Formulas (proxy-based, documented):
    ── Volatility Trigger™ ──
    Last major concentration of positive gamma support BEFORE zero gamma flip.
    Proxy: Max Pain ± 0.35 × (Call Wall − Put Wall)
    This sits ABOVE the zero gamma level. When broken → dealers flip to short gamma.

    ── Risk Pivot ──
    Outer boundary of structural gamma support zone.
    Proxy: SMA(20) ± 2.5 × STD(20)
    Within zone = dealers act as stabilizers. Outside = pro-cyclical hedging.

    ── Structural Zone ──
    [Risk Pivot Lower, Risk Pivot Upper]
    """
    px = _safe_float(px)
    sma20 = _safe_float(sma20, px)
    std20 = _safe_float(std20, px * 0.02)
    max_pain = _safe_float(max_pain, sma20)
    call_wall = _safe_float(call_wall, sma20 + std20 * 2.0)
    put_wall = _safe_float(put_wall, sma20 - std20 * 2.0)

    spread = call_wall - put_wall
    if spread <= 0:
        spread = abs(sma20 * 0.04)

    # Volatility Trigger: Max Pain ± 0.35 × spread
    # This is the "last line of defense" before zero gamma
    vt_upper = max_pain + 0.35 * spread
    vt_lower = max_pain - 0.35 * spread

    # Risk Pivot: SMA(20) ± 2.5 × STD(20)
    rp_upper = sma20 + 2.5 * std20
    rp_lower = sma20 - 2.5 * std20

    # Structural Zone width
    zone_width = rp_upper - rp_lower

    # Position within structural zone (0 = at lower pivot, 1 = at upper pivot)
    if zone_width > 0:
        pos_in_zone = (px - rp_lower) / zone_width
    else:
        pos_in_zone = 0.5

    # Distance to Volatility Trigger
    if px > max_pain:
        dist_to_vt = (vt_upper - px) / px if px > 0 else 0
        vt_direction = "UPPER"
    else:
        dist_to_vt = (px - vt_lower) / px if px > 0 else 0
        vt_direction = "LOWER"

    # Status
    if rp_lower <= px <= rp_upper:
        zone_status = "INSIDE_STRUCTURAL_ZONE"
        zone_color = "#3FB950"  # Green — stabilizers active
    else:
        zone_status = "OUTSIDE_STRUCTURAL_ZONE"
        zone_color = "#F85149"  # Red — pro-cyclical, acceleration risk

    # Near volatility trigger?
    near_vt = abs(dist_to_vt) < 0.015  # Within 1.5%

    return {
        "volatility_trigger_upper": round(vt_upper, 4),
        "volatility_trigger_lower": round(vt_lower, 4),
        "volatility_trigger": round(vt_upper if px > max_pain else vt_lower, 4),
        "volatility_trigger_direction": vt_direction,
        "near_volatility_trigger": near_vt,
        "risk_pivot_upper": round(rp_upper, 4),
        "risk_pivot_lower": round(rp_lower, 4),
        "risk_pivot": round(rp_upper if px > sma20 else rp_lower, 4),
        "structural_zone": [round(rp_lower, 4), round(rp_upper, 4)],
        "structural_zone_width_pct": round(zone_width / px * 100, 2) if px > 0 else 0,
        "pos_in_zone": round(pos_in_zone, 3),
        "zone_status": zone_status,
        "zone_color": zone_color,
        "max_pain": round(max_pain, 4),
        "call_wall": round(call_wall, 4),
        "put_wall": round(put_wall, 4),
        "note": (
            f"Vol Trigger @ {round(vt_upper if px > max_pain else vt_lower, 2)} "
            f"({"BROKEN" if near_vt else "HOLDING"}). "
            f"Risk Zone: [{round(rp_lower, 2)}, {round(rp_upper, 2)}] "
            f"({zone_status.replace("_", " ").title()})."
        )
    }

def compute_structural_levels_multi(prices: Dict[str, Any], options_data: Dict, key_tickers=None) -> Dict[str, Any]:
    """Batch compute SpotGamma structural levels for tickers."""
    out = {}
    if key_tickers is None:
        key_tickers = list(prices.keys())[:150]

    for ticker in key_tickers:
        s = prices.get(ticker)
        if s is None or not hasattr(s, "__len__") or len(s) < 20:
            continue
        try:
            s_clean = pd.to_numeric(pd.Series(s), errors="coerce").dropna()
            if len(s_clean) < 20:
                continue
            px = float(s_clean.iloc[-1])
            sma20 = float(s_clean.tail(20).mean())
            std20 = float(s_clean.tail(20).std())
            if std20 == 0 or not math.isfinite(std20):
                continue

            # Extract options data if available
            od = options_data.get(ticker, {}) if isinstance(options_data, dict) else {}
            max_pain = od.get("max_pain") if isinstance(od, dict) else None
            call_wall = od.get("call_wall") if isinstance(od, dict) else None
            put_wall = od.get("put_wall") if isinstance(od, dict) else None

            out[ticker] = compute_structural_levels(px, sma20, std20, max_pain, call_wall, put_wall)
        except Exception:
            continue

    return out

if __name__ == "__main__":
    result = compute_structural_levels(520.0, 518.0, 4.5, 518.0, 528.0, 512.0)
    print(result)
