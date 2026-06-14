"""options_greeks_engine.py — Vanna/Charm calendar + Gamma wall framework v40

Built from Edward's NVTS deep-dive template. Computes/presents:
  1. VANNA/CHARM WINDOW — based on monthly OPEX calendar (3rd Friday)
     • Window opens: Monday of week BEFORE opex
     • Window peaks: Tuesday of opex week
     • Charm decay accelerates into expiry (Wed-Fri opex week)
  2. GAMMA WALLS — call wall (resistance), put wall (support), gamma flip
  3. MM POSITIONING — long gamma (vol suppress) vs short gamma (vol amplify)
  4. SHORT SQUEEZE mechanics — short interest %, days-to-cover
  5. IV CRUSH risk — post-event/post-opex vanna reversal
  6. EXPECTED MOVE — implied by ATM straddle

References: Cem Karsan (Vanna/Charm/monthly OPEX flows), SpotGamma (walls/flip),
NVTS case study (May 2026 squeeze: vanna/charm window 18-26 May → $33.82 ATH).
"""
from __future__ import annotations
import datetime as dt
from typing import Dict, Optional, List
import calendar


# ═══════════════════════════════════════════════════════════════════════════
# OPEX CALENDAR — Monthly options expiration (3rd Friday)
# ═══════════════════════════════════════════════════════════════════════════

def _third_friday(year: int, month: int) -> dt.date:
    """Return the 3rd Friday of given month — monthly OPEX."""
    c = calendar.Calendar(firstweekday=calendar.MONDAY)
    fridays = [d for d in c.itermonthdates(year, month)
               if d.month == month and d.weekday() == 4]
    return fridays[2] if len(fridays) >= 3 else fridays[-1]


def get_opex_calendar(ref_date: Optional[dt.date] = None) -> Dict:
    """Return current + next monthly OPEX dates and vanna/charm window status."""
    today = ref_date or dt.date.today()

    # Find this month's opex
    this_opex = _third_friday(today.year, today.month)
    if today > this_opex:
        # Move to next month
        nm = today.month + 1
        ny = today.year
        if nm > 12:
            nm = 1; ny += 1
        next_opex = _third_friday(ny, nm)
        current_opex = next_opex
    else:
        current_opex = this_opex
        nm = today.month + 1
        ny = today.year
        if nm > 12:
            nm = 1; ny += 1
        next_opex = _third_friday(ny, nm)

    # Vanna/Charm window: Monday of week before opex → Tuesday of opex week
    # opex is Friday. Opex week Monday = opex - 4 days. Window start = opex - 11 days (Mon prev week)
    window_start = current_opex - dt.timedelta(days=11)  # Monday week before
    window_peak = current_opex - dt.timedelta(days=3)     # Tuesday opex week
    window_end = current_opex - dt.timedelta(days=1)      # Thursday (charm max)

    days_to_opex = (current_opex - today).days

    # Window status
    if today < window_start:
        window_status = "PRE_WINDOW"
        window_note = f"Vanna/charm window belum buka. Opens {window_start.isoformat()}"
    elif window_start <= today <= window_peak:
        window_status = "WINDOW_ACTIVE_BUILDING"
        window_note = (f"🔥 VANNA/CHARM WINDOW ACTIVE — building toward peak {window_peak.isoformat()}. "
                       f"Dealer hedging flows accelerating.")
    elif window_peak < today <= window_end:
        window_status = "WINDOW_PEAK_CHARM_MAX"
        window_note = (f"⚡ CHARM MAX — opex week, charm decay forcing dealer delta hedging daily. "
                       f"Mechanical push toward max-pain/walls until {current_opex.isoformat()}.")
    elif today == current_opex:
        window_status = "OPEX_DAY"
        window_note = "📅 OPEX DAY — max charm, pinning to max-pain likely. Post-close = window resets."
    else:
        window_status = "POST_OPEX"
        window_note = "Post-opex — vanna reversal / IV crush risk if IV elevated."

    return {
        "today": today.isoformat(),
        "current_opex": current_opex.isoformat(),
        "next_opex": next_opex.isoformat(),
        "days_to_opex": days_to_opex,
        "vanna_charm_window": {
            "start": window_start.isoformat(),
            "peak": window_peak.isoformat(),
            "end": window_end.isoformat(),
            "status": window_status,
            "note": window_note,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# GAMMA / GREEKS ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════

def analyze_gamma_positioning(opts: Dict, px: float) -> Dict:
    """Analyze gamma walls + MM positioning regime."""
    if not opts or not px:
        return {"available": False}

    call_wall = opts.get("call_wall") or opts.get("call_wall_strike")
    put_wall = opts.get("put_wall") or opts.get("put_wall_strike")
    gamma_flip = opts.get("gamma_flip") or opts.get("vol_trigger") or opts.get("zero_gamma")
    max_pain = opts.get("max_pain")
    net_gex = opts.get("gex") or opts.get("net_gex")

    result = {"available": True}

    # Gamma regime
    if net_gex is not None:
        try:
            gex_val = float(net_gex)
            if gex_val > 0:
                result["regime"] = "LONG_GAMMA"
                result["regime_note"] = (
                    "🟢 MM LONG GAMMA → volatility SUPPRESSED. Price mean-reverts within walls. "
                    "Buy dips / sell rips works. Sell premium (iron condor/strangle)."
                )
            else:
                result["regime"] = "SHORT_GAMMA"
                result["regime_note"] = (
                    "🔴 MM SHORT GAMMA → volatility AMPLIFIED. Breakouts accelerate (dealer chases). "
                    "Buy options, avoid selling premium. Gamma squeeze risk above call wall."
                )
            result["net_gex"] = gex_val
        except (TypeError, ValueError):
            pass

    # Walls
    if call_wall:
        try:
            cw = float(call_wall)
            result["call_wall"] = cw
            result["call_wall_dist_pct"] = round((cw - px) / px * 100, 2)
        except (TypeError, ValueError):
            pass
    if put_wall:
        try:
            pw = float(put_wall)
            result["put_wall"] = pw
            result["put_wall_dist_pct"] = round((pw - px) / px * 100, 2)
        except (TypeError, ValueError):
            pass
    if gamma_flip:
        try:
            gf = float(gamma_flip)
            result["gamma_flip"] = gf
            result["above_flip"] = px > gf
        except (TypeError, ValueError):
            pass
    if max_pain:
        try:
            result["max_pain"] = float(max_pain)
        except (TypeError, ValueError):
            pass

    return result


def analyze_short_squeeze(opts: Dict, fundamentals: Dict = None) -> Dict:
    """Short squeeze mechanics (NVTS-style). Needs short interest data."""
    fundamentals = fundamentals or {}
    si_pct = (opts.get("short_interest_pct") or opts.get("short_pct_float")
              or fundamentals.get("short_percent_of_float"))
    days_to_cover = opts.get("days_to_cover") or fundamentals.get("days_to_cover")

    if si_pct is None:
        return {"available": False}

    try:
        si = float(si_pct) * 100 if float(si_pct) < 1 else float(si_pct)
    except (TypeError, ValueError):
        return {"available": False}

    result = {"available": True, "short_interest_pct": round(si, 2)}
    if days_to_cover is not None:
        try:
            result["days_to_cover"] = round(float(days_to_cover), 2)
        except (TypeError, ValueError):
            pass

    # Squeeze potential
    if si > 20:
        result["squeeze_risk"] = "HIGH"
        result["note"] = (
            f"🚀 HIGH SQUEEZE RISK — {si:.1f}% short interest. "
            f"Catalyst + call buying can force violent covering (NVTS playbook: 25.9% SI → +300% in 6wk)."
        )
    elif si > 10:
        result["squeeze_risk"] = "MODERATE"
        result["note"] = f"⚠️ Moderate short interest {si:.1f}% — squeeze possible on catalyst."
    else:
        result["squeeze_risk"] = "LOW"
        result["note"] = f"Short interest {si:.1f}% — low squeeze potential."
    return result


def build_options_intelligence(ticker: str, opts: Dict, px: float,
                                fundamentals: Dict = None,
                                ref_date: Optional[dt.date] = None) -> Dict:
    """Full options intelligence package (NVTS-style synthesis)."""
    calendar_data = get_opex_calendar(ref_date)
    gamma = analyze_gamma_positioning(opts, px) if opts else {"available": False}
    squeeze = analyze_short_squeeze(opts or {}, fundamentals)

    # Expected move
    expected_move = None
    if opts:
        em = opts.get("expected_move_pct") or opts.get("expected_move")
        iv = opts.get("atm_iv") or opts.get("iv_30d")
        if em:
            try:
                expected_move = round(float(em), 2)
            except (TypeError, ValueError):
                pass
        elif iv:
            try:
                # Approx weekly expected move from annualized IV
                iv_val = float(iv)
                if iv_val > 1:
                    iv_val /= 100
                expected_move = round(iv_val / (52 ** 0.5) * 100, 2)
            except (TypeError, ValueError):
                pass

    return {
        "ticker": ticker,
        "opex_calendar": calendar_data,
        "gamma": gamma,
        "squeeze": squeeze,
        "expected_move_pct": expected_move,
    }
