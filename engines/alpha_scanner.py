"""
alpha_scanner.py — score ANY ticker's ALPHA POTENTIAL (asymmetric upside) + READINESS, and route
non-alpha names back to the normal market tab.

HONEST FRAME (agreed with Edward): nothing predicts a 100×–1000× in advance. What IS detectable is the
*set of characteristics that historically precede* large asymmetric moves, plus how *ready* the name is
to move now. This engine scores those — it does not promise multibaggers.

ALPHA POTENTIAL (room + setup, 0–100):
  - size/liquidity tier: smaller base = more room to multiply (also riskier — flagged)
  - structural bottleneck / moat (the multibagger thesis)
  - accumulation footprint already present (smart money in before the crowd)
  - relative strength (leadership)
  - position vs high: basing below high = room; already extended = less asymmetry left
  - attention/crowding: low = "belum rame" (crowd hasn't arrived → the alpha)
READINESS (0–100): markup-readiness (enough inventory + coiled) + breakout + multi-TF confluence.

Pure-logic + defensive. Features are assembled by the caller from snap/bandar/price. Tested in __main__.
"""
from __future__ import annotations
from typing import Optional


def _num(x) -> Optional[float]:
    try:
        v = float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def alpha_potential(*, mcap_usd=None, adv_usd=None, has_bottleneck=False, accumulation=False,
                    rs_bias=0, dist_to_high_pct=None, attention=None, n_sources=0) -> dict:
    """Score the asymmetric-upside SETUP (not a prediction). Returns {score, tier, reasons, illiquid_flag}."""
    score = 0.0
    reasons = []
    illiquid = False

    m = _num(mcap_usd)
    if m is not None:
        if m < 300e6:
            score += 25; reasons.append("microcap (<$300M): ruang gede tapi risiko tinggi")
        elif m < 2e9:
            score += 18; reasons.append("smallcap (<$2B): ruang multibag bagus")
        elif m < 10e9:
            score += 10; reasons.append("midcap (<$10B): ruang sedang")
        elif m < 50e9:
            score += 4; reasons.append("largecap: ruang terbatas")
        else:
            reasons.append("megacap: hampir mustahil multibag")

    a = _num(adv_usd)
    if a is not None and a < 1e6:
        illiquid = True
        reasons.append(f"ADV ${a/1e6:.1f}M — ILIKUID (slippage/exit risk)")

    if has_bottleneck:
        score += 22; reasons.append("bottleneck/moat struktural (tesis multibag)")
    if accumulation:
        score += 20; reasons.append("footprint akumulasi udah ada (smart money duluan)")
    if _num(rs_bias) and rs_bias > 0:
        score += 10; reasons.append("relative-strength leader")
    elif _num(rs_bias) and rs_bias < 0:
        score -= 6; reasons.append("RS laggard")

    d = _num(dist_to_high_pct)
    if d is not None:
        if 8 <= d <= 45:
            score += 12; reasons.append(f"basing {d:.0f}% di bawah high (ada ruang naik)")
        elif d < 3:
            score += 3; reasons.append("udah di high (asymmetry sisa dikit)")
        elif d > 70:
            score -= 5; reasons.append(f"{d:.0f}% di bawah high (mungkin broken/value-trap)")

    at = _num(attention)
    if at is not None:
        if at < 0.3:
            score += 15; reasons.append("low attention — BELUM RAME (the alpha)")
        elif at > 0.75:
            score -= 8; reasons.append("udah rame/crowded — alpha tipis")

    if n_sources >= 2:
        score += 5; reasons.append(f"{n_sources} sumber independen")

    score = max(0, min(100, score))
    tier = ("HIGH" if score >= 60 else "MEDIUM" if score >= 45 else "LOW")
    return {"score": int(round(score)), "tier": tier, "illiquid_flag": illiquid, "reasons": reasons}


def alpha_readiness(*, markup_verdict=None, breakout=False, confluence_conviction=None,
                    stealth=False) -> dict:
    """How ready to move NOW. Returns {score, level, reasons}."""
    score = 0.0
    reasons = []
    mv = (markup_verdict or "").upper()
    if mv == "READY":
        score += 45; reasons.append("markup-ready (inventory cukup + coiled)")
    elif mv == "BUILDING":
        score += 28; reasons.append("inventory lagi dibangun")
    elif mv == "EARLY":
        score += 8; reasons.append("akumulasi masih awal")
    if breakout:
        score += 25; reasons.append("breakout aktif")
    cc = (confluence_conviction or "").upper()
    score += {"FULL": 25, "STRONG": 18, "PARTIAL": 8}.get(cc, 0)
    if cc in ("FULL", "STRONG"):
        reasons.append(f"multi-TF {cc}")
    if stealth:
        score += 8; reasons.append("stealth-accum aktif")
    score = max(0, min(100, score))
    level = ("READY" if score >= 60 else "WARMING" if score >= 35 else "EARLY")
    return {"score": int(round(score)), "level": level, "reasons": reasons}


def classify_alpha(features: dict) -> dict:
    """Combine potential + readiness → routing verdict. NOT-ALPHA names go to the market tab."""
    pot = alpha_potential(
        mcap_usd=features.get("mcap_usd"), adv_usd=features.get("adv_usd"),
        has_bottleneck=features.get("has_bottleneck", False),
        accumulation=features.get("accumulation", False), rs_bias=features.get("rs_bias", 0),
        dist_to_high_pct=features.get("dist_to_high_pct"), attention=features.get("attention"),
        n_sources=features.get("n_sources", 0))
    rdy = alpha_readiness(
        markup_verdict=features.get("markup_verdict"), breakout=features.get("breakout", False),
        confluence_conviction=features.get("confluence_conviction"), stealth=features.get("stealth", False))

    p, r = pot["score"], rdy["score"]
    if p >= 60 and r >= 60:
        verdict, route = "🚀 ALPHA-READY (potensi tinggi + siap gerak)", "alpha_center"
    elif p >= 60 and r >= 35:
        verdict, route = "👀 ALPHA-WARMING (potensi tinggi, mulai panas)", "alpha_center"
    elif p >= 60:
        verdict, route = "🌱 EARLY-ALPHA (potensi tinggi, masih akumulasi awal)", "alpha_center"
    elif p >= 45:
        verdict, route = "📋 ALPHA-WATCH (potensi sedang)", "alpha_center"
    else:
        verdict, route = "↩️ NOT-ALPHA → market tab biasa", "market_tab"
    return {"verdict": verdict, "route": route, "potential": pot, "readiness": rdy,
            "alpha_score": p, "readiness_score": r}


def route_alpha(potential_score, readiness_score) -> dict:
    """Routing verdict from PRE-COMPUTED potential + readiness scores (0–100). Lets a caller that already
    has its own potential/readiness (e.g. Alpha Center's _alpha_score/_readiness) reuse the same ladder
    without re-deriving features. Mirrors classify_alpha's thresholds."""
    try:
        p = max(0.0, min(100.0, float(potential_score or 0)))
        r = max(0.0, min(100.0, float(readiness_score or 0)))
    except (TypeError, ValueError):
        p = r = 0.0
    if p >= 60 and r >= 60:
        verdict, route, emoji = "ALPHA-READY", "alpha_center", "🚀"
    elif p >= 60 and r >= 35:
        verdict, route, emoji = "ALPHA-WARMING", "alpha_center", "👀"
    elif p >= 60:
        verdict, route, emoji = "EARLY-ALPHA", "alpha_center", "🌱"
    elif p >= 45:
        verdict, route, emoji = "ALPHA-WATCH", "alpha_center", "📋"
    else:
        verdict, route, emoji = "NOT-ALPHA", "market_tab", "↩️"
    return {"verdict": verdict, "route": route, "emoji": emoji,
            "alpha_score": int(p), "readiness_score": int(r)}


def scan(universe_features: dict) -> dict:
    """universe_features: {ticker: features}. Returns ranked alpha names + the market-tab remainder."""
    rows = []
    for t, f in (universe_features or {}).items():
        try:
            c = classify_alpha(f or {})
            rows.append({"ticker": t, **c})
        except Exception:
            continue
    alpha = [r for r in rows if r["route"] == "alpha_center"]
    market = [r["ticker"] for r in rows if r["route"] == "market_tab"]
    alpha.sort(key=lambda r: (r["alpha_score"], r["readiness_score"]), reverse=True)
    return {"alpha_ranked": alpha, "to_market_tab": market,
            "n_alpha": len(alpha), "n_market": len(market)}


if __name__ == "__main__":
    print("=== SELF-TEST alpha_scanner ===")
    # high-potential, ready microcap w/ bottleneck + accumulation + markup-ready
    a = classify_alpha({"mcap_usd": 250e6, "adv_usd": 5e6, "has_bottleneck": True, "accumulation": True,
                        "rs_bias": 1, "dist_to_high_pct": 20, "attention": 0.2, "n_sources": 3,
                        "markup_verdict": "READY", "breakout": True, "confluence_conviction": "FULL",
                        "stealth": True})
    assert a["route"] == "alpha_center" and "ALPHA-READY" in a["verdict"], a
    print("✓ ALPHA-READY:", a["alpha_score"], "/", a["readiness_score"])
    # high potential but early (accumulating, not ready)
    e = classify_alpha({"mcap_usd": 500e6, "has_bottleneck": True, "accumulation": True,
                        "dist_to_high_pct": 30, "attention": 0.2, "markup_verdict": "EARLY"})
    assert e["route"] == "alpha_center" and ("EARLY" in e["verdict"] or "WATCH" in e["verdict"] or "WARMING" in e["verdict"]), e
    print("✓ early/watch:", e["verdict"])
    # megacap, crowded, extended → NOT alpha → market tab
    m = classify_alpha({"mcap_usd": 800e9, "has_bottleneck": False, "accumulation": False,
                        "dist_to_high_pct": 1, "attention": 0.9, "rs_bias": 0})
    assert m["route"] == "market_tab", m
    print("✓ NOT-ALPHA → market tab")
    # illiquid flag
    il = alpha_potential(mcap_usd=200e6, adv_usd=200e3, has_bottleneck=True)
    assert il["illiquid_flag"] is True
    print("✓ illiquid flag")
    # scan ranking + routing
    s = scan({"AAA": {"mcap_usd": 250e6, "has_bottleneck": True, "accumulation": True,
                      "markup_verdict": "READY", "breakout": True, "confluence_conviction": "FULL",
                      "attention": 0.2, "dist_to_high_pct": 20},
              "BBB": {"mcap_usd": 900e9, "attention": 0.95, "dist_to_high_pct": 1}})
    assert s["n_alpha"] == 1 and s["to_market_tab"] == ["BBB"], s
    print("✓ scan →", s["n_alpha"], "alpha,", s["n_market"], "to market tab")
    print("ALL TESTS PASSED ✅")
