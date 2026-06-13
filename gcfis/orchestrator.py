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
from .engines.bottleneck_engine import run_bottleneck, run_bottleneck_migration
from .engines.crypto import run_crypto
from .engines.accumulation import run_accumulation
from .engines.positioning import run_positioning
from .engines.dealer import run_dealer
from .engines.broker_flow import run_broker_flow
from .engines.reflexivity import run_reflexivity
from .engines.entry import run_entry
from .engines.flow_type import run_flow_type
from .engines.market_mode import run_market_mode
from .engines.elimination import run_elimination
from .engines.response_zone import run_response_zone
from .engines.internals import run_internals, run_horizon
from .engines.surge import run_surge
from .engines.crash_bottom import run_crash_bottom
from .meta.final_desk import build_final_desk
from .meta.decision_stack import build_decision_stack
from .engines.leadlag_discovery import run_leadlag_discovery
from .engines.rotation import run_rotation
from .engines.portfolio import run_portfolio
from .engines.cross_asset import run_cross_asset
from .engines.narrative import build_reason
from .meta.regime_meta import run_regime_meta
from .core.change_core import delta_z as _dz, last as _last
from .markets import market_of, is_long_only
import numpy as np

def _ticker_theme(tkr, theme_baskets):
    for th, ts in (theme_baskets or {}).items():
        if tkr in ts: return th
    return ""

def run_gcfis(prices: dict, bench: pd.Series, regime_posterior: dict,
              systemic_inputs=None, growth_inputs=None, infl_inputs=None, liquidity_inputs=None,
              returns_matrix=None, index_returns=None, theme_baskets=None, bottleneck_nodes=None,
              crypto_inputs=None, etf_flows=None, options_chains=None, broker_flow_by_ticker=None,
              volumes=None, cot_by_ticker=None, leadlag_pairs=None, min_adv=0.0, cross_asset_snapshot=None,
              ticker_node_map=None, subthemes=None,
              earnings_rev_by_ticker=None, inst_own_by_ticker=None, etf_flow_by_ticker=None,
              options_oi_by_ticker=None, social_by_ticker=None, short_int_by_ticker=None, lev_etf_set=None,
              leadlag_cfg=None, dealer_by_ticker=None, bottleneck_node_history=None, market_hints=None, driver_data=None, typef_by_ticker=None, confluence_min=55.0):
    si = systemic_inputs or {}
    # --- SYSTEMIC / CONTEXT (L1-L6, L10) ---
    frag = run_fragility(si, returns_matrix, index_returns)
    shock = run_shock(si, index_returns)
    fwd = run_forward_macro(growth_inputs or {}, infl_inputs or {})
    liq = run_liquidity(liquidity_inputs or {})
    flow = run_flow(prices, bench, etf_flows)
    theme = run_theme(theme_baskets or {}, prices, bench) if theme_baskets else {"ok": False, "themes": {}}
    bott = run_bottleneck(bottleneck_nodes) if bottleneck_nodes else {"ok": False}
    bott_mig = run_bottleneck_migration(bottleneck_node_history) if bottleneck_node_history else {"ok": False}
    crypto = run_crypto(crypto_inputs) if crypto_inputs else {"ok": False}
    cross = run_cross_asset(cross_asset_snapshot) if cross_asset_snapshot else {"ok": False, "regime": None, "defer_longs": False, "divergences": []}
    liq_score = liq.get("liquidity_regime", 50.0)
    systemic = {"fragility": frag.get("fragility", 0), "shock_prob": shock.get("shock_prob", 0),
                "liquidity_regime": liq_score, "forward_quad": fwd.get("forward_quad"),
                "cross_asset_regime": cross.get("regime")}

    # --- STAGE-1 ELIMINATION (doc 3): buang sampah sebelum scoring ---
    eliminated = []
    kept = {}
    for _tkr, _px in prices.items():
        _el = run_elimination(_px, (volumes or {}).get(_tkr), min_adv=min_adv)
        if _el.get("eliminated"):
            eliminated.append({"ticker": _tkr, "reasons": _el.get("reasons", [])})
        else:
            kept[_tkr] = _px
    prices = kept

    # --- PER-TICKER (L7,L9,L8,B5, broker, flow, mode, response) ---
    bott_scores = bott.get("scores", {}) if bott.get("ok") else {}
    node_map = dict(bott.get("ticker_node", {})) if bott.get("ok") else {}
    if ticker_node_map: node_map.update(ticker_node_map)
    dealers = {}; per_ticker = {}
    for tkr, px in prices.items():
        a = run_accumulation(tkr, px, bench, volume=(volumes or {}).get(tkr),
                             earnings_rev=(earnings_rev_by_ticker or {}).get(tkr),
                             inst_own=(inst_own_by_ticker or {}).get(tkr),
                             options_oi=(options_oi_by_ticker or {}).get(tkr),
                             social=(social_by_ticker or {}).get(tkr),
                             short_int=(short_int_by_ticker or {}).get(tkr),
                             lev_etf_exists=(tkr in (lev_etf_set or set())))
        pos = run_positioning(tkr, **(cot_by_ticker.get(tkr, {}) if cot_by_ticker else {}))
        if dealer_by_ticker and tkr in dealer_by_ticker:
            d = dealer_by_ticker[tkr]                      # use v40's already-computed GEX/walls (flagged real vs proxy)
        elif options_chains:
            d = run_dealer((options_chains or {}).get(tkr), spot=float(px.iloc[-1]))
        else:
            d = {"ok": False, "gex_sign": 0, "regime": "unknown"}
        refl = run_reflexivity(px, volume=(volumes or {}).get(tkr))
        dealers[tkr] = d
        th = _ticker_theme(tkr, theme_baskets)
        a.update({"theme": th, "subtheme": (subthemes or {}).get(tkr, ""),
                  "theme_score": theme.get("themes", {}).get(th, {}).get("strength", 0.0) if theme.get("ok") else None,
                  "dealer_sign": d.get("gex_sign", 0), "cot_extreme_long": pos.get("extreme_long", False),
                  "cot_index": pos.get("cot_index"), "positioning_oi_roc": pos.get("oi_roc_z"),
                  "reflexivity": refl.get("reflexivity") if refl.get("ok") else None,
                  "runaway": bool(refl.get("runaway", False))})
        node = node_map.get(tkr)
        if node and node in bott_scores:
            a["bottleneck_score"] = bott_scores[node]; a["bottleneck_node"] = node
        if pos.get("crowding") is not None: a["crowding"] = pos["crowding"]
        if broker_flow_by_ticker and tkr in broker_flow_by_ticker:
            bf = run_broker_flow(broker_flow_by_ticker[tkr], price_down=(px.iloc[-1] < px.iloc[-20] if len(px) > 20 else True))
            a["broker_sign"] = 1 if bf.get("verdict") == "NET_ACCUMULATION" else -1
            a["broker_verdict"] = bf.get("verdict", "")
        if (volumes or {}).get(tkr) is not None:
            a["adv"] = float((px * volumes[tkr]).tail(20).mean())
        a["market"] = market_of(tkr, (market_hints or {}).get(tkr))
        flw = run_flow_type(px, (volumes or {}).get(tkr))
        a["flow"] = flw
        a["flow01"] = flw.get("flow01") if flw.get("ok") else None
        a["market_mode"] = run_market_mode(px, dealer=d, flow=flw, crowding=a.get("crowding", 50.0),
                                            adoption_velocity=a.get("adoption_velocity", 0.0))
        a["response"] = run_response_zone(px)
        a["dealer"] = d
        a["horizon"] = run_horizon(px)
        # BandarMetrics REDESIGN (IDX only, needs Type-F fb/fs): regime-conditioned flow replaces the proxy
        if a["market"] == "idx" and typef_by_ticker and tkr in typef_by_ticker:
            try:
                from .engines.flow_regime import FlowRegimeEngine
                bm = FlowRegimeEngine(typef_by_ticker[tkr]).latest()
                a["bm"] = bm
                try:
                    _pf = bm.compute().tail(260)
                    a["bm"]["series_real"] = {"index": [d.strftime("%Y-%m-%d") for d in _pf.index],
                        "close": [float(x) for x in _pf["close_px"]], "lpm": [float(x) for x in _pf["lpm"]],
                        "ff_cum": [float(x) for x in _pf["ff_cum"]], "ff_net": [float(x) for x in _pf["ff_net"]],
                        "intensity": [float(x) for x in _pf["intensity"]]}
                except Exception:
                    pass
                a["bm"]["false_accum"] = bool(float(a["bm"].get("lpm_slope_z", 0) or 0) > 0.5 and float(a["bm"].get("liq_expand", 1) or 1) < 0.98)
                a["bm"]["participation"] = a["bm"].get("breadth")
                a["flow01"] = float(np.clip(0.5 + (bm["flow_score"] / 200.0) * bm["confidence"], 0.0, 1.0))
                if a.get("broker_sign", 0) == 0:
                    a["broker_sign"] = 1 if bm["flow_score"] > 20 else -1 if bm["flow_score"] < -20 else 0
            except Exception:
                a["bm"] = {"regime": "ERROR"}
        per_ticker[tkr] = a

    # --- LEAD-LAG (LX) + ROTATION: wire the moat INTO selection (was decorative) ---
    ll = run_leadlag_discovery(prices, candidate_pairs=leadlag_pairs, **(leadlag_cfg or {})) if len(prices) >= 2 else {"ok": False, "edges": []}
    rotation = run_rotation(ll.get("edges", []), prices)
    for f, sigrot in rotation.items():
        if f in per_ticker:
            per_ticker[f]["rotation"] = sigrot
            per_ticker[f]["rotation_strength"] = sigrot["strength"]

    # --- ASSET SELECTION (L12) ---
    ranking = run_regime_meta(per_ticker, systemic, regime_posterior, min_adv=min_adv, confluence_min=confluence_min)

    # --- ENTRY (L13) + cross-asset gate + full contract attach + reason per signal ---

    shock_p = shock.get("shock_prob", 0) if shock.get("ok") else 0
    frag_v = frag.get("fragility", 0) if frag.get("ok") else 0
    longs, shorts, spots, deferred, avoided = [], [], [], [], []
    for sig in ranking["signals"]:
        px = prices[sig.ticker]; p = float(px.iloc[-1])
        mkt = market_of(sig.ticker, (market_hints or {}).get(sig.ticker))
        lo = is_long_only(sig.ticker, (market_hints or {}).get(sig.ticker))
        if sig.direction in ("long", "short"):
            e = run_entry(px, sig.direction, dealer=dealers.get(sig.ticker), liquidity_score=liq_score, long_only=lo)
            if e.get("ok"):
                sig.entry_type = e["entry_type"]; sig.entry_valid = e["valid"]; sig.gamma_regime = e["gamma_regime"]
                sig.entry_px = e["entry_px"]; sig.stop = e["stop"]; sig.target = e["target"]; sig.rr = e["rr"]
        # options panel (real GEX/gamma/walls/vanna/charm or unknown — never fabricated)
        d = dealers.get(sig.ticker, {})
        sig.options = {"call_wall": d.get("call_wall"), "put_wall": d.get("put_wall"), "gex": d.get("gex"),
                       "gex_sign": d.get("gex_sign", 0), "gamma": d.get("gamma"), "gamma_flip": d.get("gamma_flip"),
                       "vanna": d.get("vanna"), "charm": d.get("charm"), "is_real": bool(d.get("ok"))}
        # macro context stamped per ticker
        sig.macro = {"quad": systemic.get("forward_quad"), "liquidity_regime": liq_score,
                     "fragility": frag_v, "shock_prob": shock_p, "cross_asset_regime": cross.get("regime"),
                     "market": mkt}
        sig.shock_prob = shock_p
        a = per_ticker[sig.ticker]
        # complete Scores panel (liquidity/dealer/positioning) — full GCFIS Scores contract
        sig.scores["liquidity"] = round(liq_score, 1)
        sig.scores["dealer"] = d.get("gex_sign", 0)
        if a.get("cot_index") is not None: sig.scores["positioning"] = a.get("cot_index")
        # institutional detail (revision/ownership_Δ/etf_flow surface when data supplied)
        er = (earnings_rev_by_ticker or {}).get(sig.ticker)
        own = (inst_own_by_ticker or {}).get(sig.ticker)
        etf = (etf_flow_by_ticker or {}).get(sig.ticker)
        sig.institutional = {"adoption_stage": a.get("stage"), "crowding": a.get("crowding"),
                             "adoption_velocity": a.get("adoption_velocity"), "bottleneck_node": a.get("bottleneck_node"),
                             "revision": (round(_last(_dz(er)), 2) if er is not None else None),
                             "ownership_delta": (round(_last(_dz(own)), 2) if own is not None else None),
                             "etf_flow": (round(_last(etf), 2) if etf is not None else None)}
        # Opportunity scenarios (vol-scaled price fan, ~1Q horizon)
        move = float(px.pct_change().tail(63).std() or 0.02) * np.sqrt(63)
        sig.opportunity = {"bear": round(p * (1 - 1.0 * move), 2), "base": round(p * (1 + 0.4 * move), 2),
                           "bull": round(p * (1 + 1.5 * move), 2), "supercycle": round(p * (1 + 3.5 * move), 2)}
        sig.rotation = a.get("rotation", {})              # lead-lag rotation timing (if primed by a fired leader)
        sig.market = mkt
        sig.response = a.get("response", {})
        sig.bm = a.get("bm", {})
        sig.surge = (a.get("surge") or {}).get("score")
        build_decision_stack(sig, a)                       # doc 6: SO WHAT DO I DO NOW
        try:
            if sig.entry_valid and sig.entry and sig.stop and sig.target and sig.entry > 0:
                _p = float(sig.conviction) / 100.0
                sig.ev = round(100.0 * (_p * abs(sig.target - sig.entry) - (1 - _p) * abs(sig.entry - sig.stop)) / sig.entry, 2)
        except Exception:
            sig.ev = None
        # cross-asset gate: defer NEW longs during liquidation ('data good but price falling' guard)
        deferred_long = bool(cross.get("defer_longs") and sig.direction == "long"
                             and sig.action in ("BUILD_LONG", "START_SCALING"))
        if deferred_long:
            sig.entry_valid = False
        # LONG-ONLY ENFORCEMENT (doc 5): a buy-only market (IDX) can't short — a bearish/distribution
        # read becomes AVOID/REDUCE, never a tradeable short with a target below entry.
        if lo and (sig.action == "BUILD_SHORT" or sig.direction == "short"):
            sig.action = "AVOID"; sig.direction = "none"; sig.entry_type = "AVOID"; sig.entry_valid = False
            sig.reason = f"long-only ({mkt}): distribution/bearish — reduce if holding, no short. " + (sig.reason or "")
            build_decision_stack(sig, a)                   # re-stack as REDUCE_AVOID
            avoided.append(sig.as_dict()); continue
        sig.reason = build_reason(sig, a, systemic, cross)
        row = sig.as_dict()
        if deferred_long:
            deferred.append(row)
        elif sig.action == "BUILD_LONG" or (sig.action == "START_SCALING" and sig.direction == "long"):
            longs.append(row)
        elif sig.action == "BUILD_SHORT" or (sig.action == "START_SCALING" and sig.direction == "short"):
            shorts.append(row)
        if a.get("sweet_spot") and sig.scores["meta_long"] >= 50 and not deferred_long:
            spots.append(row)
    longs.sort(key=lambda r: r["scores"]["meta_long"], reverse=True)
    shorts.sort(key=lambda r: r["scores"]["meta_short"], reverse=True)
    # --- PORTFOLIO GUARD: are the longs actually ONE bet? scale correlated clusters ---
    pf = run_portfolio([r["ticker"] for r in longs], prices)
    for r in longs:
        r["alloc_mult"] = pf.get("alloc_mult", {}).get(r["ticker"], 1.0)
        if r.get("execution"):
            r["execution"]["size_x"] = round(min(1.0, r.get("conviction", 0) / 100.0) * r["alloc_mult"], 2)
    def _cat(rows, c): return [r for r in rows if r.get("category") == c]
    sections = {"early_monsters": _cat(longs, "STRUCTURAL_LONG"),
                "tactical_momentum": _cat(longs, "TACTICAL_MOMENTUM"),
                "squeeze": _cat(longs, "SQUEEZE"),
                "mean_reversion": _cat(longs, "MEAN_REVERSION"),
                "distribution_warning": shorts + avoided}
    from .market_drivers import read_all as _read_drivers
    drivers = _read_drivers(driver_data)
    internals = run_internals(prices, bench)
    for _t, _a in per_ticker.items():
        _a["surge"] = run_surge(_a, systemic, internals)
    crash = run_crash_bottom(systemic, internals, per_ticker)
    return {"ok": True, "drivers": drivers, "internals": internals, "crash": crash, "systemic_flat": systemic, "final_desk": build_final_desk(ranking, per_ticker, regime_posterior),
            "systemic": {"fragility": frag, "shock": shock, "forward_macro": fwd, "liquidity": liq,
                         "flow": flow, "theme": theme, "bottleneck": bott, "bottleneck_migration": bott_mig, "crypto": crypto, "cross_asset": cross},
            "ranking": {"regime_weights": ranking["regime_weights"], "systemic_stress": ranking["systemic_stress"],
                        "master_long": longs, "master_short": shorts, "master_spot": spots,
                        "deferred_longs": deferred, "avoided_long_only": avoided, "portfolio": pf,
                        "sections": sections, "eliminated": eliminated},
            "leadlag": {k: v for k, v in ll.items() if k != "_engine"},
            "rotation": rotation, "per_ticker": per_ticker}
