"""regime_hmm.py — L1 State Layer: REAL Gaussian HMM fitted at RUNTIME on the daily feature vector
(replaces the quad→lookup posterior). Latent states are mapped to the GCFIS regime taxonomy by their
return/vol signature (lowest mean-return state = risk_off … highest = risk_on). Graceful fallback to a
vol/trend heuristic when hmmlearn is unavailable or data is thin. Fitting at runtime on real series is
NOT synthetic theatre — it learns the regime structure of whatever data the app feeds it."""
from __future__ import annotations
import numpy as np, pandas as pd

try:
    from hmmlearn.hmm import GaussianHMM
    _HAVE_HMM = True
except Exception:                                            # pragma: no cover
    _HAVE_HMM = False

REGIMES_5 = ["risk_off", "transition_down", "chop", "transition_up", "risk_on"]
REGIMES_3 = ["risk_off", "chop", "risk_on"]

def _features(index_returns, breadth=None, xasset_corr=None, vix=None) -> pd.DataFrame:
    r = pd.to_numeric(pd.Series(index_returns), errors="coerce").dropna()
    f = pd.DataFrame(index=r.index)
    f["ret20"] = r.rolling(20).mean()
    f["vol20"] = r.rolling(20).std()
    f["ret5"] = r.rolling(5).mean()
    if vix is not None: f["vix"] = pd.to_numeric(pd.Series(vix), errors="coerce").reindex(r.index)
    if breadth is not None: f["breadth"] = pd.to_numeric(pd.Series(breadth), errors="coerce").reindex(r.index)
    if xasset_corr is not None: f["xcorr"] = pd.to_numeric(pd.Series(xasset_corr), errors="coerce").reindex(r.index)
    return f.dropna()

_QUAD_PRIOR = {"Q1": {"risk_on": 0.55, "transition_up": 0.30, "chop": 0.15},
               "Q2": {"risk_on": 0.45, "transition_up": 0.30, "chop": 0.25},
               "Q3": {"chop": 0.45, "transition_down": 0.35, "risk_off": 0.20},
               "Q4": {"risk_off": 0.55, "transition_down": 0.30, "chop": 0.15}}

def _fallback(index_returns, gip_hint: str | None = None) -> dict:
    r = pd.to_numeric(pd.Series(index_returns), errors="coerce").dropna()
    if len(r) < 25:
        return {"ok": True, "method": "neutral", "posterior": {"chop": 1.0}, "state": "chop"}
    ret = r.tail(20).mean(); vol = r.tail(20).std(); vol_hi = r.rolling(20).std().tail(120).quantile(0.7)
    if vol > (vol_hi or vol) and ret < 0: post = {"risk_off": 0.7, "transition_down": 0.3}
    elif ret < 0:                          post = {"transition_down": 0.6, "chop": 0.4}
    elif vol > (vol_hi or vol) and ret > 0: post = {"transition_up": 0.6, "risk_on": 0.4}
    elif ret > 0:                          post = {"risk_on": 0.7, "transition_up": 0.3}
    else:                                  post = {"chop": 1.0}
    q = _QUAD_PRIOR.get(str(gip_hint or "").upper()[:2])
    if q:                                                   # blend trend heuristic 50/50 with the system's own quad call
        keys = set(post) | set(q)
        post = {k: round(0.5 * post.get(k, 0.0) + 0.5 * q.get(k, 0.0), 3) for k in keys}
        s = sum(post.values()) or 1.0
        post = {k: v / s for k, v in post.items()}
        method = "heuristic_fallback+gip"
    else:
        method = "heuristic_fallback"
    return {"ok": True, "method": method, "posterior": post, "state": max(post, key=post.get)}

def run_regime_hmm(index_returns, n_states: int = 5, breadth=None, xasset_corr=None, vix=None, seed: int = 42, gip_hint: str | None = None) -> dict:
    f = _features(index_returns, breadth, xasset_corr, vix)
    if not _HAVE_HMM or len(f) < 150:
        return _fallback(index_returns, gip_hint)
    X = ((f - f.mean()) / (f.std() + 1e-9)).values
    names = REGIMES_5 if n_states == 5 else (REGIMES_3 if n_states == 3 else [f"S{i}" for i in range(n_states)])
    try:
        m = GaussianHMM(n_components=n_states, covariance_type="diag", n_iter=200, random_state=seed)
        m.fit(X)
        post = m.predict_proba(X)[-1]
        order = np.argsort([m.means_[s][0] for s in range(n_states)])   # by mean ret20 (col 0), ascending
        name_by_state = {int(s): names[rank] for rank, s in enumerate(order)}
        posterior = {}
        for s in range(n_states):
            posterior[name_by_state[s]] = posterior.get(name_by_state[s], 0.0) + float(post[s])
        return {"ok": True, "method": "GaussianHMM", "posterior": {k: round(v, 3) for k, v in posterior.items()},
                "state": max(posterior, key=posterior.get), "n_states": n_states}
    except Exception:
        return _fallback(index_returns, gip_hint)
