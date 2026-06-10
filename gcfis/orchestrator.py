"""orchestrator.py — runs ALL 13 GCFIS layers + Entry, emits full per-ticker contract + master ranking.
Every layer degrades gracefully when its data isn't supplied (returns ok:False, never fabricates)."""
from __future__ import annotations
import pandas as pd
from .engines.fragility import run_fragility
from .engines.shock import run_shock
from .engines.forward_macro import run_forward_macro
from .engines.liquidity import run_liquidity
from .engines.flow import run_flow
from .engines.theme import run_theme
from .engines.bottleneck_engine import run_bottleneck
from .engines.crypto import run_crypto
from .engines.accumulation import run_accumulation
from .engines.positioning import run_positioning
from .engines.dealer import run_dealer
from .engines.broker_flow import run_broker_flow
from .engines.entry import run_entry
from .engines.leadlag_discovery import run_leadlag_discovery
from .engines.cross_asset import run_cross_asset
from .engines.narrative import build_reason
from .meta.regime_meta import run_regime_meta

def _ticker_theme(tkr, theme_baskets):
    for th, ts in (theme_baskets or {}).items():
        if tkr in ts: return th
    return ""

def run_gcfis(prices: dict, bench: pd.Series, regime_posterior: dict,
              systemic_inputs=None, growth_inputs=None, infl_inputs=None, liquidity_inputs=None,
              returns_matrix=None, index_returns=None, theme_baskets=None, bottleneck_nodes=None,
              crypto_inputs=None, etf_flows=None, options_chains=None, broker_flow_by_ticker=None,
              volumes=None, cot_by_ticker=None, leadlag_pairs=None, min_adv=0.0, cross_asset_snapshot=None):
    si = systemic_inputs or {}
    # --- SYSTEMIC / CONTEXT (L1-L6, L10) ---
    frag = run_fragility(si, returns_matrix, index_returns)
    shock = run_shock(si, index_returns)
    fwd = run_forward_macro(growth_inputs or {}, infl_inputs or {})
    liq = run_liquidity(liquidity_inputs or {})
    flow = run_flow(prices, bench, etf_flows)
    theme = run_theme(theme_baskets or {}, prices, bench) if theme_baskets else {"ok": False, "themes": {}}
    bott = run_bottleneck(bottleneck_nodes) if bottleneck_nodes else {"ok": False}
    crypto = run_crypto(crypto_inputs) if crypto_inputs else {"ok": False}
    cross = run_cross_asset(cross_asset_snapshot) if cross_asset_snapshot else {"ok": False, "regime": None, "defer_longs": False, "divergences": []}
    liq_score = liq.get("liquidity_regime", 50.0)
    systemic = {"fragility": frag.get("fragility", 0), "shock_prob": shock.get("shock_prob", 0),
                "liquidity_regime": liq_score, "forward_quad": fwd.get("forward_quad"),
                "cross_asset_regime": cross.get("regime")}

    # --- PER-TICKER (L7,L9,L8, broker) ---
    dealers = {}; per_ticker = {}
    for tkr, px in prices.items():
        a = run_accumulation(tkr, px, bench, volume=(volumes or {}).get(tkr))
        pos = run_positioning(tkr, **(cot_by_ticker.get(tkr, {}) if cot_by_ticker else {}))
        d = run_dealer((options_chains or {}).get(tkr), spot=float(px.iloc[-1])) if options_chains else {"ok": False, "gex_sign": 0, "regime": "unknown"}
        dealers[tkr] = d
        th = _ticker_theme(tkr, theme_baskets)
        a.update({"theme": th, "theme_score": theme.get("themes", {}).get(th, {}).get("strength", 0.0),
                  "dealer_sign": d.get("gex_sign", 0),
                  "cot_extreme_long": pos.get("extreme_long", False)})
        if pos.get("crowding") is not None: a["crowding"] = pos["crowding"]
        if broker_flow_by_ticker and tkr in broker_flow_by_ticker:
            bf = run_broker_flow(broker_flow_by_ticker[tkr], price_down=(px.iloc[-1] < px.iloc[-20] if len(px) > 20 else True))
            a["broker_sign"] = 1 if bf.get("verdict") == "NET_ACCUMULATION" else -1
            a["broker_verdict"] = bf.get("verdict", "")
        if (volumes or {}).get(tkr) is not None:
            a["adv"] = float((px * volumes[tkr]).tail(20).mean())
        per_ticker[tkr] = a

    # --- ASSET SELECTION (L12) ---
    ranking = run_regime_meta(per_ticker, systemic, regime_posterior, min_adv=min_adv)

    # --- ENTRY (L13) + cross-asset gate + reason narrative per signal ---
    longs, shorts, spots, deferred = [], [], [], []
    for sig in ranking["signals"]:
        if sig.direction in ("long", "short"):
            e = run_entry(prices[sig.ticker], sig.direction, dealer=dealers.get(sig.ticker), liquidity_score=liq_score)
            if e.get("ok"):
                sig.entry_type = e["entry_type"]; sig.entry_valid = e["valid"]; sig.gamma_regime = e["gamma_regime"]
                sig.entry_px = e["entry_px"]; sig.stop = e["stop"]; sig.target = e["target"]; sig.rr = e["rr"]
        # cross-asset gate: defer NEW longs during liquidation ('data good but price falling' guard)
        deferred_long = bool(cross.get("defer_longs") and sig.direction == "long"
                             and sig.action in ("BUILD_LONG", "START_SCALING"))
        if deferred_long:
            sig.entry_valid = False
        sig.reason = build_reason(sig, per_ticker[sig.ticker], systemic, cross)   # logical WHY + entry + defer note
        row = sig.as_dict()
        if deferred_long:
            deferred.append(row)
        elif sig.action == "BUILD_LONG" or (sig.action == "START_SCALING" and sig.direction == "long"):
            longs.append(row)
        elif sig.action == "BUILD_SHORT" or (sig.action == "START_SCALING" and sig.direction == "short"):
            shorts.append(row)
        if per_ticker[sig.ticker].get("sweet_spot") and sig.scores["meta_long"] >= 50 and not deferred_long:
            spots.append(row)
    longs.sort(key=lambda r: r["scores"]["meta_long"], reverse=True)
    shorts.sort(key=lambda r: r["scores"]["meta_short"], reverse=True)
    ll = run_leadlag_discovery(prices, candidate_pairs=leadlag_pairs) if len(prices) >= 2 else {"ok": False}
    return {"ok": True,
            "systemic": {"fragility": frag, "shock": shock, "forward_macro": fwd, "liquidity": liq,
                         "flow": flow, "theme": theme, "bottleneck": bott, "crypto": crypto, "cross_asset": cross},
            "ranking": {"regime_weights": ranking["regime_weights"], "systemic_stress": ranking["systemic_stress"],
                        "master_long": longs, "master_short": shorts, "master_spot": spots,
                        "deferred_longs": deferred},
            "leadlag": {k: v for k, v in ll.items() if k != "_engine"}, "per_ticker": per_ticker}
