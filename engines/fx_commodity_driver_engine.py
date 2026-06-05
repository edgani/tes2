"""
fx_commodity_driver_engine.py — encodes the FX/COMMODITIES setup playbook into signals.

Pure-logic, defensive (returns neutral on missing data — never raises). Primitives are unit-tested
in __main__. UI/data wiring (feeding live DXY / TIPS real yield / oil curve / GSR) is the next step;
these functions take explicit inputs so they're testable and correct in isolation.

Sources encoded (see FX_COMMO_SETUP_PLAYBOOK.md):
  - COT Index = (net − 52w_low)/(52w_high − 52w_low)×100; commercial = smart money (contrarian)
  - Gold 2026: real-yield correlation structurally broken → weight DXY + CB-buying; GYDI paradox
  - Oil: backwardation (front>deferred) = bullish; contango = bearish + roll-drag
  - GSR: >80 → silver cheap (favor XAG); <60 → gold cheap (favor XAU); 60–80 neutral; mean-revert
  - Currency strength: rank by (rate-diff + COT index + momentum); long strongest vs short weakest
  - Confluence: full-conviction only when TAIL+TREND+TRADE+driver+COT all aligned
"""
from __future__ import annotations
from typing import Optional


def _num(x) -> Optional[float]:
    try:
        v = float(x)
        return v if v == v else None  # reject NaN
    except (TypeError, ValueError):
        return None


# ── 1. COT INDEX ───────────────────────────────────────────────────────────
def cot_index(net_now, net_52w_high, net_52w_low) -> Optional[float]:
    """Normalize current net position into 0–100 vs its 52-week range."""
    n, hi, lo = _num(net_now), _num(net_52w_high), _num(net_52w_low)
    if n is None or hi is None or lo is None or hi <= lo:
        return None
    return max(0.0, min(100.0, (n - lo) / (hi - lo) * 100.0))


def cot_signal(commercial_idx, spec_idx) -> dict:
    """Commercial = smart money (contrarian). LONG setup: commercials heavy-long + specs heavy-short."""
    c, s = _num(commercial_idx), _num(spec_idx)
    if c is None and s is None:
        return {"bias": 0, "label": "COT n/a", "reason": "no COT data"}
    bias, label, reason = 0, "COT netral", "positioning seimbang"
    if c is not None and c >= 75:
        bias, label, reason = 1, "COT bullish", f"commercial heavy-long ({c:.0f}/100)"
    elif c is not None and c <= 25:
        bias, label, reason = -1, "COT bearish", f"commercial heavy-short ({c:.0f}/100)"
    if s is not None and s >= 85:
        reason += f" · spec crowded-long ({s:.0f}) → unwind risk"
    elif s is not None and s <= 15:
        reason += f" · spec crowded-short ({s:.0f}) → squeeze risk"
    return {"bias": bias, "label": label, "reason": reason}


# ── 2. GOLD (XAU) ────────────────────────────────────────────────────────────
def gold_bias(dxy_trend=None, real_yield_30d_bp=None, gold_30d_ret=None,
              cb_buying_strong=None) -> dict:
    """2026-aware: real-yield link broken → DXY + CB-buying dominant. dxy_trend: -1 down/0/+1 up."""
    score = 0.0
    reasons = []
    dt = _num(dxy_trend)
    if dt is not None:
        score += -1.4 * dt  # DXY down = gold up (strongest residual driver)
        reasons.append(f"DXY {'turun (tailwind)' if dt < 0 else 'naik (headwind)' if dt > 0 else 'flat'}")
    ry = _num(real_yield_30d_bp)
    g30 = _num(gold_30d_ret)
    gydi = False
    if ry is not None and g30 is not None and g30 > 0 and ry > 0:
        gydi = True  # gold up AND real-yield up = structural bid (paradox)
        mag = min(abs(g30) / 0.10, 1) * 50 + min(abs(ry) / 75, 1) * 50
        score += 0.8
        reasons.append(f"GYDI paradox ON (struktural bid, score {mag:.0f})")
    elif ry is not None:
        score += -0.5 * (ry / 50.0)  # downweighted vs classic model (corr broke down)
        reasons.append(f"real-yield {ry:+.0f}bp (bobot turun — korelasi pecah 2026)")
    if cb_buying_strong:
        score += 1.0
        reasons.append("CB buying kuat")
    bias = 1 if score >= 0.8 else -1 if score <= -0.8 else 0
    return {"bias": bias, "score": round(score, 2), "gydi_paradox": gydi,
            "label": {1: "Gold bullish", -1: "Gold bearish", 0: "Gold netral"}[bias],
            "reason": " · ".join(reasons) or "data driver kurang"}


# ── 3. OIL (WTI) — curve structure ──────────────────────────────────────────
def oil_curve_bias(front_px=None, deferred_px=None) -> dict:
    """Backwardation (front>deferred) = bullish (tight supply now). Contango = bearish + roll-drag."""
    f, d = _num(front_px), _num(deferred_px)
    if f is None or d is None or f <= 0:
        return {"bias": 0, "structure": "n/a", "label": "Oil curve n/a", "roll": "n/a",
                "reason": "butuh harga front + deferred contract"}
    spread_pct = (f - d) / f * 100.0
    if spread_pct > 0.3:
        return {"bias": 1, "structure": "backwardation", "label": "Oil bullish",
                "roll": "positive roll (tailwind buat long futures)",
                "reason": f"backwardation {spread_pct:+.2f}% (front>deferred): supply ketat, demand sekarang"}
    if spread_pct < -0.3:
        return {"bias": -1, "structure": "contango", "label": "Oil bearish",
                "roll": "roll-cost drag (USO rugi roll)",
                "reason": f"contango {spread_pct:+.2f}% (front<deferred): oversupply / demand near-term lemah"}
    return {"bias": 0, "structure": "flat", "label": "Oil netral", "roll": "minimal",
            "reason": f"kurva flat ({spread_pct:+.2f}%)"}


# ── 4. GOLD/SILVER RATIO selector ────────────────────────────────────────────
def gsr_state(gold_px=None, silver_px=None) -> dict:
    """GSR >80 → silver murah (favor XAG); <60 → gold murah (favor XAU); 60–80 neutral."""
    g, s = _num(gold_px), _num(silver_px)
    if g is None or s is None or s <= 0:
        return {"gsr": None, "favor": "n/a", "label": "GSR n/a", "reason": "butuh harga gold + silver"}
    gsr = g / s
    if gsr >= 90:
        favor, note = "silver", "EKSTREM (>90): tiap kali era modern, silver outperform setelahnya"
    elif gsr >= 80:
        favor, note = "silver", "silver murah relatif (>80) — bias XAGUSD, tunggu reversal konfirmasi"
    elif gsr <= 60:
        favor, note = "gold", "silver udah outperform jauh (<60) — gold better value, bias XAUUSD"
    else:
        favor, note = "neutral", "zona netral (60–80) — gak ada yang jelas mispriced"
    return {"gsr": round(gsr, 1), "favor": favor, "label": f"GSR {gsr:.1f} → {favor}", "reason": note}


# ── 5. CURRENCY STRENGTH (pick strongest vs weakest) ─────────────────────────
def currency_strength(scores: dict) -> dict:
    """scores: {ccy: {'rate_diff': x, 'cot_idx': 0-100, 'momentum': pct}}. Returns ranked + best pair."""
    if not scores:
        return {"ranked": [], "long": None, "short": None, "pair": None, "reason": "no inputs"}
    ranked = []
    for ccy, m in scores.items():
        rd = _num(m.get("rate_diff")) or 0.0
        cot = _num(m.get("cot_idx"))
        mom = _num(m.get("momentum")) or 0.0
        # normalize: rate-diff and momentum scaled; cot centered at 50
        composite = 0.45 * rd + 0.30 * (mom / 2.0) + 0.25 * (((cot - 50) / 50.0) if cot is not None else 0.0)
        ranked.append((ccy, round(composite, 3)))
    ranked.sort(key=lambda t: t[1], reverse=True)
    if len(ranked) < 2:
        return {"ranked": ranked, "long": ranked[0][0] if ranked else None,
                "short": None, "pair": None, "reason": "butuh ≥2 mata uang"}
    strongest, weakest = ranked[0][0], ranked[-1][0]
    return {"ranked": ranked, "long": strongest, "short": weakest,
            "pair": f"{strongest}/{weakest}",
            "reason": f"long {strongest} (skor {ranked[0][1]:+.2f}) vs short {weakest} ({ranked[-1][1]:+.2f}) = spread terbesar"}


# ── 6. CONFLUENCE GATE (naik & panjang, bukan 1–2%) ──────────────────────────
def confluence(trade_phase=0, trend_phase=0, tail_phase=0, driver_bias=0,
               cot_aligned=None) -> dict:
    """Full conviction only when TAIL+TREND+TRADE+driver all aligned (same sign) + COT not opposing."""
    phases = [_num(trade_phase) or 0, _num(trend_phase) or 0, _num(tail_phase) or 0]
    d = _num(driver_bias) or 0
    aligned_long = all(p > 0 for p in phases) and d > 0
    aligned_short = all(p < 0 for p in phases) and d < 0
    cot_ok = (cot_aligned is None) or (cot_aligned == (1 if aligned_long else -1 if aligned_short else 0)) or cot_aligned == 0
    if (aligned_long or aligned_short) and cot_ok:
        side = "LONG" if aligned_long else "SHORT"
        return {"conviction": "FULL", "side": side, "hold": "position (ratusan %+ mungkin)",
                "reason": f"TAIL+TREND+TRADE+driver semua {side.lower()}" + ("" if cot_aligned is None else " + COT searah")}
    # partial: TRADE-only or mixed
    bull_ct = sum(1 for p in phases if p > 0)
    bear_ct = sum(1 for p in phases if p < 0)
    if bull_ct >= 2 or bear_ct >= 2:
        return {"conviction": "PARTIAL", "side": "LONG" if bull_ct > bear_ct else "SHORT",
                "hold": "scalp/swing 1–3% (atau leverage)",
                "reason": "TF belum align penuh — TAIL/TREND/TRADE/driver campur"}
    return {"conviction": "NONE", "side": "FLAT", "hold": "tunggu",
            "reason": "gak ada alignment"}


def evaluate(ticker: str, *, dxy_trend=None, real_yield_30d_bp=None, gold_30d_ret=None,
             cb_buying_strong=None, front_px=None, deferred_px=None, gold_px=None, silver_px=None,
             commercial_idx=None, spec_idx=None, trade_phase=0, trend_phase=0, tail_phase=0) -> dict:
    """Combine the relevant primitives for a ticker. Defensive — only uses inputs provided."""
    t = (ticker or "").upper()
    out = {"ticker": ticker, "cot": cot_signal(commercial_idx, spec_idx)}
    driver = {"bias": 0}
    if any(k in t for k in ("GC", "GLD", "XAU")):
        driver = gold_bias(dxy_trend, real_yield_30d_bp, gold_30d_ret, cb_buying_strong)
        out["gsr"] = gsr_state(gold_px, silver_px)
    elif any(k in t for k in ("SI", "SLV", "XAG")):
        out["gsr"] = gsr_state(gold_px, silver_px)
        driver = {"bias": 1 if out["gsr"].get("favor") == "silver" else 0,
                  "label": "Silver " + ("bias (GSR)" if out["gsr"].get("favor") == "silver" else "netral"),
                  "reason": out["gsr"].get("reason", "")}
    elif any(k in t for k in ("CL", "USO", "WTI", "BZ")):
        driver = oil_curve_bias(front_px, deferred_px)
    out["driver"] = driver
    out["confluence"] = confluence(trade_phase, trend_phase, tail_phase, driver.get("bias", 0),
                                   out["cot"].get("bias"))
    return out


def _coerce_trend(val, prev=None):
    """Turn a level+prev (or a series) into a -1/0/+1 trend sign."""
    try:
        if isinstance(val, (list, tuple)) and len(val) >= 2:
            a, b = float(val[-1]), float(val[max(0, len(val) - 21)])
            if b:
                ch = (a - b) / abs(b)
                return 1 if ch > 0.005 else -1 if ch < -0.005 else 0
        v, p = float(val), (float(prev) if prev is not None else None)
        if p is not None and p:
            ch = (v - p) / abs(p)
            return 1 if ch > 0.005 else -1 if ch < -0.005 else 0
    except (TypeError, ValueError, ZeroDivisionError):
        pass
    return None


def evaluate_from_snap(snap: dict, ticker: str, peers: Optional[dict] = None) -> dict:
    """Adapter: pull whatever macro fields the live snap carries → engine inputs. Fully defensive:
    every field is optional and the engine returns neutral/n/a when data is absent (never raises).

    Reads (best-effort, multiple shapes tolerated):
      - DXY trend  ← snap['dxy'] (level, {level,prev}, or series) / snap['dxy_series']
      - real yield ← snap['real_yield'] or snap['macro']['real_yield'] (30d Δbp if a series is present)
      - gold/silver px ← snap own price + `peers` map {'gold':px,'silver':px} when provided (for GSR)
      - oil curve  ← snap['oil_front']/snap['oil_deferred'] when present
      - TRADE/TREND/TAIL phases ← snap['risk_range'] phase signs when present
    Caller is expected to pass `peers` for GSR (cross-ticker) since a single-ticker snap won't have both.
    """
    snap = snap or {}
    macro = snap.get("macro") or {}

    # DXY trend
    dxy_trend = None
    if "dxy_series" in snap:
        dxy_trend = _coerce_trend(snap.get("dxy_series"))
    if dxy_trend is None:
        dv = snap.get("dxy")
        if isinstance(dv, dict):
            dxy_trend = _coerce_trend(dv.get("level"), dv.get("prev"))
        else:
            dxy_trend = _coerce_trend(dv, snap.get("dxy_prev") or macro.get("dxy_prev"))

    # real yield (level → coarse bp proxy if no series)
    ry = snap.get("real_yield", macro.get("real_yield"))
    ry_bp = None
    try:
        if isinstance(ry, (list, tuple)) and len(ry) >= 2:
            ry_bp = (float(ry[-1]) - float(ry[max(0, len(ry) - 21)])) * 100.0
        elif ry is not None:
            ry_bp = None  # only a level; leave bp unknown (engine downweights anyway)
    except (TypeError, ValueError):
        ry_bp = None

    # ticker 30d return (for GYDI paradox on gold)
    g30 = None
    for k in ("price_series", "closes", "prices"):
        s = snap.get(k)
        if isinstance(s, (list, tuple)) and len(s) > 21 and s[-21]:
            try:
                g30 = (float(s[-1]) - float(s[-21])) / float(s[-21]); break
            except (TypeError, ValueError, ZeroDivisionError):
                pass

    # GSR needs both metals — only if caller supplied peers
    gold_px = silver_px = None
    if peers:
        gold_px = peers.get("gold") or peers.get("XAUUSD") or peers.get("GC=F")
        silver_px = peers.get("silver") or peers.get("XAGUSD") or peers.get("SI=F")

    # phases from risk_range if present (sign of each duration's bias)
    rr = snap.get("risk_range") or {}
    def _ph(side):
        v = rr.get(side) or rr.get(side.lower()) or {}
        if isinstance(v, dict):
            b = v.get("bias") or v.get("phase_sign") or v.get("signal")
            return _coerce_trend([0, b]) if isinstance(b, (int, float)) else 0
        return 0

    return evaluate(
        ticker,
        dxy_trend=dxy_trend, real_yield_30d_bp=ry_bp, gold_30d_ret=g30,
        cb_buying_strong=snap.get("cb_buying_strong"),
        front_px=snap.get("oil_front"), deferred_px=snap.get("oil_deferred"),
        gold_px=gold_px, silver_px=silver_px,
        commercial_idx=snap.get("cot_commercial_idx"), spec_idx=snap.get("cot_spec_idx"),
        trade_phase=_ph("TRADE"), trend_phase=_ph("TREND"), tail_phase=_ph("TAIL"),
    )


if __name__ == "__main__":
    print("=== SELF-TEST fx_commodity_driver_engine ===")
    # COT index
    assert cot_index(80, 100, 0) == 80.0
    assert cot_index(50, 50, 50) is None  # degenerate range
    assert cot_index(None, 1, 0) is None
    print("✓ cot_index")
    # gold: DXY down + CB buying → bullish; GYDI paradox
    g = gold_bias(dxy_trend=-1, cb_buying_strong=True)
    assert g["bias"] == 1, g
    gp = gold_bias(real_yield_30d_bp=40, gold_30d_ret=0.05)
    assert gp["gydi_paradox"] is True, gp
    print("✓ gold_bias", g["label"], "| GYDI:", gp["gydi_paradox"])
    # oil: backwardation bullish, contango bearish
    assert oil_curve_bias(80, 78)["bias"] == 1
    assert oil_curve_bias(78, 80)["bias"] == -1
    assert oil_curve_bias(None, 80)["bias"] == 0
    print("✓ oil_curve_bias")
    # GSR
    assert gsr_state(5000, 50)["favor"] == "silver"      # GSR=100
    assert gsr_state(3000, 60)["favor"] == "gold"        # GSR=50
    assert gsr_state(3500, 50)["favor"] == "neutral"     # GSR=70
    print("✓ gsr_state", gsr_state(5000, 50)["label"])
    # currency strength
    cs = currency_strength({"USD": {"rate_diff": -1, "momentum": -2, "cot_idx": 30},
                            "EUR": {"rate_diff": 1, "momentum": 3, "cot_idx": 70},
                            "JPY": {"rate_diff": 0, "momentum": 1, "cot_idx": 55}})
    assert cs["long"] == "EUR" and cs["short"] == "USD", cs
    print("✓ currency_strength →", cs["pair"])
    # confluence
    assert confluence(1, 1, 1, 1, 1)["conviction"] == "FULL"
    assert confluence(1, 1, -1, 1)["conviction"] in ("PARTIAL", "NONE")
    assert confluence(0, 0, 0, 0)["conviction"] == "NONE"
    print("✓ confluence")
    # evaluate end-to-end (gold + oil)
    eg = evaluate("XAUUSD", dxy_trend=-1, cb_buying_strong=True, gold_px=5000, silver_px=50,
                  trade_phase=1, trend_phase=1, tail_phase=1)
    eo = evaluate("CL=F", front_px=80, deferred_px=78, trade_phase=1, trend_phase=1, tail_phase=1)
    assert eg["driver"]["bias"] == 1 and eg["confluence"]["conviction"] == "FULL", eg
    assert eo["driver"]["bias"] == 1, eo
    print("✓ evaluate:", eg["driver"]["label"], "/", eg["confluence"]["conviction"], "|", eo["driver"]["label"])
    # snap adapter (defensive): synthetic snap with dxy series down + peers for GSR
    snap = {"dxy_series": [104 - i * 0.12 for i in range(25)],
            "price_series": [4800] * 20 + [5000], "risk_range": {}}
    es = evaluate_from_snap(snap, "XAUUSD", peers={"gold": 5000, "silver": 50})
    assert es["driver"]["bias"] == 1, es  # DXY trending down → gold bullish
    assert es["gsr"]["favor"] == "silver", es
    assert evaluate_from_snap({}, "GC=F")["driver"]["bias"] == 0  # empty snap → neutral, no crash
    print("✓ evaluate_from_snap:", es["driver"]["label"], "| GSR", es["gsr"]["label"])
    print("ALL TESTS PASSED ✅")
