"""
real_flow_engine.py — REAL buyer-vs-seller pressure: is there genuine DEMAND (more real buyers) to
back a long, or genuine DISTRIBUTION (more real sellers) to back a short?

Edward's ask: before going long, confirm REAL buyers > sellers (real demand); before shorting,
confirm REAL sellers > buyers (real distribution). "REAL" = aggressive EXECUTED flow (who crossed the
spread), NOT order-book quotes (those get spoofed) and NOT wash/fake volume.

HONEST DATA NOTE — this is the crux:
  • TRUE aggressor delta needs tick/trade-print data (volume at ask vs volume at bid → Bookmap / Sierra /
    exchange aggregated feed). The system fetches OHLCV (yfinance), so by default we ESTIMATE delta from
    OHLC — the standard tick-rule + close-location proxy. Every free "delta" indicator does this; we label
    it as a proxy rather than pretending it's real order flow. Pass `true_delta_series` (e.g. a crypto
    exchange CVD feed) to upgrade from proxy → real.
  • Crypto caveat: on unregulated venues wash trading has averaged >70% of reported volume, so we run a
    light volume-quality check and haircut confidence when volume looks fabricated.

What makes this more than a CVD line — the REAL filters:
  • ABSORPTION (effort vs result): if buyers are aggressive (delta up) but price WON'T rise, sellers are
    absorbing → the real control is the SELL side (don't long). Mirror for selling absorbed by buyers.
  • DIVERGENCE: price new high but CVD lower high → move lacks real participation (fake rally).
  • PERSISTENCE: a real campaign trends the CVD across many bars, not one spike.

Pure-logic + defensive. Unit-tested in __main__.
"""
from __future__ import annotations
from typing import Optional, Sequence


def _cols(df):
    """Accept a pandas DataFrame or dict-of-lists → (O,H,L,C,V) as float lists. [] on failure."""
    try:
        if hasattr(df, "columns"):
            g = lambda k: [float(x) for x in df[k].tolist()]
        else:
            g = lambda k: [float(x) for x in df[k]]
        o, h, l, c, v = g("Open"), g("High"), g("Low"), g("Close"), g("Volume")
        n = min(len(o), len(h), len(l), len(c), len(v))
        return o[:n], h[:n], l[:n], c[:n], v[:n]
    except Exception:
        return [], [], [], [], []


def bar_delta(o, h, l, c, v):
    """Split one bar's volume into REAL buy vs sell via close-location (CLV). Returns (buy, sell, delta).
    CLV = ((C−L) − (H−C))/(H−L) ∈ [−1,+1]: +1 closed at high (buyers won the bar), −1 at low."""
    rng = h - l
    if rng <= 0 or v <= 0:
        return v / 2.0, v / 2.0, 0.0
    clv = ((c - l) - (h - c)) / rng
    clv = max(-1.0, min(1.0, clv))
    buy_frac = (clv + 1.0) / 2.0
    buy = v * buy_frac
    sell = v - buy
    return buy, sell, buy - sell


def compute_cvd(df, true_delta_series: Optional[Sequence[float]] = None):
    """CVD proxy (or true CVD if a real delta series is supplied). Returns dict with series + slope."""
    o, h, l, c, v = _cols(df)
    if len(c) < 5:
        return {"ok": False, "reason": "data kurang"}
    if true_delta_series is not None and len(true_delta_series) >= len(c):
        deltas = [float(x) for x in true_delta_series[-len(c):]]
        buys = [max(0.0, d) for d in deltas]; sells = [max(0.0, -d) for d in deltas]
        source = "true_aggressor_feed"
    else:
        buys, sells, deltas = [], [], []
        for i in range(len(c)):
            b, s, d = bar_delta(o[i], h[i], l[i], c[i], v[i])
            buys.append(b); sells.append(s); deltas.append(d)
        source = "ohlc_proxy"
    cvd = []
    run = 0.0
    for d in deltas:
        run += d; cvd.append(run)
    # slope over last 20 (or all)
    w = min(20, len(cvd))
    cvd_slope = (cvd[-1] - cvd[-w]) / (abs(cvd[-w]) + 1e-9) if w >= 2 else 0.0
    return {"ok": True, "source": source, "deltas": deltas, "buys": buys, "sells": sells,
            "cvd": cvd, "cvd_slope": cvd_slope}


def _wash_quality(volumes) -> dict:
    """Light volume-quality check (crypto wash proxy). Flags implausible spikes + round-number clustering.
    Returns {suspect_frac 0-1, haircut 0-1}. NOT a forensic test — a confidence dampener."""
    vs = [float(x) for x in volumes if x and x == x]
    if len(vs) < 20:
        return {"suspect_frac": 0.0, "haircut": 0.0}
    med = sorted(vs)[len(vs) // 2] or 1.0
    spikes = sum(1 for x in vs if x > med * 8)                       # absurd vs median
    rounds = sum(1 for x in vs if x > 0 and (x % 1000 == 0 or x % 500 == 0))  # too-round prints
    suspect = (spikes + 0.5 * rounds) / len(vs)
    suspect = max(0.0, min(1.0, suspect))
    return {"suspect_frac": round(suspect, 3), "haircut": round(min(0.4, suspect), 3)}


def real_flow(df, *, true_delta_series: Optional[Sequence[float]] = None, window: int = 10,
              market: str = "generic") -> dict:
    """Verdict on REAL buyer/seller control + whether it confirms a long or short.

    Verdicts:
      REAL_DEMAND       buyers aggressive AND price rising      → confirm LONG (genuine demand)
      REAL_DISTRIBUTION sellers aggressive AND price falling    → confirm SHORT (genuine distribution)
      BULL_ABSORPTION   sellers aggressive BUT price won't fall → buyers absorbing → bullish (don't short)
      BEAR_ABSORPTION   buyers aggressive BUT price won't rise  → sellers absorbing → bearish (don't long)
      BALANCED          no clear edge
    """
    cv = compute_cvd(df, true_delta_series)
    if not cv.get("ok"):
        return {"ok": False, "verdict": "n/a", "reason": cv.get("reason", "no data"),
                "confirms_long": False, "confirms_short": False}
    o, h, l, c, v = _cols(df)
    w = min(window, len(c) - 1)
    buys_w = sum(cv["buys"][-w:]); sells_w = sum(cv["sells"][-w:])
    tot = buys_w + sells_w
    buy_ratio = buys_w / tot if tot > 0 else 0.5
    price_chg = (c[-1] - c[-w]) / c[-w] if c[-w] else 0.0

    # persistence: CVD slope sign consistency over the window
    persistent = (cv["cvd_slope"] > 0) == (buy_ratio > 0.5)

    BUY_T, SELL_T = 0.55, 0.45
    PRICE_T = 0.003  # ~0.3% over the window = "moved"
    if buy_ratio >= BUY_T:
        if price_chg > PRICE_T:
            verdict = "REAL_DEMAND"
        elif price_chg < -PRICE_T:
            verdict = "BEAR_ABSORPTION"            # heavy buying yet price FELL → sellers absorbing hard
        else:
            verdict = "BEAR_ABSORPTION"            # heavy buying, price flat → absorbed (not real demand)
    elif buy_ratio <= SELL_T:
        if price_chg < -PRICE_T:
            verdict = "REAL_DISTRIBUTION"
        elif price_chg > PRICE_T:
            verdict = "BULL_ABSORPTION"            # heavy selling yet price ROSE → buyers absorbing
        else:
            verdict = "BULL_ABSORPTION"            # heavy selling, price flat → absorbed
    else:
        verdict = "BALANCED"

    # confidence
    conf = min(1.0, abs(buy_ratio - 0.5) * 2 * 1.3)        # imbalance magnitude
    if persistent:
        conf = min(1.0, conf + 0.1)
    if verdict in ("BEAR_ABSORPTION", "BULL_ABSORPTION"):
        conf = min(1.0, conf + 0.1)                         # absorption is a high-information tell
    wq = _wash_quality(v) if market == "crypto" else {"suspect_frac": 0.0, "haircut": 0.0}
    conf = max(0.0, conf - wq["haircut"])

    confirms_long = verdict in ("REAL_DEMAND", "BULL_ABSORPTION")
    confirms_short = verdict in ("REAL_DISTRIBUTION", "BEAR_ABSORPTION")

    label = {
        "REAL_DEMAND": f"🟢 REAL DEMAND — buyer beneran > seller ({buy_ratio:.0%} buy) + harga naik {price_chg*100:+.1f}%",
        "REAL_DISTRIBUTION": f"🔴 REAL DISTRIBUSI — seller beneran > buyer ({(1-buy_ratio):.0%} sell) + harga turun {price_chg*100:+.1f}%",
        "BULL_ABSORPTION": f"🟢 BULL ABSORPTION — seller agresif ({(1-buy_ratio):.0%} sell) TAPI harga gak turun → buyer nyerap (bullish, jgn short)",
        "BEAR_ABSORPTION": f"🔴 BEAR ABSORPTION — buyer agresif ({buy_ratio:.0%} buy) TAPI harga gak naik → seller nyerap (bearish, jgn long)",
        "BALANCED": f"⚪ BALANCED — buy {buy_ratio:.0%} / sell {1-buy_ratio:.0%}, gak ada yang dominan",
    }[verdict]

    return {"ok": True, "verdict": verdict, "label": label, "confirms_long": confirms_long,
            "confirms_short": confirms_short, "buy_ratio": round(buy_ratio, 3),
            "price_chg_window": round(price_chg, 4), "cvd_slope": round(cv["cvd_slope"], 4),
            "persistent": persistent, "confidence": round(conf, 2), "source": cv["source"],
            "wash_quality": wq,
            "note": ("CVD proxy dari OHLC (tick-rule + close-location), BUKAN order-flow tick asli. "
                     "Kasih feed delta exchange (crypto) buat upgrade ke REAL aggressor." if cv["source"] == "ohlc_proxy"
                     else "True aggressor delta feed.")}


if __name__ == "__main__":
    print("=== SELF-TEST real_flow_engine ===")
    def tape(o,h,l,c,v): return {"Open":o,"High":h,"Low":l,"Close":c,"Volume":v}
    n=30
    # REAL_DEMAND: closes near highs + price rising
    base=[100+i*0.5 for i in range(n)]
    rd=tape([b-0.3 for b in base],[b+0.4 for b in base],[b-0.5 for b in base],[b+0.35 for b in base],[1e6]*n)
    r=real_flow(rd); print("RD:", r["verdict"], r["buy_ratio"], r["confidence"]); assert r["verdict"]=="REAL_DEMAND" and r["confirms_long"]
    # REAL_DISTRIBUTION: closes near lows + price falling
    dn=[100-i*0.5 for i in range(n)]
    rdi=tape([d+0.3 for d in dn],[d+0.5 for d in dn],[d-0.4 for d in dn],[d-0.35 for d in dn],[1e6]*n)
    r2=real_flow(rdi); print("RDist:", r2["verdict"], r2["buy_ratio"]); assert r2["verdict"]=="REAL_DISTRIBUTION" and r2["confirms_short"]
    # BEAR_ABSORPTION: buyers aggressive (close near high each bar) but price FLAT (highs capped)
    flat=100.0
    ba=tape([flat-0.8]*n,[flat+0.2]*n,[flat-1.0]*n,[flat+0.15]*n,[2e6]*n)  # closes near high, but level constant
    r3=real_flow(ba); print("BearAbs:", r3["verdict"], r3["buy_ratio"], "Δpx", r3["price_chg_window"]); assert r3["verdict"]=="BEAR_ABSORPTION" and not r3["confirms_long"]
    # BULL_ABSORPTION: sellers aggressive (close near low) but price FLAT (buyers defend)
    bu=tape([flat+0.8]*n,[flat+1.0]*n,[flat-0.2]*n,[flat-0.15]*n,[2e6]*n)
    r4=real_flow(bu); print("BullAbs:", r4["verdict"], r4["buy_ratio"]); assert r4["verdict"]=="BULL_ABSORPTION" and not r4["confirms_short"]
    # BALANCED: closes mid-bar
    bal=tape([100]*n,[101]*n,[99]*n,[100+ (0.05 if i%2 else -0.05) for i in range(n)],[1e6]*n)
    r5=real_flow(bal); print("Bal:", r5["verdict"], r5["buy_ratio"]); assert r5["verdict"]=="BALANCED"
    # true-delta feed overrides proxy
    r6=real_flow(rd, true_delta_series=[5e5]*n); assert r6["source"]=="true_aggressor_feed"
    print("source w/ feed:", r6["source"])
    # crypto wash haircut lowers confidence
    washv=[1000*1000]*n  # super-round + spiky
    rw=tape([b-0.3 for b in base],[b+0.4 for b in base],[b-0.5 for b in base],[b+0.35 for b in base],washv)
    r7=real_flow(rw, market="crypto"); print("wash haircut:", r7["wash_quality"]); assert r7["wash_quality"]["haircut"]>0
    # defensive
    assert real_flow({"Open":[],"High":[],"Low":[],"Close":[],"Volume":[]})["verdict"]=="n/a"
    print("ALL TESTS PASSED ✅")
