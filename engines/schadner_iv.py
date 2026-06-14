"""engines/schadner_iv.py — Schadner (2026) Explicit Black-Scholes Implied Volatility v1.0
Paper: "An Explicit Solution to Black-Scholes Implied Volatility" (arXiv:2604.24480)
University of Liechtenstein, April 2026.

Formulas:
  Away-from-forward:
    σ(K,C) = (2/√T) × [F⁻¹_IG((1−c)/m ; 2/|k| , 1)]^(−1/2)
  At-the-forward (K=F):
    σ(K=F,C) = (2/√T) × Φ⁻¹((c+1)/2)

Where:
  c = C/(D·F)   normalized call price
  k = ln(K/F)   forward log-moneyness
  m = 1 if K≥F, else m = K/F
  F⁻¹_IG = inverse Gaussian (Wald) quantile function
  Φ⁻¹ = inverse standard normal CDF

No iterative solver needed for ATM. For OTM/ITM uses numerical inversion
of inverse Gaussian CDF (binary search fallback if scipy unavailable).
"""
import math
from typing import Dict, Any, Optional
import numpy as np

# ── Try scipy for exact inverse Gaussian PPF ──
try:
    from scipy.stats import invgauss
    _HAS_SCIPY = True
except Exception:
    _HAS_SCIPY = False

def _norm_ppf(p):
    """Inverse standard normal CDF."""
    try:
        from scipy.stats import norm
        return norm.ppf(p)
    except Exception:
        # Abramowitz & Stegun approximation (Beasley-Springer-Moro)
        if p <= 0:
            return -1e10
        if p >= 1:
            return 1e10
        a = [2.50662823884, -18.61500062529, 41.39119773534, -25.44106049637]
        b = [-8.47351093090, 23.08336743743, -21.06224101826, 3.13082909833]
        c = [0.3374754822726147, 0.9761690190917186, 0.1607979714918209,
             0.0276438810333863, 0.0038405729373609, 0.0003951896511919,
             0.0000321767881768, 0.0000002888167364, 0.0000003960315187]
        y = p - 0.5
        if abs(y) < 0.42:
            r = y * y
            x = y * (((a[3]*r + a[2])*r + a[1])*r + a[0]) /                     ((((b[3]*r + b[2])*r + b[1])*r + b[0])*r + 1.0)
        else:
            r = p if y <= 0 else 1 - p
            r = math.log(-math.log(r))
            x = c[0] + r * (c[1] + r * (c[2] + r * (c[3] + r * (c[4] + r * (c[5] + r * (c[6] + r * (c[7] + r * c[8])))))))
            if y < 0:
                x = -x
        return x

def _ig_cdf(x, mu, lam=1.0):
    """Inverse Gaussian (Wald) CDF: F(x; μ, λ)."""
    if x <= 0:
        return 0.0
    if mu <= 0 or lam <= 0:
        return 0.0
    a = math.sqrt(lam / x)
    b1 = (x / mu) - 1.0
    b2 = (x / mu) + 1.0
    try:
        from scipy.stats import norm
        term1 = norm.cdf(a * b1)
        term2 = math.exp(2.0 * lam / mu) * norm.cdf(-a * b2)
        return term1 + term2
    except Exception:
        # Fallback to erf approximation for Φ
        def _phi_cdf(z):
            return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
        term1 = _phi_cdf(a * b1)
        term2 = math.exp(2.0 * lam / mu) * _phi_cdf(-a * b2)
        return term1 + term2

def _ig_ppf(p, mu, lam=1.0, tol=1e-12, max_iter=200):
    """Inverse Gaussian quantile via binary search (fallback if no scipy)."""
    if p <= 0:
        return 1e-12
    if p >= 1:
        return 1e6

    if _HAS_SCIPY:
        try:
            # scipy invgauss parameterization: mu = mean, scale = lambda
            return invgauss.ppf(p, mu=mu, scale=lam)
        except Exception:
            pass

    # Binary search for x where CDF(x) = p
    # Inverse Gaussian is right-skewed; mean = mu, mode ≈ mu*(sqrt(1+9*mu²/4lam²)-3*mu/2*lam)
    lo = 1e-12
    hi = max(mu * 20.0, 10.0)

    # Expand hi until CDF(hi) > p
    for _ in range(50):
        if _ig_cdf(hi, mu, lam) >= p:
            break
        hi *= 2.0

    for _ in range(max_iter):
        mid = (lo + hi) * 0.5
        cdf_mid = _ig_cdf(mid, mu, lam)
        if abs(cdf_mid - p) < tol:
            return mid
        if cdf_mid < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) * 0.5

def schadner_iv(C: float, K: float, F: float, T: float, D: float = 1.0) -> Optional[float]:
    """
    Schadner (2026) explicit implied volatility.

    Args:
        C: Call option price (undiscounted if D=1)
        K: Strike price
        F: Forward price (spot * exp(r*T) for non-div, or spot for quick proxy)
        T: Time to maturity in YEARS
        D: Discount factor (exp(-r*T)), default 1.0 for quick proxy

    Returns:
        Implied volatility as decimal (e.g., 0.20 for 20%), or None if invalid.
    """
    # Validation
    if C is None or K is None or F is None or T is None:
        return None
    C = float(C); K = float(K); F = float(F); T = float(T); D = float(D)
    if T <= 0 or F <= 0 or K <= 0 or C <= 0:
        return None
    if C >= F * D:  # Call price >= forward — arbitrage or deep ITM near expiry
        # Return high vol proxy
        return 2.0

    c = C / (D * F)  # normalized call price
    k = math.log(K / F)  # forward log-moneyness

    # At-the-forward (|k| < epsilon)
    eps = 1e-10
    if abs(k) < eps:
        # σ = (2/√T) × Φ⁻¹((c+1)/2)
        z = (c + 1.0) / 2.0
        if z <= 0 or z >= 1:
            return None
        phi_inv = _norm_ppf(z)
        sigma = (2.0 / math.sqrt(T)) * phi_inv
        return max(0.001, sigma)

    # Away from forward
    # m = 1 if K >= F, else m = K/F
    m = 1.0 if K >= F else (K / F)

    # Argument for inverse Gaussian CDF: (1-c)/m
    p_arg = (1.0 - c) / m
    if p_arg <= 0:
        # Deep ITM — return high vol
        return 2.0
    if p_arg >= 1:
        return 0.001

    # Inverse Gaussian parameters: μ = 2/|k|, λ = 1
    mu_ig = 2.0 / abs(k)
    lam_ig = 1.0

    # F⁻¹_IG(p_arg; mu_ig, lam_ig)
    x_ig = _ig_ppf(p_arg, mu_ig, lam_ig)
    if x_ig is None or x_ig <= 0:
        return None

    # σ = (2/√T) × (x_ig)^(-1/2)
    sigma = (2.0 / math.sqrt(T)) * math.pow(x_ig, -0.5)
    return max(0.001, sigma)

def validate_iv_proxy(ticker: str, proxy_iv: float, exact_iv: float) -> Dict[str, Any]:
    """Compare proxy IV vs Schadner exact IV."""
    proxy_iv = _safe_float(proxy_iv)
    exact_iv = _safe_float(exact_iv)
    if exact_iv > 0:
        err_pct = abs(exact_iv - proxy_iv) / exact_iv * 100.0
    else:
        err_pct = 0.0
    return {
        "ticker": ticker,
        "iv_proxy": round(proxy_iv, 6),
        "iv_exact": round(exact_iv, 6),
        "error_pct": round(err_pct, 4),
        "assessment": "EXCELLENT" if err_pct < 5 else "GOOD" if err_pct < 15 else "POOR" if err_pct < 30 else "BROKEN",
    }

def _safe_float(v, default=0.0):
    if v is None:
        return default
    try:
        f = float(v)
        return f if math.isfinite(f) else default
    except:
        return default

if __name__ == "__main__":
    # Test: ATM call, F=100, K=100, T=0.25, C=3.99 (≈ 20% vol via Black-Scholes)
    sigma = schadner_iv(C=3.99, K=100.0, F=100.0, T=0.25, D=1.0)
    print(f"Schadner IV (ATM): {sigma:.4f}  (expected ≈ 0.20)")

    # Test: OTM call, F=100, K=105, T=0.25, C=1.50
    sigma2 = schadner_iv(C=1.50, K=105.0, F=100.0, T=0.25, D=1.0)
    print(f"Schadner IV (OTM): {sigma2:.4f}")
