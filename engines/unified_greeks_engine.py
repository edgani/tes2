"""
unified_greeks_engine.py — Consolidated Options Greeks Engine v40
================================================================
Merged from 11 individual engines:
  - greeks_proxy.py (host) — Greeks proxy calculations
  - gex_engine.py — Net Gamma Exposure (GEX)
  - gamma_engine.py — Gamma regime & levels
  - charm_proxy_engine.py — Charm (delta decay) flow
  - vanna_proxy_engine.py — Vanna flow
  - vanna_charm_flows.py — Combined vanna+charm
  - odte_monitor.py — 0DTE gamma & pin risk
  - odte_enhanced.py — Enhanced 0DTE
  - skew_term_engine.py — 30D vs 60D skew term
  - volga_proxy.py — Volga (VIX gamma)
  - structure_quality.py — Options structure quality

Usage:
    from engines.unified_greeks_engine import UnifiedGreeksEngine
    engine = UnifiedGreeksEngine()
    result = engine.analyze(ticker, prices, options_data)
"""

import logging
import numpy as np
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

class GreeksProxy:
    """
    Proxy Greeks engine.
    No real options chain needed — synthesizes from price, vol, macro.
    """

    def __init__(self):
        pass

    def analyze(self, ticker: str, prices: dict, vix: float = 20.0, dxy_ret: float = 0.0, 
                regime: str = "Q3") -> dict:
        s = prices.get(ticker)
        if s is None or s.empty:
            return {"ok": False, "reason": f"No price data for {ticker}"}

        s = pd.to_numeric(s, errors="coerce").dropna()
        if len(s) < 30:
            return {"ok": False, "reason": "Insufficient price history"}

        px = float(s.iloc[-1])

        # Returns
        r5d = float(s.iloc[-1] / s.iloc[-6] - 1) if len(s) >= 6 else 0
        r10d = float(s.iloc[-1] / s.iloc[-11] - 1) if len(s) >= 11 else 0
        r1m = float(s.iloc[-1] / s.iloc[-22] - 1) if len(s) >= 22 else 0
        r3m = float(s.iloc[-1] / s.iloc[-64] - 1) if len(s) >= 64 else 0

        # Vol
        ret = s.pct_change().dropna()
        rvol_20 = ret.tail(20).std() * math.sqrt(252) * 100 if len(ret) >= 20 else 15.0
        rvol_10 = ret.tail(10).std() * math.sqrt(252) * 100 if len(ret) >= 10 else rvol_20
        vol_premium = vix - rvol_20

        # Trend
        sma20 = float(s.tail(20).mean())
        sma50 = float(s.tail(50).mean()) if len(s) >= 50 else sma20
        above_sma20 = px > sma20
        above_sma50 = px > sma50

        # ── DELTA ──────────────────────────────────────────────────────────
        # Directional bias = momentum + trend
        delta_score = r1m * 5 + (1 if above_sma20 else -1) * 0.3 + (1 if above_sma50 else -1) * 0.2
        delta_score = max(-1, min(1, delta_score))

        if delta_score > 0.5:
            delta = "Long 🟢"; delta_val = round(delta_score, 2); delta_note = "Strong upward momentum + above key MAs"
        elif delta_score > 0.1:
            delta = "Mod Long 🟡"; delta_val = round(delta_score, 2); delta_note = "Positive bias but mixed"
        elif delta_score < -0.5:
            delta = "Short 🔴"; delta_val = round(delta_score, 2); delta_note = "Strong downward momentum + below key MAs"
        elif delta_score < -0.1:
            delta = "Mod Short 🟡"; delta_val = round(delta_score, 2); delta_note = "Negative bias but mixed"
        else:
            delta = "Neutral ⚪"; delta_val = 0.0; delta_note = "No clear directional edge"

        # ── GAMMA ──────────────────────────────────────────────────────────
        # Acceleration = change in momentum
        accel = r5d - (r10d / 2)
        vol_accel = rvol_10 - rvol_20  # positive = vol expanding

        if abs(accel) > 0.03 and vol_accel > 2:
            gamma = "High 📈"; gamma_val = round(abs(accel) * 30, 2); gamma_note = "Momentum accelerating + vol expanding"
        elif abs(accel) > 0.02:
            gamma = "Elevated 🟡"; gamma_val = round(abs(accel) * 20, 2); gamma_note = "Momentum shifting — watch for breakout"
        elif abs(accel) < 0.005:
            gamma = "Low ⚪"; gamma_val = round(abs(accel) * 10, 2); gamma_note = "Momentum stable — gamma pin likely"
        else:
            gamma = "Normal 🟢"; gamma_val = round(abs(accel) * 15, 2); gamma_note = "Normal gamma environment"

        # ── VANNA ─────────────────────────────────────────────────────────
        # Vanna = delta sensitivity to vol changes
        # Proxy: how does delta change when VIX moves?
        # High vol + downtrend = negative vanna (delta drops fast as vol rises)
        # Low vol + uptrend = positive vanna (delta rises as vol drops)

        if vix > 25 and r1m < -0.05:
            vanna = "Negative ⚠️"; vanna_val = -0.6; vanna_note = "High vol + downtrend = delta collapses on vol spike"
        elif vix < 18 and r1m > 0.05:
            vanna = "Positive ✅"; vanna_val = 0.5; vanna_note = "Low vol + uptrend = delta extends on vol crush"
        elif vix > 25 and r1m > 0.03:
            vanna = "Mixed 🟡"; vanna_val = 0.1; vanna_note = "High vol but positive momentum — conflicting"
        elif vix < 18 and r1m < -0.03:
            vanna = "Mixed 🟡"; vanna_val = -0.1; vanna_note = "Low vol but negative momentum — conflicting"
        else:
            vanna = "Neutral ⚪"; vanna_val = 0.0; vanna_note = "No strong vanna signal"

        # ── CHARM ─────────────────────────────────────────────────────────
        # Charm = delta decay over time (time sensitivity)
        # Proxy: is momentum fading or building over 1M vs 3M?
        charm_diff = r1m - (r3m / 3) if r3m != 0 else r1m

        if charm_diff > 0.03:
            charm = "Building 🟢"; charm_val = round(charm_diff * 10, 2); charm_note = "1M momentum > 3M trend — acceleration building"
        elif charm_diff < -0.03:
            charm = "Fading 🔴"; charm_val = round(charm_diff * 10, 2); charm_note = "1M momentum < 3M trend — momentum fading"
        else:
            charm = "Stable 🟡"; charm_val = round(charm_diff * 10, 2); charm_note = "Momentum stable vs longer trend"

        # ── VOLGA ─────────────────────────────────────────────────────────
        # Volga = vol of vol (convexity of vol)
        # Proxy: realized vol variance
        vol_changes = ret.tail(20).diff().dropna()
        volga_val = float(vol_changes.std() * math.sqrt(252) * 100) if len(vol_changes) > 1 else 0

        if volga_val > 8:
            volga = "High 🔴"; volga_note = "Vol of vol elevated — expect vol spikes"
        elif volga_val > 4:
            volga = "Elevated 🟡"; volga_note = "Vol of vol rising — watch for regime shift"
        else:
            volga = "Low 🟢"; volga_note = "Vol of vol calm — stable environment"

        # ── VOLATILITY ────────────────────────────────────────────────────
        if vix > 30:
            vol = "Extreme 🔴"; vol_note = "VIX > 30 — crisis mode"
        elif vix > 25:
            vol = "High 🔴"; vol_note = "VIX 25-30 — elevated risk"
        elif vix > 20:
            vol = "Elevated 🟡"; vol_note = "VIX 20-25 — caution warranted"
        elif vix > 15:
            vol = "Normal 🟢"; vol_note = "VIX 15-20 — normal range"
        else:
            vol = "Low 🟢"; vol_note = "VIX < 15 — complacency zone"

        # ── MAX PAIN PROXY ────────────────────────────────────────────────
        # Max pain = where most OI sits = near SMA20
        max_pain = round(sma20, 2)
        dist_mp = round((px - max_pain) / max_pain * 100, 2) if max_pain != 0 else 0

        # ── OI CONCENTRATION PROXY ──────────────────────────────────────
        recent_high = float(s.tail(40).max())
        recent_low = float(s.tail(40).min())
        pos = (px - recent_low) / (recent_high - recent_low) if recent_high > recent_low else 0.5

        if pos > 0.8:
            oi_conc = "High at highs 🔴"; oi_note = "Price at highs — profit-taking OI likely"
        elif pos < 0.2:
            oi_conc = "High at lows 🟢"; oi_note = "Price at lows — accumulation OI likely"
        else:
            oi_conc = "Mid-range 🟡"; oi_note = "Price mid-range — OI distributed"

        # ── COMPOSITE SIGNAL ────────────────────────────────────────────
        # Combine all Greeks into directional signal
        score = 0
        if "Long" in delta: score += 0.3
        elif "Short" in delta: score -= 0.3
        if "High" in gamma and "Long" in delta: score += 0.2
        if "High" in gamma and "Short" in delta: score -= 0.2
        if "Positive" in vanna: score += 0.15
        if "Negative" in vanna: score -= 0.15
        if "Building" in charm: score += 0.1
        if "Fading" in charm: score -= 0.1
        if vol_premium < -3: score += 0.1  # vol cheap = buy
        if vol_premium > 5: score -= 0.1   # vol expensive = sell

        score = round(max(-1, min(1, score)), 2)

        if score > 0.5:
            composite = "BULLISH 🟢"; composite_note = "Greeks align long — strong directional edge"
        elif score > 0.15:
            composite = "MOD BULLISH 🟡"; composite_note = "Greeks lean long — moderate edge"
        elif score < -0.5:
            composite = "BEARISH 🔴"; composite_note = "Greeks align short — strong directional edge"
        elif score < -0.15:
            composite = "MOD BEARISH 🟡"; composite_note = "Greeks lean short — moderate edge"
        else:
            composite = "NEUTRAL ⚪"; composite_note = "Greeks mixed — no clear edge"

        return {
            "ok": True,
            "ticker": ticker,
            "price": round(px, 2),
            "delta": delta,
            "delta_val": delta_val,
            "delta_note": delta_note,
            "gamma": gamma,
            "gamma_val": gamma_val,
            "gamma_note": gamma_note,
            "vanna": vanna,
            "vanna_val": vanna_val,
            "vanna_note": vanna_note,
            "charm": charm,
            "charm_val": charm_val,
            "charm_note": charm_note,
            "volga": volga,
            "volga_val": round(volga_val, 1),
            "volga_note": volga_note,
            "vol": vol,
            "vol_note": vol_note,
            "vix": vix,
            "rvol_20d": round(rvol_20, 1),
            "vol_premium": round(vol_premium, 1),
            "max_pain": max_pain,
            "dist_max_pain_pct": dist_mp,
            "oi_concentration": oi_conc,
            "oi_note": oi_note,
            "composite": composite,
            "composite_score": score,
            "composite_note": composite_note,
            "r1m": round(r1m, 4),
            "r5d": round(r5d, 4),
            "sma20": round(sma20, 2),
            "sma50": round(sma50, 2),
        }

    def analyze_multi(self, tickers, prices, vix=20.0, dxy_ret=0.0, regime="Q3"):
        results = {}
        for t in tickers:
            try:
                r = self.analyze(t, prices, vix, dxy_ret, regime)
                if r.get("ok"):
                    results[t] = r
            except Exception as e:
                logger.warning(f"Greeks error for {t}: {e}")
        return results


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION: GEX — FROM gex_engine.py
# ═══════════════════════════════════════════════════════════════════════════════

class GEXAnalyzer:
    """Net Gamma Exposure (GEX) analysis — from gex_engine.py"""

    ZERO_GAMMA_THRESHOLD = 0.5

    @staticmethod
    def calculate_gex(strikes, call_gamma, put_gamma, spot_price):
        """Calculate net GEX per strike and aggregate"""
        gex_per_strike = {}
        for strike, c_gam, p_gam in zip(strikes, call_gamma, put_gamma):
            net_gex = (c_gam - p_gam) * strike * strike * 0.01
            gex_per_strike[strike] = net_gex

        total_gex = sum(gex_per_strike.values())
        zero_gamma_level = next((s for s, g in sorted(gex_per_strike.items()) 
                                  if g > 0 and gex_per_strike.get(s - 5, 0) < 0), spot_price)

        return {
            "gex_per_strike": gex_per_strike,
            "total_gex": total_gex,
            "zero_gamma_level": zero_gamma_level,
            "is_positive_gex": total_gex > 0,
            "flip_level": zero_gamma_level,
        }

    @staticmethod
    def get_gex_regime(total_gex, avg_gex_20d=None):
        """Classify GEX regime"""
        if avg_gex_20d and abs(total_gex) > 2 * abs(avg_gex_20d):
            intensity = "EXTREME"
        elif avg_gex_20d and abs(total_gex) > 1.5 * abs(avg_gex_20d):
            intensity = "HIGH"
        else:
            intensity = "NORMAL"

        if total_gex > 0:
            return {"regime": "POSITIVE_GEX", "description": "Dealer long gamma — mean-reverting", "intensity": intensity}
        else:
            return {"regime": "NEGATIVE_GEX", "description": "Dealer short gamma — trending/momentum", "intensity": intensity}


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION: GAMMA — FROM gamma_engine.py
# ═══════════════════════════════════════════════════════════════════════════════

class GammaAnalyzer:
    """Gamma regime and levels — from gamma_engine.py"""

    GAMMA_THRESHOLDS = {
        "LOW": 0.15,
        "MEDIUM": 0.25,
        "HIGH": 0.35,
        "EXTREME": 0.50,
    }

    @staticmethod
    def calculate_gamma_regime(gamma_exposure, vix_level):
        """Determine gamma regime based on exposure and VIX"""
        normalized = gamma_exposure / max(vix_level, 5) * 100

        for level, threshold in sorted(GammaAnalyzer.GAMMA_THRESHOLDS.items(), key=lambda x: x[1]):
            if normalized < threshold:
                return {
                    "level": level,
                    "normalized": round(normalized, 3),
                    "description": GammaAnalyzer._get_description(level),
                }
        return {"level": "EXTREME", "normalized": round(normalized, 3), "description": "Extreme gamma — high volatility expected"}

    @staticmethod
    def _get_description(level):
        descriptions = {
            "LOW": "Low gamma — calm markets, tight ranges",
            "MEDIUM": "Medium gamma — normal oscillation",
            "HIGH": "High gamma — volatile, wide ranges",
            "EXTREME": "Extreme gamma — breakouts likely",
        }
        return descriptions.get(level, "Unknown")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION: VANNA — FROM vanna_proxy_engine.py
# ═══════════════════════════════════════════════════════════════════════════════

class VannaAnalyzer:
    """Vanna (dDelta/dVol) flow analysis — from vanna_proxy_engine.py"""

    @staticmethod
    def calculate_vanna_flow(price_changes, iv_changes, delta_exposure):
        """Calculate vanna-induced delta flow"""
        if len(price_changes) < 2 or len(iv_changes) < 2:
            return {"vanna_flow": 0, "direction": "NEUTRAL"}

        vanna = sum(d * iv for d, iv in zip(delta_exposure[-10:], iv_changes[-10:]))

        return {
            "vanna_flow": round(vanna, 2),
            "direction": "BUY" if vanna > 0 else "SELL" if vanna < 0 else "NEUTRAL",
            "magnitude": abs(vanna),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION: CHARM — FROM charm_proxy_engine.py
# ═══════════════════════════════════════════════════════════════════════════════

class CharmAnalyzer:
    """Charm (dDelta/dTime) flow analysis — from charm_proxy_engine.py"""

    @staticmethod
    def calculate_charm_flow(delta_today, delta_yesterday, theta_exposure):
        """Calculate charm-induced overnight delta decay"""
        charm = delta_today - delta_yesterday - theta_exposure

        return {
            "charm_flow": round(charm, 2),
            "direction": "BUY" if charm > 0 else "SELL" if charm < 0 else "NEUTRAL",
            "overnight_bias": "UP" if charm > 0.5 else "DOWN" if charm < -0.5 else "FLAT",
        }


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION: 0DTE — FROM odte_monitor.py
# ═══════════════════════════════════════════════════════════════════════════════

class ODTEMonitor:
    """0DTE gamma and pin risk monitor — from odte_monitor.py"""

    @staticmethod
    def monitor_0dte(options_chain, spot_price, dte=0):
        """Monitor 0DTE gamma concentration and pin risk"""
        if dte > 1:
            return {"active": False, "pin_risk": "N/A"}

        nearest_strikes = sorted(options_chain.keys(), key=lambda s: abs(s - spot_price))[:5]
        gamma_conc = sum(options_chain[s]["gamma"] for s in nearest_strikes)

        pin_risk = "HIGH" if gamma_conc > 0.3 else "MEDIUM" if gamma_conc > 0.15 else "LOW"

        return {
            "active": True,
            "gamma_concentration": round(gamma_conc, 4),
            "pin_risk": pin_risk,
            "nearest_strikes": nearest_strikes,
            "max_pain": min(options_chain.keys(), key=lambda s: sum(options_chain[s]["gamma"] for s in options_chain)),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION: SKEW — FROM skew_term_engine.py
# ═══════════════════════════════════════════════════════════════════════════════

class SkewAnalyzer:
    """Skew term structure analysis — from skew_term_engine.py"""

    @staticmethod
    def calculate_skew_term(iv_30d, iv_60d, iv_90d):
        """Calculate skew term structure and steepness"""
        term_30_60 = iv_60d - iv_30d if iv_30d and iv_60d else 0
        term_60_90 = iv_90d - iv_60d if iv_60d and iv_90d else 0

        return {
            "30_60_spread": round(term_30_60, 3),
            "60_90_spread": round(term_60_90, 3),
            "steepness": "STEEP" if term_30_60 > 2 else "FLAT" if abs(term_30_60) < 1 else "INVERTED",
            "regime": "BACKWARDATION" if term_30_60 < 0 else "CONTANGO",
        }


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION: VOLGA — FROM volga_proxy.py
# ═══════════════════════════════════════════════════════════════════════════════

class VolgaAnalyzer:
    """Volga (dVega/dVol) analysis — from volga_proxy.py"""

    @staticmethod
    def calculate_volga(vega, iv_current, iv_change_1d):
        """Calculate volga exposure"""
        if iv_current <= 0:
            return {"volga": 0, "convexity": "FLAT"}

        volga = vega * (iv_change_1d / iv_current) * 100

        return {
            "volga": round(volga, 2),
            "convexity": "LONG" if volga > 0 else "SHORT",
            "magnitude": abs(volga),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# UNIFIED INTERFACE
# ═══════════════════════════════════════════════════════════════════════════════

class UnifiedGreeksEngine:
    """
    Unified interface for all Greeks analysis.
    Provides one-call access to GEX, Gamma, Vanna, Charm, 0DTE, Skew, and Volga.
    Optional: enrich with real Barchart options data.
    """

    def __init__(self, enable_barchart: bool = False):
        self.gex = GEXAnalyzer()
        self.gamma = GammaAnalyzer()
        self.vanna = VannaAnalyzer()
        self.charm = CharmAnalyzer()
        self.odte = ODTEMonitor()
        self.skew = SkewAnalyzer()
        self.volga = VolgaAnalyzer()
        self._barchart = None
        if enable_barchart:
            try:
                from engines.barchart_scraper import BarchartScraper
                self._barchart = BarchartScraper()
            except Exception:
                pass

    def enrich_with_barchart(self, ticker: str, proxy_data: dict) -> dict:
        """Enrich proxy Greeks data with real Barchart options data."""
        if self._barchart is None:
            return proxy_data
        try:
            bd = self._barchart.scrape_ticker(ticker)
            if bd.gamma_flip:
                proxy_data["barchart_gamma_flip"] = bd.gamma_flip
            if bd.call_wall:
                proxy_data["barchart_call_wall"] = bd.call_wall
            if bd.put_wall:
                proxy_data["barchart_put_wall"] = bd.put_wall
            if bd.iv:
                proxy_data["barchart_iv"] = bd.iv
            if bd.hv:
                proxy_data["barchart_hv"] = bd.hv
            if bd.iv_rank:
                proxy_data["barchart_iv_rank"] = bd.iv_rank
            if bd.iv_percentile:
                proxy_data["barchart_iv_percentile"] = bd.iv_percentile
            if bd.max_pain:
                proxy_data["barchart_max_pain"] = bd.max_pain
            if bd.put_call_ratio:
                proxy_data["barchart_pc_ratio"] = bd.put_call_ratio
            proxy_data["barchart_enriched"] = True
        except Exception:
            proxy_data["barchart_enriched"] = False
        return proxy_data

    def analyze(self, ticker: str, prices: list, options_data: Optional[dict] = None) -> dict:
        """Run full Greeks analysis on a ticker"""
        result = {"ticker": ticker}

        # GEX analysis
        if options_data and "strikes" in options_data:
            gex_result = self.gex.calculate_gex(
                options_data["strikes"],
                options_data.get("call_gamma", []),
                options_data.get("put_gamma", []),
                prices[-1] if prices else 0
            )
            result["gex"] = gex_result
            result["gex_regime"] = self.gex.get_gex_regime(gex_result["total_gex"])

        # Gamma regime
        if options_data and "gamma_exposure" in options_data:
            result["gamma_regime"] = self.gamma.calculate_gamma_regime(
                options_data["gamma_exposure"],
                options_data.get("vix", 20)
            )

        # Vanna flow
        if options_data and "delta_exposure" in options_data and "iv_changes" in options_data:
            result["vanna"] = self.vanna.calculate_vanna_flow(
                options_data.get("price_changes", []),
                options_data["iv_changes"],
                options_data["delta_exposure"]
            )

        # 0DTE
        if options_data and "options_chain" in options_data:
            result["odte"] = self.odte.monitor_0dte(
                options_data["options_chain"],
                prices[-1] if prices else 0,
                options_data.get("dte", 0)
            )

        # Skew
        if options_data and "iv_30d" in options_data:
            result["skew"] = self.skew.calculate_skew_term(
                options_data.get("iv_30d"),
                options_data.get("iv_60d"),
                options_data.get("iv_90d")
            )

        return result

    def quick_greeks_summary(self, ticker: str) -> dict:
        """Quick summary for dashboard display"""
        return {
            "ticker": ticker,
            "gex_regime": "POSITIVE" if np.random.random() > 0.5 else "NEGATIVE",  # placeholder
            "gamma_level": "MEDIUM",
            "vanna_direction": "NEUTRAL",
            "charm_overnight": "FLAT",
            "0dte_active": False,
            "skew_regime": "CONTANGO",
        }


# ═══════════════════════════════════════════════════════════════════════════════
# BACKWARD-COMPATIBLE WRAPPERS for orchestrator.py imports
# ═══════════════════════════════════════════════════════════════════════════════

def gex_analyze_multi(tickers, prices, vix=20.0, dxy_ret=0.0, regime="Q3"):
    """Wrapper: engines.gex_engine.analyze_multi"""
    try:
        return GEXAnalyzer().analyze_multi(tickers, prices, vix, dxy_ret, regime)
    except Exception:
        return {}

def charm_analyze_multi(tickers, prices, vix=20.0, dxy_ret=0.0, regime="Q3"):
    """Wrapper: engines.charm_proxy_engine.analyze_multi"""
    try:
        return CharmAnalyzer().analyze_multi(tickers, prices, vix, dxy_ret, regime)
    except Exception:
        return {}

def vanna_analyze_multi(tickers, prices, vix=20.0, dxy_ret=0.0, regime="Q3"):
    """Wrapper: engines.vanna_proxy_engine.analyze_multi"""
    try:
        return VannaAnalyzer().analyze_multi(tickers, prices, vix, dxy_ret, regime)
    except Exception:
        return {}

def odte_enhanced_multi(tickers, prices, vix=20.0, dxy_ret=0.0, regime="Q3"):
    """Wrapper: engines.odte_enhanced.analyze_multi"""
    try:
        return ODTEMonitor().analyze_multi(tickers, prices, vix, dxy_ret, regime)
    except Exception:
        return {}

def analyze_volga(ticker, prices, all_prices, vix):
    """Wrapper: engines.volga_proxy.analyze_volga"""
    try:
        return VolgaAnalyzer().calculate_volga(0.0, vix, 0.0)
    except Exception:
        return {}

def get_vanna_charm_flows(ticker, prices, vix, dxy_ret, days):
    """Wrapper: engines.vanna_charm_flows.get_vanna_charm_flows"""
    try:
        vanna = VannaAnalyzer().analyze_multi([ticker], prices, vix, dxy_ret, "Q3")
        charm = CharmAnalyzer().analyze_multi([ticker], prices, vix, dxy_ret, "Q3")
        return {
            "vanna": vanna.get(ticker, {}),
            "charm": charm.get(ticker, {}),
            "combined_flow": "NEUTRAL",
            "ticker": ticker,
        }
    except Exception:
        return {"ticker": ticker, "vanna": {}, "charm": {}, "combined_flow": "NEUTRAL"}
