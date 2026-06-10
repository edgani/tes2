"""cross_asset.py — Cross-Asset Coherence Engine. Answers 'why is X moving like this?' by reading
the WHOLE tape together and classifying the cross-asset REGIME, then flagging divergences (e.g.
gold DOWN while nominal yields DOWN = real-yield/deleveraging override, NOT a monetary regime).
Feeds the per-ticker reason narrative + gates entries (defer longs during liquidation)."""
from __future__ import annotations

def run_cross_asset(snap: dict) -> dict:
    """snap: daily % changes. keys (any subset): gold, silver, oil, spx, ndx, btc, eth,
    ust2y_chg, ust10y_chg, dxy_chg, vix_chg, hy_oas_chg (yields/oas chg = bps or %)."""
    g = snap.get; 
    def dn(k, t=0.0): v = g(k); return (v is not None and v < t)
    def up(k, t=0.0): v = g(k); return (v is not None and v > t)
    risk_dn = dn("spx") or dn("ndx") or dn("btc")
    commod_dn = dn("gold") or dn("oil") or dn("silver")
    bonds_rally = dn("ust10y_chg")            # yields down = bonds up
    yields_up = up("ust10y_chg")
    vix_up = up("vix_chg")
    dollar_up = up("dxy_chg")
    oil_up = up("oil")
    stocks_up = up("spx") or up("ndx")
    gsr_rising = (g("gold") is not None and g("silver") is not None and g("gold") > g("silver"))  # growth-fear

    # regime classification (priority order)
    if risk_dn and commod_dn and (bonds_rally or vix_up):
        regime, why = "DELEVERAGING", ("Everything sold (risk + commodities) while bonds catch the haven bid "
            "and VIX rises — forced liquidation / margin-driven de-risking. Correlations -> 1.")
        defer_longs = True
    elif oil_up and yields_up and risk_dn:
        regime, why = "STAGFLATION_SCARE", ("Energy up + yields up + equities down — sticky-inflation / "
            "policy-hold pressure. Favours energy & real assets, hurts long-duration growth.")
        defer_longs = False
    elif commod_dn and bonds_rally and risk_dn:
        regime, why = "DEFLATION_GROWTH_SCARE", ("Commodities + equities down with bonds bid — demand/growth "
            "scare; breakevens likely falling faster than nominal yields (real yields up).")
        defer_longs = True
    elif stocks_up and yields_up and (up("oil") or up("gold")):
        regime, why = "GROWTH_ON", "Equities + yields + commodities up together — reflationary risk-on."
        defer_longs = False
    elif bonds_rally and (up("gold")) and not dollar_up:
        regime, why = "MONETARY_EASING", "Yields down + gold up + dollar soft — classic easing/lower-real-yield bid."
        defer_longs = False
    else:
        regime, why = "MIXED", "No clean cross-asset regime — signals are crosscurrents; trade selectively."
        defer_longs = False

    # divergence flags (the 'paradox' detector)
    div = []
    if dn("gold") and bonds_rally:
        div.append("GOLD↓ while NOMINAL YIELDS↓: haven bid is in BONDS not gold — either real yields rising "
                   "(breakevens down more) or gold sold for liquidity in a de-risking. Not a monetary-easing tape.")
    if dn("gold") and dn("silver") and gsr_rising:
        div.append("Gold/Silver ratio RISING (silver underperforms): growth-fear / industrial-demand stress.")
    if stocks_up and vix_up:
        div.append("Equities↑ with VIX↑: hedging into strength — distribution risk under the surface.")
    if dn("btc") and dn("gold") and dn("oil"):
        div.append("Crypto + gold + oil all down together = broad liquidity withdrawal, not asset-specific news.")
    return {"ok": True, "regime": regime, "why": why, "defer_longs": defer_longs,
            "divergences": div, "gold_silver_ratio_rising": gsr_rising}
