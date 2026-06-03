"""engines/volsignals_regime.py — VolSignals Dealer Regime Classification v1.0
Methodology: GEX sign + Distance-to-Flip + Vanna alignment → Regime + Confidence
No external API needed. Pure math from existing snapshot data.
"""
import math
from typing import Dict, Any

def _safe_float(v, default=0.0):
    if v is None:
        return default
    try:
        f = float(v)
        return f if math.isfinite(f) else default
    except:
        return default

def classify_dealer_regime(gex, vanna, charm, px, max_pain, gamma_flip_up, gamma_flip_down, gamma_regime=""):
    """
    VolSignals-style 3-input regime classification.

    Inputs:
      gex: net gamma exposure (float, sign matters)
      vanna: vanna flow (float)
      charm: charm decay (float)
      px: current price
      max_pain: max pain strike
      gamma_flip_up: upper gamma flip level
      gamma_flip_down: lower gamma flip level
      gamma_regime: string like "POSITIVE", "NEGATIVE", etc.

    Returns:
      {
        "dealer_regime": "STABILIZING" | "AMPLIFYING" | "TRANSITION",
        "confidence": "High" | "Moderate" | "Low",
        "vanna_alignment": "VIRTUOUS" | "VICIOUS" | "NEUTRAL",
        "charm_bias": "SUPPORT" | "EROSION" | "NEUTRAL",
        "distance_to_flip_pct": float,  # % distance to nearest flip
        "regime_score": float,  # 0-100 composite
        "note": str
      }
    """
    gex = _safe_float(gex)
    vanna = _safe_float(vanna)
    charm = _safe_float(charm)
    px = _safe_float(px)
    max_pain = _safe_float(max_pain, px)
    gf_up = _safe_float(gamma_flip_up, px * 1.05)
    gf_down = _safe_float(gamma_flip_down, px * 0.95)

    # 1. GEX sign → base regime
    if gex > 0.5:
        base_regime = "STABILIZING"
        base_score = 60
    elif gex < -0.5:
        base_regime = "AMPLIFYING"
        base_score = 60
    else:
        base_regime = "TRANSITION"
        base_score = 30

    # Override from gamma_regime string if provided
    if "POS" in str(gamma_regime).upper():
        base_regime = "STABILIZING"
        base_score = max(base_score, 65)
    elif "NEG" in str(gamma_regime).upper():
        base_regime = "AMPLIFYING"
        base_score = max(base_score, 65)

    # 2. Distance to nearest gamma flip
    if px > 0 and gf_up > gf_down:
        dist_up = abs(gf_up - px) / px
        dist_down = abs(px - gf_down) / px
        dist_to_flip = min(dist_up, dist_down)
    else:
        dist_to_flip = 0.05

    # Near flip = higher confidence, far = lower
    if dist_to_flip < 0.01:
        dist_score = 25  # Very close — regime about to flip
        dist_note = "Near gamma flip — regime transition imminent"
    elif dist_to_flip < 0.03:
        dist_score = 15
        dist_note = "Close to gamma flip"
    else:
        dist_score = 5
        dist_note = "Far from gamma flip — regime stable"

    # 3. Vanna alignment
    # Virtuous: vanna > 0 (rally → vol crush → dealers buy → support)
    # Vicious: vanna < 0 (rally → vol expansion → dealers sell → pressure)
    if vanna > 0.3:
        vanna_align = "VIRTUOUS"
        vanna_score = 20
        vanna_note = "Vanna virtuous cycle — rallies dampen vol"
    elif vanna < -0.3:
        vanna_align = "VICIOUS"
        vanna_score = 20
        vanna_note = "Vanna vicious cycle — rallies amplify vol"
    else:
        vanna_align = "NEUTRAL"
        vanna_score = 5
        vanna_note = "Vanna neutral — no strong spot-vol feedback"

    # 4. Charm bias
    # Charm > 0: put support strengthening over time
    # Charm < 0: put support eroding
    if charm > 0.3:
        charm_bias = "SUPPORT"
        charm_score = 10
        charm_note = "Charm strengthening put support"
    elif charm < -0.3:
        charm_bias = "EROSION"
        charm_score = 10
        charm_note = "Charm eroding put support — acceleration risk"
    else:
        charm_bias = "NEUTRAL"
        charm_score = 3
        charm_note = "Charm neutral"

    # 5. Composite regime score
    total_score = base_score + dist_score + vanna_score + charm_score

    # Confidence based on data quality + alignment
    if abs(gex) > 1.0 and abs(vanna) > 0.5:
        confidence = "High"
    elif abs(gex) > 0.3 or abs(vanna) > 0.2:
        confidence = "Moderate"
    else:
        confidence = "Low"

    # Final regime adjustment
    # If STABILIZING but VICIOUS vanna → downgrade to TRANSITION (conflicting signals)
    # If AMPLIFYING but VIRTUOUS vanna → TRANSITION
    final_regime = base_regime
    if base_regime == "STABILIZING" and vanna_align == "VICIOUS" and abs(vanna) > 0.4:
        final_regime = "TRANSITION"
        note = f"GEX stabilizing but vanna vicious — conflicting. {dist_note}. {vanna_note}. {charm_note}"
    elif base_regime == "AMPLIFYING" and vanna_align == "VIRTUOUS" and abs(vanna) > 0.4:
        final_regime = "TRANSITION"
        note = f"GEX amplifying but vanna virtuous — conflicting. {dist_note}. {vanna_note}. {charm_note}"
    else:
        note = f"{base_regime}. {dist_note}. {vanna_note}. {charm_note}"

    return {
        "dealer_regime": final_regime,
        "base_regime": base_regime,
        "confidence": confidence,
        "vanna_alignment": vanna_align,
        "charm_bias": charm_bias,
        "distance_to_flip_pct": round(dist_to_flip * 100, 2),
        "regime_score": min(100, total_score),
        "note": note,
        "components": {
            "gex": gex,
            "vanna": vanna,
            "charm": charm,
            "dist_to_flip": dist_to_flip,
        }
    }

def compute_dealer_regime_multi(prices: Dict[str, Any], gex_data: Dict, vanna_data: Dict,
                                charm_data: Dict, gamma_data: Dict, key_tickers=None) -> Dict[str, Any]:
    """
    Batch compute VolSignals-style dealer regime for all tickers.
    """
    out = {}
    if key_tickers is None:
        key_tickers = list(prices.keys())[:150]

    for ticker in key_tickers:
        gex = None
        vanna = None
        charm = None
        px = None
        max_pain = None
        gf_up = None
        gf_down = None
        gamma_regime = ""

        # Extract from gex_data
        gd = gex_data.get(ticker, {}) if isinstance(gex_data, dict) else {}
        if isinstance(gd, dict):
            gex = gd.get("net_gex") or gd.get("gex") or gd.get("total_gex")

        # Extract from vanna_data
        vd = vanna_data.get(ticker, {}) if isinstance(vanna_data, dict) else {}
        if isinstance(vd, dict):
            vanna = vd.get("vanna")

        # Extract from charm_data
        cd = charm_data.get(ticker, {}) if isinstance(charm_data, dict) else {}
        if isinstance(cd, dict):
            charm = cd.get("charm")

        # Extract from gamma_data
        gmd = gamma_data.get(ticker, {}) if isinstance(gamma_data, dict) else {}
        if isinstance(gmd, dict):
            max_pain = gmd.get("max_pain")
            gamma_regime = gmd.get("regime", "")

        # Get price
        s = prices.get(ticker)
        if s is not None and hasattr(s, "__len__") and len(s) > 0:
            try:
                import pandas as pd
                s_clean = pd.to_numeric(pd.Series(s), errors="coerce").dropna()
                if len(s_clean) > 0:
                    px = float(s_clean.iloc[-1])
            except Exception:
                pass

        # Proxy gamma flip from price action if missing
        if px and (gf_up is None or gf_down is None):
            try:
                import pandas as pd
                s_clean = pd.to_numeric(pd.Series(s), errors="coerce").dropna()
                if len(s_clean) >= 20:
                    sma20 = float(s_clean.tail(20).mean())
                    std20 = float(s_clean.tail(20).std())
                    if std20 > 0:
                        gf_up = sma20 + std20 * 1.5
                        gf_down = sma20 - std20 * 1.5
                        if max_pain is None:
                            max_pain = sma20
            except Exception:
                pass

        if px is None:
            continue

        out[ticker] = classify_dealer_regime(
            gex=gex, vanna=vanna, charm=charm, px=px,
            max_pain=max_pain, gamma_flip_up=gf_up, gamma_flip_down=gf_down,
            gamma_regime=gamma_regime
        )

    return out

if __name__ == "__main__":
    # Quick test
    result = classify_dealer_regime(
        gex=1.2, vanna=-0.5, charm=0.1, px=520.0,
        max_pain=518.0, gamma_flip_up=525.0, gamma_flip_down=510.0
    )
    print(result)
