"""
equity_driver_engine.py — what actually DRIVES a US-equity move (ATH-to-ATH / breakout).

Edward's question for US stocks: "what makes a name rip and keep ripping?" The durable drivers:
  - RELATIVE STRENGTH vs benchmark (leaders lead; RS up = institutional preference)
  - BREAKOUT from a base + VOLUME confirmation (supply exhausted, demand steps up)
  - DEALER GAMMA regime: negative-gamma = dealers chase price (amplifies trend / squeeze fuel);
    positive-gamma = dealers fade moves (pinning / mean-revert, caps upside)
  - PROXIMITY to 52w/all-time high: names making new highs have no overhead supply (no trapped sellers)
  - MOMENTUM (ROC) as confirmation

Pure-logic + defensive. Gamma can be fed from the existing GEX/unified_greeks engine. Tested in __main__.
"""
from __future__ import annotations
from typing import Optional, Sequence


def _num(x) -> Optional[float]:
    try:
        v = float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def relative_strength(stock_ret_20d=None, bench_ret_20d=None) -> dict:
    """RS = stock − benchmark return. Positive = outperforming (leadership)."""
    s, b = _num(stock_ret_20d), _num(bench_ret_20d)
    if s is None or b is None:
        return {"bias": 0, "rs": None, "label": "RS n/a", "reason": "butuh return saham + benchmark"}
    rs = s - b
    if rs > 0.02:
        return {"bias": 1, "rs": round(rs, 4), "label": "RS leader", "reason": f"outperform benchmark +{rs*100:.1f}pp (institusi prefer)"}
    if rs < -0.02:
        return {"bias": -1, "rs": round(rs, 4), "label": "RS laggard", "reason": f"underperform {rs*100:.1f}pp"}
    return {"bias": 0, "rs": round(rs, 4), "label": "RS inline", "reason": "gerak seiring benchmark"}


def breakout_state(close_series: Sequence[float] = None, lookback: int = 60, vol_ratio=None) -> dict:
    """Close above lookback-window high (+0.5%) = breakout; vol_ratio>1.5 confirms conviction."""
    if not close_series or len(close_series) < lookback + 2:
        return {"bias": 0, "breakout": False, "label": "breakout n/a", "reason": "data harga kurang"}
    cs = [c for c in close_series if _num(c) is not None]
    base_high = max(cs[-lookback:-2]) if len(cs) > lookback else max(cs[:-1])
    last = cs[-1]
    vr = _num(vol_ratio)
    if base_high and last > base_high * 1.005:
        confirmed = vr is not None and vr > 1.5
        return {"bias": 1, "breakout": True, "confirmed": confirmed,
                "label": "breakout" + (" (vol-confirmed)" if confirmed else " (low vol — hati2)"),
                "reason": f"close > {lookback}d-base high" + (f" + volume {vr:.1f}× (konfirmasi)" if confirmed else " tapi volume tipis")}
    if base_high and last < min(cs[-lookback:-2]) * 0.995:
        return {"bias": -1, "breakout": False, "label": "breakdown", "reason": f"close < {lookback}d-base low"}
    return {"bias": 0, "breakout": False, "label": "in base", "reason": "masih dalam range/base"}


def gamma_regime(net_dealer_gamma=None) -> dict:
    """Dealer gamma. Negative = dealers buy-high/sell-low (amplify trend, squeeze fuel). Positive = pin."""
    g = _num(net_dealer_gamma)
    if g is None:
        return {"bias": 0, "regime": "n/a", "label": "gamma n/a", "reason": "butuh net dealer gamma (GEX)"}
    if g < 0:
        return {"bias": 1, "regime": "negative", "label": "neg-gamma (trend amplifier)",
                "reason": "dealer kejar harga → move keperpanjang, fuel buat squeeze"}
    return {"bias": 0, "regime": "positive", "label": "pos-gamma (pinning)",
            "reason": "dealer fade move → harga ke-pin/mean-revert, upside ke-cap"}


def distance_to_high(price=None, high_52w=None) -> dict:
    """At/near 52w-high = no overhead supply (no trapped sellers above) = clean tape for markup."""
    p, hi = _num(price), _num(high_52w)
    if p is None or hi is None or hi <= 0:
        return {"bias": 0, "dist_pct": None, "label": "ATH n/a", "reason": "butuh harga + 52w high"}
    dist = (hi - p) / hi * 100.0
    if dist < 2:
        return {"bias": 1, "dist_pct": round(dist, 1), "label": "at 52w-high", "reason": "new-high zone, gak ada supply nyangkut di atas"}
    if dist < 8:
        return {"bias": 1, "dist_pct": round(dist, 1), "label": "near high", "reason": f"{dist:.1f}% dari 52w-high"}
    if dist > 30:
        return {"bias": -1, "dist_pct": round(dist, 1), "label": "deep below high", "reason": f"{dist:.0f}% di bawah high (overhead supply tebal)"}
    return {"bias": 0, "dist_pct": round(dist, 1), "label": "mid-range", "reason": f"{dist:.0f}% di bawah high"}


def equity_driver(close_series: Sequence[float] = None, *, bench_ret_20d=None,
                  net_dealer_gamma=None, high_52w=None, vol_ratio=None, lookback: int = 60) -> dict:
    """Composite driver verdict for a US name."""
    cs = [c for c in (close_series or []) if _num(c) is not None]
    stock_ret = None
    if len(cs) > 21:
        stock_ret = (cs[-1] - cs[-21]) / cs[-21] if cs[-21] else None
    rs = relative_strength(stock_ret, bench_ret_20d)
    bo = breakout_state(cs, lookback=lookback, vol_ratio=vol_ratio)
    ga = gamma_regime(net_dealer_gamma)
    dh = distance_to_high(cs[-1] if cs else None, high_52w)

    biases = [x["bias"] for x in (rs, bo, ga, dh)]
    score = sum(biases)
    nonzero = [b for b in biases if b != 0]
    if bo["bias"] == 1 and rs["bias"] == 1 and score >= 2:
        verdict = "BREAKOUT (driver kuat)"
    elif score >= 2:
        verdict = "MOMENTUM/leadership"
    elif score <= -2:
        verdict = "WEAK/distribusi"
    elif bo.get("label") == "in base" and rs["bias"] >= 0:
        verdict = "BASING (tunggu breakout)"
    else:
        verdict = "campur/netral"
    bias = 1 if score >= 2 else -1 if score <= -2 else 0
    return {"verdict": verdict, "bias": bias, "score": score,
            "drivers": {"relative_strength": rs, "breakout": bo, "gamma": ga, "distance_to_high": dh}}


if __name__ == "__main__":
    print("=== SELF-TEST equity_driver_engine ===")
    assert relative_strength(0.08, 0.03)["bias"] == 1
    assert relative_strength(0.01, 0.06)["bias"] == -1
    base = [100 + i * 0.05 for i in range(80)]            # flat base (enough bars)
    brk = base + [base[-1] * 1.02]                          # breakout bar
    assert breakout_state(brk, lookback=60, vol_ratio=2.5)["breakout"] is True
    assert breakout_state(brk, lookback=60, vol_ratio=2.5)["confirmed"] is True
    assert breakout_state(base + [base[-1] * 0.90], lookback=60)["bias"] == -1
    assert gamma_regime(-5e8)["bias"] == 1 and gamma_regime(5e8)["bias"] == 0
    assert distance_to_high(99, 100)["bias"] == 1
    assert distance_to_high(60, 100)["bias"] == -1
    print("✓ primitives")
    cs = [100 + i * 0.1 for i in range(40)] + [104 + i * 0.6 for i in range(25)]  # basing then ripping
    ed = equity_driver(cs, bench_ret_20d=0.01, net_dealer_gamma=-3e8, high_52w=cs[-1] * 1.005, vol_ratio=2.2)
    assert ed["bias"] == 1 and "BREAKOUT" in ed["verdict"], ed
    print("✓ composite →", ed["verdict"], "| score", ed["score"])
    assert equity_driver([])["bias"] == 0
    print("✓ defensive")
    print("ALL TESTS PASSED ✅")
