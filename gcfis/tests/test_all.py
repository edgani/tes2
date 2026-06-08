"""Synthetic correctness suite — ALL 13 GCFIS layers + entry + end-to-end. Validates LOGIC."""
import numpy as np, pandas as pd, sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from gcfis.engines.change_detection import classify_series
from gcfis.engines.fragility import run_fragility
from gcfis.engines.shock import run_shock
from gcfis.engines.forward_macro import run_forward_macro
from gcfis.engines.liquidity import run_liquidity
from gcfis.engines.flow import run_flow
from gcfis.engines.theme import run_theme
from gcfis.engines.bottleneck_engine import run_bottleneck, bottleneck_score
from gcfis.engines.positioning import run_positioning
from gcfis.engines.crypto import run_crypto
from gcfis.engines.accumulation import run_accumulation
from gcfis.engines.broker_flow import run_broker_flow
from gcfis.engines.dealer import run_dealer
from gcfis.engines.entry import run_entry
from gcfis.orchestrator import run_gcfis

rng = np.random.default_rng(0); N = 400; idx = pd.bdate_range("2023-01-01", periods=N)
def S(v): return pd.Series(v, index=idx)
bench = S(100 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, N))))

def t_l1_fragility():
    hi = run_fragility({"credit": S(np.linspace(0,5,N)), "breadth": S(np.linspace(0,-5,N)), "vol": S(np.linspace(0,5,N))})
    lo = run_fragility({k: S(rng.normal(0,1,N)) for k in ("credit","breadth","vol")})
    assert hi["fragility"] > lo["fragility"] and hi["fragility"] > 70; print(f"  L1 fragility {hi['fragility']} vs {lo['fragility']}  OK")
def t_l2_forward_macro():
    up=np.cumsum(np.linspace(0,0.12,N)); dn=np.cumsum(np.linspace(0.12,0,N))
    r=run_forward_macro({"sox":S(up),"copper_gold":S(up*.9)},{"breakeven":S(dn)}); assert r["forward_quad"]=="Q1"; print(f"  L2 forward_macro quad={r['forward_quad']}  OK")
def t_l3_liquidity():
    r=run_liquidity({"fed_bs":S(np.linspace(8e6,8.5e6,N)),"tga":S(np.linspace(0.5e6,0.4e6,N)),"rrp":S(np.linspace(2e6,1e6,N))})
    assert r["ok"] and r["expanding"]; print(f"  L3 liquidity regime={r['liquidity_regime']} expanding={r['expanding']}  OK")
def t_l4_flow():
    px={"WIN":S(100*np.exp(np.cumsum(rng.normal(0.003,0.01,N)))),"LOSE":S(100*np.exp(np.cumsum(rng.normal(-0.003,0.01,N))))}
    r=run_flow(px,bench); assert "WIN" in r["rotating_in"]; print(f"  L4 flow in={r['rotating_in']} out={r['rotating_out']}  OK")
def t_l5_theme():
    px={"A":S(100*np.exp(np.cumsum(rng.normal(0.003,0.01,N)))),"B":S(100*np.exp(np.cumsum(rng.normal(0.002,0.01,N))))}
    r=run_theme({"AI":["A","B"]},px,bench); assert r["themes"]["AI"]["cohort_rs"]>0; print(f"  L5 theme AI rs={r['themes']['AI']['cohort_rs']}  OK")
def t_l6_bottleneck():
    assert bottleneck_score(.9,.9,.9,.9,0)==0 and bottleneck_score(.8,.8,.8,.8,.8)>.7
    r=run_bottleneck({"GPU":dict(scarcity=.9,demand_growth=.9,lead_time=.8,replace_diff=.9,pricing_power=.8),"COMMODITY":dict(scarcity=.3,demand_growth=.3,lead_time=.2,replace_diff=.1,pricing_power=.2)})
    assert r["tightest_bottleneck"]=="GPU"; print(f"  L6 bottleneck tightest={r['tightest_bottleneck']}  OK")
def t_l8_dealer():
    chain=pd.DataFrame([{"strike":100,"oi":5000,"iv":.3,"type":"C","T":.05},{"strike":100,"oi":800,"iv":.3,"type":"P","T":.05}])
    d=run_dealer(chain,100); assert d["gex_sign"]==1 and d["regime"]=="mean_reversion"
    assert run_dealer(None,100)["regime"]=="unknown"; print(f"  L8 dealer regime={d['regime']} (no-chain=unknown, not fabricated)  OK")
def t_l9_positioning():
    r=run_positioning("X",cot_net=S(np.r_[rng.normal(0,1,N-1),[10]])); assert r["extreme_long"]; print(f"  L9 positioning cot={r['cot_index']} extreme_long={r['extreme_long']}  OK")
def t_l10_crypto():
    r=run_crypto({"etf_flow":S(np.cumsum(rng.normal(0.05,0.1,N))),"funding":S(rng.normal(0,1,N))}); assert r["ok"]; print(f"  L10 crypto score={r['crypto_score']}  OK")
def t_l7_accumulation():
    px=S(100*np.exp(np.cumsum(rng.normal(0.002,0.012,N)))); vol=S(np.r_[rng.normal(1e6,1e5,N-60),rng.normal(2.2e6,2e5,60)])
    r=run_accumulation("T",px,bench,volume=vol); assert r["accumulation"]>0
    m=run_accumulation("M",S(100*np.exp(np.cumsum(np.r_[rng.normal(0.001,0.01,N-40),rng.normal(0.02,0.01,40)]))),bench,volume=vol,lev_etf_exists=True)
    assert m["stage"]=="RETAIL_MANIA" and m["exit_signal"]; print(f"  L7 accumulation acc={r['accumulation']} | mania exit={m['exit_signal']}  OK")
def t_broker():
    b=[{"broker":"AK","agg_buy":21000,"pass_buy":3700,"agg_sell":0,"pass_sell":0,"is_foreign":True},
       {"broker":"XA","agg_buy":0,"pass_buy":0,"agg_sell":5500,"pass_sell":34000},
       {"broker":"YP","agg_buy":0,"pass_buy":0,"agg_sell":1200,"pass_sell":0}]
    r=run_broker_flow(b); lab={x["broker"]:x["label"] for x in r["brokers"]}
    assert lab["AK"]=="BUILDING_LONG" and lab["XA"]=="DELIBERATE_SELLING" and lab["YP"]=="PANIC_SELLING"; print(f"  broker_flow {lab}  OK")
def t_l13_entry():
    up=S(100*np.exp(np.cumsum(rng.normal(0.0015,0.01,N))))
    e=run_entry(up,"long",dealer={"gex_sign":-1,"regime":"momentum"}); assert e["ok"] and e["entry_type"] in("BREAKOUT","CONTINUATION")
    bad=run_entry(up,"long",dealer={"gex_sign":1,"regime":"mean_reversion"}); assert not bad["valid"]  # gamma-aware reject
    print(f"  L13 entry: momentum->{e['entry_type']} rr={e['rr']} | posGamma breakout flagged invalid={not bad['valid']}  OK")
def t_end_to_end():
    strong=S(100*np.exp(np.cumsum(rng.normal(0.003,0.012,N)))); weak=S(100*np.exp(np.cumsum(rng.normal(-0.001,0.012,N))))
    vol=S(np.r_[rng.normal(1e6,1e5,N-60),rng.normal(2.5e6,2e5,60)])
    chain=pd.DataFrame([{"strike":float(strong.iloc[-1]),"oi":2000,"iv":.4,"type":"P","T":.05},{"strike":float(strong.iloc[-1])*1.05,"oi":3000,"iv":.4,"type":"P","T":.05}])  # put-heavy -> GEX<0 momentum
    out=run_gcfis({"STRONG":strong,"WEAK":weak},bench,{"risk_on":0.8,"chop":0.2},
                  systemic_inputs={"credit":S(rng.normal(0,1,N)),"vol":S(rng.normal(0,1,N))},
                  growth_inputs={"sox":S(np.cumsum(rng.normal(0.02,0.1,N)))}, infl_inputs={"breakeven":S(np.cumsum(rng.normal(0,0.1,N)))},
                  theme_baskets={"AI":["STRONG"]}, options_chains={"STRONG":chain}, volumes={"STRONG":vol,"WEAK":vol},
                  bottleneck_nodes={"GPU":dict(scarcity=.9,demand_growth=.9,lead_time=.8,replace_diff=.9,pricing_power=.8)})
    assert out["ok"]
    longs=out["ranking"]["master_long"]; assert len(longs)>=1, "expected STRONG as a long"
    top=longs[0]; assert top["entry_type"] and top["rr"]>=0 and top["gamma_regime"] in ("momentum","mean_reversion","unknown")
    print(f"  E2E: quad={out['systemic']['forward_macro']['forward_quad']} | {top['ticker']} {top['action']} "
          f"entry={top['entry_type']} rr={top['rr']} stop={top['stop']} gamma={top['gamma_regime']} | "
          f"bottleneck={out['systemic']['bottleneck'].get('tightest_bottleneck')}  OK")

if __name__ == "__main__":
    print("GCFIS full suite (13 layers + entry + e2e)"); print("-"*64)
    for fn in (t_l1_fragility,t_l2_forward_macro,t_l3_liquidity,t_l4_flow,t_l5_theme,t_l6_bottleneck,
               t_l7_accumulation,t_l8_dealer,t_l9_positioning,t_l10_crypto,t_broker,t_l13_entry,t_end_to_end):
        fn()
    print("-"*64); print("ALL TESTS PASSED")
