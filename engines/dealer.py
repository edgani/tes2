"""dealer.py — L8 Dealer Engine. REAL signed GEX/Vanna/Charm from an options chain (Black-Scholes).
Sign convention (SqueezeMetrics/SpotGamma): dealers long calls / short puts.
  GEX>0 -> dealers long gamma -> sell rallies/buy dips -> MEAN-REVERSION regime
  GEX<0 -> dealers short gamma -> amplify -> MOMENTUM / crash-accelerant regime
No chain -> {ok:False, regime:'unknown'} (NEVER fabricates greeks from price)."""
from __future__ import annotations
import numpy as np, pandas as pd
from scipy.stats import norm

def _bs_gamma(S, K, T, sigma, r=0.04):
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    return float(norm.pdf(d1) / (S * sigma * np.sqrt(T)))

def _bs_vanna(S, K, T, sigma, r=0.04):
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return float(-norm.pdf(d1) * d2 / sigma)

def _bs_charm(S, K, T, sigma, r=0.04):
    """Charm = ∂Δ/∂t (delta decay per year). Call convention; dealer sign applied outside."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return float(-norm.pdf(d1) * (2 * r * T - d2 * sigma * np.sqrt(T)) / (2 * T * sigma * np.sqrt(T)))

def run_dealer(chain: pd.DataFrame | None, spot: float, r: float = 0.04) -> dict:
    """chain columns: strike, oi, iv, type ('C'/'P'), T (years to expiry)."""
    if chain is None or len(chain) == 0 or not spot:
        return {"ok": False, "regime": "unknown", "reason": "no options chain (greeks NOT fabricated)"}
    gex = 0.0; vanna = 0.0; charm = 0.0; net_gamma = 0.0; net_by_strike = {}
    calls, puts = {}, {}
    for _, row in chain.iterrows():
        K, oi, iv, typ, T = row["strike"], row["oi"], row["iv"], str(row["type"]).upper()[0], row["T"]
        g = _bs_gamma(spot, K, T, iv, r); va = _bs_vanna(spot, K, T, iv, r); ch = _bs_charm(spot, K, T, iv, r)
        dollar_gamma = oi * g * 100 * spot**2 * 0.01
        sign = 1.0 if typ == "C" else -1.0          # dealer long calls / short puts
        gex += sign * dollar_gamma; vanna += sign * oi * va * 100
        charm += sign * oi * ch * 100; net_gamma += sign * oi * g * 100
        net_by_strike[K] = net_by_strike.get(K, 0.0) + sign * dollar_gamma
        (calls if typ == "C" else puts)[K] = (calls if typ == "C" else puts).get(K, 0) + oi
    # zero-gamma flip: strike where cumulative net gamma crosses zero
    ks = sorted(net_by_strike); cum = np.cumsum([net_by_strike[k] for k in ks])
    flip = next((ks[i] for i in range(len(ks)) if cum[i] >= 0), spot) if len(ks) else spot
    regime = "mean_reversion" if gex > 0 else "momentum"
    return {"ok": True, "gex": round(gex, 1), "gex_sign": int(np.sign(gex)), "regime": regime,
            "gamma": round(net_gamma, 2), "gamma_flip": round(float(flip), 2),
            "call_wall": (max(calls, key=calls.get) if calls else None),
            "put_wall": (max(puts, key=puts.get) if puts else None),
            "vanna": round(vanna, 1), "charm": round(charm, 1)}
