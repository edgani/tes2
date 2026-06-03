"""ihsg_broker.py — IHSG Broker Proxy Engine
Detects crossing, accumulation, distribution, cornering supply.
"""
import pandas as pd
import numpy as np

def analyze_broker(ticker: str, prices: dict):
    """Return broker analysis dict for an IHSG ticker."""
    s = prices.get(ticker)
    if s is None or (hasattr(s, "__len__") and len(s) < 30):
        return None
    try:
        s_clean = pd.to_numeric(pd.Series(s), errors="coerce").dropna()
        if len(s_clean) < 30:
            return None

        px = float(s_clean.iloc[-1])
        r5d = float(s_clean.iloc[-1] / s_clean.iloc[-6] - 1) if len(s_clean) >= 6 else 0
        r20d = float(s_clean.iloc[-1] / s_clean.iloc[-21] - 1) if len(s_clean) >= 21 else r5d

        vol_5 = float(s_clean.tail(5).std())
        vol_20 = float(s_clean.tail(20).std()) if len(s_clean) >= 20 else vol_5
        vol_60 = float(s_clean.tail(60).std()) if len(s_clean) >= 60 else vol_20

        range_5 = float(s_clean.tail(5).max() - s_clean.tail(5).min())
        range_20 = float(s_clean.tail(20).max() - s_clean.tail(20).min()) if len(s_clean) >= 20 else range_5

        # Crossing detection: high vol but price goes nowhere
        crossing = False
        if vol_20 > 0 and vol_5 / vol_20 > 1.5 and range_5 / max(range_20, 0.001) < 0.15:
            crossing = True

        # Cornering: volume drying up then sudden spike
        cornering = False
        if vol_60 > 0 and vol_20 / vol_60 < 0.5 and r5d > 0.03:
            cornering = True

        # Real accumulation / distribution
        real_acc = r5d > 0.03 and r20d > 0.05 and not crossing
        real_dist = r5d < -0.03 and r20d < -0.05 and not crossing

        conf = 0
        signal = "NEUTRAL"
        if real_acc:
            conf = min(100, int(50 + abs(r5d) * 500))
            signal = "ACCUMULATION"
        elif real_dist:
            conf = min(100, int(50 + abs(r5d) * 500))
            signal = "DISTRIBUTION"
        elif crossing:
            conf = 70
            signal = "CROSSING"
        elif cornering:
            conf = 65
            signal = "CORNERING"

        # Broker summary narrative
        if signal == "ACCUMULATION":
            narrative = "Real accumulation detected: price + volume up, no crossing noise. Likely institutional buying."
        elif signal == "DISTRIBUTION":
            narrative = "Real distribution: sustained selling pressure. Avoid or short."
        elif signal == "CROSSING":
            narrative = "Crossing detected: high volume but flat price = broker matching / wash trading. Wait for breakout."
        elif signal == "CORNERING":
            narrative = "Cornering supply: volume dried up then spike. Possible float tightening / goreng phase."
        else:
            narrative = "No clear broker signal. Neutral flow."

        return {
            "ticker": ticker, "price": px, "signal": signal, "confidence": conf,
            "real_accumulation": real_acc, "real_distribution": real_dist,
            "crossing_detected": crossing, "cornering_supply": cornering,
            "r5d": round(r5d, 4), "r20d": round(r20d, 4),
            "vol_ratio": round(vol_5 / vol_20, 2) if vol_20 > 0 else 1.0,
            "range_ratio": round(range_5 / max(range_20, 0.001), 2),
            "drying_up": round(vol_20 / vol_60, 2) if vol_60 > 0 else 1.0,
            "narrative": narrative,
        }
    except Exception:
        return None

def broker_html(data: dict, ticker: str):
    """Return HTML snippet for broker display."""
    if not data:
        return '<div style="font-size:0.65rem;color:#484F58;">Broker data unavailable</div>'

    color_map = {
        "ACCUMULATION": "#3FB950", "DISTRIBUTION": "#F85149",
        "CROSSING": "#D29922", "CORNERING": "#A855F7", "NEUTRAL": "#8B949E"
    }
    color = color_map.get(data["signal"], "#8B949E")

    html = (
        '<div class="ts-panel" style="border-color:' + color + '40;">'
        '<div class="ts-panel-title">🏦 IDX Broker Proxy (' + ticker + ')</div>'
        '<div class="ts-grid-4">'
        '<div class="ts-stat"><div class="ts-stat-label">Signal</div>'
        '<div class="ts-stat-value" style="color:' + color + ';">' + data["signal"] + '</div></div>'
        '<div class="ts-stat"><div class="ts-stat-label">Confidence</div>'
        '<div class="ts-stat-value">' + str(data["confidence"]) + '%</div></div>'
        '<div class="ts-stat"><div class="ts-stat-label">5D Return</div>'
        '<div class="ts-stat-value" style="color:' + ("#3FB950" if data["r5d"] > 0 else "#F85149") + ';">' + "{:+.1f}%".format(data["r5d"]*100) + '</div></div>'
        '<div class="ts-stat"><div class="ts-stat-label">Vol Ratio</div>'
        '<div class="ts-stat-value">' + str(data["vol_ratio"]) + '</div></div>'
        '</div>'
        '<div style="font-size:0.65rem;color:#8B949E;margin-top:4px;">' + data["narrative"] + '</div>'
        '<div style="font-size:0.6rem;color:#484F58;margin-top:2px;">'
        'Range ratio: ' + str(data["range_ratio"]) + ' · Drying up: ' + str(data["drying_up"]) +
        '</div>'
        '</div>'
    )
    return html
