"""engines/yfinance_options.py — Real Options Chain via yfinance
Fetches live options data (strikes, bid/ask, volume, OI, IV) for US equities.
Computes: Put/Call Ratio, Max Pain, Expected Move, Unusual Activity, GEX approx.
"""
import logging
import math
from typing import Dict, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False
    logger.warning("yfinance not installed. Run: pip install yfinance")


class YFinanceOptionsEngine:
    """Live options chain analyzer using Yahoo Finance."""

    def __init__(self):
        self._cache: Dict[str, Dict] = {}
        self._cache_time: Dict[str, datetime] = {}
        self.cache_ttl_minutes = 30

    def _get_ticker(self, symbol: str) -> Optional[yf.Ticker]:
        if not YF_AVAILABLE:
            return None
        try:
            return yf.Ticker(symbol)
        except Exception as e:
            logger.warning(f"yfinance ticker error for {symbol}: {e}")
            return None

    def _fetch_chain(self, symbol: str, expiration: Optional[str] = None) -> Optional[Dict]:
        """Fetch options chain for nearest expiration (or specified)."""
        t = self._get_ticker(symbol)
        if t is None:
            return None
        try:
            # Get available expirations
            exps = t.options
            if not exps:
                return None
            target_exp = expiration or exps[0]  # nearest expiration
            chain = t.option_chain(target_exp)
            calls = chain.calls
            puts = chain.puts
            return {
                "expiration": target_exp,
                "calls": calls,
                "puts": puts,
                "underlying": t.info.get("regularMarketPrice") or t.info.get("previousClose"),
                "symbol": symbol,
            }
        except Exception as e:
            logger.warning(f"Options chain fetch failed for {symbol}: {e}")
            return None

    def _calc_max_pain(self, calls, puts, underlying: float) -> float:
        """Max Pain = strike with minimum total dollar value loss for option holders."""
        try:
            all_strikes = sorted(set(calls["strike"].tolist() + puts["strike"].tolist()))
            min_loss = float("inf")
            max_pain = underlying
            for strike in all_strikes:
                # Call loss at expiration if price = strike
                call_oi = calls[calls["strike"] == strike]["openInterest"].sum() if "openInterest" in calls.columns else 0
                put_oi = puts[puts["strike"] == strike]["openInterest"].sum() if "openInterest" in puts.columns else 0
                # Simplified: pain = ITM value × OI
                call_itm = max(0, underlying - strike) * call_oi
                put_itm = max(0, strike - underlying) * put_oi
                total = call_itm + put_itm
                if total < min_loss:
                    min_loss = total
                    max_pain = strike
            return round(max_pain, 2)
        except Exception:
            return round(underlying, 2)

    def _calc_put_call_ratio(self, calls, puts) -> Dict:
        """Volume and OI based put/call ratios."""
        try:
            call_vol = calls["volume"].sum() if "volume" in calls.columns else 0
            put_vol = puts["volume"].sum() if "volume" in puts.columns else 0
            call_oi = calls["openInterest"].sum() if "openInterest" in calls.columns else 0
            put_oi = puts["openInterest"].sum() if "openInterest" in puts.columns else 0
            return {
                "pc_volume": round(put_vol / max(call_vol, 1), 2),
                "pc_oi": round(put_oi / max(call_oi, 1), 2),
                "call_volume": int(call_vol),
                "put_volume": int(put_vol),
                "call_oi": int(call_oi),
                "put_oi": int(put_oi),
            }
        except Exception:
            return {"pc_volume": 1.0, "pc_oi": 1.0, "call_volume": 0, "put_volume": 0, "call_oi": 0, "put_oi": 0}

    def _calc_expected_move(self, calls, puts, underlying: float) -> Dict:
        """Expected move from ATM straddle: (Call ATM + Put ATM) × 0.85."""
        try:
            # Find ATM strike
            atm_diff = abs(calls["strike"] - underlying)
            atm_idx = atm_diff.idxmin() if atm_diff.min() < underlying * 0.05 else None
            if atm_idx is not None:
                call_atm = calls.loc[atm_idx]
                # Find corresponding put
                put_match = puts[puts["strike"] == call_atm["strike"]]
                if not put_match.empty:
                    put_atm = put_match.iloc[0]
                    straddle = (call_atm.get("lastPrice", 0) + put_atm.get("lastPrice", 0))
                    expected = straddle * 0.85
                    return {
                        "straddle": round(straddle, 2),
                        "expected_move": round(expected, 2),
                        "expected_pct": round(expected / max(underlying, 0.01), 3),
                        "atm_strike": round(call_atm["strike"], 2),
                    }
        except Exception:
            pass
        return {"straddle": 0, "expected_move": 0, "expected_pct": 0, "atm_strike": underlying}

    def _find_unusual_activity(self, calls, puts, threshold: float = 5.0) -> List[Dict]:
        """Find strikes where Volume/OI ratio > threshold."""
        unusual = []
        try:
            for df, kind in [(calls, "CALL"), (puts, "PUT")]:
                if "volume" not in df.columns or "openInterest" not in df.columns:
                    continue
                for _, row in df.iterrows():
                    vol = row.get("volume", 0)
                    oi = row.get("openInterest", 1)
                    if oi > 10 and vol / oi > threshold:
                        unusual.append({
                            "strike": round(row["strike"], 2),
                            "type": kind,
                            "volume": int(vol),
                            "oi": int(oi),
                            "vol_oi_ratio": round(vol / oi, 1),
                            "iv": row.get("impliedVolatility"),
                            "last_price": row.get("lastPrice"),
                        })
            # Sort by vol/oi ratio desc
            unusual.sort(key=lambda x: x["vol_oi_ratio"], reverse=True)
        except Exception:
            pass
        return unusual[:10]  # top 10

    def _approx_gex(self, calls, puts, underlying: float) -> Dict:
        """Approximate Gamma Exposure from chain (simplified)."""
        try:
            # Approximate gamma from delta and IV using Black-Scholes proxy
            # Simplified: gamma ≈ N'(d1) / (S × σ × sqrt(T))
            # We'll use a rough approximation based on moneyness and IV
            total_gex = 0
            max_gamma_strike = underlying
            max_gamma_val = 0
            for df, sign in [(calls, 1), (puts, -1)]:
                for _, row in df.iterrows():
                    if "openInterest" not in row or "impliedVolatility" not in row:
                        continue
                    oi = row["openInterest"]
                    iv = row["impliedVolatility"] or 0.3
                    strike = row["strike"]
                    # Rough gamma proxy: OI × IV × exp(-distance_from_ATM)
                    dist = abs(strike - underlying) / max(underlying, 1)
                    gamma_proxy = oi * iv * math.exp(-dist * 5) * sign
                    total_gex += gamma_proxy
                    if abs(gamma_proxy) > max_gamma_val:
                        max_gamma_val = abs(gamma_proxy)
                        max_gamma_strike = strike

            regime = "POSITIVE" if total_gex > 0 else "NEGATIVE" if total_gex < 0 else "NEUTRAL"
            return {
                "total_gex_approx": round(total_gex, 0),
                "max_gamma_strike": round(max_gamma_strike, 2),
                "regime": regime,
                "note": "Approximate GEX from OI × IV proxy (not exchange-reported)",
            }
        except Exception:
            return {"total_gex_approx": 0, "regime": "UNKNOWN", "note": "GEX calc failed"}

    def analyze(self, ticker: str, prices=None, vix: float = 20) -> Dict:
        """Full options analysis for a single ticker."""
        cache_key = f"{ticker}_opts"
        if cache_key in self._cache:
            if (datetime.now() - self._cache_time.get(cache_key, datetime.min)) < timedelta(minutes=self.cache_ttl_minutes):
                return self._cache[cache_key]

        chain = self._fetch_chain(ticker)
        if chain is None:
            return {"ok": False, "reason": f"No options data for {ticker}"}

        calls = chain["calls"]
        puts = chain["puts"]
        underlying = chain.get("underlying") or 0
        exp = chain["expiration"]

        max_pain = self._calc_max_pain(calls, puts, underlying)
        pc = self._calc_put_call_ratio(calls, puts)
        em = self._calc_expected_move(calls, puts, underlying)
        unusual = self._find_unusual_activity(calls, puts, threshold=5.0)
        gex = self._approx_gex(calls, puts, underlying)

        # IV term structure proxy (just nearest expiration)
        avg_iv_calls = calls["impliedVolatility"].mean() if "impliedVolatility" in calls.columns else 0
        avg_iv_puts = puts["impliedVolatility"].mean() if "impliedVolatility" in puts.columns else 0
        avg_iv = (avg_iv_calls + avg_iv_puts) / 2

        result = {
            "ok": True,
            "ticker": ticker,
            "expiration": exp,
            "underlying": round(underlying, 2),
            "max_pain": max_pain,
            "dist_max_pain_pct": round((underlying - max_pain) / max(max_pain, 0.01) * 100, 2),
            "put_call_ratio": pc,
            "expected_move": em,
            "unusual_activity": unusual,
            "gex": gex,
            "avg_iv": round(avg_iv, 3),
            "iv_skew": round(avg_iv_puts - avg_iv_calls, 4),
            "call_count": len(calls),
            "put_count": len(puts),
            "source": "Yahoo Finance Options (LIVE)",
        }
        self._cache[cache_key] = result
        self._cache_time[cache_key] = datetime.now()
        return result

    def analyze_multi(self, tickers: List[str], prices=None, vix: float = 20, **kwargs) -> Dict[str, Dict]:
        """Batch analyze multiple tickers."""
        results = {}
        for t in tickers:
            try:
                r = self.analyze(t, prices, vix)
                if r.get("ok"):
                    results[t] = r
            except Exception as e:
                logger.warning(f"Options analysis failed for {t}: {e}")
        return results


# Singleton
options_engine = YFinanceOptionsEngine()


def analyze(ticker: str, prices=None, vix: float = 20) -> Dict:
    return options_engine.analyze(ticker, prices, vix)


def analyze_multi(tickers: List[str], prices=None, vix: float = 20, **kwargs) -> Dict[str, Dict]:
    return options_engine.analyze_multi(tickers, prices, vix)
