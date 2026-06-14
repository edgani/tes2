"""
onchain_engine.py — crypto on-chain accumulation / cornering / distribution detection.

Answers Edward's question: "is someone quietly accumulating / cornering supply → price likely up?"
by reading the on-chain footprint that retail can't see on a price chart.

Pure-logic + defensive (neutral on missing data). NOTE: needs an on-chain data feed (Glassnode /
CryptoQuant / Nansen API) to run LIVE — the system doesn't fetch on-chain yet, so wiring this needs
an API key. Logic is unit-tested in __main__ and correct in isolation.

Encoded signals (grounded in CryptoQuant/Glassnode/Nansen methodology, 2026):
  - Exchange NETFLOW: negative (outflow>inflow) = accumulation/bullish; positive = distribution
  - Exchange RESERVES declining → supply-shock (thin float, demand has outsized price impact)
  - WHALE accumulation (1k–100k cohort balance ↑) + Glassnode Accumulation Trend Score (0–1, →1 = accumulating)
  - MVRV / MVRV Z-Score: low (<0.85 z) = undervalued/bottom; high (>7 z) = top warning
  - aSOPR: <1 loss-dominant (capitulation); crossing >1 = profit transition (early bull)
  - Funding rate: deeply negative = shorts pay longs = contrarian bullish
  - Stablecoin inflow to exchanges = dry powder (bullish); + coin outflow = strong institutional accumulation
"""
from __future__ import annotations
from typing import Optional


def _num(x) -> Optional[float]:
    try:
        v = float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def netflow_signal(net_exchange_flow_7d=None) -> dict:
    """Net coins to exchanges over ~7d. Negative = outflow = accumulation/bullish."""
    n = _num(net_exchange_flow_7d)
    if n is None:
        return {"bias": 0, "label": "netflow n/a", "reason": "no exchange flow data"}
    if n < 0:
        return {"bias": 1, "label": "outflow (akumulasi)", "reason": f"net outflow {n:,.0f} → coins ke cold storage, supply turun"}
    if n > 0:
        return {"bias": -1, "label": "inflow (distribusi)", "reason": f"net inflow {n:,.0f} → coins ke exchange, siap dijual"}
    return {"bias": 0, "label": "netflow flat", "reason": "flow seimbang"}


def reserve_signal(reserve_now=None, reserve_30d_ago=None) -> dict:
    """Exchange reserves trend. Declining = supply shock potential (bullish)."""
    r0, r1 = _num(reserve_now), _num(reserve_30d_ago)
    if r0 is None or r1 is None or r1 <= 0:
        return {"bias": 0, "label": "reserve n/a", "reason": "no reserve data"}
    chg = (r0 - r1) / r1 * 100.0
    if chg < -2:
        return {"bias": 1, "label": "reserve ↓ (supply shock)", "reason": f"reserve turun {chg:+.1f}% → float menipis, demand kecil pun gerakin harga"}
    if chg > 2:
        return {"bias": -1, "label": "reserve ↑", "reason": f"reserve naik {chg:+.1f}% → supply nambah di exchange"}
    return {"bias": 0, "label": "reserve flat", "reason": f"reserve stabil ({chg:+.1f}%)"}


def whale_signal(whale_bal_chg_30d_pct=None, accumulation_trend_score=None) -> dict:
    """Whale cohort (1k–100k) balance change + Glassnode Accumulation Trend Score (0–1)."""
    w = _num(whale_bal_chg_30d_pct)
    a = _num(accumulation_trend_score)
    bias, bits = 0, []
    if w is not None:
        if w > 0.5:
            bias = 1; bits.append(f"whale +{w:.1f}% (akumulasi)")
        elif w < -0.5:
            bias = -1; bits.append(f"whale {w:.1f}% (offload)")
        else:
            bits.append(f"whale ~flat ({w:+.1f}%)")
    if a is not None:
        if a >= 0.6:
            bias = 1 if bias >= 0 else bias; bits.append(f"AccTrend {a:.2f} (entity besar akumulasi)")
        elif a <= 0.4:
            bias = -1 if bias <= 0 else bias; bits.append(f"AccTrend {a:.2f} (distribusi)")
    if not bits:
        return {"bias": 0, "label": "whale n/a", "reason": "no whale data"}
    return {"bias": bias, "label": "whale " + ("akumulasi" if bias > 0 else "distribusi" if bias < 0 else "netral"),
            "reason": " · ".join(bits)}


def mvrv_signal(mvrv_z=None) -> dict:
    """MVRV Z-Score: <0.85 deep value/bottom; 0.85–3 normal; 3–7 elevated; >7 top warning."""
    z = _num(mvrv_z)
    if z is None:
        return {"bias": 0, "label": "MVRV n/a", "reason": "no MVRV data"}
    if z < 0.85:
        return {"bias": 1, "label": "MVRV deep value", "reason": f"MVRV-Z {z:.2f} <0.85 → zona undervalued/bottom historis"}
    if z > 7:
        return {"bias": -1, "label": "MVRV top zone", "reason": f"MVRV-Z {z:.2f} >7 → froth/top warning"}
    if z > 5:
        return {"bias": -1, "label": "MVRV elevated", "reason": f"MVRV-Z {z:.2f} → mulai panas"}
    return {"bias": 0, "label": "MVRV normal", "reason": f"MVRV-Z {z:.2f} (zona normal)"}


def sopr_signal(asopr=None) -> dict:
    """aSOPR <1 = loss-dominant (capitulation); ≥1 = profit-taking. Cross above 1 = early-bull transition."""
    s = _num(asopr)
    if s is None:
        return {"bias": 0, "label": "SOPR n/a", "reason": "no SOPR data"}
    if s < 0.98:
        return {"bias": 1, "label": "SOPR <1 (capitulation)", "reason": f"aSOPR {s:.3f} → jual rugi dominan (kapitulasi = sering bottom)"}
    if 0.98 <= s <= 1.02:
        return {"bias": 1, "label": "SOPR transisi", "reason": f"aSOPR {s:.3f} → transisi loss→profit (early bull)"}
    return {"bias": 0, "label": "SOPR >1 (profit)", "reason": f"aSOPR {s:.3f} → profit-taking normal"}


def funding_signal(funding_rate=None) -> dict:
    """Perp funding. Deeply negative = shorts pay longs = contrarian bullish (bearish overextended)."""
    fr = _num(funding_rate)
    if fr is None:
        return {"bias": 0, "label": "funding n/a", "reason": "no funding data"}
    if fr < -0.0003:
        return {"bias": 1, "label": "funding negatif", "reason": f"funding {fr*100:.3f}% → short bayar long, sentimen bear overextended (contrarian bull)"}
    if fr > 0.0005:
        return {"bias": -1, "label": "funding tinggi", "reason": f"funding {fr*100:.3f}% → long crowded (leverage froth)"}
    return {"bias": 0, "label": "funding netral", "reason": f"funding {fr*100:.3f}%"}


def stablecoin_signal(stablecoin_inflow_7d=None) -> dict:
    """Stablecoin inflow to exchanges = dry powder waiting to buy (bullish)."""
    s = _num(stablecoin_inflow_7d)
    if s is None:
        return {"bias": 0, "label": "stablecoin n/a", "reason": "no stablecoin flow"}
    if s > 0:
        return {"bias": 1, "label": "stablecoin inflow", "reason": f"stablecoin +{s:,.0f} masuk exchange → dry powder buat beli"}
    return {"bias": 0, "label": "stablecoin netral", "reason": "no net stablecoin inflow"}


def onchain_composite(net_exchange_flow_7d=None, reserve_now=None, reserve_30d_ago=None,
                      whale_bal_chg_30d_pct=None, accumulation_trend_score=None, mvrv_z=None,
                      asopr=None, funding_rate=None, stablecoin_inflow_7d=None) -> dict:
    """Aggregate verdict + CORNERING flag. No single metric decides — composite (hedge-fund style)."""
    parts = {
        "netflow": netflow_signal(net_exchange_flow_7d),
        "reserve": reserve_signal(reserve_now, reserve_30d_ago),
        "whale": whale_signal(whale_bal_chg_30d_pct, accumulation_trend_score),
        "mvrv": mvrv_signal(mvrv_z),
        "sopr": sopr_signal(asopr),
        "funding": funding_signal(funding_rate),
        "stablecoin": stablecoin_signal(stablecoin_inflow_7d),
    }
    biases = [p["bias"] for p in parts.values() if p["bias"] != 0]
    n_have = len(biases)
    score = sum(biases)
    if n_have == 0:
        verdict, label = 0, "on-chain n/a (butuh feed)"
    elif score >= 2:
        verdict, label = 1, "AKUMULASI (smart money beli diam-diam)"
    elif score <= -2:
        verdict, label = -1, "DISTRIBUSI (smart money lepas barang)"
    else:
        verdict, label = 0, "on-chain campur/netral"
    # CORNERING: reserves draining hard + whales accumulating + net outflow + supply shock → markup-ready
    cornering = (parts["reserve"]["bias"] == 1 and parts["whale"]["bias"] == 1
                 and parts["netflow"]["bias"] == 1)
    return {"verdict": verdict, "label": label, "score": score, "metrics_available": n_have,
            "cornering": cornering,
            "cornering_note": ("⚠️ CORNERING SUPPLY: reserve drain + whale akumulasi + outflow → MM lagi ngumpulin, markup likely"
                               if cornering else ""),
            "parts": parts}


def tvl_flow_signal(tvl_change_7d_pct=None) -> dict:
    """DeFiLlama TVL 7d change: capital flowing INTO the chain = on-chain accumulation proxy.
    NOTE: TVL ≠ exchange netflow/whale supply — it's DeFi locked capital, a softer/different flow signal."""
    c = _num(tvl_change_7d_pct)
    if c is None:
        return {"bias": 0, "label": "TVL n/a", "reason": "no DeFiLlama TVL"}
    if c > 5:
        return {"bias": 1, "label": "TVL inflow", "reason": f"TVL +{c:.1f}% 7d → capital masuk chain (akumulasi on-chain)"}
    if c < -5:
        return {"bias": -1, "label": "TVL outflow", "reason": f"TVL {c:.1f}% 7d → capital keluar chain"}
    return {"bias": 0, "label": "TVL flat", "reason": f"TVL {c:+.1f}% 7d"}


def evaluate_from_snap(snap: dict, ticker: str) -> dict:
    """On-chain read from whatever REAL data the snap carries (DeFiLlama TVL + funding if present).
    Honest: exchange netflow / whale / MVRV / SOPR / CORNERING need a Glassnode/CryptoQuant feed the
    system doesn't fetch — those stay n/a until a feed is supplied (don't fabricate)."""
    snap = snap or {}
    od = (snap.get("onchain_data", {}) or {}).get(ticker, {})
    od = od if isinstance(od, dict) else {}
    tvl_chg = od.get("tvl_change_7d")
    funding = od.get("funding_rate")  # only if a real feed populated it
    parts = {"tvl_flow": tvl_flow_signal(tvl_chg), "funding": funding_signal(funding)}
    biases = [p["bias"] for p in parts.values() if p["bias"] != 0]
    score = sum(biases); n = len(biases)
    if n == 0:
        verdict, label = 0, "on-chain n/a (butuh feed Glassnode/CryptoQuant buat netflow/whale/MVRV)"
    elif score >= 1:
        verdict, label = 1, "AKUMULASI on-chain (TVL inflow)"
    elif score <= -1:
        verdict, label = -1, "DISTRIBUSI on-chain (TVL outflow)"
    else:
        verdict, label = 0, "on-chain netral"
    return {"verdict": verdict, "label": label, "score": score, "available": n, "parts": parts,
            "tvl_usd": od.get("tvl") or od.get("tvl_usd"), "source": od.get("source", "none"),
            "note": ("Sinyal dari DeFiLlama TVL (proxy DeFi locked-capital). Exchange netflow / whale / "
                     "MVRV / SOPR / cornering butuh feed Glassnode/CryptoQuant — belum ada di sistem.")}


if __name__ == "__main__":
    print("=== SELF-TEST onchain_engine ===")
    assert netflow_signal(-900_000_000)["bias"] == 1
    assert netflow_signal(500_000)["bias"] == -1
    assert reserve_signal(2.0e6, 2.2e6)["bias"] == 1            # -9% reserves → bullish
    assert whale_signal(2.4, 0.7)["bias"] == 1
    assert mvrv_signal(0.5)["bias"] == 1 and mvrv_signal(8)["bias"] == -1
    assert sopr_signal(0.97)["bias"] == 1
    assert funding_signal(-0.0068)["bias"] == 1
    assert stablecoin_signal(1.2e9)["bias"] == 1
    print("✓ primitives")
    # composite: accumulation bottom (the March-2026 BTC setup from research)
    c = onchain_composite(net_exchange_flow_7d=-18000, reserve_now=2.0e6, reserve_30d_ago=2.3e6,
                          whale_bal_chg_30d_pct=2.4, accumulation_trend_score=0.7, mvrv_z=0.8,
                          asopr=0.97, funding_rate=-0.0068, stablecoin_inflow_7d=8e8)
    assert c["verdict"] == 1 and c["cornering"] is True, c
    print("✓ composite →", c["label"], "| cornering:", c["cornering"])
    # distribution top
    d = onchain_composite(net_exchange_flow_7d=50000, reserve_now=2.4e6, reserve_30d_ago=2.2e6,
                          whale_bal_chg_30d_pct=-1.5, mvrv_z=8, asopr=1.05, funding_rate=0.001)
    assert d["verdict"] == -1, d
    print("✓ composite distribusi →", d["label"])
    # no data → neutral, no crash
    assert onchain_composite()["verdict"] == 0
    print("✓ defensive (no data)")
    # tvl flow + snap adapter (DeFiLlama)
    assert tvl_flow_signal(8)["bias"] == 1 and tvl_flow_signal(-8)["bias"] == -1 and tvl_flow_signal(1)["bias"] == 0
    snap = {"onchain_data": {"BTC-USD": {"tvl": 5e9, "tvl_change_7d": 9.2, "source": "defillama"}}}
    ev = evaluate_from_snap(snap, "BTC-USD")
    assert ev["verdict"] == 1 and ev["available"] == 1 and ev["source"] == "defillama", ev
    assert evaluate_from_snap({}, "ETH-USD")["available"] == 0  # no feed → n/a, no crash
    print("✓ tvl_flow + evaluate_from_snap →", ev["label"])
    print("ALL TESTS PASSED ✅")
