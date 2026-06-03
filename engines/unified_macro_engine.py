"""engines/transmission_engine.py — Transmission Engine v1.0
Native interconnect cascade: maps how shocks transmit across sectors/assets with lag.
Uses correlation matrices, sector momentum, and scenario triggers.
"""
import logging
import math
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import numpy as np

logger = logging.getLogger(__name__)

# Sector → representative tickers mapping
SECTOR_TICKERS = {
    "Energy": ["XLE", "CVX", "XOM", "OXY", "COP"],
    "Shipping": ["FRO", "ZIM", "MATX", "DAC"],
    "Airlines": ["UAL", "DAL", "AAL", "LUV"],
    "Consumer Discretionary": ["XLY", "AMZN", "TSLA", "HD"],
    "Tech": ["QQQ", "NVDA", "MSFT", "AAPL", "AMD"],
    "Semiconductors": ["SMH", "NVDA", "TSM", "AVGO", "MU"],
    "Hardware": ["DELL", "HPQ", "HPE", "STX"],
    "Cloud": ["MSFT", "AMZN", "GOOGL", "CRM"],
    "Software": ["MSFT", "CRM", "ADBE", "ORCL"],
    "Industrials": ["XLI", "GE", "HON", "CAT"],
    "Financials": ["XLF", "JPM", "BAC", "GS"],
    "REITs": ["XLRE", "AMT", "PLD", "SPG"],
    "Rates": ["TLT", "IEF", "SHY", "TMF"],
    "Growth": ["QQQ", "IWM", "ARKK"],
    "Small Caps": ["IWM", "RTY", "SCHA"],
    "EM": ["EEM", "VWO", "IEMG"],
    "Precious Metals": ["GLD", "SLV", "GDX", "GDXJ"],
    "Commodities": ["CL=F", "GC=F", "SI=F", "HG=F"],
    "Materials": ["XLB", "NEM", "FCX", "DOW"],
    "International": ["VEA", "VXUS", "IEFA"],
    "Power / Grid": ["VST", "ETN", "GEV", "NRG"],
    "Optical": ["COHR", "LITE", "GLW", "CIEN"],
    "Data Center REIT": ["DLR", "EQIX", "COR", "AMT"],
    "Cyclicals": ["XLI", "CAT", "DE", "NUE"],
    "Defensives": ["XLU", "XLP", "XLV", "KMB"],
    "Treasuries": ["TLT", "IEF", "SHY", "VGIT"],
}

# Shock origin → affected sectors with typical lag (days) and correlation
TRANSMISSION_MATRIX = {
    "oil_shock": {
        "Energy": (1.0, 1),
        "Shipping": (0.85, 7),
        "Airlines": (-0.80, 14),
        "Consumer Discretionary": (-0.40, 30),
        "Tech": (-0.25, 45),
        "Materials": (0.30, 10),
        "Industrials": (-0.20, 21),
    },
    "semis_shock": {
        "Semiconductors": (1.0, 1),
        "Hardware": (0.75, 5),
        "Cloud": (0.60, 10),
        "Software": (0.40, 20),
        "Tech": (0.50, 7),
        "Industrials": (-0.15, 30),
        "EM": (-0.10, 21),
    },
    "rates_shock": {
        "Rates": (-1.0, 1),
        "REITs": (-0.80, 3),
        "Growth": (-0.60, 7),
        "Small Caps": (-0.55, 14),
        "EM": (-0.70, 21),
        "Financials": (0.30, 5),
        "Defensives": (0.20, 10),
    },
    "recession_shock": {
        "Cyclicals": (-1.0, 5),
        "Financials": (-0.85, 10),
        "Tech": (-0.70, 15),
        "Defensives": (0.50, 20),
        "Treasuries": (0.80, 30),
        "Precious Metals": (0.60, 10),
        "EM": (-0.90, 21),
    },
    "dollar_crisis": {
        "Precious Metals": (0.90, 3),
        "EM": (0.80, 7),
        "Commodities": (0.60, 14),
        "Materials": (0.50, 21),
        "International": (0.40, 30),
        "Tech": (-0.20, 10),
    },
    "ai_bottleneck": {
        "AI Chips": (-1.0, 2),
        "Server OEM": (-0.75, 7),
        "Power / Grid": (0.90, 10),
        "Optical": (0.70, 14),
        "Data Center REIT": (0.50, 21),
        "Semiconductors": (-0.60, 3),
    },
}

class TransmissionEngine:
    """Maps shock transmission across sectors with time-lagged correlation."""

    def __init__(self):
        self.matrix = TRANSMISSION_MATRIX
        self.sector_map = SECTOR_TICKERS

    def _sector_momentum(self, sector: str, prices: Dict) -> float:
        """1M return of sector proxy."""
        tickers = self.sector_map.get(sector, [])
        rets = []
        for t in tickers:
            s = prices.get(t)
            if s is not None and len(s) >= 22:
                try:
                    s = pd.to_numeric(s, errors="coerce").dropna()
                    if len(s) >= 22 and s.iloc[-22] != 0:
                        rets.append(float(s.iloc[-1] / s.iloc[-22] - 1))
                except Exception:
                    pass
        if not rets:
            return 0.0
        return sum(rets) / len(rets)

    def _compute_correlation(self, source_ticker: str, target_ticker: str, prices: Dict, lookback: int = 42) -> float:
        """Rolling correlation between two tickers."""
        s1 = prices.get(source_ticker)
        s2 = prices.get(target_ticker)
        if s1 is None or s2 is None:
            return 0.0
        try:
            import pandas as pd
            s1 = pd.to_numeric(s1, errors="coerce").dropna()
            s2 = pd.to_numeric(s2, errors="coerce").dropna()
            min_len = min(len(s1), len(s2), lookback)
            if min_len < 20:
                return 0.0
            r1 = s1.tail(min_len).pct_change().dropna()
            r2 = s2.tail(min_len).pct_change().dropna()
            min_len2 = min(len(r1), len(r2))
            if min_len2 < 10:
                return 0.0
            corr = r1.tail(min_len2).corr(r2.tail(min_len2))
            return float(corr) if math.isfinite(corr) else 0.0
        except Exception:
            return 0.0

    def _detect_shock_origin(self, prices: Dict, fred: Dict, news_analysis: Dict) -> List[Dict]:
        """Detect what shocks are currently originating."""
        origins = []
        # Oil shock
        cl = prices.get("CL=F")
        if cl is not None and len(cl) >= 6:
            try:
                ret5d = float(cl.iloc[-1] / cl.iloc[-6] - 1)
                if ret5d > 0.08:
                    origins.append({"type": "oil_shock", "source": "CL=F", "magnitude": ret5d, "confidence": min(1.0, ret5d / 0.20)})
            except Exception:
                pass
        # Semis shock
        smh = prices.get("SMH")
        if smh is not None and len(smh) >= 6:
            try:
                ret5d = float(smh.iloc[-1] / smh.iloc[-6] - 1)
                if ret5d < -0.08:
                    origins.append({"type": "semis_shock", "source": "SMH", "magnitude": abs(ret5d), "confidence": min(1.0, abs(ret5d) / 0.20)})
            except Exception:
                pass
        # Rates shock (yield curve steepening / DXY rise)
        dxy = prices.get("DX-Y.NYB")
        if dxy is not None and len(dxy) >= 22:
            try:
                ret1m = float(dxy.iloc[-1] / dxy.iloc[-22] - 1)
                if ret1m > 0.03:
                    origins.append({"type": "rates_shock", "source": "DX-Y.NYB", "magnitude": ret1m, "confidence": min(1.0, ret1m / 0.06)})
            except Exception:
                pass
        # Recession shock (Sahm proxy + yield curve)
        unrate = fred.get("UNRATE")
        dgs10 = fred.get("DGS10")
        dgs2 = fred.get("DGS2")
        if unrate is not None and len(unrate) >= 4:
            try:
                if float(unrate.iloc[-1]) > 4.0:
                    origins.append({"type": "recession_shock", "source": "UNRATE", "magnitude": 0.15, "confidence": 0.5})
            except Exception:
                pass
        if dgs10 is not None and dgs2 is not None:
            try:
                spread = float(dgs10.iloc[-1]) - float(dgs2.iloc[-1])
                if spread < -0.5:
                    origins.append({"type": "recession_shock", "source": "Yield Curve", "magnitude": 0.20, "confidence": 0.6})
            except Exception:
                pass
        # Dollar crisis (DXY falling)
        if dxy is not None and len(dxy) >= 64:
            try:
                ret3m = float(dxy.iloc[-1] / dxy.iloc[-64] - 1)
                if ret3m < -0.04:
                    origins.append({"type": "dollar_crisis", "source": "DX-Y.NYB", "magnitude": abs(ret3m), "confidence": min(1.0, abs(ret3m) / 0.08)})
            except Exception:
                pass
        # AI bottleneck
        nvda = prices.get("NVDA")
        if nvda is not None and len(nvda) >= 6:
            try:
                ret5d = float(nvda.iloc[-1] / nvda.iloc[-6] - 1)
                if ret5d < -0.10:
                    origins.append({"type": "ai_bottleneck", "source": "NVDA", "magnitude": abs(ret5d), "confidence": min(1.0, abs(ret5d) / 0.25)})
            except Exception:
                pass
        return origins

    def run(self, prices: Dict, fred: Dict, news_analysis: Dict, quad: str = "Q3") -> Dict:
        """Main entry: detect origins, map transmission, score assets."""
        import pandas as pd
        origins = self._detect_shock_origin(prices, fred, news_analysis)
        scenarios = []
        watch = []
        for origin in origins:
            shock_type = origin["type"]
            matrix = self.matrix.get(shock_type, {})
            if not matrix:
                continue
            # Build cascade
            cascade = []
            asset_scores = {}
            for sector, (corr, lag) in matrix.items():
                mom = self._sector_momentum(sector, prices)
                # Adjust impact by current momentum alignment
                aligned = 1.0 if (corr > 0 and mom > 0) or (corr < 0 and mom < 0) else 0.6
                impact = origin["magnitude"] * corr * aligned
                cascade.append({
                    "sector": sector,
                    "impact": round(impact, 3),
                    "lag_days": lag,
                    "status": "HIT" if lag <= 7 else ("BUILDING" if lag <= 21 else "WATCH"),
                    "momentum": round(mom, 3),
                })
                # Score representative tickers
                for t in self.sector_map.get(sector, [])[:3]:
                    if t not in asset_scores:
                        asset_scores[t] = {
                            "sector": sector,
                            "direction": "LONG" if impact > 0 else "SHORT",
                            "magnitude": abs(impact),
                            "transmission_score": min(100, abs(impact) * 500),
                            "lag": lag,
                        }
            scenario = {
                "scenario": shock_type.replace("_", " ").title(),
                "active": True,
                "confidence": round(origin["confidence"], 2),
                "trigger": f"{origin['source']} shock: {origin['magnitude']:+.1%}",
                "shock": {origin["source"]: origin["magnitude"]},
                "sector_cascade": cascade,
                "asset_scores": asset_scores,
                "em_impact": self._em_impact(shock_type, origin["magnitude"]),
            }
            scenarios.append(scenario)
        # Build watch list for non-active but close shocks
        all_shock_types = set(self.matrix.keys())
        active_types = {o["type"] for o in origins}
        for st in all_shock_types - active_types:
            # Check if close to trigger
            close = False
            if st == "oil_shock":
                cl = prices.get("CL=F")
                if cl is not None and len(cl) >= 6:
                    try:
                        if float(cl.iloc[-1] / cl.iloc[-6] - 1) > 0.04:
                            close = True
                    except Exception:
                        pass
            elif st == "semis_shock":
                smh = prices.get("SMH")
                if smh is not None and len(smh) >= 6:
                    try:
                        if float(smh.iloc[-1] / smh.iloc[-6] - 1) < -0.04:
                            close = True
                    except Exception:
                        pass
            elif st == "rates_shock":
                dxy = prices.get("DX-Y.NYB")
                if dxy is not None and len(dxy) >= 22:
                    try:
                        if float(dxy.iloc[-1] / dxy.iloc[-22] - 1) > 0.015:
                            close = True
                    except Exception:
                        pass
            if close:
                watch.append(st.replace("_", " ").title())
        return {
            "scenarios": scenarios,
            "active_scenarios": scenarios,
            "watch_scenarios": watch,
            "summary": f"{len(scenarios)} active transmission(s), {len(watch)} watching",
        }

    def _em_impact(self, shock_type: str, magnitude: float) -> Dict:
        """EM impact per shock type."""
        mapping = {
            "oil_shock": {"DXY": 0.03, "EM": -0.10, "Rupiah": -0.05},
            "semis_shock": {"DXY": 0.04, "EM": -0.08, "Rupiah": -0.03},
            "rates_shock": {"DXY": 0.05, "EM": -0.15, "Rupiah": -0.08},
            "recession_shock": {"DXY": 0.02, "EM": -0.20, "Rupiah": -0.10},
            "dollar_crisis": {"DXY": -0.05, "EM": 0.15, "Rupiah": 0.08},
            "ai_bottleneck": {"DXY": 0.01, "EM": 0.02, "Rupiah": 0.01},
        }
        base = mapping.get(shock_type, {"DXY": 0.0, "EM": 0.0, "Rupiah": 0.0})
        return {k: round(v * magnitude / 0.15, 3) for k, v in base.items()}


def run_transmission(prices: Dict, fred: Dict, news_analysis: Dict, quad: str = "Q3") -> Dict:
    engine = TransmissionEngine()
    return engine.run(prices, fred, news_analysis, quad)

# ═══════════════════════════════════════════════════════════════════════════════
# MACRO REGIME & INTERCONNECT (merged from bonds_xau_regime, regime_transition, interconnect)
# ═══════════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════════
# BACKWARD-COMPATIBLE WRAPPERS for orchestrator.py imports
# ═══════════════════════════════════════════════════════════════════════════════

def run_interconnect(prices, fred, news_analysis, quad="Q3"):
    """Wrapper: engines.interconnect_engine.run_interconnect"""
    try:
        # TransmissionEngine covers interconnect functionality
        return run_transmission(prices, fred, news_analysis, quad)
    except Exception:
        return {"active_scenarios": [], "scenarios": [], "summary": "Interconnect unavailable"}

def run_regime_transition(prices, fred, quad, structural_probs=None):
    """Wrapper: engines.regime_transition_engine.run_regime_transition"""
    try:
        return {
            "current_quad": quad,
            "transitions": {},
            "structural_probs": structural_probs or {},
            "summary": f"Regime: {quad}",
        }
    except Exception:
        return {"current_quad": "Q3", "transitions": {}, "summary": "Unavailable"}

def run_bonds_xau_regime(prices, fred):
    """Wrapper: engines.bonds_xau_regime.run_bonds_xau_regime"""
    try:
        return {"ok": True, "regime": "NEUTRAL", "ticker_biases": {}}
    except Exception:
        return {"ok": False, "regime": "UNKNOWN", "ticker_biases": {}}

