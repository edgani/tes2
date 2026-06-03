"""bonds_xau_regime.py — TLT vs GLD regime indicator."""
def run_bonds_xau(prices):
    try:
        tlt = prices.get("TLT"); gld = prices.get("GLD")
        if tlt is None or gld is None: return {"signal": "NEUTRAL"}
        tlt_mom = (float(tlt.iloc[-1]) / float(tlt.iloc[-21]) - 1) if len(tlt) >= 21 else 0
        gld_mom = (float(gld.iloc[-1]) / float(gld.iloc[-21]) - 1) if len(gld) >= 21 else 0
        ratio = tlt_mom - gld_mom
        if ratio > 0.02: sig = "RISK_OFF_BONDS"
        elif ratio < -0.02: sig = "REFLATION_GOLD"
        else: sig = "NEUTRAL"
        return {"signal": sig, "tlt_mom": round(tlt_mom, 4), "gld_mom": round(gld_mom, 4)}
    except Exception: return {"signal": "NEUTRAL"}
