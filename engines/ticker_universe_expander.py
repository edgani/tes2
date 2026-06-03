"""ticker_universe_expander.py — multi-market ticker universe."""
UNIVERSE = {
    "us_equity_indices": ["^GSPC", "SPY", "^NDX", "QQQ", "^DJI", "DIA", "^RUT", "IWM"],
    "us_sectors": ["XLK", "XLF", "XLE", "XLI", "XLY", "XLP", "XLV", "XLU", "XLB", "XLC", "XLRE"],
    "us_megacaps": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO", "TSM", "AMD"],
    "ai_optical": ["COHR", "LITE", "AAOI", "POET", "MRVL", "CRDO", "SITM", "AXTI", "GLW"],
    "ai_packaging": ["AMKR", "ASX", "INTC"],
    "ai_power": ["VRT", "ETN", "GEV", "VST", "TLN", "CEG", "NVTS"],
    "memory_storage": ["MU", "WDC", "STX", "SNDK"],
    "energy": ["CL=F", "USO", "XLE", "XOP", "OIH", "VLO", "MPC", "OXY"],
    "tankers": ["FRO", "STNG", "INSW", "DHT", "TNK", "TRMD", "ASC"],
    "materials": ["FCX", "SCCO", "MP", "USAR", "ATI", "MTRN", "AA"],
    "metals": ["GC=F", "GLD", "SI=F", "SLV", "GDX", "HG=F"],
    "uranium_nuclear": ["CCJ", "UEC", "DNN", "SMR", "OKLO", "BWXT"],
    "crypto": ["BTC-USD", "ETH-USD", "SOL-USD", "MSTR", "MARA", "RIOT", "COIN"],
    "fx_majors": ["EURUSD=X", "GBPUSD=X", "JPY=X", "AUDUSD=X", "USDCAD=X"],
    "ihsg_big_banks": ["BBCA.JK", "BMRI.JK", "BBRI.JK", "BBNI.JK"],
    "ihsg_consumer": ["INDF.JK", "ICBP.JK", "UNVR.JK"],
    "ihsg_commodities": ["ADRO.JK", "ITMG.JK", "PTBA.JK", "BUMI.JK", "MEDC.JK", "PGAS.JK"],
    "ihsg_barito_group": ["TPIA.JK", "BREN.JK", "BRPT.JK", "CUAN.JK", "PTRO.JK"],
}

def get_universe(market=None):
    if market: return UNIVERSE.get(market, [])
    return [t for lst in UNIVERSE.values() for t in lst]

def expand(base=None):
    return list(set(get_universe()))
