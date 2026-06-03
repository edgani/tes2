"""engines/maker_framework.py — IDX Maker Roadmap / Thought-Process Engine

Encodes the framework from the "goreng menggoreng saham" essay (Om B's playbook).

CORE THESIS (faithful to the source): broker-summary / bandarmology is mostly *semu*
(wash circulation through dozens of nominees across many securities, all converging to
one source). You CANNOT read the maker by staring at broksum. So this engine detects the
maker's ROADMAP PHASE from PRICE + VOLUME STRUCTURE (Wyckoff-like), not from broksum.
Broker-summary, IF provided, is used ONLY to FLAG wash-circulation — never as a buy/sell
signal. The actionable edge per the essay: understand the maker's roadmap and ride the
markup patiently; don't chase ticks; don't panic on fake-foreign selling; and recognize
that "looks cheap after a drop" is usually the DISTRIBUTION trap.

The 4 phases:
  PERSIAPAN  → (not price-detectable; roadmap/funding/nominees lined up)
  AKUMULASI  → price lowered then stagnant range to shake out impatient holders; offer
               thicker than bid (fake supply); fake foreign selling; bad news early.
  MARKUP     → bid thick > offer; maker eats own offers (semu); volume rises; chart drawn
               'beautifully'; tape reading; square position; good news to justify.
  DISTRIBUSI → good news no longer moves price (exhaustion); made to look 'cheap' (trap);
               high volume but price stuck; dumps into a fake-thick bid; block sale.

This module is market-agnostic in its PRICE/VOLUME core (applies to any thin, maker-driven
market). The broksum wash-checks are IDX-flavored but conceptually portable.
"""
from __future__ import annotations
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def _pct(a, b):
    try:
        return float(a) / float(b) - 1.0 if b else 0.0
    except Exception:
        return 0.0


def analyze_maker_framework(
    ticker: str,
    prices,
    volume=None,
    broksum: Optional[Dict] = None,
    news_good: Optional[bool] = None,
    shares_outstanding: Optional[float] = None,
) -> Dict:
    """Detect the maker roadmap phase + traps from price/volume; flag wash if broksum given.

    Args:
        prices: pd.Series of closes (or array-like).
        volume: optional pd.Series of volume (enhances phase confidence).
        broksum: optional {"brokers": [{"code","net","buy","sell","foreign":bool}], ...}
                 — used ONLY for wash flags, never as a directional signal.
        news_good: optional bool — was recent material news positive? (for exhaustion check)
        shares_outstanding: optional float (lots or shares) — for the volume>float wash check.
    Returns dict: phase, confidence, tells[], traps[], wash_flags[], action, thought_process.
    """
    import pandas as pd
    import numpy as np

    out = {
        "ticker": ticker, "phase": "UNCLEAR", "confidence": 0.0,
        "tells": [], "traps": [], "wash_flags": [], "action": "WATCH",
        "thought_process": "",
    }
    try:
        s = pd.to_numeric(pd.Series(prices), errors="coerce").dropna()
    except Exception:
        return out
    if len(s) < 60:
        out["thought_process"] = "Insufficient history (<60 bars) to read a maker roadmap."
        return out

    px = float(s.iloc[-1])
    ma20 = float(s.tail(20).mean())
    ma50 = float(s.tail(50).mean())
    ma200 = float(s.tail(min(200, len(s))).mean())
    hi = float(s.tail(252).max() if len(s) >= 252 else s.max())
    lo = float(s.tail(252).min() if len(s) >= 252 else s.min())
    dd_from_high = _pct(px, hi)          # ≤0
    runup_from_low = _pct(px, lo)        # ≥0
    ret20 = _pct(s.iloc[-1], s.iloc[-21]) if len(s) >= 21 else 0.0
    ret60 = _pct(s.iloc[-1], s.iloc[-61]) if len(s) >= 61 else 0.0

    # range tightness over last 40 bars (stagnation / coiling = accumulation tell)
    win = s.tail(40)
    rng_pct = _pct(float(win.max()), float(win.min()))  # high/low-1 over the window
    coiling = rng_pct < 0.14

    # deceleration = recent per-bar pace notably below the 60-bar pace (topping).
    # NOT raw cumulative (ret20 spans fewer bars so is naturally smaller than ret60 —
    # comparing them directly mislabels a steady markup as distribution).
    pace20 = ret20 / 20.0
    pace60 = ret60 / 60.0
    decel = (ret60 > 0.25) and (pace20 < pace60 * 0.5)

    # volume structure (optional)
    vol_rising = vol_climax = vol_dry = False
    if volume is not None:
        try:
            v = pd.to_numeric(pd.Series(volume), errors="coerce").dropna()
            if len(v) >= 60:
                v20, v60 = float(v.tail(20).mean()), float(v.tail(60).mean())
                vol_rising = v20 > v60 * 1.25
                vol_climax = float(v.tail(5).mean()) > v60 * 2.2
                vol_dry = v20 < v60 * 0.7
        except Exception:
            pass

    tells, traps = [], []

    # ── PHASE INFERENCE (price/volume structure) ───────────────────────────
    phase, conf = "UNCLEAR", 0.0

    # DISTRIBUSI: big run-up, momentum rolling over, churn (high vol, price stuck), and
    # — the essay's key tell — good news no longer lifts price.
    # DISTRIBUSI: big run-up rolling over, churn (high vol/price stuck), or — the essay's
    # PRIMARY tell — good news that no longer lifts price (news exhaustion).
    news_exhaustion = (news_good is True and runup_from_low > 0.4 and abs(ret20) < 0.04)
    if (runup_from_low > 0.6 and decel) or news_exhaustion:
        phase, conf = "DISTRIBUSI", 0.5
        if decel:
            conf += 0.05
            tells.append("Big run-up + momentum rolling over (markup exhausting)")
        if vol_climax and abs(ret20) < 0.05:
            conf += 0.15
            tells.append("High volume but price stuck — churn = distribution into demand")
        if news_exhaustion:
            conf += 0.20
            tells.append("Good news no longer moves price — NEWS EXHAUSTION (classic distribusi)")
        traps.append("Pullbacks here look 'cheap' but are the maker DISTRIBUTING — not dip-buys")

    # MARKUP: above MAs, strong run with rising volume, higher-highs.
    elif px > ma20 and px > ma50 and ret60 > 0.15 and (vol_rising or volume is None):
        phase, conf = "MARKUP", 0.55
        tells.append("Price > 20/50 MA on a strong run — markup underway")
        if vol_rising:
            conf += 0.15; tells.append("Volume expanding into the rise")
        if runup_from_low > 1.5 and (vol_climax or abs(ret20) > 0.35):
            traps.append("Parabolic + volume climax — late markup, exhaustion risk")
            conf = min(conf, 0.6)

    # AKUMULASI: well off the highs, coiling in a stagnant range (shakeout), volume drying
    # then basing. The essay: maker lowers price then holds a sideways range to bore out
    # impatient holders, with fake-thick offers + fake foreign selling.
    elif coiling and (-0.65 < dd_from_high < -0.15):
        phase, conf = "AKUMULASI", 0.5
        tells.append("Well off highs + tight stagnant range = shakeout / absorption zone")
        if vol_dry:
            conf += 0.15; tells.append("Volume dried up — supply being absorbed quietly")
        if px >= ma50 * 0.98 and dd_from_high < -0.2:
            conf += 0.10; tells.append("Price holding ~50MA despite the drawdown (defended)")

    # Early AKUMULASI / post-crash base
    elif dd_from_high < -0.6 and coiling:
        phase, conf = "AKUMULASI", 0.4
        tells.append("Deep post-distribution base, coiling at lows (early accumulation)")

    out["phase"], out["confidence"] = phase, round(min(conf, 0.95), 2)

    # ── TRAP: the essay's signature 'looks cheap' distribution trap ─────────
    if -0.45 < dd_from_high < -0.18 and runup_from_low > 0.5 and decel:
        traps.append("'LOOKS CHEAP' TRAP: down from the high but still far above base + "
                     "momentum fading — likely distribution, not a discount")

    # ── WASH-CIRCULATION FLAGS (broksum is FLAG-ONLY, never a buy signal) ───
    if broksum and isinstance(broksum, dict):
        brokers = broksum.get("brokers") or []
        try:
            gross = sum(abs(float(b.get("buy", 0)) - float(b.get("sell", 0))) for b in brokers)
            net_total = sum(float(b.get("buy", 0)) - float(b.get("sell", 0)) for b in brokers)
            if gross > 0 and abs(net_total) / gross < 0.10:
                out["wash_flags"].append("Aggregate net ≈ 0 vs gross — consortium wash "
                                         "(buyers are also the sellers; circulation is semu)")
            top_buyer = max(brokers, key=lambda b: float(b.get("buy", 0)), default=None)
            top_seller = max(brokers, key=lambda b: float(b.get("sell", 0)), default=None)
            if top_buyer and top_seller and top_buyer.get("code") == top_seller.get("code"):
                out["wash_flags"].append(f"Top buyer == top seller ({top_buyer.get('code')}) "
                                         "— same hand on both sides (wash)")
            if shares_outstanding:
                big = max((float(b.get("buy", 0)) for b in brokers), default=0)
                if big > float(shares_outstanding):
                    out["wash_flags"].append("A single broker 'bought' more than shares "
                                             "outstanding — impossible for real demand (wash)")
            for b in brokers:
                if b.get("foreign") and abs(float(b.get("net", 0))) > 0 and runup_from_low < 2:
                    out["wash_flags"].append(f"Heavy FOREIGN flow ({b.get('code')}) on a small/"
                                             "mid-cap — ~90% likely a nominee, NOT real foreign")
                    break
        except Exception:
            pass

    out["tells"], out["traps"] = tells, traps

    # ── ACTION + THOUGHT PROCESS (the essay's edge: ride the roadmap, don't chase) ──
    if phase == "AKUMULASI":
        out["action"] = "ACCUMULATE_WITH_MAKER"
        out["thought_process"] = (
            "Maker likely absorbing in a boring range. Expect shakeouts, fake-thick offers, "
            "and fake-foreign selling designed to scare you out. Edge = patience: accumulate "
            "into weakness and HOLD; don't panic on 'foreign exit' (likely nominee). "
            "Confirmation that accumulation is ending = a single dominant accumulator + "
            "limited downside even on bad news.")
    elif phase == "MARKUP":
        out["action"] = "RIDE_DONT_CHASE"
        out["thought_process"] = (
            "Markup underway — maker pushing with square-position circulation and tape "
            "reading. Ride the trend; do NOT chase the 3-5 tick gertakan or panic when a "
            "thick bid is suddenly pulled (that's pace control). Good news will be released "
            "to justify the rise. Trail, don't front-run.")
    elif phase == "DISTRIBUSI":
        out["action"] = "AVOID_DISTRIBUTION"
        out["thought_process"] = (
            "Distribution signs: run-up exhausting, churn on high volume, and good news that "
            "no longer lifts price. The 'cheap' pullback is the TRAP — maker is dumping into "
            "a fake-thick bid and via block sale. Do NOT average down here. Stand aside until "
            "a fresh base forms.")
    else:
        out["action"] = "WATCH"
        out["thought_process"] = ("No clear maker phase from price/volume structure. "
                                  "Per the essay, do not read broksum day-to-day — wait for a "
                                  "structural read (range shakeout, markup, or churn).")

    return out


def analyze_universe_maker(prices: Dict, volumes: Optional[Dict] = None,
                           broksums: Optional[Dict] = None) -> Dict:
    """Run the maker-framework over a dict of {ticker: price_series}. Defensive per ticker."""
    volumes = volumes or {}
    broksums = broksums or {}
    res = {}
    for t, s in (prices or {}).items():
        try:
            res[t] = analyze_maker_framework(t, s, volume=volumes.get(t),
                                             broksum=broksums.get(t))
        except Exception as e:
            logger.debug(f"maker_framework failed for {t}: {e}")
    return res
