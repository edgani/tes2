"""Synthetic correctness tests — validate LOGIC (not market alpha). All must PASS."""
import numpy as np, pandas as pd, sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from gcfis.engines.change_detection import classify_series
from gcfis.engines.fragility import run_fragility
from gcfis.engines.shock import run_shock
from gcfis.engines.forward_macro import run_forward_macro
from gcfis.engines.accumulation import run_accumulation
from gcfis.engines.broker_flow import run_broker_flow
from gcfis.orchestrator import run_gcfis

rng = np.random.default_rng(0)
N = 400; idx = pd.bdate_range("2023-01-01", periods=N)
def series(vals): return pd.Series(vals, index=idx)

def t_change_detection():
    accel = series(np.cumsum(np.linspace(0, 2, N)) + np.cumsum(rng.normal(0, 0.1, N)))  # accelerating up
    r = classify_series(accel)
    assert r["state"] in ("ACCELERATING_UP", "RECOVERING"), r
    decel = series(np.cumsum(np.linspace(2, -2, N)))  # rising then rolling over
    print("  change_detection:", r["state"], "| decel:", classify_series(decel)["state"], "OK")

def t_fragility():
    stress = {"credit": series(np.linspace(0, 5, N)), "breadth": series(np.linspace(0, -5, N)),
              "vol": series(np.linspace(0, 5, N)), "funding": series(np.linspace(0, 4, N))}
    calm = {k: series(rng.normal(0, 1, N)) for k in ("credit", "breadth", "vol", "funding")}
    hi = run_fragility(stress); lo = run_fragility(calm)
    assert hi["fragility"] > lo["fragility"] and hi["fragility"] > 70, (hi, lo)
    print(f"  fragility: stress={hi['fragility']} ({hi['label']}) vs calm={lo['fragility']}  OK")

def t_shock():
    stress = {"vix_ts": series(np.linspace(0, 5, N)), "hy_oas": series(np.linspace(0, 5, N)),
              "move": series(np.linspace(0, 4, N))}
    calm = {k: series(rng.normal(0, 1, N)) for k in ("vix_ts", "hy_oas", "move")}
    hi = run_shock(stress); lo = run_shock(calm)
    assert hi["shock_prob"] > lo["shock_prob"] and hi["shock_prob"] > 70, (hi, lo)
    print(f"  shock: stress P={hi['shock_prob']} vs calm P={lo['shock_prob']}  OK")

def t_forward_macro():
    # quad is set by GROC/IROC (Δz = acceleration), NOT level. Build accelerating growth (convex up)
    # + decelerating inflation (concave, flattening) so GROC>0, IROC<0 deterministically -> Q1.
    accel_up = np.cumsum(np.linspace(0.0, 0.12, N))     # increments grow -> recent change rising
    decel    = np.cumsum(np.linspace(0.12, 0.0, N))     # increments shrink -> recent change falling
    up = {"sox": series(accel_up), "copper_gold": series(accel_up * 0.9), "smallcap_ratio": series(accel_up * 1.1)}
    r = run_forward_macro(up, {"breakeven": series(decel)})
    assert r["GROC"] > 0 and r["IROC"] < 0 and r["forward_quad"] == "Q1", r
    print(f"  forward_macro: MIFG={r['MIFG']} GROC={r['GROC']} IROC={r['IROC']} quad={r['forward_quad']} ({r['quad_name']})  OK")

def t_accumulation():
    bench = series(100 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, N))))
    # outperformer with rising vol, low crowding -> sweet spot / smart_money
    px = series(100 * np.exp(np.cumsum(rng.normal(0.002, 0.012, N))))
    vol = series(np.r_[rng.normal(1e6, 1e5, N - 60), rng.normal(2.2e6, 2e5, 60)])
    r = run_accumulation("TEST", px, bench, volume=vol)
    assert r["accumulation"] > 0, r
    # mania: parabolic + lev etf -> RETAIL_MANIA + exit
    para = series(100 * np.exp(np.cumsum(np.r_[rng.normal(0.001, 0.01, N - 40), rng.normal(0.02, 0.01, 40)])))
    m = run_accumulation("MANIA", para, bench, volume=vol, lev_etf_exists=True)
    assert m["stage"] == "RETAIL_MANIA" and m["exit_signal"], m
    print(f"  accumulation: acc={r['accumulation']} stage={r['stage']} sweet={r['sweet_spot']} | mania={m['stage']} exit={m['exit_signal']}  OK")

def t_broker_flow():
    # HUMI-like: foreign aggressive buyer building, domestic big two-sided seller distributing, tiny retail panic
    brokers = [
        {"broker": "AK", "agg_buy": 21000, "pass_buy": 3700, "agg_sell": 0, "pass_sell": 0, "is_foreign": True},
        {"broker": "XA", "agg_buy": 0, "pass_buy": 0, "agg_sell": 5500, "pass_sell": 34000, "is_foreign": False},
        {"broker": "YP", "agg_buy": 0, "pass_buy": 0, "agg_sell": 1200, "pass_sell": 0, "is_foreign": False},
        {"broker": "XL", "agg_buy": 0, "pass_buy": 5100, "agg_sell": 2100, "pass_sell": 0, "is_foreign": False},
    ]
    r = run_broker_flow(brokers, price_down=True)
    lab = {b["broker"]: b["label"] for b in r["brokers"]}
    assert lab["AK"] == "BUILDING_LONG", lab
    assert lab["XA"] == "DELIBERATE_SELLING", lab
    assert lab["YP"] == "PANIC_SELLING", lab
    print(f"  broker_flow: {lab} | verdict={r['verdict']}  OK")

def t_orchestrator_end_to_end():
    bench = series(100 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, N))))
    prices = {f"T{i}": series(100 * np.exp(np.cumsum(rng.normal(0.001 * (i - 1), 0.012, N)))) for i in range(4)}
    out = run_gcfis(prices, bench, regime_posterior={"risk_on": 0.7, "chop": 0.3},
                    systemic_inputs={"credit": series(rng.normal(0, 1, N)), "vol": series(rng.normal(0, 1, N))},
                    growth_inputs={"sox": series(np.cumsum(rng.normal(0.02, 0.1, N)))},
                    infl_inputs={"breakeven": series(np.cumsum(rng.normal(0.0, 0.1, N)))})
    assert out["ok"] and out["ranking"]["ok"]
    print(f"  orchestrator: quad={out['systemic']['forward_macro']['forward_quad']} "
          f"frag={out['systemic']['fragility'].get('fragility')} "
          f"longs={len(out['ranking']['master_long'])} shorts={len(out['ranking']['master_short'])}  OK")

if __name__ == "__main__":
    print("GCFIS synthetic correctness suite")
    print("-" * 60)
    for fn in (t_change_detection, t_fragility, t_shock, t_forward_macro,
               t_accumulation, t_broker_flow, t_orchestrator_end_to_end):
        fn()
    print("-" * 60)
    print("ALL TESTS PASSED")
