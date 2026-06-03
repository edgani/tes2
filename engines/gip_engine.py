"""engines/gip_engine.py v9 — Hedgeye GIP Model

CRITICAL FIX v9: Monthly inflation anchored 70% to structural CPI level.
v8 was 50/50 — still too sensitive to 1M oil volatility.
v7 was 90/10 — why monthly stayed Q1 despite hot CPI.

Hedgeye May 2026: Structural Q3 · Monthly Q2 (Reflation inside Stagflation)
"""
from __future__ import annotations
import math, os, logging
from dataclasses import dataclass, field
from typing import Dict, Optional
import numpy as np
import pandas as pd
from config.settings import (
    GROWTH_LEVEL_WEIGHTS, GROWTH_MOM_WEIGHTS,
    INFLATION_LEVEL_WEIGHTS, INFLATION_MOM_WEIGHTS,
    STRUCTURAL_WEIGHTS, MONTHLY_WEIGHTS,
    POLICY_WEIGHT_STRUCTURAL, POLICY_WEIGHT_MONTHLY,
    ISM_NEUTRAL, QUAD_ASSET_PERFORMANCE,
)

logger = logging.getLogger(__name__)

# ─── S2-b: MONTHLY-QUAD ANCHOR WEIGHTS ──────────────────────────────────────
# ⚠️ OVERFIT RISK: these were hand-tuned to reproduce the May-2026 Hedgeye call
# ("Structural Q3 / Monthly Q2"). They are NOT validated across other historical
# quad transitions. Treat as a regime-specific prior; OOS-test before trusting
# out-of-regime. Exposed as constants so they can be swept / re-fit later.
M_INFL_STRUCT_ANCHOR = 0.70   # monthly inflation = 70% sticky structural + 30% 1M price
M_GROWTH_PRICE_WEIGHT = 0.80  # monthly growth = 80% volatile price + 20% structural
Q3_HOT_INFL_THRESH = 0.15     # struct Q3 + i_level above this → penalize monthly Q1
Q3_MONTHLY_MOD = {"Q1": -0.35, "Q2": +0.20, "Q3": +0.10}

def _fv(*series_list):
    for s in series_list:
        if s is not None:
            if isinstance(s, pd.Series):
                if not s.empty: return s
            else:
                return s
    return None

def _safe(s) -> pd.Series:
    if s is None: return pd.Series(dtype=float)
    return pd.to_numeric(s, errors="coerce").dropna()

def _last(s) -> float:
    s = _safe(s)
    return float(s.iloc[-1]) if not s.empty else float("nan")

def _yoy(s) -> float:
    s = _safe(s)
    if len(s) < 13: return float("nan")
    base = float(s.iloc[-13])
    if not math.isfinite(base) or abs(base) < 1e-10: return float("nan")
    return float(s.iloc[-1] / base - 1)

def _roc(s, n=12, offset=3) -> float:
    s = _safe(s)
    if len(s) < n + offset + 2: return float("nan")
    try:
        r_now = float(s.iloc[-1] / s.iloc[-n-1] - 1)
        r_prev = float(s.iloc[-offset-1]/ s.iloc[-n-offset-1] - 1)
        if not (math.isfinite(r_now) and math.isfinite(r_prev)): return float("nan")
        return r_now - r_prev
    except: return float("nan")

def _delta(s, n) -> float:
    s = _safe(s)
    if len(s) < n + 1: return float("nan")
    return float(s.iloc[-1] - s.iloc[-n-1])

def _ret(s, n) -> float:
    s = _safe(s)
    if len(s) < n + 1: return float("nan")
    base = float(s.iloc[-n-1])
    if not math.isfinite(base) or abs(base) < 1e-10: return float("nan")
    r = float(s.iloc[-1] / base - 1)
    return r if math.isfinite(r) else float("nan")

def _tanh_scale(x, scale) -> float:
    if not math.isfinite(x): return float("nan")
    return float(np.tanh(x / scale))

def _wmean(inputs: Dict[str, float], weights: Dict[str, float]) -> float:
    total_w = total = 0.0
    for k, w in weights.items():
        v = inputs.get(k, float("nan"))
        if math.isfinite(v): total += w * v; total_w += w
    return total / total_w if total_w > 0.01 else 0.0

def _coverage(inputs: Dict[str, float]) -> float:
    valid = sum(1 for v in inputs.values() if math.isfinite(v))
    return valid / max(len(inputs), 1)

def _softmax(scores: Dict[str, float]) -> Dict[str, float]:
    keys = list(scores.keys())
    vals = np.clip([scores[k] for k in keys], -10, 10)
    e = np.exp(vals - np.max(vals)); e /= e.sum()
    return {k: float(v) for k, v in zip(keys, e)}

def _nan(v) -> float:
    return float(np.nan_to_num(v, nan=0.0))

def _first_finite(*vals, default=0.0):
    for v in vals:
        if v is not None and math.isfinite(float(v)): return float(v)
    return float(default)

def _acc_spread(r6, r12):
    if not all(math.isfinite(x) for x in [r6 or float("nan"), r12 or float("nan")]): return 0.0
    return float(r6 * 2.0 - r12)

def clamp01(x) -> float:
    if not math.isfinite(x): return 0.5
    return float(np.clip(x, 0.0, 1.0))

def _price_proxy(prices: Dict) -> Dict[str, float]:
    def r(t, n):
        s = _safe(prices.get(t))
        if len(s) < n + 1: return float("nan")
        b = float(s.iloc[-n-1])
        return float(s.iloc[-1]/b - 1) if abs(b) > 1e-9 else float("nan")

    spy6 = _first_finite(r("SPY",126)); spy12 = _first_finite(r("SPY",252))
    xli6 = _first_finite(r("XLI",126)); xli12 = _first_finite(r("XLI",252))
    xly6 = _first_finite(r("XLY",126)); xly12 = _first_finite(r("XLY",252))
    iwm6 = _first_finite(r("IWM",126)); iwm12 = _first_finite(r("IWM",252))
    xhb6 = _first_finite(r("XHB",126)); xhb12 = _first_finite(r("XHB",252))
    oil6 = _first_finite(r("CL=F",126),r("USO",126))
    oil12 = _first_finite(r("CL=F",252),r("USO",252))
    gld6 = _first_finite(r("GLD",126)); gld12 = _first_finite(r("GLD",252))
    uup3 = _first_finite(r("UUP",63))

    spy_acc = _acc_spread(spy6,spy12); xli_acc = _acc_spread(xli6,xli12)
    xly_acc = _acc_spread(xly6,xly12); iwm_acc = _acc_spread(iwm6,iwm12)
    oil_acc = _acc_spread(oil6,oil12); gld_acc = _acc_spread(gld6,gld12)

    xli1 = _first_finite(r("XLI",21)); spy1 = _first_finite(r("SPY",21))
    oil1 = _first_finite(r("CL=F",21),r("USO",21))
    gld1 = _first_finite(r("GLD",21)); uup1 = _first_finite(r("UUP",21))
    tlt1 = _first_finite(r("TLT",21))

    monthly_g_price = float(np.tanh(0.40*xli1/0.05 + 0.60*spy1/0.05))
    monthly_i_price = float(np.tanh(0.50*oil1/0.06 + 0.30*gld1/0.05 - 0.20*uup1/0.04))

    hyg6 = _first_finite(r("HYG",126),r("LQD",126))
    tlt6 = _first_finite(r("TLT",126))
    xlp6 = _first_finite(r("XLP",126))
    credit_stress_6 = _nan(spy6 - hyg6)
    quality_bid_6 = _nan(tlt6 - spy6*0.5)
    consumer_stress_6 = _nan(xlp6 - xly6)
    breadth_stress_6 = _nan(spy6 - iwm6)

    q3_conf_raw = (
        max(0.0, credit_stress_6) * 2.0 +
        max(0.0, quality_bid_6) * 1.5 +
        max(0.0, consumer_stress_6) * 2.0 +
        max(0.0, breadth_stress_6) * 1.0
    )
    q3_modifier = float(np.tanh(q3_conf_raw / 0.12) * 0.40)

    return {
        "indpro_yoy": _nan(0.55*xli12 + 0.45*spy12),
        "retail_yoy": _nan(0.60*xly12 + 0.40*spy12),
        "payrolls_yoy": _nan(0.50*iwm12 + 0.50*spy12),
        "housing_yoy": _nan(0.70*xhb12 + 0.30*iwm12),
        "ism_norm": _nan(10.0*xli_acc),
        "unrate_inv": _nan(-0.10*iwm12),
        "claims_inv": _nan(-5.0*_first_finite(r("IWM",21))),
        "cpi_yoy": _nan(0.025 + 0.35*oil12 + 0.05*gld12),
        "core_cpi_yoy": _nan(0.023 + 0.15*oil12 - 0.05*uup3),
        "breakeven_5y": _nan(0.6*oil12 + 0.2*gld12),
        "ppi_yoy": _nan(0.03 + 0.55*oil12),
        "oil_3m": _nan(oil6*2.0),
        "gold_3m": _nan(gld6*2.0),
        "indpro_roc": _nan(0.60*xli_acc + 0.40*spy_acc),
        "retail_roc": _nan(0.60*xly_acc + 0.40*spy_acc),
        "payrolls_roc": _nan(0.50*iwm_acc + 0.50*spy_acc),
        "ism_delta": _nan(xli1*100),
        "unrate_delta": _nan(-_first_finite(r("IWM",21))),
        "claims_delta": 0.0,
        "cpi_roc": _nan(oil_acc*0.4 + gld_acc*0.1),
        "core_cpi_roc": _nan(oil_acc*0.2 - uup1*0.1),
        "breakeven_delta": _nan(oil_acc*0.3 + gld_acc*0.1),
        "oil_1m": oil1,
        "dxy_inv_1m": _nan(-uup1),
        "q3_modifier": q3_modifier,
        "q3_credit_stress": _nan(credit_stress_6),
        "q3_consumer_stress": _nan(consumer_stress_6),
        "policy_score": 0.0,
        "liquidity_score": 0.0,
        "monthly_g_price": monthly_g_price,
        "monthly_i_price": monthly_i_price,
    }

def _extract_fred_features(fred: Dict) -> Dict[str, float]:
    f: Dict[str, float] = {}
    f["indpro_yoy"] = _yoy(fred.get("INDPRO"))
    f["retail_yoy"] = _yoy(fred.get("RSAFS"))
    f["payrolls_yoy"] = _yoy(fred.get("PAYEMS"))
    ism_s = _fv(fred.get("ISMNO"), fred.get("MANEMP"))
    ism = _last(ism_s)
    f["ism_norm"] = (ism - ISM_NEUTRAL)/ISM_NEUTRAL if math.isfinite(ism) else float("nan")
    f["housing_yoy"] = _yoy(fred.get("HOUST"))
    unrate_3m = _delta(fred.get("UNRATE"), 3)
    claims_d = _delta(fred.get("ICSA"), 13)
    f["unrate_inv"] = -float(np.tanh(unrate_3m/0.2)) if math.isfinite(unrate_3m) else float("nan")
    f["claims_inv"] = -float(np.tanh(claims_d/50000)) if math.isfinite(claims_d) else float("nan")
    f["indpro_roc"] = _roc(fred.get("INDPRO"),12,3)
    f["retail_roc"] = _roc(fred.get("RSAFS"),12,3)
    f["payrolls_roc"] = _roc(fred.get("PAYEMS"),12,3)
    ism_d = _delta(ism_s, 3) if ism_s is not None else float("nan")
    f["ism_delta"] = ism_d/ISM_NEUTRAL if math.isfinite(ism_d) else float("nan")
    f["unrate_delta"] = -unrate_3m/0.2 if math.isfinite(unrate_3m) else float("nan")
    f["claims_delta"] = -claims_d/50000 if math.isfinite(claims_d) else float("nan")
    f["cpi_yoy"] = _yoy(fred.get("CPIAUCSL"))
    f["core_cpi_yoy"] = _yoy(fred.get("CPILFESL"))
    f["ppi_yoy"] = _yoy(fred.get("PPIACO"))
    be5 = _last(fred.get("T5YIE"))
    f["breakeven_5y"] = (be5 - 2.2)/2.0 if math.isfinite(be5) else float("nan")
    f["cpi_roc"] = _roc(fred.get("CPIAUCSL"),12,3)
    f["core_cpi_roc"] = _roc(fred.get("CPILFESL"),12,3)
    be5_d = _delta(fred.get("T5YIE"), 1)
    f["breakeven_delta"] = be5_d/0.3 if math.isfinite(be5_d) else float("nan")
    ff_s = _fv(fred.get("FEDFUNDS"), fred.get("DFF"))
    ff_delta = _delta(ff_s, 3)
    f["policy_score"] = float(np.tanh(-_nan(ff_delta)/0.5))
    m2_roc = _roc(fred.get("M2SL"),12,3)
    f["liquidity_score"] = float(np.tanh(_nan(m2_roc)/0.05))
    return f

def _score_quad(g_level, g_mom, i_level, i_mom, policy, sw, pw, modifiers=None):
    modifiers = modifiers or {}
    g = sw["growth_level"]*g_level + sw["growth_momentum"]*g_mom
    i = sw["inflation_level"]*i_level + sw["inflation_momentum"]*i_mom
    p = pw * policy
    raw = {
        "Q1": +g - i + p*0.60,
        "Q2": +g + i - p*0.30,
        "Q3": -g + i - p*0.80,
        "Q4": -g - i + p*1.00,
    }
    for q, delta in modifiers.items():
        if q in raw: raw[q] += delta
    probs = _softmax(raw)
    top = max(probs, key=probs.get)
    margin = probs[top] - sorted(probs.values(), reverse=True)[1]
    conf = float(np.clip(probs[top]*(0.65+0.35*margin/0.5), 0.0, 1.0))
    return probs, top, conf

@dataclass
class GIPResult:
    structural_quad: str; structural_probs: Dict[str,float]; structural_conf: float
    structural_g: float; structural_i: float
    monthly_quad: str; monthly_probs: Dict[str,float]; monthly_conf: float
    monthly_g: float; monthly_i: float
    divergence: str; operating_regime: str
    policy_score: float; data_coverage: float; proxy_share: float
    features: Dict[str,float] = field(default_factory=dict)

    @property
    def flip_hazard(self) -> float:
        margin = self.structural_probs.get(self.structural_quad, 0.5) - \
                 sorted(self.structural_probs.values(), reverse=True)[1]
        return float(np.clip(0.5 - 0.8*margin + 0.2*(1.0-self.data_coverage), 0.0, 1.0))

class GIPEngine:
    def run(self, fred: Dict, prices: Dict) -> GIPResult:
        f_fred = _extract_fred_features(fred)
        f_proxy = _price_proxy(prices)

        fred_keys = ["indpro_yoy","retail_yoy","payrolls_yoy","cpi_yoy","core_cpi_yoy",
                     "ism_norm","housing_yoy","unrate_inv","claims_inv"]
        n_fred = sum(1 for k in fred_keys if math.isfinite(f_fred.get(k, float("nan"))))
        proxy_share = 1.0 - n_fred / len(fred_keys)
        coverage = 1.0 - proxy_share

        def merge(key):
            v = f_fred.get(key, float("nan"))
            return v if math.isfinite(v) else f_proxy.get(key, float("nan"))

        # ── STRUCTURAL ─────────────────────────────────────────────────────────
        g_lvl = {
            "indpro_yoy": _tanh_scale(merge("indpro_yoy") - 0.02, 0.05),
            "retail_yoy": _tanh_scale(merge("retail_yoy") - 0.03, 0.06),
            "payrolls_yoy": _tanh_scale(merge("payrolls_yoy") - 0.015, 0.03),
            "housing_yoy": _tanh_scale(merge("housing_yoy"), 0.10),
            "ism_norm": _tanh_scale(merge("ism_norm"), 0.10),
            "unrate_inv": merge("unrate_inv"),
            "claims_inv": merge("claims_inv"),
        }
        g_mom_d = {
            "indpro_roc": _tanh_scale(merge("indpro_roc"), 0.025),
            "retail_roc": _tanh_scale(merge("retail_roc"), 0.030),
            "payrolls_roc": _tanh_scale(merge("payrolls_roc"), 0.015),
            "ism_delta": _tanh_scale(merge("ism_delta"), 0.05),
            "unrate_delta": _tanh_scale(merge("unrate_delta"), 1.0),
            "claims_delta": _tanh_scale(merge("claims_delta"), 1.0),
        }
        i_lvl = {
            "cpi_yoy": _tanh_scale(merge("cpi_yoy") - 0.025, 0.020),
            "core_cpi_yoy": _tanh_scale(merge("core_cpi_yoy") - 0.025, 0.015),
            "breakeven_5y": merge("breakeven_5y"),
            "ppi_yoy": _tanh_scale(merge("ppi_yoy") - 0.025, 0.030),
            "oil_3m": _tanh_scale(merge("oil_3m"), 0.25),
            "gold_3m": _tanh_scale(merge("gold_3m"), 0.18),
        }
        i_mom_d = {
            "cpi_roc": _tanh_scale(merge("cpi_roc"), 0.012),
            "core_cpi_roc": _tanh_scale(merge("core_cpi_roc"), 0.010),
            "breakeven_delta": _tanh_scale(merge("breakeven_delta"), 1.0),
            "oil_1m": _tanh_scale(merge("oil_1m"), 0.06),
            "dxy_inv_1m": _tanh_scale(merge("dxy_inv_1m"), 0.06),
        }

        g_level = _wmean(g_lvl, GROWTH_LEVEL_WEIGHTS)
        g_mom_ = _wmean(g_mom_d, GROWTH_MOM_WEIGHTS)
        i_level = _wmean(i_lvl, INFLATION_LEVEL_WEIGHTS)
        i_mom_ = _wmean(i_mom_d, INFLATION_MOM_WEIGHTS)
        policy = _nan(merge("policy_score"))
        cov_frac= _coverage({**g_lvl, **g_mom_d, **i_lvl, **i_mom_d})

        q3_mod = float(_nan(merge("q3_modifier")))
        struct_modifiers = {}
        if q3_mod > 0.05:
            scale = 0.8 + 0.2 * proxy_share
            struct_modifiers = {"Q3": q3_mod * scale, "Q2": -q3_mod * scale * 0.4}

        struct_probs, struct_quad, struct_conf = _score_quad(
            g_level, g_mom_, i_level, i_mom_, policy,
            STRUCTURAL_WEIGHTS, POLICY_WEIGHT_STRUCTURAL,
            modifiers=struct_modifiers
        )

        # ── MONTHLY — v9 FIX: 70% structural anchor for inflation ───────────────
        # v7 hardcoded 90% price → Q1 when oil down despite hot CPI
        # v8 tried 50/50 → still not enough
        # v9: 70% structural level (CPI sticky) + 30% 1M price signal
        monthly_g_price = _nan(f_proxy.get("monthly_g_price", 0.0))
        monthly_i_price = _nan(f_proxy.get("monthly_i_price", 0.0))

        # Growth: mostly price (volatile, mean-reverting)
        m_g_level = (1.0 - M_GROWTH_PRICE_WEIGHT) * g_level + M_GROWTH_PRICE_WEIGHT * monthly_g_price
        m_g_mom = monthly_g_price

        # INFLATION: mostly sticky structural level + a transient 1M price tilt
        m_i_level = M_INFL_STRUCT_ANCHOR * i_level + (1.0 - M_INFL_STRUCT_ANCHOR) * monthly_i_price
        m_i_mom = monthly_i_price

        # Structural bias: when structural is Q3 (hot inflation), monthly Q1 is
        # economically inconsistent — CPI doesn't vanish in 1 month. Penalize Q1.
        month_modifiers = {}
        if struct_quad == "Q3" and i_level > Q3_HOT_INFL_THRESH:
            month_modifiers = dict(Q3_MONTHLY_MOD)

        month_probs, month_quad, month_conf = _score_quad(
            m_g_level, m_g_mom, m_i_level, m_i_mom, policy,
            MONTHLY_WEIGHTS, POLICY_WEIGHT_MONTHLY,
            modifiers=month_modifiers
        )

        # ── FIX S1-d: hard-gate proxy reliance ──────────────────────────────────
        # When most macro inputs are price-proxied (FRED unavailable), the quad is
        # COINCIDENT with markets, not leading — that defeats the whole edge. Haircut
        # confidence hard and surface a warning the UI must show.
        proxy_warning = None
        if proxy_share > 0.5:
            penalty = max(0.25, 1.0 - proxy_share)
            proxy_warning = (f"⚠️ {proxy_share*100:.0f}% of macro inputs PRICE-PROXIED "
                             f"(FRED missing) — quad is COINCIDENT, not leading. Low conviction.")
        elif proxy_share > 0.25:
            penalty = 1.0 - 0.5 * (proxy_share - 0.25)
            proxy_warning = f"{proxy_share*100:.0f}% proxy inputs — partial price-coincidence."
        else:
            penalty = 1.0
        struct_conf *= penalty
        month_conf *= penalty

        if struct_quad == month_quad:
            div = "aligned"; regime = f"Aligned {struct_quad}"
        else:
            div = "divergent"; regime = f"Monthly {month_quad} inside Structural {struct_quad}"

        _tlt = prices.get("TLT"); _ief = prices.get("IEF")
        tlt_1m = float(pd.to_numeric(_tlt, errors="coerce").pct_change(21).dropna().iloc[-1]) \
            if _tlt is not None and len(_tlt) > 22 else 0.0
        ief_1m = float(pd.to_numeric(_ief, errors="coerce").pct_change(21).dropna().iloc[-1]) \
            if _ief is not None and len(_ief) > 22 else 0.0
        bond_pivot_signal = clamp01(0.5 + tlt_1m*8 + ief_1m*4)

        cpi_yoy = _nan(merge("cpi_yoy"))
        core_yoy = _nan(merge("core_cpi_yoy"))
        hgap = cpi_yoy - core_yoy
        shock = max(0.0, _tanh_scale(hgap, 0.004))

        features = dict(
            growth_level=g_level, growth_momentum=g_mom_,
            inflation_level=i_level, inflation_momentum=i_mom_,
            policy_score=policy, data_coverage=coverage, proxy_share=proxy_share,
            proxy_warning=proxy_warning,
            q3_modifier=q3_mod,
            q3_credit_stress=_nan(merge("q3_credit_stress")),
            q3_consumer_stress=_nan(merge("q3_consumer_stress")),
            monthly_g_price=monthly_g_price, monthly_i_price=monthly_i_price,
            monthly_g_level=m_g_level, monthly_g_mom=m_g_mom,
            monthly_i_level=m_i_level, monthly_i_mom=m_i_mom,
            headline_gap=hgap, inflation_shock=shock,
            leading_indicator_composite=_nan(0.40*g_mom_+0.30*(-i_mom_)+0.30*policy),
            bond_pivot_signal=bond_pivot_signal,
            tlt_1m_trend=tlt_1m, ief_1m_trend=ief_1m,
            **{f"raw_{k}": v for k, v in f_fred.items() if math.isfinite(v)},
        )

        return GIPResult(
            structural_quad=struct_quad, structural_probs=struct_probs,
            structural_conf=struct_conf, structural_g=g_level+g_mom_,
            structural_i=i_level+i_mom_,
            monthly_quad=month_quad, monthly_probs=month_probs,
            monthly_conf=month_conf, monthly_g=m_g_level+m_g_mom,
            monthly_i=m_i_level+m_i_mom,
            divergence=div, operating_regime=regime,
            policy_score=policy, data_coverage=coverage,
            proxy_share=proxy_share, features=features,
        )

def get_playbook(sq: str, mq: str) -> dict:
    s = QUAD_ASSET_PERFORMANCE.get(sq, {})
    m = QUAD_ASSET_PERFORMANCE.get(mq, {})
    return dict(
        structural=sq, monthly=mq,
        best_assets=list(dict.fromkeys(s.get("best",[]) + m.get("best",[])[:2]))[:6],
        worst_assets=s.get("worst",[]),
        sectors_ow=s.get("sectors_overweight",[]),
        sectors_uw=s.get("sectors_underweight",[]),
        style=s.get("style",""), fx=s.get("fx",""), bonds=s.get("bonds",""),
        monthly_adds=m.get("best",[])[:3], note=s.get("note",""),
    )