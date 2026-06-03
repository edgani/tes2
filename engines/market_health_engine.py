"""market_health_engine.py — composite market health indicator."""
def run_market_health(prices, vix=None, dxy=None):
    try:
        spx = prices.get("^GSPC") or prices.get("SPY")
        if spx is None: return {"score": 50, "label": "UNKNOWN"}
        # Distance to 200-day MA
        spx = spx.dropna()
        if len(spx) < 200: return {"score": 50, "label": "INSUFFICIENT"}
        ma200 = float(spx.tail(200).mean())
        px = float(spx.iloc[-1])
        trend = ((px / ma200) - 1) * 100
        # VIX adjustment
        vix_pen = 0
        if vix is not None:
            if vix > 30: vix_pen = -30
            elif vix > 22: vix_pen = -15
            elif vix < 14: vix_pen = +10
        score = 50 + trend * 2 + vix_pen
        score = max(0, min(100, score))
        if score >= 75: label = "🟢 STRONG"
        elif score >= 55: label = "🟢 HEALTHY"
        elif score >= 40: label = "🟡 NEUTRAL"
        elif score >= 25: label = "🟠 WEAK"
        else: label = "🔴 CRITICAL"
        return {"score": round(score, 1), "label": label,
                "trend_pct": round(trend, 2), "vix": vix}
    except Exception: return {"score": 50, "label": "ERROR"}

class MarketHealthEngine:
    def run(self, prices, vix=None, dxy=None):
        return run_market_health(prices, vix, dxy)
