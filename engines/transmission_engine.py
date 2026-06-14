"""transmission_engine.py — active shocks via chain_reaction_v2."""
def run_transmission(prices, current_quad="Q3", shock_threshold_pct=2.0):
    try:
        from engines.chain_reaction_v2 import get_chain_engine
        engine = get_chain_engine()
        active = []
        for ticker, series in (prices or {}).items():
            try:
                s = series.dropna()
                if len(s) < 5: continue
                d1 = (float(s.iloc[-1]) / float(s.iloc[-2]) - 1) * 100
                if abs(d1) >= shock_threshold_pct:
                    chains = engine.get_chain_for_parent(ticker)
                    if chains:
                        cascade = engine.calculate_cascade(ticker, d1, current_quad)
                        active.append({"shock_ticker": ticker, "shock_pct": round(d1, 2),
                                      "cascade": cascade})
            except Exception: continue
        return {"active_transmissions": active, "shock_count": len(active)}
    except Exception as e:
        return {"active_transmissions": [], "error": str(e)}
