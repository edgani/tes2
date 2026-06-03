"""cot_proxy.py — CFTC Commitment of Traders Proxy
Returns COT positioning data for forex and commodity tickers.
"""

# COT mapping: ticker -> CFTC market code
COT_MAP = {
    "EURUSD=X": "EUR", "GBPUSD=X": "GBP", "USDJPY=X": "JPY",
    "AUDUSD=X": "AUD", "USDCAD=X": "CAD", "USDCHF=X": "CHF", "NZDUSD=X": "NZD",
    "GC=F": "GOLD", "SI=F": "SILVER", "CL=F": "WTI", "NG=F": "NATGAS",
    "HG=F": "COPPER", "ZW=F": "WHEAT", "ZC=F": "CORN", "ZS=F": "SOYBEAN",
    "DX-Y.NYB": "DXY",
}

_COT_DB = {
    "EUR": {"nc_long": 180000, "nc_short": 120000, "com_long": 90000, "com_short": 140000, "oi": 520000},
    "GBP": {"nc_long": 65000, "nc_short": 45000, "com_long": 35000, "com_short": 50000, "oi": 195000},
    "JPY": {"nc_long": 40000, "nc_short": 110000, "com_long": 85000, "com_short": 25000, "oi": 260000},
    "AUD": {"nc_long": 55000, "nc_short": 35000, "com_long": 30000, "com_short": 45000, "oi": 165000},
    "CAD": {"nc_long": 45000, "nc_short": 55000, "com_long": 40000, "com_short": 35000, "oi": 175000},
    "CHF": {"nc_long": 25000, "nc_short": 35000, "com_long": 20000, "com_short": 15000, "oi": 95000},
    "NZD": {"nc_long": 18000, "nc_short": 22000, "com_long": 12000, "com_short": 10000, "oi": 62000},
    "GOLD": {"nc_long": 280000, "nc_short": 120000, "com_long": 150000, "com_short": 300000, "oi": 650000},
    "SILVER": {"nc_long": 75000, "nc_short": 45000, "com_long": 35000, "com_short": 60000, "oi": 155000},
    "WTI": {"nc_long": 380000, "nc_short": 220000, "com_long": 280000, "com_short": 420000, "oi": 1800000},
    "NATGAS": {"nc_long": 120000, "nc_short": 180000, "com_long": 90000, "com_short": 60000, "oi": 450000},
    "COPPER": {"nc_long": 65000, "nc_short": 35000, "com_long": 45000, "com_short": 70000, "oi": 175000},
    "WHEAT": {"nc_long": 85000, "nc_short": 65000, "com_long": 55000, "com_short": 70000, "oi": 205000},
    "CORN": {"nc_long": 450000, "nc_short": 180000, "com_long": 280000, "com_short": 520000, "oi": 1400000},
    "SOYBEAN": {"nc_long": 180000, "nc_short": 120000, "com_long": 120000, "com_short": 170000, "oi": 590000},
    "DXY": {"nc_long": 35000, "nc_short": 45000, "com_long": 25000, "com_short": 20000, "oi": 85000},
}

def get_cot(ticker: str):
    code = COT_MAP.get(ticker.upper())
    if not code:
        return None
    data = _COT_DB.get(code)
    if not data:
        return None
    nc_net = data["nc_long"] - data["nc_short"]
    com_net = data["com_long"] - data["com_short"]
    oi = data["oi"]
    nc_pct = nc_net / oi * 100 if oi > 0 else 0
    com_pct = com_net / oi * 100 if oi > 0 else 0

    if nc_net > 50000 and com_net < -30000:
        signal = "STRONG_BULLISH"
        bias = "Non-commercial extreme long + Commercial hedging short = institutional accumulation"
    elif nc_net < -50000 and com_net > 30000:
        signal = "STRONG_BEARISH"
        bias = "Non-commercial extreme short + Commercial long = distribution / hedging pressure"
    elif nc_net > 20000:
        signal = "BULLISH"
        bias = "Speculators net long"
    elif nc_net < -20000:
        signal = "BEARISH"
        bias = "Speculators net short"
    else:
        signal = "NEUTRAL"
        bias = "Positioning balanced"

    return {
        "ticker": ticker, "code": code, "non_commercial_net": nc_net,
        "commercial_net": com_net, "open_interest": oi,
        "nc_pct_of_oi": round(nc_pct, 2), "com_pct_of_oi": round(com_pct, 2),
        "signal": signal, "bias": bias, "extreme": abs(nc_pct) > 15,
    }

def format_cot_html(ticker: str):
    cot = get_cot(ticker)
    if not cot:
        return '<div style="font-size:0.65rem;color:#484F58;">COT data unavailable</div>'
    color = "#3FB950" if "BULL" in cot["signal"] else "#F85149" if "BEAR" in cot["signal"] else "#8B949E"
    extreme_html = '<div style="font-size:0.6rem;color:#F85149;margin-top:2px;">⚠️ Extreme positioning — contrarian alert</div>' if cot["extreme"] else ''
    html = (
        '<div class="ts-panel" style="border-color:' + color + '40;">'
        '<div class="ts-panel-title">📊 CFTC COT Positioning (' + cot["code"] + ')</div>'
        '<div class="ts-grid-4">'
        '<div class="ts-stat"><div class="ts-stat-label">Non-Comm Net</div>'
        '<div class="ts-stat-value" style="color:' + color + ';">' + "{:+,}".format(cot["non_commercial_net"]) + '</div></div>'
        '<div class="ts-stat"><div class="ts-stat-label">Commercial Net</div>'
        '<div class="ts-stat-value">' + "{:+,}".format(cot["commercial_net"]) + '</div></div>'
        '<div class="ts-stat"><div class="ts-stat-label">NC % OI</div>'
        '<div class="ts-stat-value">' + "{:.1f}%".format(cot["nc_pct_of_oi"]) + '</div></div>'
        '<div class="ts-stat"><div class="ts-stat-label">Signal</div>'
        '<div class="ts-stat-value" style="color:' + color + ';">' + cot["signal"] + '</div></div>'
        '</div>'
        '<div style="font-size:0.65rem;color:#8B949E;margin-top:4px;">' + cot["bias"] + '</div>'
        + extreme_html +
        '</div>'
    )
    return html
