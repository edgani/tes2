"""v2 foundation tests — verifiable HERE (fixtures); live fetch verifiable on Cloud only."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd


def t_fred_parser_and_macro():
    from core.data_layer import _parse_fred, derive_macro
    csv = ("DATE,WALCL,WTREGEN,RRPONTSYD,BAMLH0A0HYM2,BAMLC0A0CM,DFII10,T10Y2Y,VIXCLS\n"
           "2026-05-01,6900000,750,250,3.10,1.05,2.10,0.30,18.0\n"
           "2026-05-08,6890000,760,240,3.40,1.12,2.18,0.22,21.0\n"
           "2026-05-15,6880000,740,260,.,1.20,2.25,0.15,24.0\n")
    df = _parse_fred(csv)
    m = derive_macro(df)
    assert m["net_liquidity"]["provenance"] == "REAL"
    assert abs(m["net_liquidity"]["series"].iloc[0] - (6900000/1000 - 750 - 250)) < 1e-6   # $bn math
    assert "hy_oas" in m and m["hy_oas"]["series"].iloc[1] == 3.40                          # credit real
    assert m["hy_oas"]["series"].iloc[-1] == 3.40                                           # "." ffilled
    print(f"  FRED: NetLiq={m['net_liquidity']['value']:.0f}bn | HY OAS series ok | curve+VIX parsed  OK")


def t_shock_engine_real_vs_proxy():
    from engines.shock_engine import run_shock_engine
    ix = pd.bdate_range("2025-11-01", periods=160)
    # stress tape: HY OAS widening hard, NetLiq draining, real yields rising
    hy = pd.Series(np.linspace(3.0, 3.0, 120).tolist() + np.linspace(3.0, 5.2, 40).tolist(), index=ix)
    nl = pd.Series(np.linspace(6200, 6200, 120).tolist() + np.linspace(6200, 5600, 40).tolist(), index=ix)
    ry = pd.Series(np.linspace(1.8, 1.8, 120).tolist() + np.linspace(1.8, 2.8, 40).tolist(), index=ix)
    macro = {"hy_oas": {"series": hy}, "net_liquidity": {"series": nl}, "real_yield_10y": {"series": ry}}
    hot = run_shock_engine(macro, {"ratio": 1.08, "provenance": "REAL"}, breadth=0.30)
    assert hot["shock_prob"] >= 65 and hot["crash_type"] == "SYSTEMIC", hot
    assert hot["confidence"] == "high" and hot["provenance"]["credit_stress"] == "REAL"
    # calm + NO real feeds → must NOT fire high and must self-label low confidence (no proxy bluffing)
    calm = run_shock_engine({}, {"ratio": None}, breadth=None)
    assert calm["shock_prob"] <= 55 and calm["confidence"].startswith("low"), calm
    # flush: vol spike, credit calm → recoverable, not systemic
    hyc = pd.Series(np.full(160, 3.0), index=ix)
    flush = run_shock_engine({"hy_oas": {"series": hyc}}, {"ratio": 1.10, "provenance": "REAL"}, breadth=0.52)
    assert flush["crash_type"] in ("FLUSH", "LOW"), flush
    print(f"  SHOCK: systemic={hot['shock_prob']}(conf {hot['confidence']}) · calm={calm['shock_prob']}(conf {calm['confidence']}) · flush={flush['crash_type']}  OK")


def t_typef_parser_reuse():
    from core.typef_idx import parse_stock_summary
    j = '{"data":[{"StockCode":"BREN","OpenPrice":4070,"High":4270,"Low":4060,"Close":4080,"Volume":51411300,"Value":212e9,"ForeignBuy":80e9,"ForeignSell":77.5e9}]}'
    d = parse_stock_summary(j, "20260612")
    assert len(d) == 1 and d.iloc[0]["code"] == "BREN" and d.iloc[0]["fb"] == 80e9
    print(f"  TYPE-F: IDX parser reused ok (BREN fb={d.iloc[0]['fb']:.0f})  OK")


if __name__ == "__main__":
    for fn in (t_fred_parser_and_macro, t_shock_engine_real_vs_proxy, t_typef_parser_reuse):
        fn()
    print("-" * 60)
    print("V2 FOUNDATION TESTS PASSED")
