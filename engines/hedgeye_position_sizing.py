"""hedgeye_position_sizing.py — VIX-bucket × Quad-fit × Conviction sizing v40

Real implementation (replaces stub). Hedgeye public methodology:
  Base: 50-100 bps inception, 150-200 bps breakout
  VIX bucket: Investable (9-18) 1.0×, Chop (18-29) 0.5×, F-bucket (29+) 0.1×
  Quad fit: GREAT 1.0, GOOD 0.7, NEUTRAL 0.4, BAD 0.1, AVOID 0
  Conviction (1-10): linear 0.10-1.00
  Distance-to-LRR bonus: ≤2% → +30bp, ≤5% → +15bp
  Keith TRADE BEARISH override → block
"""
from typing import Dict, Optional, List
import logging
logger = logging.getLogger(__name__)

QUAD_SECTOR_FIT = {
    "Q1": {
        "GREAT": ["XLK", "QQQ", "IGV", "SOXX", "XLY", "XLC", "XBI", "XHB"],
        "GOOD": ["NVDA", "META", "AMZN", "GOOG", "AAPL", "MSFT", "TSLA", "AMD", "AVGO", "MU"],
        "AVOID": ["XLU", "XLP", "TLT", "GLD", "VNQ"],
    },
    "Q2": {
        "GREAT": ["XLE", "XLF", "XLI", "XOP", "OIH", "XLB", "IWM", "EFA"],
        "GOOD": ["JPM", "BAC", "GS", "FCX", "CAT", "DE", "MU", "AVGO", "MEDC.JK", "ADRO.JK"],
        "AVOID": ["TLT", "XLP", "GLD"],
    },
    "Q3": {
        "GREAT": ["XLE", "GLD", "GDX", "XME", "DBC", "USO", "UNG", "PALL", "CL=F", "GC=F"],
        "GOOD": ["FCX", "NEM", "CCJ", "MOS", "CF", "VLO", "OXY", "FRO", "STNG"],
        "AVOID": ["XLY", "IYC", "ITB", "XHB"],
    },
    "Q4": {
        "GREAT": ["UUP", "TLT", "XLU", "XLP", "GLD", "MUB", "AGG"],
        "GOOD": ["VZ", "T", "WMT", "KO", "PG", "PEP", "NEE"],
        "AVOID": ["JNK", "HYG", "IWM", "EEM", "XLE", "XLF"],
    },
}

def get_quad_fit(ticker: str, quad: str) -> str:
    q = QUAD_SECTOR_FIT.get(quad, {})
    if ticker in q.get("GREAT", []): return "GREAT"
    if ticker in q.get("GOOD", []): return "GOOD"
    if ticker in q.get("AVOID", []): return "AVOID"
    opp = {"Q1": "Q4", "Q4": "Q1", "Q2": "Q3", "Q3": "Q2"}.get(quad)
    if opp and ticker in QUAD_SECTOR_FIT.get(opp, {}).get("GREAT", []):
        return "BAD"
    return "NEUTRAL"

def get_vix_bucket(vix: float) -> Dict:
    # S3-a: Hedgeye published buckets — 9–19 investable, 20–29 chop, 29+ f-bucket.
    # (Was <18 investable, which mislabelled VIX 18–19 as chop.)
    if vix < 20:
        return {"bucket": "INVESTABLE", "multiplier": 1.0, "label": "🟢 Investable (9-19)"}
    if vix < 29:
        return {"bucket": "CHOP", "multiplier": 0.5, "label": "🟡 Chop (20-29)"}
    return {"bucket": "F_BUCKET", "multiplier": 0.10, "label": "🔴 F-bucket (29+)"}

def calculate_position_size(ticker, quad, vix, conviction=5, rr_data=None,
                             keith_signal=None, is_breakout=False,
                             current_position_bps=0):
    base = 175 if is_breakout else 75
    vix_d = get_vix_bucket(vix)
    fit = get_quad_fit(ticker, quad)
    fit_mult = {"GREAT": 1.0, "GOOD": 0.70, "NEUTRAL": 0.40, "BAD": 0.10, "AVOID": 0.0}.get(fit, 0.40)
    conv = max(1, min(10, conviction)) / 10.0

    dist_bonus = 0
    if rr_data and "trade" in rr_data:
        px = rr_data.get("px", 0); lrr = rr_data["trade"].get("lrr", 0)
        if px > 0 and lrr > 0:
            d = (px - lrr) / px * 100
            if 0 < d <= 2.0: dist_bonus = 30
            elif d <= 5.0: dist_bonus = 15

    keith_block = False; keith_boost = 1.0
    if keith_signal:
        sig = keith_signal.get("TRADE", keith_signal.get("trade", "NEUTRAL"))
        if isinstance(sig, str):
            if sig.upper() == "BEARISH": keith_block = True
            elif sig.upper() == "BULLISH": keith_boost = 1.10

    if keith_block:
        return {"ticker": ticker, "bps": 0, "blocked": True,
                "reason": "Keith TRADE BEARISH", "quad_fit": fit,
                "vix_bucket": vix_d["bucket"]}

    bps = int(base * vix_d["multiplier"] * fit_mult * conv * keith_boost + dist_bonus)
    bps = max(0, min(bps, 250))  # per-signal ADD cap

    # S3-c: enforce Hedgeye POSITION envelope (equities max 6%). This function sizes
    # the ADD; clamp so cumulative position never exceeds 6%, and flag when at cap.
    MAX_POSITION_BPS = 600
    cur = max(0, int(current_position_bps))
    room = max(0, MAX_POSITION_BPS - cur)
    bps = min(bps, room)
    position_after = cur + bps
    at_max = position_after >= MAX_POSITION_BPS

    if bps >= 150: tier = "🔵 FULL"
    elif bps >= 75: tier = "🟢 HALF"
    elif bps >= 25: tier = "🟡 QUARTER"
    elif bps > 0: tier = "⚪ MINIMAL"
    else: tier = "❌ NONE"

    return {"ticker": ticker, "bps": bps, "blocked": False, "tier": tier,
            "quad_fit": fit, "vix_bucket": vix_d["bucket"],
            "vix_bucket_label": vix_d["label"], "is_breakout": is_breakout,
            "distance_bonus": dist_bonus,
            "position_after_bps": position_after, "at_max_position": at_max,
            "max_position_bps": MAX_POSITION_BPS,
            "explanation": f"{base}bp × {vix_d['multiplier']}vix × {fit_mult}({fit}) × {conv}conv × {keith_boost}Keith + {dist_bonus}dist = {bps}bp (pos {position_after}/{MAX_POSITION_BPS}bp)"}

def run_sizing(candidates, quad, vix, keith_signals=None, rr_data=None):
    """Batch sizing — replaces conviction_sizing stub."""
    ks = keith_signals or {}; rd = rr_data or {}
    out = []; total = 0
    for c in candidates or []:
        if isinstance(c, str):
            c = {"ticker": c, "conviction": 5}
        t = c.get("ticker") if isinstance(c, dict) else None
        if not t: continue
        s = calculate_position_size(t, quad, vix,
            conviction=c.get("conviction", 5),
            rr_data=rd.get(t), keith_signal=ks.get(t),
            is_breakout=c.get("is_breakout", False))
        out.append(s)
        if not s["blocked"]: total += s["bps"]
    return {"positions": out, "total_bps": total,
            "total_pct": round(total / 100, 2),
            "blocked_count": sum(1 for x in out if x["blocked"]),
            "quad_applied": quad, "vix_applied": vix}
