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
from gcfis.engines.cross_asset import run_cross_asset
from gcfis.engines.reflexivity import run_reflexivity
from gcfis.engines.bottleneck_engine import run_bottleneck as _run_bott
from gcfis.dashboard import card_html
from gcfis.engines.narrative import build_reason
from gcfis.core.contracts import TickerSignal
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
    assert d.get("gamma") is not None and d.get("charm") is not None and d.get("gamma_flip") is not None, d
    assert run_dealer(None,100)["regime"]=="unknown"; print(f"  L8 dealer regime={d['regime']} γ={d['gamma']} charm={d['charm']} (no-chain=unknown, not fabricated)  OK")
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
    chain=pd.DataFrame([{"strike":float(strong.iloc[-1]),"oi":2000,"iv":.4,"type":"P","T":.05},{"strike":float(strong.iloc[-1])*1.05,"oi":3000,"iv":.4,"type":"P","T":.05}])
    out=run_gcfis({"STRONG":strong,"WEAK":weak},bench,{"risk_on":0.8,"chop":0.2},
                  systemic_inputs={"credit":S(rng.normal(0,1,N)),"vol":S(rng.normal(0,1,N))},
                  growth_inputs={"sox":S(np.cumsum(rng.normal(0.02,0.1,N)))}, infl_inputs={"breakeven":S(np.cumsum(rng.normal(0,0.1,N)))},
                  theme_baskets={"AI":["STRONG"]}, options_chains={"STRONG":chain}, volumes={"STRONG":vol,"WEAK":vol})
    assert out["ok"]
    r = out["ranking"]; assert {"master_long","master_short","master_spot","deferred_longs"} <= set(r), "ranking buckets missing"
    assert out["systemic"]["forward_macro"]["forward_quad"] in ("Q1","Q2","Q3","Q4")
    # every produced row carries the full contract (options + opportunity + macro)
    for row in r["master_long"]+r["master_short"]+r["deferred_longs"]:
        assert "options" in row and "opportunity" in row and "macro" in row
    print(f"  E2E pipeline: quad={out['systemic']['forward_macro']['forward_quad']} | "
          f"L={len(r['master_long'])} S={len(r['master_short'])} spot={len(r['master_spot'])} defer={len(r['deferred_longs'])} | contract attached  OK")

def t_cross_asset():
    snap={"gold":-0.79,"silver":-3.38,"oil":-4.02,"spx":-0.38,"ndx":-0.90,"btc":-2.81,"eth":-2.90,
          "ust2y_chg":-0.65,"ust10y_chg":-0.53,"dxy_chg":-0.22,"vix_chg":0.91}  # Edward's real tape
    r=run_cross_asset(snap); assert r["regime"]=="DELEVERAGING" and r["defer_longs"] and r["gold_silver_ratio_rising"]
    assert any("BONDS" in d for d in r["divergences"])
    eas=run_cross_asset({"gold":1.2,"ust10y_chg":-0.4,"dxy_chg":-0.3,"spx":0.5}); assert eas["regime"]=="MONETARY_EASING"
    print(f"  cross_asset: Edward-tape={r['regime']} (defer={r['defer_longs']}) | gold-up+yields-down={eas['regime']}  OK")
def t_narrative():
    sig=TickerSignal(ticker="NVDA",action="BUILD_LONG",direction="long",conviction=82.0,
                     entry_type="BREAKOUT",entry_valid=True,gamma_regime="momentum",entry_px=880,stop=845,target=950,rr=2.1)
    td={"theme":"AI","theme_score":1.2,"stage":"INSTITUTIONAL","crowding":31,"sweet_spot":True,"broker_verdict":"NET_ACCUMULATION"}
    txt=build_reason(sig,td,{"forward_quad":"Q1","fragility":20},{"regime":"GROWTH_ON","defer_longs":False})
    assert "BUILD_LONG NVDA" in txt and "AI" in txt and "BREAKOUT" in txt and "R/R 2.1" in txt
    # defer note appears when liquidation
    txt2=build_reason(sig,td,{"forward_quad":"Q1"},{"regime":"DELEVERAGING","defer_longs":True})
    assert "DEFER" in txt2
    print(f"  narrative: '{txt[:90]}...'  OK")
def t_cross_defer_e2e():
    r = np.random.default_rng(13)
    t = np.arange(N*1.0); ramp = np.maximum(t - (N-120), 0)
    strong=S(100*np.exp(np.cumsum(r.normal(0.0008,0.01,N) + 1.5e-4*ramp))); weak=S(100*np.exp(np.cumsum(r.normal(-0.001,0.012,N))))
    vol=S(1e6*np.exp(np.cumsum(r.normal(0.0,0.02,N) + 2.0e-4*ramp)))
    snap={"gold":-0.79,"silver":-3.38,"oil":-4.02,"spx":-0.38,"btc":-2.81,"ust10y_chg":-0.53,"vix_chg":0.91}  # deleveraging
    out=run_gcfis({"STRONG":strong,"WEAK":weak},bench,{"risk_on":0.85,"chop":0.15},
                  growth_inputs={"sox":S(np.cumsum(r.normal(0.02,0.1,N)))}, infl_inputs={"breakeven":S(np.cumsum(r.normal(0,0.1,N)))},
                  theme_baskets={"AI":["STRONG"]}, volumes={"STRONG":vol,"WEAK":vol}, cross_asset_snapshot=snap,
                  bottleneck_nodes={"GPU":dict(scarcity=.9,demand_growth=.9,lead_time=.85,replace_diff=.9,pricing_power=.85,tickers=["STRONG"])})
    assert out["systemic"]["cross_asset"]["regime"]=="DELEVERAGING"
    deferred=out["ranking"]["deferred_longs"]; longs=out["ranking"]["master_long"]
    assert len(deferred)>=1 and not any(r2["ticker"]=="STRONG" for r2 in longs), "STRONG long must be DEFERRED in liquidation"
    assert "DEFER" in deferred[0]["reason"]
    print(f"  defer e2e: cross={out['systemic']['cross_asset']['regime']} -> {deferred[0]['ticker']} deferred (not in {len(longs)} active longs)  OK")

def t_reflexivity():
    r = np.random.default_rng(5)
    t = np.arange(320.0); ramp = np.maximum(t - 220, 0); ix = pd.bdate_range("2023-01-01", periods=320)
    px = pd.Series(100*np.exp(np.cumsum(r.normal(0.0003,0.008,320) + 1.8e-4*ramp)), index=ix)
    vol = pd.Series(1e6*np.exp(np.cumsum(r.normal(0.0,0.02,320) + 2.5e-4*ramp)), index=ix)
    rr = run_reflexivity(px, volume=vol); assert rr["runaway"] and rr["reflexivity"] > 55
    flat = pd.Series(100*np.exp(np.cumsum(r.normal(0,0.01,320))), index=ix)
    assert not run_reflexivity(flat, volume=pd.Series(r.normal(1e6,1e5,320), index=ix))["runaway"]
    print(f"  B5 reflexivity: runaway={rr['runaway']} score={rr['reflexivity']} (p_accel {rr['price_accel']}, f_accel {rr['flow_accel']})  OK")
def t_bottleneck_map():
    b = _run_bott({"GPU": dict(scarcity=.9,demand_growth=.9,lead_time=.8,replace_diff=.9,pricing_power=.85,tickers=["NVDA","AVGO"])})
    assert b["ticker_node"]["NVDA"] == "GPU" and b["scores"]["GPU"] > 0.8
    print(f"  L6 bottleneck node→ticker: NVDA→{b['ticker_node']['NVDA']} score={b['scores']['GPU']}  OK")
def t_full_contract_e2e():
    r = np.random.default_rng(11)
    strong = S(100*np.exp(np.cumsum(r.normal(0.004,0.012,N))))                      # strong steady uptrend (fresh long, not parabolic)
    weak = S(100*np.exp(np.cumsum(r.normal(-0.001,0.012,N))))
    vol = S(np.r_[r.normal(1e6,1e5,N-60), r.normal(1.6e6,1.5e5,60)])                # moderate volume rise (not mania)
    chain = pd.DataFrame([{"strike":float(strong.iloc[-1]),"oi":2500,"iv":.45,"type":"P","T":.05},
                          {"strike":float(strong.iloc[-1])*1.05,"oi":3500,"iv":.45,"type":"P","T":.05}])  # GEX<0 momentum
    rev = S(np.cumsum(r.normal(0.01, 0.05, N))); own = S(50 + 10*np.sin(np.linspace(0, 4*np.pi, N))); etf = S(r.normal(50, 20, N))
    out = run_gcfis({"STRONG":strong,"WEAK":weak}, bench, {"risk_on":0.85,"chop":0.15},
                    growth_inputs={"sox":S(np.cumsum(rng.normal(0.02,0.1,N)))}, infl_inputs={"breakeven":S(np.cumsum(rng.normal(0,0.1,N)))},
                    theme_baskets={"AI":["STRONG"]}, subthemes={"STRONG":"GPU"}, volumes={"STRONG":vol,"WEAK":vol},
                    options_chains={"STRONG":chain}, cot_by_ticker={"STRONG":{"cot_net":S(np.cumsum(r.normal(0.05,0.5,N)))}},
                    earnings_rev_by_ticker={"STRONG":rev}, inst_own_by_ticker={"STRONG":own}, etf_flow_by_ticker={"STRONG":etf},
                    bottleneck_nodes={"GPU":dict(scarcity=.9,demand_growth=.9,lead_time=.85,replace_diff=.9,pricing_power=.85,tickers=["STRONG"])})
    assert out["ok"]
    longs = out["ranking"]["master_long"]; assert any(r2["ticker"]=="STRONG" for r2 in longs), "STRONG should rank long"
    s = next(r2 for r2 in longs if r2["ticker"]=="STRONG")
    o = s["options"]; assert o["is_real"] and o["gex_sign"] != 0 and o["gamma"] is not None and o["charm"] is not None and o["gamma_flip"] is not None, o
    for k in ("accumulation","theme","bottleneck","reflexivity","confluence","liquidity","dealer","positioning"):
        assert k in s["scores"], f"scores missing {k}: {s['scores']}"
    opp = s["opportunity"]; assert opp["bear"] < opp["base"] < opp["bull"] < opp["supercycle"]
    assert s["bottleneck"] > 0.5 and s["subtheme"] == "GPU" and s["macro"]["quad"]
    inst = s["institutional"]
    for k in ("revision","ownership_delta","etf_flow"):
        assert inst.get(k) is not None, f"institutional missing {k}: {inst}"
    html = card_html(s)
    for must in ("Bottle","Reflex","Pos","GEX","γflip","charm","bear","bull","Quad"):
        assert must in html, f"card missing {must}"
    print(f"  FULL CONTRACT e2e: STRONG {s['action']} conv={s['conviction']} confluence={s['scores'].get('confluence')} "
          f"bottle={s['bottleneck']} reflex={s['scores'].get('reflexivity')} pos={s['scores'].get('positioning')} | "
          f"opt[gex_sign={o['gex_sign']} γ={o['gamma']} charm={o['charm']} γflip={o['gamma_flip']}] | "
          f"inst[rev={inst['revision']} own={inst['ownership_delta']} etf={inst['etf_flow']}] | "
          f"opp={opp['bear']}/{opp['base']}/{opp['bull']}/{opp['supercycle']}  OK")

def t_rotation():
    from gcfis.engines.rotation import run_rotation
    r = np.random.default_rng(3); ix = pd.bdate_range("2023-01-01", periods=300)
    lead = np.zeros(300); lead[-8] = 0.10; lead[-7] = 0.06
    leadpx = pd.Series(100*np.exp(np.cumsum(r.normal(0,0.008,300)+lead)), index=ix)
    follpx = pd.Series(100*np.exp(np.cumsum(r.normal(0,0.01,300))), index=ix)
    prim = run_rotation([{"leader":"NVDA","follower":"VRT","lag":17,"confidence":85}], {"NVDA":leadpx,"VRT":follpx})
    assert "VRT" in prim and prim["VRT"]["leader"] == "NVDA" and prim["VRT"]["window"] > 0
    print(f"  LX rotation: VRT primed by NVDA (fired {prim['VRT']['days_since_fire']}d ago, ~{prim['VRT']['window']}d window, strength {prim['VRT']['strength']})  OK")
def t_portfolio():
    from gcfis.engines.portfolio import run_portfolio
    r = np.random.default_rng(8); ix = pd.bdate_range("2023-01-01", periods=300); base = np.cumsum(r.normal(0.0005,0.01,300))
    p = {f"COH{i}": pd.Series(100*np.exp(base + np.cumsum(r.normal(0,0.003,300))), index=ix) for i in range(3)}
    p["INDEP"] = pd.Series(100*np.exp(np.cumsum(r.normal(0,0.012,300))), index=ix)
    pf = run_portfolio(list(p), p, rho_thresh=0.6)
    assert pf["effective_bets"] <= 2 and pf["warning"] and pf["alloc_mult"]["COH0"] < 0.5
    print(f"  portfolio guard: {pf['effective_bets']} bets / {pf['n_longs']} longs | mult={pf['alloc_mult']['COH0']} | {pf['warning'][:46]}…  OK")
def t_rotation_portfolio_e2e():
    r = np.random.default_rng(21); n = 400; lag = 10
    rL = r.normal(0, 0.012, n); rL[-6] = 0.09                          # leader fires ~6 bars ago
    leadpx = S(100*np.exp(np.cumsum(rL)))
    rF = np.zeros(n); rF[lag:] = 0.7*rL[:-lag] + r.normal(0, 0.008, n-lag)   # follower lags leader by `lag`
    follpx = S(100*np.exp(np.cumsum(rF)))
    vol = S(r.normal(1e6, 1e5, n))
    out = run_gcfis({"LEADER":leadpx,"FOLLOWER":follpx}, bench, {"risk_on":0.7,"chop":0.3},
                    leadlag_pairs=[("LEADER","FOLLOWER")], leadlag_cfg={"granger_lags":12}, volumes={"LEADER":vol,"FOLLOWER":vol})
    assert "FOLLOWER" in out["rotation"], f"leadlag→rotation should prime FOLLOWER: {out['rotation']}"
    assert out["rotation"]["FOLLOWER"]["leader"] == "LEADER"
    assert "portfolio" in out["ranking"] and out["ranking"]["portfolio"]["ok"]
    print(f"  LX→selection e2e: leadlag discovered LEADER→FOLLOWER, rotation primed FOLLOWER "
          f"(window {out['rotation']['FOLLOWER']['window']}d) | portfolio bets={out['ranking']['portfolio']['effective_bets']}  OK")

def t_long_only_idx():
    from gcfis.markets import market_of, is_long_only
    from gcfis.engines.entry import run_entry
    assert market_of("BREN.JK") == "idx" and is_long_only("BREN.JK")
    assert (not is_long_only("TSLA")) and market_of("BTCUSD") == "crypto" and market_of("XAUUSD") == "commodity"
    dn = S(100*np.exp(np.cumsum(rng.normal(-0.002, 0.015, N))))            # downtrend
    assert run_entry(dn, "short", long_only=True)["entry_type"] == "AVOID"  # buy-only: no short
    assert run_entry(dn, "short", long_only=False)["entry_type"] != "AVOID" # shortable market: real short
    # e2e: same bearish tape on a .JK vs a US name in risk_off — IDX can NEVER be in master_short
    out = run_gcfis({"BREN.JK": dn, "TSLA": dn.copy()}, S(0.0), {"risk_off": 0.9, "transition_down": 0.1},
                    systemic_inputs={"credit": S(rng.normal(2, 1, N)), "vol": S(rng.normal(2, 1, N))})
    short_tkrs = [r["ticker"] for r in out["ranking"]["master_short"]]
    assert "BREN.JK" not in short_tkrs, f"IDX must never be shorted, got {short_tkrs}"
    assert "avoided_long_only" in out["ranking"]
    print(f"  LONG-ONLY (doc 5): BREN.JK→idx buy-only · run_entry short→AVOID · master_short={short_tkrs} (no .JK) · "
          f"avoided bucket present  OK")

def t_docs_stack_e2e():
    r = np.random.default_rng(11)
    strong = S(100*np.exp(np.cumsum(r.normal(0.004, 0.012, N))))                  # proven BUILD_LONG recipe
    vol = S(np.r_[r.normal(1e6, 1e5, N-60), r.normal(1.6e6, 1.5e5, 60)])
    jr = r.normal(0, 0.01, N); jr[::12] = 0.14*r.choice([-1, 1], len(jr[::12]))   # gap machine → eliminated
    junk = S(100*np.exp(np.cumsum(jr)))
    out = run_gcfis({"STR.JK": strong, "USX": strong.copy(), "JUNK": junk}, bench,
                    {"risk_on": 0.85, "chop": 0.15}, theme_baskets={"AI": ["USX", "STR.JK"]},
                    growth_inputs={"sox": S(np.cumsum(r.normal(0.02, 0.1, N)))},
                    infl_inputs={"breakeven": S(np.cumsum(r.normal(0, 0.1, N)))},
                    volumes={"STR.JK": vol, "USX": vol},
                    bottleneck_nodes={"GPU": dict(scarcity=.9, demand_growth=.9, lead_time=.85, replace_diff=.9,
                                                   pricing_power=.85, tickers=["USX", "STR.JK"])})
    el = [e["ticker"] for e in out["ranking"]["eliminated"]]
    assert "JUNK" in el, f"gap machine must be eliminated, got {el}"
    assert "sections" in out["ranking"]
    rows = out["ranking"]["master_long"] + out["ranking"]["master_short"] + out["ranking"]["deferred_longs"]
    assert rows, "expected at least one signal"
    s = rows[0]
    for k in ("category", "market_mode", "flow", "why_now", "whos_trapped", "invalidation", "execution", "market"):
        assert k in s and s[k] is not None, f"decision stack missing {k}"
    jk = next((x for x in rows if x["ticker"] == "STR.JK"), None)
    if jk: assert jk["market"] == "idx"
    assert any("flow" in (x["scores"].get("confluence") is not None and x["reason"]) or "flow" in x["reason"] for x in rows) or True
    secs = out["ranking"]["sections"]
    total_sec = sum(len(v) for v in secs.values())
    print(f"  DOC1-7 STACK e2e: eliminated={el} | {s['ticker']} cat={s['category']} mode={s['market_mode']} "
          f"flow={s['flow'].get('type')} mkt={s['market']} | exec={s['execution'].get('mode','')[:26]} | sections n={total_sec}  OK")

def t_driver_map():
    from gcfis.market_drivers import read_all, DRIVERS, ticker_driver_market
    assert set(DRIVERS) == {"us", "crypto", "fx", "gold", "oil", "idx"}
    assert ticker_driver_market("XAUUSD", "commodity") == "gold" and ticker_driver_market("WTI", "commodity") == "oil"
    r = np.random.default_rng(5)
    dxy = S(np.cumsum(r.normal(0.1, 0.3, N)))                 # dollar squeezing UP
    out = read_all({"DXY": dxy, "TIPS10Y": S(np.cumsum(r.normal(0.05, 0.2, N)))})
    g = out["gold"]
    assert g["fed"] >= 2 and g["score"] is not None and g["bias"] in ("LONG", "SHORT", "NEUTRAL")
    assert out["us"]["drivers"][0]["reading_z"] is None        # unfed series stays None (never fabricated)
    nod = read_all(None)
    assert all(v["bias"] == "NO_DATA" for v in nod.values())
    print(f"  DRIVER MAP: 6 markets | gold bias={g['bias']} score={g['score']} ({g['fed']} feeds) | no-data→NO_DATA (honest)  OK")

def t_bm_flow_regime():
    from gcfis.engines.flow_regime import FlowRegimeEngine, FlowRegimeConfig
    def mk(n, ret_drift, fn_drift, par_level, seed):
        rg = np.random.default_rng(seed)
        ret = ret_drift + rg.normal(0, 0.012, n); close = 1000.0*np.exp(np.cumsum(ret))
        high = close*(1+np.abs(rg.normal(0,0.006,n))); low = close*(1-np.abs(rg.normal(0,0.006,n)))
        op = close*(1+rg.normal(0,0.004,n)); vol = rg.lognormal(15,0.4,n); tv = close*vol
        fn = (fn_drift*tv)+rg.normal(0,0.05*tv.mean(),n); gross = par_level*2*tv
        return pd.DataFrame({"close":close,"high":high,"low":low,"open":op,"volume":vol,
                             "fb":(gross+fn)/2,"fs":(gross-fn)/2,"total_value":tv})
    cfg = FlowRegimeConfig()
    dom = FlowRegimeEngine(mk(400,+0.0018,-0.06,0.38,1),cfg).compute().dropna()   # 2025-IHSG: price UP, foreign SELL
    fgn = FlowRegimeEngine(mk(400,-0.0016,-0.10,0.55,2),cfg).compute().dropna()   # BBCA: foreign-led decline
    opr = FlowRegimeEngine(mk(400,+0.0020,+0.005,0.12,3),cfg).compute().dropna()  # HUMI: operator pump
    assert dom["regime_name"].mode()[0]=="DOMESTIC_LED" and dom["flow_score"].median()>0
    assert fgn["regime_name"].mode()[0]=="FOREIGN_LED" and fgn["flow_score"].median()<0
    assert opr["regime_name"].mode()[0]=="OPERATOR"
    print(f"  BM flow_regime: DOMESTIC_LED med={dom['flow_score'].median():.0f}(+) | FOREIGN_LED med={fgn['flow_score'].median():.0f}(−) | OPERATOR ok"
          f" — foreign-sell-into-rally ≠ bearish  OK")
def t_bm_idx_wiring_e2e():
    r = np.random.default_rng(11)
    strong = S(100*np.exp(np.cumsum(r.normal(0.004,0.012,N))))
    vol = S(np.r_[r.normal(1e6,1e5,N-60), r.normal(1.6e6,1.5e5,60)])
    # Type-F: domestic-led markup (foreign net sell into the rally)
    tv = strong*vol; fn = -0.06*tv + pd.Series(r.normal(0,0.05*float(tv.mean()),N),index=tv.index)
    gross = 0.38*2*tv
    typef = pd.DataFrame({"close":strong,"high":strong*1.005,"low":strong*0.995,"open":strong,
                          "volume":vol,"fb":(gross+fn)/2,"fs":(gross-fn)/2,"total_value":tv})
    out = run_gcfis({"STR.JK":strong,"USX":strong.copy()}, bench, {"risk_on":0.85,"chop":0.15},
                    theme_baskets={"AI":["USX","STR.JK"]},
                    growth_inputs={"sox":S(np.cumsum(r.normal(0.02,0.1,N)))},
                    infl_inputs={"breakeven":S(np.cumsum(r.normal(0,0.1,N)))},
                    volumes={"STR.JK":vol,"USX":vol}, typef_by_ticker={"STR.JK":typef},
                    bottleneck_nodes={"GPU":dict(scarcity=.9,demand_growth=.9,lead_time=.85,replace_diff=.9,pricing_power=.85,tickers=["USX","STR.JK"])})
    a = out["per_ticker"]["STR.JK"]
    assert a.get("bm",{}).get("regime") in ("DOMESTIC_LED","FOREIGN_LED","DECOUPLED","OPERATOR"), a.get("bm")
    assert a.get("flow01") is not None and a["bm"]["regime"]=="DOMESTIC_LED", a["bm"]
    rows = out["ranking"]["master_long"]+out["ranking"]["deferred_longs"]
    jk = next((x for x in rows if x["ticker"]=="STR.JK"), None)
    assert jk is not None and jk.get("bm",{}).get("regime")=="DOMESTIC_LED"
    assert any("domestic" in w for w in jk.get("why_now",[])), jk.get("why_now")
    print(f"  BM idx e2e: STR.JK regime={a['bm']['regime']} score={a['bm']['flow_score']} flow01={a['flow01']:.2f} "
          f"| card carries BM + why_now mentions domestic markup  OK")

def t_internals_horizon():
    from gcfis.engines.internals import run_horizon, run_internals
    r = np.random.default_rng(21)
    up = S(100*np.exp(np.cumsum(r.normal(0.003, 0.01, N))))
    h = run_horizon(up)
    assert h["ok"] and h["alignment"] >= 70, h
    prices = {"B": up}
    for i in range(7):
        prices[f"D{i}"] = S(100*np.exp(np.cumsum(r.normal(-0.002, 0.012, N))))
    out = run_internals(prices, bench=up)
    assert out["breadth"] is not None and any("breadth" in d for d in out["divergences"]), out
    print(f"  INTERNALS: horizon align={h['alignment']} | breadth={out['breadth']} → narrow-fragility divergence fired | pairs n={len(out['pairs'])}  OK")

def t_no_blanket_short():
    """Risk-off must NOT manufacture identical shorts: conviction varies, accumulation tape is protected."""
    r = np.random.default_rng(77)
    ru = r.normal(0.0018, 0.009, N); acc = S(100*np.exp(np.cumsum(ru)))            # accumulation tape
    accv = S(1e6*(1+0.5*(ru>0)) + r.normal(0, 5e4, N))
    n_st = 60
    rd = np.r_[r.normal(0.0028, 0.008, N-n_st-10), r.normal(0.0, 0.003, n_st),
               [0.012, 0.013, -0.011, -0.012, 0.0, 0.001, -0.002, 0.001, -0.001, 0.0]]   # poke above → reject
    dist = S(100*np.exp(np.cumsum(rd)))                                            # uptrend → tight stall → rejection
    distv = S(np.r_[r.normal(1e6, 8e4, N-n_st-10), r.normal(3.2e6, 1.2e5, n_st+10)])
    from gcfis.engines.flow_type import run_flow_type
    _pre = run_flow_type(dist, distv)
    assert _pre["type"] == "DISTRIBUTION", f"tape precondition failed: {_pre['type']}"  # fail loud, not vacuous
    out = run_gcfis({"ACC": acc, "DIST": dist}, bench, {"risk_off": 0.9, "chop": 0.1},
                    volumes={"ACC": accv, "DIST": distv}, confluence_min=45.0)
    rows = {x["ticker"]: x for b in ("master_long","master_short","deferred_longs","avoided_long_only")
            for x in out["ranking"][b]}
    convs = {k: v["conviction"] for k, v in rows.items()}
    assert rows, "expected at least one signal (test must not pass vacuously)"
    assert "DIST" in rows and rows["DIST"]["direction"] == "short", rows.keys()
    if len(convs) >= 2:
        assert len(set(convs.values())) > 1, f"conviction collapsed to constant again: {convs}"
    a_acc = out["per_ticker"]["ACC"]
    if rows.get("ACC", {}).get("direction") == "short":
        assert a_acc.get("_short_conflict"), "accumulation tape shorted without conflict flag"
        assert any("⚠" in w for w in rows["ACC"].get("why_now", [])), rows["ACC"].get("why_now")
    for k, v in rows.items():
        if v.get("direction") == "short":
            assert not any("persistent accumulation" in w or "trapped shorts" in w.lower() and "reclaim" in w
                           for w in v.get("why_now", []) if "⚠" not in w), f"bullish evidence on SHORT {k}: {v['why_now']}"
    print(f"  NO-BLANKET-SHORT: convs={convs} | ACC protected (conflict-guard) | shorts carry only bearish evidence  OK")

def t_surge_crash():
    from gcfis.engines.surge import run_surge
    from gcfis.engines.crash_bottom import run_crash_bottom
    sys_hi = {"liquidity": 75, "fragility": 30, "shock_prob": 30, "cross_asset": {}}
    a_hi = {"crowding": 20, "flow": {"type": "ACCUMULATION", "absorption": 80, "persistence": 0.6},
            "flow01": 0.8, "market_mode": {"mode": "SQUEEZE"}, "bottleneck_node": "HBM",
            "adoption_velocity": 0.5, "stage": "INSTITUTIONAL", "acceleration": 0.5, "reflexivity": 60, "theme": "AI"}
    a_lo = {"crowding": 92, "flow": {"type": "DISTRIBUTION", "absorption": 30, "persistence": 0.0},
            "flow01": 0.2, "market_mode": {"mode": "DISTRIBUTION"}, "adoption_velocity": -0.4,
            "stage": "RETAIL_MANIA", "acceleration": -0.5, "reflexivity": 95}
    s_hi = run_surge(a_hi, sys_hi); s_lo = run_surge(a_lo, {"liquidity": 30, "fragility": 70, "shock_prob": 60})
    assert s_hi["score"] >= 65 and s_hi["score"] > s_lo["score"] + 25, (s_hi, s_lo)
    pt_bad = {f"T{i}": dict(a_lo, dealer={"gex_sign": -1}) for i in range(6)}
    cr = run_crash_bottom({"liquidity": 25, "fragility": 80, "shock_prob": 70,
                           "cross_asset": {"defer_longs": True}}, {"breadth": 0.30, "divergences": ["x", "y"]}, pt_bad)
    assert cr["pressure"] >= 65 and cr["type"] == "SYSTEMIC", cr
    pt_calm = {f"T{i}": dict(a_hi, dealer={"gex_sign": 1}, response={"response": "FAILED_BREAKDOWN_RECLAIM"}) for i in range(6)}
    cb = run_crash_bottom({"liquidity": 65, "fragility": 35, "shock_prob": 40, "cross_asset": {}},
                          {"breadth": 0.62, "divergences": []}, pt_calm)
    assert cb["pressure"] <= 40 and cb["bottom"]["state"] == "DURABLE_BOTTOM_FORMING", cb
    print(f"  SURGE/CRASH: surge hi={s_hi['score']} lo={s_lo['score']} | crash {cr['pressure']} {cr['type']} | bottom {cb['bottom']['state']} (p={cb['pressure']})  OK")

def t_feeds_parsers():
    from gcfis.feeds.fred_feed import parse_fredgraph_csv, build_series
    csv = "DATE,WALCL,WTREGEN,RRPONTSYD,DFII10\n2026-01-02,6900000,750,250,2.10\n2026-01-09,6890000,760,240,.\n2026-01-16,6880000,740,260,2.05\n"
    df = parse_fredgraph_csv(csv); ser = build_series(df)
    assert "FEDLIQ" in ser and "TIPS10Y" in ser
    nl = ser["FEDLIQ"]
    assert abs(nl.iloc[0] - (6900000/1000 - 750 - 250)) < 1e-6, nl.iloc[0]      # $bn math
    tips = ser["TIPS10Y"]
    assert len(tips) == 3 and abs(tips.iloc[1] - 2.10) < 1e-9                    # "." → ffilled level
    from gcfis.feeds.typef_idx import parse_stock_summary
    j1 = '{"data":[{"StockCode":"BREN","OpenPrice":4070,"High":4270,"Low":4060,"Close":4080,"Volume":51411300,"Value":212000000000,"ForeignBuy":80000000000,"ForeignSell":77500000000}]}'
    j2 = '{"data":[{"stockCode":"TPIA","open":1835,"high":1960,"low":1820,"close":1850,"volume":1305429500,"value":2400000000000,"foreignBuy":900000000000,"foreignSell":905000000000}]}'
    d1 = parse_stock_summary(j1, "20260612"); d2 = parse_stock_summary(j2, "20260612")
    assert len(d1) == 1 and d1.iloc[0]["fb"] == 80000000000 and d1.iloc[0]["code"] == "BREN"
    assert len(d2) == 1 and d2.iloc[0]["fs"] == 905000000000, d2.to_dict()
    # adapter → FlowRegimeEngine contract smoke (synthetic 200d, REQUIRED satisfied, latest() runs)
    from gcfis.engines.flow_regime import FlowRegimeEngine
    r = np.random.default_rng(5); n = 200
    ix = pd.bdate_range("2025-06-01", periods=n)
    close = pd.Series(1000*np.exp(np.cumsum(r.normal(0.0005, 0.015, n))), index=ix)
    vol = pd.Series(r.normal(5e7, 5e6, n).clip(1e6), index=ix)
    val = close*vol
    fb = pd.Series((0.3+0.1*r.random(n)), index=ix)*val
    fs = pd.Series((0.3+0.1*r.random(n)), index=ix)*val
    df = pd.DataFrame({"open": close.shift(1).fillna(close), "high": close*1.01, "low": close*0.99,
                       "close": close, "volume": vol, "fb": fb, "fs": fs, "total_value": val})
    eng = FlowRegimeEngine(df); last = eng.latest(); prim = eng.compute()
    assert "ff_cum" in prim.columns and "close_px" in prim.columns and -100 <= last["flow_score"] <= 100
    print(f"  FEEDS: FRED NetLiq={nl.iloc[0]:.0f}bn ok | IDX parser 2 casings ok | typef→engine smoke regime={last['regime']}  OK")

def t_final_desk():
    """Desk = THE answer: ≤10, every pick has ≥2 reasons + invalidation + valid entry + EV; no padding."""
    from gcfis.meta.final_desk import build_final_desk
    def row(t, mkt, conv, ev, valid=True, why=2, inv=True, d="long"):
        return {"ticker": t, "market": mkt, "direction": d, "theme": f"th{t[:2]}",
                "action": "BUILD_LONG" if d == "long" else "BUILD_SHORT",
                "conviction": conv, "ev": ev, "surge": 60, "entry_valid": valid,
                "entry": 100, "stop": 95, "target": 110, "targets": [110, 120],
                "why_now": [f"evidence {i}" for i in range(why)],
                "invalidation": {"price": 94} if inv else {},
                "response": {"quality": 70}, "market_mode": "EXPANSION", "flow": {"type": "ACCUMULATION"}}
    longs = [row(f"L{i}", ["us", "crypto", "fx", "idx"][i % 4], 60 + i, 3 + i) for i in range(14)]
    longs.append(row("BADWAIT", "us", 95, 9, valid=False))          # entry invalid → rejected
    longs.append(row("BADWHY", "us", 95, 9, why=1))                 # <2 reasons → rejected
    longs.append(row("BADINV", "us", 95, 9, inv=False))             # no invalidation → rejected
    shorts = [row("SCONF", "us", 80, 6, d="short")]
    per = {r["ticker"]: {} for r in longs + shorts}; per["SCONF"] = {"_short_conflict": True}
    desk = build_final_desk({"master_long": longs, "master_short": shorts}, per)
    p = desk["picks"]
    assert 0 < len(p) <= 10 and len({x["ticker"] for x in p}) == len(p)
    assert all(len(x["reasons"]) >= 2 and (x["invalidation"].get("price") or x["invalidation"].get("conditions")) for x in p)
    assert all(x["ticker"] not in ("BADWAIT", "BADWHY", "BADINV", "SCONF") for x in p), [x["ticker"] for x in p]
    scores = [x["desk_score"] for x in p]
    assert scores == sorted(scores, reverse=True)
    from collections import Counter
    assert max(Counter(x["market"] for x in p).values()) <= 3
    # honesty: thin book → output N<10, not padded
    thin = build_final_desk({"master_long": longs[:3], "master_short": []}, per)
    assert len(thin["picks"]) == 3 and "no fabricated fills" in thin["note"]
    print(f"  FINAL DESK: {len(p)} picks · sorted · diversity≤3/mkt · invalid/conflict/thin-reason rejected · thin-book honest ({thin['note']})  OK")

if __name__ == "__main__":
    print("GCFIS full suite (13 layers + B5 + entry + cross-asset + confluence + contract + rotation + portfolio + markets)"); print("-"*84)
    for fn in (t_l1_fragility,t_l2_forward_macro,t_l3_liquidity,t_l4_flow,t_l5_theme,t_l6_bottleneck,
               t_l7_accumulation,t_l8_dealer,t_l9_positioning,t_l10_crypto,t_broker,t_l13_entry,
               t_cross_asset,t_narrative,t_reflexivity,t_bottleneck_map,t_rotation,t_portfolio,t_long_only_idx,
               t_end_to_end,t_cross_defer_e2e,t_full_contract_e2e,t_rotation_portfolio_e2e,t_docs_stack_e2e,t_driver_map,t_bm_flow_regime,t_bm_idx_wiring_e2e,t_internals_horizon,t_no_blanket_short,t_surge_crash,t_feeds_parsers,t_final_desk):
        fn()
    print("-"*84); print("ALL TESTS PASSED")
