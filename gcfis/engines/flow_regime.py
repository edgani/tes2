"""flow_regime.py — BandarMetrics REDESIGNED (regime-aware foreign-flow engine).
Verdict tiers applied: KEEP Corr_F + Par_F (high edge), EFD = Corr_F×Par_F (composite driver),
LPM CONDITIONAL-only (validity gate: liq expansion + breadth + slope), Intensity trigger-only.
DROPPED: Vol Rotation (forward-edge ~0), AvgCost standalone, Net Buy/Sell F (redundant derivative).
Core thesis (validated vs 2025 IHSG ATH-on-foreign-net-sell + BBCA/ISAT/TPIA/HUMI):
foreign flow's SIGN is regime-dependent. DomesticNet = −ForeignNet ⇒ foreign selling into a RISING
tape = domestic-led markup (NOT bearish). Weights are PRIORS — walk-forward before trusting."""
from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum
import numpy as np, pandas as pd

class RegimeState(IntEnum):
    DECOUPLED = 0; FOREIGN_LED = 1; DOMESTIC_LED = 2; OPERATOR = 3

@dataclass(frozen=True)
class FlowRegimeConfig:
    vwap_n: int = 20; corr_w: int = 60; adv_short: int = 20; adv_long: int = 63
    atr_short: int = 14; atr_long: int = 63; lpm_smooth: int = 20; slope_k: int = 10
    z_n: int = 20; persist_n: int = 10
    par_f_floor: float = 0.20; tau: float = 0.30; corr_smooth: int = 8; par_smooth: int = 20
    w_fgn: float = 3.0; w_lpm_dom: float = 0.9; w_brd: float = 0.7
    w_lpm_op: float = 0.9; w_int: float = 0.5

def _z(s, n):
    m = s.rolling(n, min_periods=max(2, n // 2)).mean()
    sd = s.rolling(n, min_periods=max(2, n // 2)).std()
    return (s - m) / sd.replace(0.0, np.nan)

def _slope(s, k): return s - s.shift(k)

class FlowRegimeEngine:
    REQUIRED = ("close", "high", "low", "open", "volume", "fb", "fs")
    def __init__(self, df, config=None):
        missing = [c for c in self.REQUIRED if c not in df.columns]
        if missing: raise ValueError(f"missing required columns: {missing}")
        self.cfg = config or FlowRegimeConfig(); self.df = df.copy(); eps = 1e-12
        self.df["volume"] = self.df["volume"].clip(lower=eps)
        if "total_value" not in self.df: self.df["total_value"] = self.df["close"] * self.df["volume"]
        self.df["total_value"] = self.df["total_value"].clip(lower=eps)
    def _prims(self):
        c, cfg = self.df, self.cfg; out = pd.DataFrame(index=c.index)
        tp = (c["high"] + c["low"] + c["close"]) / 3.0
        vwap = (tp * c["volume"]).rolling(cfg.vwap_n, min_periods=cfg.vwap_n).sum() / c["volume"].rolling(cfg.vwap_n, min_periods=cfg.vwap_n).sum()
        fn = c["fb"] - c["fs"]
        out["par_f"] = ((c["fb"] + c["fs"]) / (2.0 * c["total_value"])).clip(0, 1)
        out["par_f_s"] = out["par_f"].ewm(span=cfg.par_smooth, adjust=False).mean()
        # Corr_F = PRICE LEVEL vs CUMULATIVE foreign flow (matches BM magnitudes; regime TAG not inference)
        corr_f = c["close"].rolling(cfg.corr_w, min_periods=cfg.corr_w // 2).corr(fn.cumsum())
        out["corr_f_s"] = corr_f.clip(-1, 1).ewm(span=cfg.corr_smooth, adjust=False).mean()
        out["efd"] = out["corr_f_s"] * out["par_f_s"]
        pressure = (c["close"] - vwap) * c["volume"]
        out["lpm"] = pressure.fillna(0.0).cumsum().ewm(span=cfg.lpm_smooth, adjust=False).mean()
        out["lpm_slope_z"] = _z(_slope(out["lpm"], cfg.slope_k), cfg.z_n)
        adv_s = c["total_value"].rolling(cfg.adv_short, min_periods=cfg.adv_short // 2).mean()
        adv_l = c["total_value"].rolling(cfg.adv_long, min_periods=cfg.adv_long // 2).mean()
        out["liq_expand"] = adv_s / adv_l
        out["breadth"] = np.sign(pressure).rolling(cfg.persist_n, min_periods=2).mean()
        out["ff_net"] = fn
        out["ff_cum"] = fn.cumsum()
        out["close_px"] = c["close"]
        out["lpm_valid"] = ((out["lpm_slope_z"] > 0) & (out["liq_expand"] > 1.0) & (out["breadth"] > 0)).astype(int)
        zint = _z(_slope(out["lpm"], cfg.slope_k), cfg.z_n).abs()
        out["intensity"] = np.where(zint > 1.5, zint, 0.0)
        out["int_signed"] = out["intensity"] * np.sign(out["lpm_slope_z"]).fillna(0)
        out["fgn_p"] = (fn.rolling(cfg.slope_k).sum() / c["total_value"].rolling(cfg.slope_k).sum()).clip(-1, 1)
        out["lpm_p"] = np.sign(_slope(out["lpm"], cfg.slope_k)) * ((out["lpm_slope_z"].abs() / 2.0).clip(0, 1))
        return out
    def _classify(self, p):
        cfg = self.cfg
        cond = [p["par_f_s"] < cfg.par_f_floor, p["corr_f_s"] > cfg.tau, p["corr_f_s"] < -cfg.tau]
        choice = [int(RegimeState.OPERATOR), int(RegimeState.FOREIGN_LED), int(RegimeState.DOMESTIC_LED)]
        return pd.Series(np.select(cond, choice, default=int(RegimeState.DECOUPLED)), index=p.index, dtype=int)
    def compute(self):
        cfg = self.cfg; p = self._prims(); state = self._classify(p)
        fgn, lpm = p["fgn_p"].fillna(0), p["lpm_p"].fillna(0)
        brd, ins = p["breadth"].fillna(0), np.tanh(p["int_signed"].fillna(0))
        score = 100.0 * np.select(
            [state == RegimeState.FOREIGN_LED, state == RegimeState.DOMESTIC_LED, state == RegimeState.OPERATOR],
            [np.tanh(cfg.w_fgn * fgn), np.tanh(cfg.w_lpm_dom * lpm + cfg.w_brd * brd),   # DOMESTIC: NO foreign term
             np.tanh(cfg.w_lpm_op * lpm + cfg.w_int * ins)],
            default=0.4 * np.tanh(0.5 * fgn + 0.5 * lpm))
        ac, par = p["corr_f_s"].abs(), p["par_f_s"]
        conf = np.select(
            [state == RegimeState.FOREIGN_LED, state == RegimeState.DOMESTIC_LED, state == RegimeState.OPERATOR],
            [np.clip(ac * np.minimum(par / 0.5, 1.5), 0.3, 1.0), np.clip(ac * np.minimum(par / 0.5, 1.5), 0.3, 1.0),
             np.clip((1.0 - par / cfg.par_f_floor) * 0.5 + 0.5, 0.4, 0.9)], default=0.25)
        p["regime"] = state; p["regime_name"] = state.map({int(s): s.name for s in RegimeState})
        p["flow_score"] = score; p["confidence"] = conf
        return p
    def latest(self):
        r = self.compute().iloc[-1]
        return {"regime": r["regime_name"], "flow_score": round(float(r["flow_score"]), 2),
                "confidence": round(float(r["confidence"]), 2), "par_f": round(float(r["par_f_s"]), 4),
                "corr_f": round(float(r["corr_f_s"]), 4), "efd": round(float(r["efd"]), 4),
                "lpm": round(float(r["lpm"]), 2), "lpm_valid": int(r["lpm_valid"]),
                "liq_expand": round(float(np.nan_to_num(r["liq_expand"], nan=1.0)), 3),
                "lpm_slope_z": round(float(np.nan_to_num(r["lpm_slope_z"])), 2),
                "breadth": round(float(np.nan_to_num(r["breadth"])), 2)}
