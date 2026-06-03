"""crypto_onchain.py — Crypto On-Chain Analytics Proxy
Whale accumulation, funding, exchange balance, unlock calendar.
"""
import pandas as pd
import numpy as np

_ONCHAIN_META = {
    "BTC-USD": {"exchange_balance": 2300000, "exchange_change_30d": -45000, "whale_wallets_1k_plus": 2100, "funding_rate": 0.0001, "fear_greed": 65},
    "ETH-USD": {"exchange_balance": 18000000, "exchange_change_30d": -120000, "whale_wallets_10k_plus": 1650, "funding_rate": 0.00015, "fear_greed": 58},
    "SOL-USD": {"exchange_balance": 8500000, "exchange_change_30d": -80000, "whale_wallets_10k_plus": 420, "funding_rate": 0.0002, "fear_greed": 72},
    "XRP-USD": {"exchange_balance": 450000000, "exchange_change_30d": 5000000, "whale_wallets_1m_plus": 85, "funding_rate": 0.00005, "fear_greed": 45},
    "DOGE-USD": {"exchange_balance": 12000000000, "exchange_change_30d": -200000000, "whale_wallets_1m_plus": 120, "funding_rate": 0.00008, "fear_greed": 55},
    "ADA-USD": {"exchange_balance": 6500000000, "exchange_change_30d": -100000000, "whale_wallets_1m_plus": 95, "funding_rate": 0.00003, "fear_greed": 48},
    "AVAX-USD": {"exchange_balance": 2800000, "exchange_change_30d": -150000, "whale_wallets_10k_plus": 180, "funding_rate": 0.00025, "fear_greed": 60},
    "DOT-USD": {"exchange_balance": 120000000, "exchange_change_30d": -5000000, "whale_wallets_10k_plus": 95, "funding_rate": 0.0001, "fear_greed": 50},
}

_UNLOCK_CALENDAR = [
    {"token": "SOL", "date": "2026-06-01", "amount_m": 20, "type": "Cliff", "impact": "HIGH"},
    {"token": "AVAX", "date": "2026-05-20", "amount_m": 5, "type": "Linear", "impact": "MEDIUM"},
    {"token": "ARB", "date": "2026-05-25", "amount_m": 100, "type": "Cliff", "impact": "HIGH"},
    {"token": "OP", "date": "2026-06-15", "amount_m": 30, "type": "Linear", "impact": "MEDIUM"},
    {"token": "APT", "date": "2026-07-01", "amount_m": 15, "type": "Cliff", "impact": "MEDIUM"},
    {"token": "SUI", "date": "2026-06-20", "amount_m": 25, "type": "Linear", "impact": "HIGH"},
]

def analyze_onchain(ticker: str, prices: dict):
    meta = _ONCHAIN_META.get(ticker.upper(), None)
    s = prices.get(ticker)
    if s is None or len(s) < 22:
        return None
    try:
        s_clean = pd.to_numeric(pd.Series(s), errors="coerce").dropna()
        if len(s_clean) < 22:
            return None
        px = float(s_clean.iloc[-1])
        r1m = float(s_clean.iloc[-1] / s_clean.iloc[-22] - 1)
        r7d = float(s_clean.iloc[-1] / s_clean.iloc[-8] - 1) if len(s_clean) >= 8 else r1m
        vol = float(s_clean.tail(20).std())
        vol_40 = float(s_clean.tail(40).std()) if len(s_clean) >= 40 else vol
        mean_20 = float(s_clean.tail(20).mean())

        whale_signal = "NEUTRAL"
        if r7d > 0.05 and (vol / vol_40 if vol_40 > 0 else 1) < 1.2:
            whale_signal = "ACCUMULATING"
        elif r7d < -0.05 and (vol / vol_40 if vol_40 > 0 else 1) > 1.3:
            whale_signal = "DISTRIBUTING"

        funding = meta["funding_rate"] if meta else 0.0001
        funding_extreme = abs(funding) > 0.0005

        exchange_signal = "NEUTRAL"
        if meta and meta["exchange_change_30d"] < -50000:
            exchange_signal = "OUTFLOW_BULLISH"
        elif meta and meta["exchange_change_30d"] > 50000:
            exchange_signal = "INFLOW_BEARISH"

        token = ticker.replace("-USD", "").upper()
        upcoming = [u for u in _UNLOCK_CALENDAR if u["token"] == token and u["date"] >= "2026-05-26"]

        score = min(1.0, max(0.0, 0.5 + r1m * 5 + (0.2 if whale_signal == "ACCUMULATING" else -0.2 if whale_signal == "DISTRIBUTING" else 0)))

        return {
            "ticker": ticker, "price": px, "momentum_score": round(score, 3),
            "r1m": round(r1m, 4), "r7d": round(r7d, 4),
            "whale_signal": whale_signal, "exchange_signal": exchange_signal,
            "funding_rate": funding, "funding_extreme": funding_extreme,
            "volatility_20d": round(vol / mean_20 if mean_20 > 0 else 0, 4),
            "trend_direction": "UP" if r1m > 0.05 else ("DOWN" if r1m < -0.05 else "SIDE"),
            "upcoming_unlocks": upcoming,
            "meta": meta,
        }
    except Exception:
        return None

def onchain_html(data: dict, ticker: str):
    if not data:
        return '<div style="font-size:0.65rem;color:#484F58;">On-chain data unavailable</div>'

    whale_color = "#3FB950" if data["whale_signal"] == "ACCUMULATING" else "#F85149" if data["whale_signal"] == "DISTRIBUTING" else "#8B949E"
    exchange_color = "#3FB950" if "OUTFLOW" in data["exchange_signal"] else "#F85149" if "INFLOW" in data["exchange_signal"] else "#8B949E"
    funding_color = "#F85149" if data["funding_extreme"] else "#8B949E"

    unlock_html = ""
    if data["upcoming_unlocks"]:
        unlock_html = '<div style="font-size:0.6rem;color:#F85149;margin-top:4px;">🔓 Upcoming Unlocks:<br>'
        for u in data["upcoming_unlocks"][:3]:
            unlock_html += '• ' + u["token"] + ': ' + str(u["amount_m"]) + 'M on ' + u["date"] + ' (' + u["impact"] + ')<br>'
        unlock_html += '</div>'

    html = (
        '<div class="ts-panel" style="border-color:#A855F740;">'
        '<div class="ts-panel-title">⛓️ On-Chain Analytics (' + ticker + ')</div>'
        '<div class="ts-grid-4">'
        '<div class="ts-stat"><div class="ts-stat-label">Whale Signal</div>'
        '<div class="ts-stat-value" style="color:' + whale_color + ';">' + data["whale_signal"] + '</div></div>'
        '<div class="ts-stat"><div class="ts-stat-label">Exchange Flow</div>'
        '<div class="ts-stat-value" style="color:' + exchange_color + ';">' + data["exchange_signal"] + '</div></div>'
        '<div class="ts-stat"><div class="ts-stat-label">Funding</div>'
        '<div class="ts-stat-value" style="color:' + funding_color + ';">' + "{:.4f}%".format(data["funding_rate"]*100) + '</div></div>'
        '<div class="ts-stat"><div class="ts-stat-label">1M Return</div>'
        '<div class="ts-stat-value" style="color:' + ("#3FB950" if data["r1m"] > 0 else "#F85149") + ';">' + "{:+.1f}%".format(data["r1m"]*100) + '</div></div>'
        '</div>'
        '<div style="font-size:0.65rem;color:#8B949E;margin-top:4px;">'
        'Momentum Score: <b>' + str(data["momentum_score"]) + '</b> · Trend: ' + data["trend_direction"] +
        '</div>'
        + unlock_html +
        '</div>'
    )
    return html
