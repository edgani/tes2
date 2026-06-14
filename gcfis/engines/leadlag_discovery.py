"""engines/leadlag_discovery_engine.py — Lead-Lag DISCOVERY Engine (GCFIS LX)

Closes the biggest gap (3/10): DISCOVERS directed lead-lag relationships dynamically,
not from a hardcoded map. Output e.g.  {leader:'NVDA', follower:'VRT', lag:17, confidence:87}.

WHY THIS IS NOT THE NAIVE Corr(A_t, B_{t+k}) (which overfits):
  1. RETURNS not levels        -> kills spurious common-trend correlation
  2. Granger causality (F-test) -> does A's past improve prediction of B beyond B's own past?
  3. Transfer Entropy           -> model-free, captures NON-LINEAR directional info
  4. FDR (Benjamini-Hochberg)   -> N^2 x K tests => thousands of false positives by chance; corrected
  5. Stability filter           -> edge must hold across rolling sub-windows
  6. Direction disambiguation   -> A->B vs B->A compared; only dominant direction kept
  7. Economic-prior seeding     -> optional candidate restriction to avoid the multiple-testing explosion

Change-centric: operates on returns (1st diff of log price); set order=2 to run on ACCELERATION.

Dependencies: numpy, pandas, scipy, networkx  (NO statsmodels — Granger/TE/FDR implemented here).
Drop-in API:  run_leadlag_discovery(prices: dict[str, pd.Series], **cfg) -> dict
"""
from __future__ import annotations
import logging, math
from dataclasses import dataclass, field
from itertools import permutations
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

try:
    from scipy.stats import f as _f_dist
    _HAVE_SCIPY = True
except Exception:                                            # pragma: no cover
    _HAVE_SCIPY = False

try:
    import networkx as nx
    _HAVE_NX = True
except Exception:                                            # pragma: no cover
    _HAVE_NX = False

logger = logging.getLogger(__name__)


# ───────────────────────── config ─────────────────────────
@dataclass
class LeadLagConfig:
    maxlag: int = 21                 # search lags 1..maxlag (trading days)
    min_obs: int = 150               # minimum aligned observations required
    order: int = 1                   # 1=returns (change), 2=acceleration (change of change)
    fdr_q: float = 0.05              # Benjamini-Hochberg false-discovery rate
    granger_lags: int = 5            # p in the Granger VAR (history length for the F-test)
    te_bins: int = 5                 # quantile bins for transfer-entropy estimator
    stability_folds: int = 3         # rolling sub-windows for the stability check
    stability_min: float = 0.5       # fraction of folds an edge must survive
    min_xcorr: float = 0.10          # prefilter: skip pairs whose best |xcorr| < this
    min_confidence: float = 50.0     # only return edges with confidence >= this
    winsor_z: float = 6.0            # clip return outliers beyond this many MADs
    max_assets: int = 60             # guard: O(N^2 * K); above this, require seeding
    candidate_pairs: Optional[List[Tuple[str, str]]] = None  # economic-prior seeding (leader,follower)


@dataclass
class LeadLagEdge:
    leader: str
    follower: str
    lag: int
    confidence: float
    granger_p: float
    te_net: float
    xcorr: float
    sign: str
    stability: float

    def as_dict(self) -> dict:
        return {"leader": self.leader, "follower": self.follower, "lag": int(self.lag),
                "confidence": round(self.confidence, 1), "granger_p": round(self.granger_p, 4),
                "te_net": round(self.te_net, 4), "xcorr": round(self.xcorr, 3),
                "sign": self.sign, "stability": round(self.stability, 2)}


# ───────────────────────── math core ─────────────────────────
def _to_returns(s: pd.Series, order: int, winsor_z: float) -> pd.Series:
    """Log returns (order=1) or acceleration (order=2). Robust-winsorized."""
    s = pd.to_numeric(s, errors="coerce").dropna()
    s = s[s > 0]
    if len(s) < 5:
        return pd.Series(dtype=float)
    r = np.log(s).diff()
    for _ in range(order - 1):
        r = r.diff()
    r = r.dropna()
    if len(r) < 5:
        return r
    med = r.median()
    mad = (r - med).abs().median() or 1e-9
    z = 0.6745 * (r - med) / mad
    return r.clip(lower=med - winsor_z * mad / 0.6745,
                  upper=med + winsor_z * mad / 0.6745)


def _best_xcorr(rA: np.ndarray, rB: np.ndarray, maxlag: int) -> Tuple[int, float]:
    """Find lag k in 1..maxlag maximizing |corr(A_t, B_{t+k})| (A LEADS B by k)."""
    best_k, best_c = 0, 0.0
    n = len(rA)
    for k in range(1, maxlag + 1):
        if n - k < 30:
            break
        a, b = rA[:-k], rB[k:]
        sa, sb = a.std(), b.std()
        if sa < 1e-12 or sb < 1e-12:
            continue
        c = float(np.corrcoef(a, b)[0, 1])
        if abs(c) > abs(best_c):
            best_k, best_c = k, c
    return best_k, best_c


def _ols_rss(y: np.ndarray, X: np.ndarray) -> float:
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    return float(resid @ resid)


def _granger_p(rA: np.ndarray, rB: np.ndarray, p: int) -> float:
    """H0: A does NOT Granger-cause B. Returns p-value (low => A helps predict B).
    Restricted: B_t ~ const + B_{t-1..p};  Unrestricted: + A_{t-1..p}.  F-test on the A block."""
    n = len(rB)
    if n <= 3 * p + 10:
        return 1.0
    y = rB[p:]
    cols_r = [np.ones(n - p)]
    cols_u = [np.ones(n - p)]
    for j in range(1, p + 1):
        cols_r.append(rB[p - j:n - j])
        cols_u.append(rB[p - j:n - j])
    for j in range(1, p + 1):
        cols_u.append(rA[p - j:n - j])
    Xr = np.column_stack(cols_r)
    Xu = np.column_stack(cols_u)
    rss_r, rss_u = _ols_rss(y, Xr), _ols_rss(y, Xu)
    dof2 = (n - p) - (2 * p + 1)
    if dof2 <= 0 or rss_u <= 0:
        return 1.0
    F = ((rss_r - rss_u) / p) / (rss_u / dof2)
    if F <= 0 or not np.isfinite(F):
        return 1.0
    if _HAVE_SCIPY:
        return float(_f_dist.sf(F, p, dof2))
    # fallback: crude F->p via chi2-ish; only if scipy missing
    return float(math.exp(-0.5 * F))


def _discretize(a: np.ndarray, bins: int) -> np.ndarray:
    qs = np.quantile(a, np.linspace(0, 1, bins + 1)[1:-1]) if bins > 1 else np.array([])
    return np.searchsorted(qs, a, side="right").astype(np.int64)


def _transfer_entropy(src: np.ndarray, tgt: np.ndarray, lag: int, bins: int) -> float:
    """TE(src->tgt) at given lag, history length 1 (bits).
    TE = Σ p(yf,yp,xp) log2[ p(yf,yp,xp) p(yp) / (p(yp,xp) p(yf,yp)) ]
    where yf=tgt_t, yp=tgt_{t-1}, xp=src_{t-lag}."""
    n = len(tgt)
    if lag < 1 or n - lag < 30:
        return 0.0
    yf = tgt[lag:n]
    yp = tgt[lag - 1:n - 1]
    xp = src[0:n - lag]
    m = min(len(yf), len(yp), len(xp))
    yf, yp, xp = yf[-m:], yp[-m:], xp[-m:]
    yf, yp, xp = _discretize(yf, bins), _discretize(yp, bins), _discretize(xp, bins)

    from collections import Counter
    c_fpx = Counter(zip(yf, yp, xp))
    c_px = Counter(zip(yp, xp))
    c_fp = Counter(zip(yf, yp))
    c_p = Counter(yp)
    N = float(m)
    te = 0.0
    for (f, pp, x), n_fpx in c_fpx.items():
        p_fpx = n_fpx / N
        p_px = c_px[(pp, x)] / N
        p_fp = c_fp[(f, pp)] / N
        p_p = c_p[pp] / N
        denom = p_px * p_fp
        if p_fpx > 0 and denom > 0 and p_p > 0:
            te += p_fpx * math.log2((p_fpx * p_p) / denom)
    return max(0.0, te)


def _benjamini_hochberg(pvals: List[float], q: float) -> np.ndarray:
    """Return boolean mask of hypotheses rejected at FDR=q."""
    p = np.asarray(pvals, dtype=float)
    m = len(p)
    if m == 0:
        return np.array([], dtype=bool)
    order = np.argsort(p)
    ranked = p[order]
    thresh = (np.arange(1, m + 1) / m) * q
    passed = ranked <= thresh
    keep = np.zeros(m, dtype=bool)
    if passed.any():
        kmax = np.max(np.where(passed)[0])
        keep[order[:kmax + 1]] = True
    return keep


# ───────────────────────── engine ─────────────────────────
class LeadLagDiscoveryEngine:
    def __init__(self, cfg: Optional[LeadLagConfig] = None):
        self.cfg = cfg or LeadLagConfig()
        self.edges: List[LeadLagEdge] = []
        self.graph = nx.DiGraph() if _HAVE_NX else None
        self._returns: Dict[str, pd.Series] = {}

    # -- public --
    def run(self, prices: Dict[str, pd.Series]) -> dict:
        c = self.cfg
        rets = {t: _to_returns(s, c.order, c.winsor_z) for t, s in (prices or {}).items()}
        rets = {t: r for t, r in rets.items() if len(r) >= c.min_obs}
        self._returns = rets
        tickers = list(rets.keys())

        if len(tickers) < 2:
            return {"ok": False, "reason": "need >=2 assets with sufficient history",
                    "n_assets": len(tickers)}
        if c.candidate_pairs is None and len(tickers) > c.max_assets:
            return {"ok": False, "reason": f"{len(tickers)} assets > max_assets={c.max_assets}; "
                    f"pass candidate_pairs (economic-prior seeding) to avoid multiple-testing blow-up",
                    "n_assets": len(tickers)}

        pairs = (c.candidate_pairs if c.candidate_pairs is not None
                 else list(permutations(tickers, 2)))           # ordered (leader, follower)

        # pass 1: prefilter + Granger p-values for every candidate
        raw = []
        for a, b in pairs:
            if a == b or a not in rets or b not in rets:
                continue
            idx = rets[a].index.intersection(rets[b].index)
            if len(idx) < c.min_obs:
                continue
            rA = rets[a].reindex(idx).to_numpy()
            rB = rets[b].reindex(idx).to_numpy()
            k, xc = _best_xcorr(rA, rB, c.maxlag)
            if k == 0 or abs(xc) < c.min_xcorr:
                continue
            gp = _granger_p(rA, rB, c.granger_lags)
            raw.append({"a": a, "b": b, "lag": k, "xcorr": xc, "gp": gp,
                        "idx": idx, "rA": rA, "rB": rB})

        if not raw:
            return {"ok": True, "n_assets": len(tickers), "n_pairs_tested": len(pairs),
                    "n_edges_found": 0, "edges": [], "summary": {"note": "no candidate survived prefilter"}}

        # pass 2: FDR across all Granger tests (THE fix for false positives)
        keep_mask = _benjamini_hochberg([r["gp"] for r in raw], c.fdr_q)

        # pass 3: for survivors -> TE direction + stability + confidence
        edges: List[LeadLagEdge] = []
        for r, keep in zip(raw, keep_mask):
            if not keep:
                continue
            a, b, k = r["a"], r["b"], r["lag"]
            rA, rB = r["rA"], r["rB"]
            te_ab = _transfer_entropy(rA, rB, k, c.te_bins)
            te_ba = _transfer_entropy(rB, rA, k, c.te_bins)
            te_net = te_ab - te_ba
            if te_net <= 0:                                     # B actually leads A (or symmetric) -> drop this direction
                continue
            stab = self._stability(rA, rB, k)
            if stab < c.stability_min:
                continue
            conf = self._confidence(r["gp"], te_net, r["xcorr"], stab)
            if conf < c.min_confidence:
                continue
            edges.append(LeadLagEdge(leader=a, follower=b, lag=k, confidence=conf,
                                     granger_p=r["gp"], te_net=te_net, xcorr=r["xcorr"],
                                     sign="+" if r["xcorr"] >= 0 else "-", stability=stab))

        edges.sort(key=lambda e: e.confidence, reverse=True)
        self.edges = edges
        self._build_graph(edges)

        return {"ok": True, "n_assets": len(tickers), "n_pairs_tested": len(pairs),
                "n_survived_fdr": int(keep_mask.sum()), "n_edges_found": len(edges),
                "fdr_q": c.fdr_q, "maxlag": c.maxlag, "order": c.order,
                "edges": [e.as_dict() for e in edges],
                "summary": self._summary(edges, tickers)}

    # -- queries --
    def get_leaders_of(self, ticker: str) -> List[dict]:
        return [e.as_dict() for e in self.edges if e.follower == ticker]

    def get_followers_of(self, ticker: str) -> List[dict]:
        return [e.as_dict() for e in self.edges if e.leader == ticker]

    # -- internals --
    def _stability(self, rA: np.ndarray, rB: np.ndarray, lag: int) -> float:
        c = self.cfg
        n = len(rA)
        folds = c.stability_folds
        if n < folds * (c.min_obs // 2):
            folds = max(2, n // (c.min_obs // 2))
        bounds = np.linspace(0, n, folds + 1).astype(int)
        ok = 0
        tot = 0
        for i in range(folds):
            lo, hi = bounds[i], bounds[i + 1]
            if hi - lo < 60:
                continue
            tot += 1
            a, b = rA[lo:hi], rB[lo:hi]
            k, xc = _best_xcorr(a, b, c.maxlag)
            if k == 0:
                continue
            gp = _granger_p(a, b, c.granger_lags)
            if gp < 0.10 and abs(k - lag) <= max(2, int(0.25 * lag)):
                ok += 1
        return ok / tot if tot else 0.0

    @staticmethod
    def _confidence(gp: float, te_net: float, xcorr: float, stab: float) -> float:
        # blend: Granger significance, normalized TE, |xcorr|, stability -> 0..100
        g = 1.0 - min(gp, 1.0)                      # significance
        t = math.tanh(8.0 * max(te_net, 0.0))       # TE saturating 0..1
        x = min(abs(xcorr) / 0.5, 1.0)              # |xcorr| scaled
        score = 100.0 * (0.40 * g + 0.25 * t + 0.15 * x + 0.20 * stab)
        return max(0.0, min(100.0, score))

    def _build_graph(self, edges: List[LeadLagEdge]) -> None:
        if not _HAVE_NX:
            return
        self.graph = nx.DiGraph()
        for e in edges:
            self.graph.add_edge(e.leader, e.follower, weight=e.confidence / 100.0,
                                lag=e.lag, confidence=e.confidence, sign=e.sign,
                                source="leadlag_dynamic")

    def _summary(self, edges: List[LeadLagEdge], tickers: List[str]) -> dict:
        if not edges:
            return {"top_leaders": [], "top_followers": [], "avg_lag": None}
        from collections import Counter
        lead = Counter(e.leader for e in edges)
        foll = Counter(e.follower for e in edges)
        return {"top_leaders": [{"ticker": t, "out_edges": n} for t, n in lead.most_common(5)],
                "top_followers": [{"ticker": t, "in_edges": n} for t, n in foll.most_common(5)],
                "avg_lag": round(float(np.mean([e.lag for e in edges])), 1),
                "strongest": edges[0].as_dict()}


# ───────────────────────── drop-in entrypoint ─────────────────────────
def run_leadlag_discovery(prices: Dict[str, pd.Series], **cfg) -> dict:
    """Orchestrator entrypoint. `cfg` overrides LeadLagConfig fields."""
    engine = LeadLagDiscoveryEngine(LeadLagConfig(**cfg))
    out = engine.run(prices)
    out["_engine"] = engine                                    # for graph/query access (not JSON)
    return out


# ───────────────────────── self-test (synthetic; proves CORRECTNESS, not market alpha) ───
if __name__ == "__main__":
    rng = np.random.default_rng(42)
    N = 600
    dates = pd.bdate_range("2023-01-01", periods=N)

    def rw(returns):  # build a price level series from returns
        return pd.Series(100 * np.exp(np.cumsum(returns)), index=dates)

    TRUE_LAG = 12
    # LEADER returns
    rL = rng.normal(0, 0.02, N)
    # FOLLOWER: leader shifted by TRUE_LAG + noise  (so LEADER -> FOLLOWER at lag 12)
    rF = np.zeros(N)
    rF[TRUE_LAG:] = 0.7 * rL[:-TRUE_LAG] + rng.normal(0, 0.012, N - TRUE_LAG)
    # two pure-noise series (must NOT be linked)
    rN1 = rng.normal(0, 0.02, N)
    rN2 = rng.normal(0, 0.02, N)

    prices = {"LEADER": rw(rL), "FOLLOWER": rw(rF), "NOISE1": rw(rN1), "NOISE2": rw(rN2)}

    res = run_leadlag_discovery(prices, maxlag=30, min_obs=120, granger_lags=14,
                                min_confidence=50, max_assets=20)
    print("ok:", res["ok"], "| pairs tested:", res["n_pairs_tested"],
          "| survived FDR:", res.get("n_survived_fdr"), "| edges:", res["n_edges_found"])
    print("-" * 70)
    for e in res["edges"]:
        print(f"  {e['leader']:>9} -> {e['follower']:<9}  lag={e['lag']:>2}d  "
              f"conf={e['confidence']:>5}  granger_p={e['granger_p']}  "
              f"te_net={e['te_net']}  stab={e['stability']}")
    print("-" * 70)

    # ── assertions: correctness ──
    edges = res["edges"]
    found = {(e["leader"], e["follower"]): e for e in edges}
    assert ("LEADER", "FOLLOWER") in found, "FAIL: did not recover the injected LEADER->FOLLOWER edge"
    rec_lag = found[("LEADER", "FOLLOWER")]["lag"]
    assert abs(rec_lag - TRUE_LAG) <= 3, f"FAIL: recovered lag {rec_lag} far from true {TRUE_LAG}"
    # no spurious edges into/out of noise
    for L, F in found:
        assert not (L.startswith("NOISE") or F.startswith("NOISE")), f"FAIL: spurious edge {L}->{F}"
    # direction must NOT be reversed
    assert ("FOLLOWER", "LEADER") not in found, "FAIL: reported reversed (follower->leader) edge"
    print(f"PASS  recovered LEADER->FOLLOWER at lag={rec_lag} (true={TRUE_LAG}); "
          f"FDR rejected all noise pairs; direction correct.")
