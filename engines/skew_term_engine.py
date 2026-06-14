"""skew_term_engine.py — realized return skew proxy."""
import numpy as np
def run_skew_term(prices_dict):
    out = {}
    for t, s in (prices_dict or {}).items():
        try:
            r = np.log(s.dropna().pct_change().dropna() + 1).values
            if len(r) < 30: continue
            from scipy import stats
            sk = float(stats.skew(r[-63:]))
            out[t] = {"skew": round(sk, 4),
                     "interpretation": "FAT_LEFT_TAIL" if sk < -0.5 else "FAT_RIGHT_TAIL" if sk > 0.5 else "NORMAL"}
        except Exception:
            try:
                r = s.pct_change().dropna().values[-63:]
                sk = float(((r - r.mean()) ** 3).mean() / max((r.std() ** 3), 1e-9))
                out[t] = {"skew": round(sk, 4),
                         "interpretation": "FAT_LEFT_TAIL" if sk < -0.5 else "FAT_RIGHT_TAIL" if sk > 0.5 else "NORMAL"}
            except Exception: continue
    return out
