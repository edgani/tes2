"""engines/market_card_renderer.py -- Market-Specific Ticker Card Renderer v1.0

Renders beautiful, market-specific ticker cards with:
  - Visual entry zone bar
  - Multi-target (T1/T2/T3) with timelines
  - Market-specific data panels (options/Greeks, COT, on-chain, etc.)
  - Thesis panel
  - Execution checklist

Usage:
    from engines.market_card_renderer import render_market_card
    html = render_market_card(row, market_type="us_equity", scraper_data={})
    st.markdown(html, unsafe_allow_html=True)
"""

import math
from typing import Dict, List, Optional

# ──────────────────────────────────────────────────────────────────────────────
# Color constants
# ──────────────────────────────────────────────────────────────────────────────
COLORS = {
    "bg": "#0a0e17",
    "card": "#111827",
    "section": "#1a2236",
    "border": "#1e293b",
    "border_active": "#334155",
    "text": "#f1f5f9",
    "text_secondary": "#94a3b8",
    "text_muted": "#64748b",
    "green": "#10b981",
    "green_dim": "rgba(16,185,129,0.15)",
    "red": "#ef4444",
    "red_dim": "rgba(239,68,68,0.15)",
    "blue": "#3b82f6",
    "blue_dim": "rgba(59,130,246,0.15)",
    "yellow": "#f59e0b",
    "yellow_dim": "rgba(245,158,11,0.15)",
    "purple": "#8b5cf6",
    "cyan": "#06b6d4",
    "pink": "#ec4899",
    "accent_us": "#10b981",
    "accent_fx": "#8b5cf6",
    "accent_comm": "#f59e0b",
    "accent_crypto": "#06b6d4",
    "accent_ihsg": "#ec4899",
}

# ──────────────────────────────────────────────────────────────────────────────
# Accent helpers
# ──────────────────────────────────────────────────────────────────────────────
_MARKET_ACCENT_MAP = {
    "us_equity": COLORS["accent_us"],
    "forex": COLORS["accent_fx"],
    "commodity": COLORS["accent_comm"],
    "crypto": COLORS["accent_crypto"],
    "ihsg": COLORS["accent_ihsg"],
}


def _accent(market_type: str) -> str:
    return _MARKET_ACCENT_MAP.get(market_type, COLORS["accent_us"])


def _dim_color(hex_color: str, alpha: float = 0.15) -> str:
    """Convert hex to rgba with given alpha."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ──────────────────────────────────────────────────────────────────────────────
# Format helpers
# ──────────────────────────────────────────────────────────────────────────────
def _ffm(v, market_type: str = "us_equity") -> str:
    """Format a numeric value for display based on market type."""
    if v is None:
        return "\u2014"
    try:
        f = float(v)
        if not math.isfinite(f):
            return "\u2014"
        if market_type == "forex":
            return f"{f:,.5f}"
        elif market_type == "crypto":
            return f"{f:,.4f}" if abs(f) < 1 else f"{f:,.2f}"
        elif market_type == "commodity":
            return f"{f:,.2f}"
        elif market_type == "ihsg":
            return f"{f:,.0f}" if abs(f) > 100 else f"{f:,.2f}"
        else:
            return f"{f:,.2f}"
    except (ValueError, TypeError):
        return "\u2014"


def _ffm_pct(v, suffix: str = "%") -> str:
    """Format a percentage value."""
    if v is None:
        return "\u2014"
    try:
        f = float(v)
        if not math.isfinite(f):
            return "\u2014"
        return f"{f:,.1f}{suffix}"
    except (ValueError, TypeError):
        return "\u2014"


def _ffm_currency(v, prefix: str = "$") -> str:
    """Format a currency value."""
    if v is None:
        return "\u2014"
    try:
        f = float(v)
        if not math.isfinite(f):
            return "\u2014"
        return f"{prefix}{abs(f):,.2f}"
    except (ValueError, TypeError):
        return "\u2014"


# ──────────────────────────────────────────────────────────────────────────────
# Shared UI components
# ──────────────────────────────────────────────────────────────────────────────
def _signal_color(direction: str) -> str:
    return COLORS["green"] if direction.upper() == "LONG" else COLORS["red"]


def _signal_bg(direction: str) -> str:
    return COLORS["green_dim"] if direction.upper() == "LONG" else COLORS["red_dim"]


def _grade_color(grade: str) -> str:
    g = grade.upper()
    if g in ("A", "S"):
        return COLORS["green"]
    elif g == "B":
        return COLORS["blue"]
    elif g == "C":
        return COLORS["yellow"]
    else:
        return COLORS["red"]


def _rr_color(rr: float) -> str:
    if rr >= 3:
        return COLORS["green"]
    elif rr >= 2:
        return COLORS["blue"]
    elif rr >= 1:
        return COLORS["yellow"]
    return COLORS["red"]


# ──────────────────────────────────────────────────────────────────────────────
# Signal Badge
# ──────────────────────────────────────────────────────────────────────────────
def _build_signal_badge(direction: str, grade: str, confidence: float, rr: float) -> str:
    """Build the header signal badge (LONG/SHORT with grade & confidence)."""
    sig_color = _signal_color(direction)
    sig_bg = _signal_bg(direction)
    g_color = _grade_color(grade)
    r_color = _rr_color(rr)
    direction_upper = direction.upper()

    return f"""
<div style="padding:14px 16px 10px 16px;">
  <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
    <div style="display:flex;align-items:center;gap:10px;">
      <span style="background:{sig_bg};color:{sig_color};padding:4px 12px;border-radius:6px;font-size:13px;font-weight:700;border:1px solid {sig_color};">
        {direction_upper}
      </span>
      <span style="color:{g_color};font-size:22px;font-weight:800;">
        Grade {grade.upper()}
      </span>
    </div>
    <div style="display:flex;align-items:center;gap:12px;">
      <span style="color:{COLORS['text_secondary']};font-size:12px;">
        Confidence <b style="color:{COLORS['text']};">{confidence}%</b>
      </span>
      <span style="color:{r_color};font-size:12px;background:{_dim_color(r_color,0.12)};padding:3px 8px;border-radius:4px;">
        R:R {rr:.1f}:1
      </span>
    </div>
  </div>
</div>
"""


# ──────────────────────────────────────────────────────────────────────────────
# Entry Zone Bar -- visual horizontal bar showing stop->entry->current->T1->T2->T3
# ──────────────────────────────────────────────────────────────────────────────
def _build_entry_zone_bar(
    entry: float,
    stop: float,
    current: float,
    t1: float,
    t2: float,
    t3: float,
    market_type: str,
) -> str:
    """Build a visual entry zone bar with price markers."""
    values = {"stop": stop, "entry": entry, "current": current, "t1": t1, "t2": t2, "t3": t3}
    if any(v is None or v == 0 for v in values.values()):
        return _build_entry_zone_bar_simple(entry, stop, current, t1, t2, t3, market_type)

    # Normalize all prices to 0-100 range
    all_vals = [stop, entry, current, t1, t2, t3]
    lo, hi = min(all_vals), max(all_vals)
    if hi == lo:
        return _build_entry_zone_bar_simple(entry, stop, current, t1, t2, t3, market_type)
    pad = (hi - lo) * 0.1
    lo, hi = lo - pad, hi + pad

    def _pct(v: float) -> float:
        return max(0.0, min(100.0, ((v - lo) / (hi - lo)) * 100))

    p_stop = _pct(stop)
    p_entry = _pct(entry)
    p_current = _pct(current)
    p_t1 = _pct(t1)
    p_t2 = _pct(t2)
    p_t3 = _pct(t3)

    # Zone widths (between adjacent markers)
    zone1_w = p_entry - p_stop  # stop -> entry (red)
    zone2_w = p_current - p_entry  # entry -> current (blue)
    zone3_w = p_t1 - p_current  # current -> t1 (green dim)
    zone4_w = p_t2 - p_t1  # t1 -> t2 (green)
    zone5_w = p_t3 - p_t2  # t2 -> t3 (green bright)
    tail_w = 100 - p_t3  # after t3

    sig_c = _signal_color("LONG" if current >= entry else "SHORT")
    is_in_entry = min(entry, stop * 1.001) <= current <= max(entry * 1.001, stop)
    current_label_bg = COLORS["blue"] if is_in_entry else sig_c

    return f"""
<div style="padding:0 16px 10px 16px;">
  <!-- Bar background -->
  <div class="mr-entry-bar" style="display:flex;height:28px;border-radius:6px;overflow:hidden;background:{COLORS['section']};border:1px solid {COLORS['border']};position:relative;margin-bottom:6px;">
    <!-- Stop zone (red dim) -->
    <div style="width:{zone1_w}%;background:{COLORS['red_dim']};border-right:1px solid {COLORS['border']};"></div>
    <!-- Entry zone (blue dim) -->
    <div style="width:{zone2_w}%;background:{COLORS['blue_dim']};border-right:1px solid {COLORS['border']};"></div>
    <!-- Current->T1 zone (green dim) -->
    <div style="width:{zone3_w}%;background:{COLORS['green_dim']};border-right:1px solid {COLORS['border']};"></div>
    <!-- T1->T2 zone (green med) -->
    <div style="width:{zone4_w}%;background:rgba(16,185,129,0.3);border-right:1px solid {COLORS['border']};"></div>
    <!-- T2->T3 zone (green bright) -->
    <div style="width:{zone5_w}%;background:rgba(16,185,129,0.5);"></div>
    <!-- Tail -->
    <div style="width:{tail_w}%;background:{COLORS['section']};"></div>
    <!-- Current price marker -->
    <div style="position:absolute;left:{p_current}%;top:0;transform:translateX(-50%);display:flex;flex-direction:column;align-items:center;z-index:5;">
      <div style="width:2px;height:28px;background:{current_label_bg};"></div>
    </div>
  </div>
  <!-- Price labels -->
  <div style="display:flex;justify-content:space-between;position:relative;height:18px;font-size:11px;">
    <div style="color:{COLORS['red']};font-weight:600;">
      S {_ffm(stop, market_type)}
    </div>
    <div style="color:{COLORS['blue']};font-weight:600;">
      E {_ffm(entry, market_type)}
    </div>
    <div style="background:{current_label_bg};color:#fff;padding:1px 7px;border-radius:3px;font-weight:700;font-size:10px;margin-top:-2px;">
      {_ffm(current, market_type)}
    </div>
    <div style="color:{COLORS['green']};">
      T1 {_ffm(t1, market_type)}
    </div>
    <div style="color:{COLORS['green']};">
      T2 {_ffm(t2, market_type)}
    </div>
    <div style="color:{COLORS['green']};">
      T3 {_ffm(t3, market_type)}
    </div>
  </div>
</div>
"""


def _build_entry_zone_bar_simple(
    entry: float,
    stop: float,
    current: float,
    t1: float,
    t2: float,
    t3: float,
    market_type: str,
) -> str:
    """Fallback simple entry zone bar when values are missing or zero."""
    return f"""
<div style="padding:0 16px 10px 16px;">
  <div class="mr-entry-bar" style="display:flex;height:8px;border-radius:4px;overflow:hidden;background:{COLORS['section']};">
    <div style="width:18%;background:{COLORS['red_dim']};"></div>
    <div style="width:12%;background:{COLORS['blue_dim']};"></div>
    <div style="width:20%;background:{COLORS['green_dim']};"></div>
    <div style="width:25%;background:rgba(16,185,129,0.3);"></div>
    <div style="width:25%;background:rgba(16,185,129,0.5);"></div>
  </div>
  <div style="display:flex;justify-content:space-between;margin-top:6px;font-size:11px;">
    <span style="color:{COLORS['red']};">S {_ffm(stop, market_type)}</span>
    <span style="color:{COLORS['blue']};">E {_ffm(entry, market_type)}</span>
    <span style="color:{COLORS['green']};">T1 {_ffm(t1, market_type)}</span>
    <span style="color:{COLORS['green']};">T2 {_ffm(t2, market_type)}</span>
    <span style="color:{COLORS['green']};">T3 {_ffm(t3, market_type)}</span>
  </div>
</div>
"""


# ──────────────────────────────────────────────────────────────────────────────
# Multi-Target Grid
# ──────────────────────────────────────────────────────────────────────────────
def _build_target_grid(
    t1: float, t2: float, t3: float, entry: float, stop: float, market_type: str
) -> str:
    """Build 3-column target grid with R:R ratios and timeframes."""
    # Risk = distance from entry to stop
    risk = abs(entry - stop) if entry and stop else 0
    targets = [
        ("T1", t1, "1-4w", COLORS["green_dim"]),
        ("T2", t2, "1-3m", "rgba(16,185,129,0.3)"),
        ("T3", t3, "3-6m+", "rgba(16,185,129,0.5)"),
    ]

    cols_html = ""
    for label, price, timeframe, bg_color in targets:
        upside = abs(price - entry) if price and entry else 0
        rr = upside / risk if risk else 0
        profit_pct = (upside / entry * 100) if entry else 0
        cols_html += f"""
    <div class="mr-target-col" style="flex:1;background:{COLORS['section']};border:1px solid {COLORS['border']};border-radius:8px;padding:10px;text-align:center;">
      <div style="font-size:10px;color:{COLORS['text_muted']};margin-bottom:3px;">{label} &middot; {timeframe}</div>
      <div style="font-size:18px;font-weight:800;color:{COLORS['green']};">{_ffm(price, market_type)}</div>
      <div style="font-size:11px;color:{COLORS['text_secondary']};margin-top:2px;">
        +{_ffm_pct(profit_pct)} &middot; R:R {rr:.1f}
      </div>
    </div>
"""

    return f"""
<div class="mr-target-grid" style="padding:0 16px 10px 16px;display:flex;gap:8px;">
  {cols_html}
</div>
"""


# ──────────────────────────────────────────────────────────────────────────────
# Panel builder helper (section wrapper)
# ──────────────────────────────────────────────────────────────────────────────
def _panel(title: str, icon: str, content_html: str, accent: str) -> str:
    """Wrap content in a consistent panel style."""
    return f"""
<div style="margin:0 16px 10px 16px;background:{COLORS['section']};border:1px solid {COLORS['border']};border-radius:10px;overflow:hidden;">
  <div style="padding:10px 12px;border-bottom:1px solid {COLORS['border']};display:flex;align-items:center;gap:8px;">
    <span style="font-size:14px;">{icon}</span>
    <span style="font-size:12px;font-weight:700;color:{accent};text-transform:uppercase;letter-spacing:0.5px;">
      {title}
    </span>
  </div>
  <div style="padding:10px 12px;">
    {content_html}
  </div>
</div>
"""


# ──────────────────────────────────────────────────────────────────────────────
# Thesis Panel
# ──────────────────────────────────────────────────────────────────────────────
def _build_thesis_panel(row: Dict, market_type: str) -> str:
    """Build thesis bullet points auto-generated from row data."""
    bullets: List[str] = []

    direction = str(row.get("direction", "LONG")).upper()
    formation = row.get("formation", "")
    setup_note = row.get("setup_note", "")
    entry = row.get("entry", 0)
    stop = row.get("stop", 0)
    t1 = row.get("target_1", row.get("trade_top", 0))
    t2 = row.get("target_2", row.get("trend_top", 0))
    confidence = row.get("confidence", 0)
    grade = row.get("grade", "C")
    risk_pct = row.get("risk_pct", 0)
    chase_text = row.get("chase_text", "")

    sig_color_hex = COLORS["green"] if direction == "LONG" else COLORS["red"]

    # Formation-based thesis
    if formation:
        bullets.append(
            f"Formation <b>{formation}</b> signals potential <b>{direction}</b> opportunity"
        )

    # Entry zone
    if entry and stop:
        risk = abs(entry - stop)
        if risk > 0:
            bullets.append(
                f"Entry {_ffm(entry, market_type)} with stop {_ffm(stop, market_type)} = risk {_ffm(risk, market_type)} ({risk_pct}% of position)"
            )

    # Targets
    if t1:
        bullets.append(f"First target at {_ffm(t1, market_type)} for initial profit-taking (1-4 week horizon)")
    if t2:
        bullets.append(f"Secondary target at {_ffm(t2, market_type)} for trend capture (1-3 month horizon)")

    # Grade & confidence
    if confidence >= 80:
        bullets.append(f"<b>High confidence</b> ({confidence}%) setup with favorable risk-reward profile")
    elif confidence >= 60:
        bullets.append(f"Moderate confidence ({confidence}%) -- confirm with volume before entry")
    else:
        bullets.append(f"Lower confidence ({confidence}%) -- reduce position size or wait for confirmation")

    # Grade context
    g = str(grade).upper()
    if g in ("A", "S"):
        bullets.append(f"Grade <b>{g}</b> = premium setup with strong confluence of signals")
    elif g == "B":
        bullets.append(f"Grade <b>B</b> = solid setup with acceptable risk parameters")
    elif g == "C":
        bullets.append(f"Grade <b>C</b> = speculative -- use half normal position size")

    # Chase warning
    if chase_text:
        bullets.append(f"<span style=\"color:{COLORS['yellow']};\">&#9888; {chase_text}</span>")

    # Setup note
    if setup_note:
        bullets.append(setup_note)

    # Fallback
    if not bullets:
        bullets.append(f"<b>{direction}</b> setup based on technical analysis framework")

    # Render
    bullet_html = ""
    for b in bullets[:6]:
        bullet_html += f"""
    <li class="mr-thesis-item" style="margin-bottom:6px;color:{COLORS['text_secondary']};font-size:12px;line-height:1.5;">
      <span style="color:{sig_color_hex};margin-right:6px;">&#9654;</span>{b}
    </li>
"""

    accent = _accent(market_type)
    return _panel(
        "Trade Thesis",
        "&#128161;",
        f"<ul style='margin:0;padding-left:18px;list-style:none;'>{bullet_html}</ul>",
        accent,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Execution Checklist
# ──────────────────────────────────────────────────────────────────────────────
def _build_checklist(
    row: Dict, px: float, entry: float, stop: float, t1: float, t2: float
) -> str:
    """Build execution checklist with check/cross/neutral status."""
    direction = str(row.get("direction", "LONG")).upper()
    confidence = row.get("confidence", 0)

    checks: List[Dict] = []

    # 1. Price in entry zone
    if px and entry and stop:
        if min(entry, stop) <= px <= max(entry, stop):
            checks.append({"label": "Price in entry zone", "status": "pass"})
        elif (direction == "LONG" and px < stop) or (direction == "SHORT" and px > stop):
            checks.append({"label": "Price in entry zone", "status": "fail"})
        else:
            checks.append({"label": "Price in entry zone", "status": "pending"})
    else:
        checks.append({"label": "Price in entry zone", "status": "pending"})

    # 2. Risk-reward acceptable
    risk = abs(entry - stop) if entry and stop else 0
    reward = abs(t1 - entry) if t1 and entry else 0
    rr = reward / risk if risk else 0
    if rr >= 2:
        checks.append({"label": f"Risk:Reward ratio >= 2:1 (current {rr:.1f}:1)", "status": "pass"})
    elif rr >= 1:
        checks.append({"label": f"Risk:Reward ratio >= 2:1 (current {rr:.1f}:1)", "status": "pending"})
    else:
        checks.append({"label": f"Risk:Reward ratio >= 2:1 (current {rr:.1f}:1)", "status": "fail"})

    # 3. Confidence threshold
    if confidence >= 75:
        checks.append({"label": f"Confidence >= 75% (current {confidence}%)", "status": "pass"})
    elif confidence >= 50:
        checks.append({"label": f"Confidence >= 75% (current {confidence}%)", "status": "pending"})
    else:
        checks.append({"label": f"Confidence >= 75% (current {confidence}%)", "status": "fail"})

    # 4. Targets defined
    if t1 and t2:
        checks.append({"label": "Multiple targets defined (T1, T2)", "status": "pass"})
    elif t1:
        checks.append({"label": "Multiple targets defined (T1, T2)", "status": "pending"})
    else:
        checks.append({"label": "Multiple targets defined (T1, T2)", "status": "fail"})

    # 5. Stop defined
    if stop:
        checks.append({"label": "Stop-loss level defined", "status": "pass"})
    else:
        checks.append({"label": "Stop-loss level defined", "status": "fail"})

    # 6. Grade check
    grade = str(row.get("grade", "C")).upper()
    if grade in ("A", "S", "B"):
        checks.append({"label": f"Grade {grade} acceptable for entry", "status": "pass"})
    elif grade == "C":
        checks.append({"label": f"Grade {grade} -- reduce position size", "status": "pending"})
    else:
        checks.append({"label": f"Grade {grade} -- exercise caution", "status": "fail"})

    # Render
    STATUS_SYMBOLS = {
        "pass": ("&#9989;", COLORS["green"]),
        "fail": ("&#10060;", COLORS["red"]),
        "pending": ("&#9723;", COLORS["yellow"]),
    }

    item_html = ""
    for c in checks:
        sym, color = STATUS_SYMBOLS.get(c["status"], STATUS_SYMBOLS["pending"])
        item_html += f"""
    <div style="display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid {COLORS['border']};">
      <span style="color:{color};font-size:13px;">{sym}</span>
      <span style="color:{COLORS['text_secondary']};font-size:12px;flex:1;">{c['label']}</span>
    </div>
"""

    # Summary
    passed = sum(1 for c in checks if c["status"] == "pass")
    total = len(checks)
    score_color = COLORS["green"] if passed >= 5 else COLORS["yellow"] if passed >= 3 else COLORS["red"]

    return _panel(
        "Execution Checklist",
        "&#9745;",
        f"""
{item_html}
<div style="margin-top:8px;padding:6px 8px;background:{_dim_color(score_color,0.12)};border-radius:6px;text-align:center;">
  <span style="color:{score_color};font-size:13px;font-weight:700;">{passed}/{total} checks passed</span>
</div>
""",
        COLORS["blue"],
    )


# ──────────────────────────────────────────────────────────────────────────────
# OPTIONS INTELLIGENCE PANEL (US Equities)
# ──────────────────────────────────────────────────────────────────────────────
def _build_options_panel_us(row: Dict, scraper_data: Optional[Dict]) -> str:
    """Build US stocks options intelligence panel with IV, Greeks, Max Pain."""
    sd = scraper_data or {}

    # Extract option data (from scraper or fallback)
    iv_rank = sd.get("iv_rank", sd.get("ivRank", 24))
    iv_pct = sd.get("iv_pct", sd.get("ivPercentile", 18))
    iv_label = sd.get("iv_label", "CHEAP")
    max_pain = sd.get("max_pain", sd.get("maxPain", 0))
    pc_ratio = sd.get("pc_ratio", sd.get("putCallRatio", 0.72))
    em = sd.get("expected_move", sd.get("expectedMove", 10.5))
    gamma_ex = sd.get("gamma_exposure", sd.get("gammaExposure", "NEGATIVE"))
    put_wall = sd.get("put_wall", sd.get("putWall", 0))
    call_wall = sd.get("call_wall", sd.get("callWall", 0))

    # Color-code IV
    if isinstance(iv_label, str) and iv_label.upper() == "CHEAP":
        iv_color = COLORS["green"]
    elif isinstance(iv_label, str) and iv_label.upper() == "EXPENSIVE":
        iv_color = COLORS["red"]
    else:
        iv_color = COLORS["yellow"]

    # Color-code P/C ratio
    try:
        pc_val = float(pc_ratio)
        if pc_val < 0.8:
            pc_color, pc_label = COLORS["green"], "BULLISH"
        elif pc_val > 1.2:
            pc_color, pc_label = COLORS["red"], "BEARISH"
        else:
            pc_color, pc_label = COLORS["yellow"], "NEUTRAL"
    except (TypeError, ValueError):
        pc_color, pc_label = COLORS["text_secondary"], "N/A"

    # Recommendation logic
    rec_lines = []
    if isinstance(iv_label, str) and iv_label.upper() == "CHEAP":
        rec_lines.append("Vol cheap (low %ile) &rarr; <b>Buy options</b> if directional bias confirmed")
    elif isinstance(iv_label, str) and iv_label.upper() == "EXPENSIVE":
        rec_lines.append("Vol expensive &rarr; <b>Sell premium</b> or use spreads to reduce cost")
    else:
        rec_lines.append("Vol fairly priced &rarr; Focus on <b>direction</b> over vol strategy")

    if isinstance(gamma_ex, str) and gamma_ex.upper() == "NEGATIVE":
        rec_lines.append("Gamma <b>NEGATIVE</b> &rarr; acceleration risk on breakout moves")
    else:
        rec_lines.append("Gamma <b>POSITIVE</b> &rarr; mean-reversion tendency expected")

    if put_wall and max_pain:
        rec_lines.append(f"Put wall <b>${put_wall}</b> / Max pain <b>${max_pain}</b> = key support zone")

    rec_html = "<br>".join(f'<div style="margin-bottom:4px;color:{COLORS["text_secondary"]};font-size:12px;line-height:1.5;">&#128161; {line}</div>' for line in rec_lines)

    # Price formatting
    max_pain_str = f"${_ffm(max_pain)}" if max_pain else "\u2014"
    put_wall_str = f"${put_wall}" if put_wall else "\u2014"

    content = f"""
<div style="display:flex;flex-wrap:wrap;gap:12px;margin-bottom:10px;">
  <div style="flex:1;min-width:140px;">
    <div style="font-size:10px;color:{COLORS['text_muted']};margin-bottom:2px;">IV Rank</div>
    <div style="font-size:14px;font-weight:700;color:{COLORS['text']};">{_ffm_pct(iv_rank)} <span style="color:{iv_color};">[{iv_label}]</span></div>
  </div>
  <div style="flex:1;min-width:140px;">
    <div style="font-size:10px;color:{COLORS['text_muted']};margin-bottom:2px;">IV %ile</div>
    <div style="font-size:14px;font-weight:700;color:{COLORS['text']};">{_ffm_pct(iv_pct)}</div>
  </div>
  <div style="flex:1;min-width:140px;">
    <div style="font-size:10px;color:{COLORS['text_muted']};margin-bottom:2px;">Exp Move</div>
    <div style="font-size:14px;font-weight:700;color:{COLORS['text']};">&plusmn;{_ffm_pct(em)}</div>
  </div>
</div>
<div style="display:flex;flex-wrap:wrap;gap:12px;margin-bottom:10px;">
  <div style="flex:1;min-width:140px;">
    <div style="font-size:10px;color:{COLORS['text_muted']};margin-bottom:2px;">Max Pain</div>
    <div style="font-size:14px;font-weight:700;color:{COLORS['text']};">{max_pain_str}</div>
  </div>
  <div style="flex:1;min-width:140px;">
    <div style="font-size:10px;color:{COLORS['text_muted']};margin-bottom:2px;">P/C Ratio</div>
    <div style="font-size:14px;font-weight:700;color:{COLORS['text']};">{pc_ratio} <span style="color:{pc_color};">[{pc_label}]</span></div>
  </div>
</div>
<div style="border-top:1px solid {COLORS['border']};padding-top:8px;">
  <div style="font-size:11px;font-weight:700;color:{COLORS['yellow']};margin-bottom:6px;">&#128161; RECOMMENDATION</div>
  {rec_html}
</div>
"""

    return _panel("Options Intelligence", "&#128202;", content, COLORS["accent_us"])


# ──────────────────────────────────────────────────────────────────────────────
# COT POSITIONING PANEL (Forex)
# ──────────────────────────────────────────────────────────────────────────────
def _build_cot_panel_forex(row: Dict, scraper_data: Optional[Dict]) -> str:
    """Build Forex COT (Commitment of Traders) positioning panel."""
    sd = scraper_data or {}

    spec_net = sd.get("spec_net", sd.get("speculators_net", -84))
    comm_net = sd.get("comm_net", sd.get("commercial_net", 112))
    retail_net = sd.get("retail_net", sd.get("retail_positioning", -28))

    # Format with + sign
    def _fmt_k(v):
        if v is None:
            return "\u2014"
        try:
            f = float(v)
            sign = "+" if f >= 0 else ""
            return f"{sign}{f:,.0f}K"
        except (TypeError, ValueError):
            return "\u2014"

    # Labels based on positioning
    def _label(v):
        if v is None:
            return "N/A"
        try:
            f = float(v)
            if f > 80:
                return "EXTREME LONG"
            elif f > 30:
                return "LONG"
            elif f > 0:
                return "MODERATE LONG"
            elif f > -30:
                return "MODERATE SHORT"
            elif f > -80:
                return "SHORT"
            else:
                return "EXTREME SHORT"
        except (TypeError, ValueError):
            return "N/A"

    spec_label = _label(spec_net)
    comm_label = _label(comm_net)
    retail_label = _label(retail_net)

    spec_color = COLORS["green"] if (spec_net or 0) > 30 else COLORS["red"] if (spec_net or 0) < -30 else COLORS["yellow"]
    comm_color = COLORS["green"] if (comm_net or 0) > 30 else COLORS["red"] if (comm_net or 0) < -30 else COLORS["yellow"]
    retail_color = COLORS["red"] if (retail_net or 0) > 0 else COLORS["green"]

    # Recommendation logic
    rec_lines = []
    direction = str(row.get("direction", "LONG")).upper()

    if spec_net and comm_net:
        if spec_net < -50 and comm_net > 50:
            rec_lines.append("Spec <b>extreme short</b> + commercial <b>accumulating</b> = <b style=\"color:#10b981;\">BULLISH</b> signal")
        elif spec_net > 50 and comm_net < -50:
            rec_lines.append("Spec <b>extreme long</b> + commercial <b>hedging</b> = <b style=\"color:#ef4444;\">BEARISH</b> signal")
        else:
            rec_lines.append("COT positioning shows <b>mixed</b> signals -- wait for clarity")

    if retail_net:
        rec_lines.append(f"Retail <b>{retail_label.lower()}</b> &rarr; contrarian <b>{direction}</b> opportunity")

    rec_html = "<br>".join(f'<div style="margin-bottom:4px;color:{COLORS["text_secondary"]};font-size:12px;line-height:1.5;">&#128161; {line}</div>' for line in rec_lines) if rec_lines else f'<div style="color:{COLORS["text_muted"]};font-size:12px;">No COT data available</div>'

    content = f"""
<div style="margin-bottom:8px;">
  <div style="display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid {COLORS['border']};">
    <span style="color:{COLORS['text_secondary']};font-size:12px;">Speculators</span>
    <span style="font-weight:700;color:{spec_color};font-size:13px;">{_fmt_k(spec_net)} [{spec_label}]</span>
  </div>
  <div style="display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid {COLORS['border']};">
    <span style="color:{COLORS['text_secondary']};font-size:12px;">Commercial</span>
    <span style="font-weight:700;color:{comm_color};font-size:13px;">{_fmt_k(comm_net)} [{comm_label}]</span>
  </div>
  <div style="display:flex;justify-content:space-between;align-items:center;padding:5px 0;">
    <span style="color:{COLORS['text_secondary']};font-size:12px;">Retail</span>
    <span style="font-weight:700;color:{retail_color};font-size:13px;">{_fmt_k(retail_net)} [{retail_label}]</span>
  </div>
</div>
<div style="border-top:1px solid {COLORS['border']};padding-top:8px;">
  <div style="font-size:11px;font-weight:700;color:{COLORS['yellow']};margin-bottom:6px;">&#128161; RECOMMENDATION</div>
  {rec_html}
</div>
"""

    return _panel("COT Positioning", "&#127942;", content, COLORS["accent_fx"])


# ──────────────────────────────────────────────────────────────────────────────
# STRUCTURE ANALYSIS PANEL (Commodities)
# ──────────────────────────────────────────────────────────────────────────────
def _build_structure_panel_commodity(row: Dict, scraper_data: Optional[Dict]) -> str:
    """Build commodity structure analysis panel (term structure, COT, seasonality)."""
    sd = scraper_data or {}

    term_structure = sd.get("term_structure", sd.get("curve", "Backwardation"))
    cot_producer = sd.get("cot_producer", sd.get("producerNet", -156))
    seasonality_month = sd.get("seasonality_month", sd.get("seasonalMonth", "January"))
    seasonality_avg = sd.get("seasonality_avg", sd.get("seasonalAvg", 2.8))
    inventory = sd.get("inventory", sd.get("inventoryChange", "-2.1%"))

    # Color-code term structure
    ts_upper = str(term_structure).upper() if term_structure else ""
    if "BACKWARD" in ts_upper:
        ts_color, ts_signal = COLORS["green"], "BULLISH"
    elif "CONTON" in ts_upper or "FLAT" in ts_upper:
        ts_color, ts_signal = COLORS["yellow"], "NEUTRAL"
    else:
        ts_color, ts_signal = COLORS["red"], "BEARISH"

    # Producer COT color
    try:
        pc_val = float(cot_producer)
        if pc_val < -100:
            pc_label = "HEDGING"
        elif pc_val < 0:
            pc_label = "LIGHT HEDGE"
        elif pc_val > 100:
            pc_label = "ACCUMULATING"
        else:
            pc_label = "NEUTRAL"
        pc_color = COLORS["green"] if pc_val > 0 else COLORS["yellow"] if pc_val > -50 else COLORS["red"]
    except (TypeError, ValueError):
        pc_label, pc_color = "N/A", COLORS["text_muted"]

    # Recommendation
    rec_lines = []
    if "BACKWARD" in ts_upper:
        rec_lines.append("<b>Backwardation</b> = supply tightness, bullish structure")
    elif "CONTON" in ts_upper or "FLAT" in ts_upper:
        rec_lines.append("<b>Contango/Flat</b> = ample supply, neutral structure")

    if seasonality_avg and float(str(seasonality_avg).replace("%","")) > 0:
        rec_lines.append(f"Seasonal <b>+{seasonality_avg}%</b> avg in {seasonality_month} = tailwind")
    elif seasonality_avg:
        rec_lines.append(f"Seasonal <b>{seasonality_avg}%</b> avg in {seasonality_month} = headwind")

    if cot_producer and float(str(cot_producer).replace("K","")) > 0:
        rec_lines.append("Producer <b>accumulating</b> = smart money buying")
    elif cot_producer:
        rec_lines.append("Producer <b>hedging</b> = lock-in selling pressure")

    rec_html = "<br>".join(f'<div style="margin-bottom:4px;color:{COLORS["text_secondary"]};font-size:12px;line-height:1.5;">&#128161; {line}</div>' for line in rec_lines) if rec_lines else f'<div style="color:{COLORS["text_muted"]};font-size:12px;">No structure data available</div>'

    content = f"""
<div style="display:flex;flex-wrap:wrap;gap:12px;margin-bottom:10px;">
  <div style="flex:1;min-width:130px;">
    <div style="font-size:10px;color:{COLORS['text_muted']};margin-bottom:2px;">Term Structure</div>
    <div style="font-size:13px;font-weight:700;color:{ts_color};">{term_structure} [{ts_signal}]</div>
  </div>
  <div style="flex:1;min-width:130px;">
    <div style="font-size:10px;color:{COLORS['text_muted']};margin-bottom:2px;">COT Producer</div>
    <div style="font-size:13px;font-weight:700;color:{pc_color};">{cot_producer}K [{pc_label}]</div>
  </div>
  <div style="flex:1;min-width:130px;">
    <div style="font-size:10px;color:{COLORS['text_muted']};margin-bottom:2px;">Seasonality ({seasonality_month})</div>
    <div style="font-size:13px;font-weight:700;color:{COLORS['text']};">+{seasonality_avg}% avg</div>
  </div>
</div>
<div style="border-top:1px solid {COLORS['border']};padding-top:8px;">
  <div style="font-size:11px;font-weight:700;color:{COLORS['yellow']};margin-bottom:6px;">&#128161; RECOMMENDATION</div>
  {rec_html}
</div>
"""

    return _panel("Structure Analysis", "&#9881;", content, COLORS["accent_comm"])


# ──────────────────────────────────────────────────────────────────────────────
# ON-CHAIN + DERIVATIVES PANEL (Crypto)
# ──────────────────────────────────────────────────────────────────────────────
def _build_onchain_panel_crypto(row: Dict, scraper_data: Optional[Dict]) -> str:
    """Build crypto on-chain + derivatives panel (GEX, funding, TVL)."""
    sd = scraper_data or {}

    gex = sd.get("gex", sd.get("gamma_exposure", "NEGATIVE"))
    gex_val = sd.get("gex_value", sd.get("gexValue", -2.4))
    funding = sd.get("funding", sd.get("fundingRate", -0.008))
    tvl_change = sd.get("tvl_change", sd.get("tvlChange", 3.2))
    exchange_flow = sd.get("exchange_flow", sd.get("exchangeNetflow", -150))
    oi_change = sd.get("oi_change", sd.get("oiChange", 5.1))

    # GEX color
    if isinstance(gex, str) and gex.upper() == "NEGATIVE":
        gex_color = COLORS["red"]
        gex_label = "ACCELERATION RISK"
    else:
        gex_color = COLORS["green"]
        gex_label = "STABILITY"

    # Funding color
    try:
        f_val = float(funding)
        if f_val < -0.005:
            fund_color, fund_label = COLORS["green"], "SHORTS PAYING"
        elif f_val > 0.01:
            fund_color, fund_label = COLORS["red"], "LONGS PAYING (FOMO)"
        else:
            fund_color, fund_label = COLORS["yellow"], "BALANCED"
    except (TypeError, ValueError):
        fund_color, fund_label = COLORS["text_muted"], "N/A"

    # TVL color
    try:
        tvl_val = float(tvl_change)
        tvl_color = COLORS["green"] if tvl_val > 0 else COLORS["red"]
        tvl_label = "INFLOWS" if tvl_val > 0 else "OUTFLOWS"
    except (TypeError, ValueError):
        tvl_color, tvl_label = COLORS["text_muted"], "N/A"

    # Recommendation
    rec_lines = []
    if isinstance(gex, str) and gex.upper() == "NEGATIVE":
        rec_lines.append(f"Neg GEX <b>-${abs(gex_val)}B</b> + neg funding = <b>SHORT SQUEEZE</b> setup")
    else:
        rec_lines.append(f"Pos GEX = mean-reversion environment, avoid breakouts")

    rec_lines.append(f"<b>Buy spot</b> or calls if breakout above GEX flip zone")

    if exchange_flow and float(str(exchange_flow).replace("M","")) < 0:
        rec_lines.append(f"Exchange <b>outflows</b> = supply leaving, bullish")
    elif exchange_flow:
        rec_lines.append(f"Exchange <b>inflows</b> = potential selling pressure")

    rec_html = "<br>".join(f'<div style="margin-bottom:4px;color:{COLORS["text_secondary"]};font-size:12px;line-height:1.5;">&#128161; {line}</div>' for line in rec_lines) if rec_lines else f'<div style="color:{COLORS["text_muted"]};font-size:12px;">No on-chain data available</div>'

    content = f"""
<div style="display:flex;flex-wrap:wrap;gap:12px;margin-bottom:10px;">
  <div style="flex:1;min-width:130px;">
    <div style="font-size:10px;color:{COLORS['text_muted']};margin-bottom:2px;">GEX</div>
    <div style="font-size:13px;font-weight:700;color:{gex_color};">{gex} -${_ffm(gex_val)}B [{gex_label}]</div>
  </div>
  <div style="flex:1;min-width:130px;">
    <div style="font-size:10px;color:{COLORS['text_muted']};margin-bottom:2px;">Funding Rate</div>
    <div style="font-size:13px;font-weight:700;color:{fund_color};">{funding}% [{fund_label}]</div>
  </div>
  <div style="flex:1;min-width:130px;">
    <div style="font-size:10px;color:{COLORS['text_muted']};margin-bottom:2px;">TVL Change</div>
    <div style="font-size:13px;font-weight:700;color:{tvl_color};">{tvl_change}% [{tvl_label}]</div>
  </div>
</div>
<div style="border-top:1px solid {COLORS['border']};padding-top:8px;">
  <div style="font-size:11px;font-weight:700;color:{COLORS['yellow']};margin-bottom:6px;">&#128161; RECOMMENDATION</div>
  {rec_html}
</div>
"""

    return _panel("On-Chain + Derivatives", "&#128279;", content, COLORS["accent_crypto"])


# ──────────────────────────────────────────────────────────────────────────────
# BROKER FLOW PANEL (IHSG)
# ──────────────────────────────────────────────────────────────────────────────
def _build_flow_panel_ihsg(row: Dict, scraper_data: Optional[Dict]) -> str:
    """Build IHSG broker flow panel (foreign/local net flows)."""
    sd = scraper_data or {}

    foreign_net = sd.get("foreign_net", sd.get("foreignFlow", 412))
    local_net = sd.get("local_net", sd.get("localFlow", -198))
    foreign_own = sd.get("foreign_ownership", sd.get("foreignOwnership", 78.4))
    consecutive_days = sd.get("consecutive_days", sd.get("foreignStreak", 3))

    # Format Rupiah
    def _fmt_rp(v):
        if v is None:
            return "\u2014"
        try:
            f = float(v)
            if abs(f) >= 1000:
                return f"Rp{f/1000:.1f}T"
            return f"Rp{f:,.0f}B"
        except (TypeError, ValueError):
            return "\u2014"

    # Colors
    f_color = COLORS["green"] if (foreign_net or 0) > 0 else COLORS["red"]
    l_color = COLORS["red"] if (local_net or 0) < 0 else COLORS["green"]
    streak_color = COLORS["green"] if consecutive_days and consecutive_days >= 3 else COLORS["yellow"]

    # Direction label
    f_label = "ACCUMULATION" if (foreign_net or 0) > 0 else "DISTRIBUTION"
    l_label = "DISTRIBUTION" if (local_net or 0) < 0 else "ACCUMULATION"

    # Recommendation
    rec_lines = []
    if foreign_net and float(str(foreign_net).replace("B","")) > 0:
        rec_lines.append(f"Asing net buy <b>{consecutive_days} hari berturut</b> + harga di bawah max pain")
        rec_lines.append(f"&rarr; <b style=\"color:#10b981;\">AKUMULASI</b> zona entry")
    else:
        rec_lines.append(f"Asing net sell terdeteksi -- tunggu konfirmasi bullish")

    if local_net and float(str(local_net).replace("B","")) < 0:
        rec_lines.append(f"Lokal <b>{l_label.lower()}</b> = konfirmasi asing menyerap saham")

    rec_html = "<br>".join(f'<div style="margin-bottom:4px;color:{COLORS["text_secondary"]};font-size:12px;line-height:1.5;">&#128161; {line}</div>' for line in rec_lines) if rec_lines else f'<div style="color:{COLORS["text_muted"]};font-size:12px;">Tidak ada data broker flow</div>'

    content = f"""
<div style="display:flex;flex-wrap:wrap;gap:12px;margin-bottom:10px;">
  <div style="flex:1;min-width:130px;">
    <div style="font-size:10px;color:{COLORS['text_muted']};margin-bottom:2px;">Foreign Net ({consecutive_days} hari)</div>
    <div style="font-size:14px;font-weight:700;color:{f_color};">{_fmt_rp(foreign_net)} [{f_label}]</div>
  </div>
  <div style="flex:1;min-width:130px;">
    <div style="font-size:10px;color:{COLORS['text_muted']};margin-bottom:2px;">Local Net</div>
    <div style="font-size:14px;font-weight:700;color:{l_color};">{_fmt_rp(local_net)} [{l_label}]</div>
  </div>
  <div style="flex:1;min-width:130px;">
    <div style="font-size:10px;color:{COLORS['text_muted']};margin-bottom:2px;">Foreign Ownership</div>
    <div style="font-size:14px;font-weight:700;color:{COLORS['text']};">{foreign_own}%</div>
  </div>
</div>
<div style="border-top:1px solid {COLORS['border']};padding-top:8px;">
  <div style="font-size:11px;font-weight:700;color:{COLORS['yellow']};margin-bottom:6px;">&#128161; REKOMENDASI</div>
  {rec_html}
</div>
"""

    return _panel("Broker Flow", "&#128178;", content, COLORS["accent_ihsg"])


# ──────────────────────────────────────────────────────────────────────────────
# MAIN RENDER FUNCTION
# ──────────────────────────────────────────────────────────────────────────────
def render_market_card(
    row: Dict,
    market_type: str = "us_equity",
    scraper_data: Optional[Dict] = None,
) -> str:
    """Render a complete market-specific ticker card.

    Args:
        row: ticker data dict (from orchestrator pipeline)
        market_type: "us_equity", "forex", "commodity", "crypto", "ihsg"
        scraper_data: optional data from scraper engines

    Returns:
        HTML string for st.markdown(unsafe_allow_html=True)
    """
    # -- Extract core fields with safe fallbacks --
    ticker = row.get("ticker", "?")
    px = row.get("price", 0) or 0
    entry = row.get("entry", 0) or 0
    stop = row.get("stop", 0) or 0
    t1 = row.get("target_1", row.get("trade_top", 0) or 0) or 0
    t2 = row.get("target_2", row.get("trend_top", 0) or 0) or 0
    t3 = row.get("target_3", row.get("tail_top", 0) or 0) or 0
    direction = str(row.get("direction", "LONG")).upper()
    grade = str(row.get("grade", "C")).upper()
    confidence = row.get("confidence", 0) or 0
    rr = row.get("rr", row.get("risk_reward", 0)) or 0

    # -- Build ticker header (with price + P&L context) --
    sig_c = _signal_color(direction)
    px_change = row.get("change_pct", 0) or 0
    change_color = COLORS["green"] if px_change >= 0 else COLORS["red"]
    change_sign = "+" if px_change >= 0 else ""
    market_label = {
        "us_equity": "US Equity",
        "forex": "Forex",
        "commodity": "Commodity",
        "crypto": "Crypto",
        "ihsg": "IHSG",
    }.get(market_type, market_type)

    ticker_header = f"""
<div style="padding:14px 16px 6px 16px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:6px;">
  <div style="display:flex;align-items:baseline;gap:10px;">
    <span style="font-size:22px;font-weight:800;color:{COLORS['text']};">{ticker}</span>
    <span style="font-size:11px;color:{COLORS['text_muted']};background:{COLORS['section']};padding:2px 7px;border-radius:4px;border:1px solid {COLORS['border']};">
      {market_label}
    </span>
  </div>
  <div style="text-align:right;">
    <div style="font-size:20px;font-weight:800;color:{COLORS['text']};">{_ffm(px, market_type)}</div>
    <div style="font-size:12px;color:{change_color};font-weight:600;">{change_sign}{px_change:.2f}%</div>
  </div>
</div>
"""

    # -- Build all sections --
    signal_badge = _build_signal_badge(direction, grade, confidence, rr)
    entry_bar = _build_entry_zone_bar(entry, stop, px, t1, t2, t3, market_type)
    target_grid = _build_target_grid(t1, t2, t3, entry, stop, market_type)
    thesis = _build_thesis_panel(row, market_type)
    checklist = _build_checklist(row, px, entry, stop, t1, t2)

    # -- Market-specific panel --
    market_panel = ""
    if market_type == "us_equity":
        market_panel = _build_options_panel_us(row, scraper_data)
    elif market_type == "forex":
        market_panel = _build_cot_panel_forex(row, scraper_data)
    elif market_type == "commodity":
        market_panel = _build_structure_panel_commodity(row, scraper_data)
    elif market_type == "crypto":
        market_panel = _build_onchain_panel_crypto(row, scraper_data)
    elif market_type == "ihsg":
        market_panel = _build_flow_panel_ihsg(row, scraper_data)

    # -- Combine into final card --
    accent = _accent(market_type)

    html = f"""<div class="mr-card" style="background:{COLORS['card']};border:1px solid {COLORS['border']};border-radius:14px;margin:0 0 16px 0;overflow:hidden;font-size:0.95rem;">
  <div style="border-top:3px solid {accent};padding:0;">
    <!-- HEADER: ticker + price -->
    {ticker_header}
    <!-- SIGNAL BADGE -->
    {signal_badge}
    <!-- ENTRY ZONE BAR -->
    {entry_bar}
    <!-- TARGET GRID -->
    {target_grid}
    <!-- MARKET-SPECIFIC PANEL -->
    {market_panel}
    <!-- THESIS PANEL -->
    {thesis}
    <!-- EXECUTION CHECKLIST -->
    {checklist}
  </div>
</div>
<style>
@media (max-width: 768px) {{
    .mr-card {{ font-size: 0.8rem !important; }}
    .mr-target-grid {{ display: block !important; }}
    .mr-target-col {{ width: 100% !important; margin-bottom: 8px; }}
    .mr-entry-bar {{ height: 8px !important; }}
    .mr-thesis-item {{ font-size: 0.75rem !important; }}
}}
</style>"""

    return html
