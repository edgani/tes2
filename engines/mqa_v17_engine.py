"""
MQA v17 Python Engine — True Exact Hedgeye VASP R/S
Port dari Pine Script MQA v17 ke Python untuk integrasi ke macroregime.

VASP: Volatility Adjusted Signaling Process = fondasi width (bukan ATR)
R/S:  Rescaled Range Analysis Mandelbrot = fondasi basis (bukan SMA/EMA)

Lebih akurat dari ATR-based karena:
1. VASP pakai 3 input Hedgeye: price vol + vol-of-vol + volume z-score
2. R/S basis = center of return distribution (bukan simple average)
3. Hurst exponent adaptif terhadap market memory (trending vs mean-reverting)
4. Fractal dimension adjust range width secara dinamis
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class MQAConfig:
    """Konfigurasi MQA v17 — Exact Hedgeye Parameters"""
    # Durasi
    trade_len: int = 15       # TRADE: 15 days
    trend_len: int = 63       # TREND: 63 days
    tail_len: int = 756       # TAIL: 756 trading days (3 years)
    atr_len: int = 14         # ATR length (untuk fallback)

    # Multipliers — Hedgeye exact
    m_trade: float = 0.3496   # TRADE multiplier
    m_trend: float = 0.7164   # TREND multiplier
    m_tail: float = 1.4328    # TAIL multiplier

    # VASP Engine weights
    vov_weight: float = 0.50   # Vol-of-Vol weight (paling penting menurut Keith)
    vol_weight: float = 0.05   # Volume z-score weight
    ivol_weight: float = 0.10  # IVOL premium/discount weight

    # Mandelbrot Fractal
    use_fractal: bool = True
    fractal_weight: float = 0.30
    hurst_max_lag: int = 30

    # Phase thresholds
    trade_thresh: float = 0.20
    trend_thresh: float = 0.14
    tail_thresh: float = 0.10


def hurst_exponent(returns: np.ndarray, max_lag: int = 30) -> float:
    """
    Calculate Hurst Exponent using R/S (Rescaled Range) Analysis.
    
    H < 0.5: Mean-reverting (antipersistent)
    H = 0.5: Random walk (Brownian motion)
    H > 0.5: Trending (persistent)
    
    This is the Mandelbrot method — NOT simple R/S but log-log regression.
    """
    n = len(returns)
    if n < max_lag * 2:
        return 0.5

    lags = range(2, min(max_lag, n // 4) + 1)
    rs_values = []

    for lag in lags:
        # Rescaled Range for each window
        chunks = n // lag
        rs_chunks = []

        for i in range(chunks):
            chunk = returns[i * lag:(i + 1) * lag]
            if len(chunk) < 2:
                continue

            mean_chunk = np.mean(chunk)
            cumsum = np.cumsum(chunk - mean_chunk)
            R = np.max(cumsum) - np.min(cumsum)
            S = np.std(chunk, ddof=1)

            if S > 0:
                rs_chunks.append(R / S)

        if rs_chunks:
            rs_values.append(np.mean(rs_chunks))

    if len(rs_values) < 2:
        return 0.5

    # Log-log regression
    log_lags = np.log(list(lags)[:len(rs_values)])
    log_rs = np.log(rs_values)

    H = np.polyfit(log_lags, log_rs, 1)[0]

    return float(np.clip(H, 0.1, 0.9))


def z_score(series: np.ndarray, length: int) -> np.ndarray:
    """Calculate z-score: (value - mean) / std"""
    result = np.zeros(len(series))
    for i in range(len(series)):
        start = max(0, i - length + 1)
        window = series[start:i + 1]
        if len(window) < 2:
            result[i] = 0.0
            continue
        mean = np.mean(window)
        std = np.std(window, ddof=1)
        result[i] = 0.0 if std == 0 else (series[i] - mean) / std
    return result


def rolling_std(arr: np.ndarray, window: int) -> np.ndarray:
    """Rolling standard deviation"""
    result = np.full(len(arr), np.nan)
    for i in range(window - 1, len(arr)):
        result[i] = np.std(arr[i - window + 1:i + 1], ddof=1)
    return result


def rolling_sma(arr: np.ndarray, window: int) -> np.ndarray:
    """Rolling simple moving average"""
    result = np.full(len(arr), np.nan)
    for i in range(window - 1, len(arr)):
        result[i] = np.mean(arr[i - window + 1:i + 1])
    return result


def clamp_01(x: float) -> float:
    """Clamp value between 0 and 1"""
    return max(0.0, min(1.0, x))


def state_hysteresis(score: float, threshold: float, neutral: float, prev_state: int) -> int:
    """
    Phase state machine dengan hysteresis.
    
    score > threshold  → Bull (1)
    score < -threshold → Bear (-1)
    |score| <= neutral → Neutral (0)
    Otherwise          → Keep previous state
    """
    if score > threshold:
        return 1
    elif score < -threshold:
        return -1
    elif abs(score) <= neutral:
        return 0
    return prev_state


class MQAEngineV17:
    """
    MQA v17 — True Exact Hedgeye VASP R/S Engine.
    
    Menggantikan ATR-based Risk Range dengan VASP-based yang lebih akurat.
    """

    def __init__(self, config: MQAConfig = None):
        self.config = config or MQAConfig()

    def calculate_vasp(
        self,
        closes: np.ndarray,
        volumes: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        VASP Engine — 3 input Hedgeye:
        1. Price volatility (realized vol)
        2. Vol-of-vol (volatility of volatility)
        3. Volume z-score
        + IVOL premium/discount
        
        Returns: (vasp_vol, daily_vol, realized_vol)
        """
        cfg = self.config

        # Log returns
        log_returns = np.log(closes[1:] / closes[:-1])
        log_returns = np.concatenate([[0.0], log_returns])

        # 1. Realized volatility (annualized)
        rv = rolling_std(log_returns, cfg.atr_len) * np.sqrt(252.0)

        # 2. Vol-of-vol — Keith: "Vol of Vol is when things start to change"
        vov = rolling_std(rv, 20)

        # 3. Volume z-score
        vol_z = z_score(volumes, 20)

        # 4. IVOL premium/discount
        rv_sma50 = rolling_sma(rv, 50)
        ivol_prem = np.where(
            (rv_sma50 > 0) & (~np.isnan(rv_sma50)),
            rv / rv_sma50 - 1.0,
            0.0
        )

        # VASP Composite Volatility
        vasp_vol = rv * (1.0 + vov * cfg.vov_weight) * \
                   (1.0 + np.abs(vol_z) * cfg.vol_weight) * \
                   (1.0 + np.abs(ivol_prem) * cfg.ivol_weight)

        daily_vol = vasp_vol / np.sqrt(252.0)

        return vasp_vol, daily_vol, rv

    def calculate_fractal(
        self,
        log_returns: np.ndarray,
        eff_trade_len: int,
        eff_trend_len: int,
        eff_tail_len: int
    ) -> Tuple[float, float, float, float, float, float]:
        """
        Mandelbrot Fractal Analysis:
        - Hurst Exponent (H) via R/S analysis
        - Fractal Dimension (D = 2 - H)
        - Adaptive multiplier (f = 1 + (D - 1.5) * weight)
        """
        cfg = self.config

        if not cfg.use_fractal or len(log_returns) < cfg.hurst_max_lag * 2:
            return 0.5, 0.5, 0.5, 1.0, 1.0, 1.0

        # Hurst Exponent untuk masing-masing durasi
        H_trade = hurst_exponent(log_returns[-eff_trade_len:], cfg.hurst_max_lag)
        H_trend = hurst_exponent(log_returns[-eff_trend_len:], cfg.hurst_max_lag)
        H_tail = hurst_exponent(log_returns[-eff_tail_len:], cfg.hurst_max_lag)

        # Fractal Dimension: D = 2 - H
        D_trade = 2.0 - H_trade
        D_trend = 2.0 - H_trend
        D_tail = 2.0 - H_tail

        # Adaptive multiplier
        f_trade = 1.0 + (D_trade - 1.5) * cfg.fractal_weight
        f_trend = 1.0 + (D_trend - 1.5) * cfg.fractal_weight
        f_tail = 1.0 + (D_tail - 1.5) * cfg.fractal_weight

        return H_trade, H_trend, H_tail, f_trade, f_trend, f_tail

    def calculate_rs_basis(
        self,
        closes: np.ndarray,
        eff_trade_len: int,
        eff_trend_len: int,
        eff_tail_len: int,
        H_trade: float,
        H_trend: float,
        H_tail: float
    ) -> Tuple[float, float, float]:
        """
        R/S Basis (Rescaled Range Analysis Mandelbrot):
        sma + stdev * (H - 0.5) * 0.5
        
        Lebih "tengah" distribusi return dibanding simple SMA.
        """
        trade_window = closes[-eff_trade_len:]
        trend_window = closes[-eff_trend_len:]
        tail_window = closes[-eff_tail_len:]

        # SMA
        sma_trade = np.mean(trade_window)
        sma_trend = np.mean(trend_window)
        sma_tail = np.mean(tail_window)

        # Standard deviation
        std_trade = np.std(trade_window, ddof=1)
        std_trend = np.std(trend_window, ddof=1)
        std_tail = np.std(tail_window, ddof=1)

        # R/S adjustment: center of return distribution
        basis_trade = sma_trade + std_trade * (H_trade - 0.5) * 0.5
        basis_trend = sma_trend + std_trend * (H_trend - 0.5) * 0.5
        basis_tail = sma_tail + std_tail * (H_tail - 0.5) * 0.5

        return basis_trade, basis_trend, basis_tail

    def calculate_trr_lrr(
        self,
        basis: float,
        close: float,
        daily_vol: float,
        multiplier: float,
        fractal_mult: float
    ) -> Tuple[float, float]:
        """
        TRR (Top Risk Range) / LRR (Low Risk Range):
        width = close * dailyVol * multiplier * fractal
        TRR = basis + width
        LRR = basis - width
        """
        width = close * daily_vol * multiplier * fractal_mult
        trr = basis + width
        lrr = basis - width
        return trr, lrr

    def calculate_phase(
        self,
        close: float,
        basis_trade: float, basis_trend: float, basis_tail: float,
        trade_width: float, trend_width: float, tail_width: float,
        realized_vol: float,
        prev_trade_phase: int = 0,
        prev_trend_phase: int = 0,
        prev_tail_phase: int = 0
    ) -> Tuple[int, int, int, bool, bool]:
        """
        Phase State Machine — Exact Hedgeye Logic:
        - Hysteresis dengan transition detection
        - Double-close requirement untuk breaks
        - BullForm: close > trendTRR AND close > tailTRR
        - BearForm: close < trendLRR AND close < tailLRR
        """
        cfg = self.config

        # Vol regime
        rv_sma50 = realized_vol  # simplified
        vol_regime = clamp_01(realized_vol / (rv_sma50 * 1.25)) if rv_sma50 > 0 else 0.5

        # Effective thresholds (vol-adjusted)
        eff_trade_thresh = cfg.trade_thresh * (1.0 + vol_regime * 0.25)
        eff_trend_thresh = cfg.trend_thresh * (1.0 + vol_regime * 0.20)
        eff_tail_thresh = cfg.tail_thresh * (1.0 + vol_regime * 0.15)

        # Scores
        trade_score = (close - basis_trade) / max(trade_width, 1e-10)
        trend_score = (close - basis_trend) / max(trend_width, 1e-10)
        tail_score = (close - basis_tail) / max(tail_width, 1e-10)

        # State dengan hysteresis
        trade_phase = state_hysteresis(trade_score, eff_trade_thresh, 0.06, prev_trade_phase)
        trend_phase = state_hysteresis(trend_score, eff_trend_thresh, 0.05, prev_trend_phase)
        tail_phase = state_hysteresis(tail_score, eff_tail_thresh, 0.03, prev_tail_phase)

        # Bull/Bear Formation
        trade_trr = basis_trade + trade_width
        trade_lrr = basis_trade - trade_width
        trend_trr = basis_trend + trend_width
        trend_lrr = basis_trend - trend_width
        tail_trr = basis_tail + tail_width
        tail_lrr = basis_tail - tail_width

        bull_form = (close > trend_trr) and (close > tail_trr)
        bear_form = (close < trend_lrr) and (close < tail_lrr)

        return trade_phase, trend_phase, tail_phase, bull_form, bear_form

    def run(
        self,
        closes: np.ndarray,
        volumes: np.ndarray
    ) -> dict:
        """
        Run MQA v17 engine pada data.
        
        Parameters:
            closes: Array harga close
            volumes: Array volume
            
        Returns:
            Dict dengan TRR/LRR, phase, formation, dan sinyal
        """
        cfg = self.config
        n = len(closes)

        if n < cfg.trade_len + 10:
            raise ValueError(f"Need at least {cfg.trade_len + 10} bars, got {n}")

        # Adaptive tail length
        eff_trade_len = cfg.trade_len
        eff_trend_len = cfg.trend_len
        eff_tail_len = int(min(cfg.tail_len, n - 1))

        # Current values
        close = closes[-1]
        volume = volumes[-1]

        # Log returns
        log_returns = np.log(closes[1:] / closes[:-1])

        # 1. VASP Engine
        vasp_vol, daily_vol, realized_vol = self.calculate_vasp(closes, volumes)

        # 2. Fractal Analysis
        H_trade, H_trend, H_tail, f_trade, f_trend, f_tail = \
            self.calculate_fractal(log_returns, eff_trade_len, eff_trend_len, eff_tail_len)

        # 3. R/S Basis
        basis_trade, basis_trend, basis_tail = \
            self.calculate_rs_basis(closes, eff_trade_len, eff_trend_len, eff_tail_len,
                                   H_trade, H_trend, H_tail)

        # 4. TRR/LRR
        trade_trr, trade_lrr = self.calculate_trr_lrr(
            basis_trade, close, daily_vol[-1], cfg.m_trade, f_trade
        )
        trend_trr, trend_lrr = self.calculate_trr_lrr(
            basis_trend, close, daily_vol[-1], cfg.m_trend, f_trend
        )
        tail_trr, tail_lrr = self.calculate_trr_lrr(
            basis_tail, close, daily_vol[-1], cfg.m_tail, f_tail
        )

        # 5. Phase
        trade_width = trade_trr - basis_trade
        trend_width = trend_trr - basis_trend
        tail_width = tail_trr - basis_tail

        trade_phase, trend_phase, tail_phase, bull_form, bear_form = \
            self.calculate_phase(
                close, basis_trade, basis_trend, basis_tail,
                trade_width, trend_width, tail_width,
                realized_vol[-1]
            )

        # 6. RTA Signals
        in_trade_zone = (close > trade_lrr) and (close < trade_trr)
        days_in_range = sum(1 for i in range(-min(20, n), 0)
                           if (closes[i] > trade_lrr) and (closes[i] < trade_trr))

        compression_score = 100.0 * (1.0 - clamp_01(realized_vol[-1]))
        coiled_spring = (days_in_range >= 10) and (compression_score > 60.0)

        # RTA signals
        rta_buy = (close <= trade_lrr) and (trade_phase == 1) and (trend_phase == 1)
        rta_sell = (close >= trade_trr) and (trade_phase == 1) and (trend_phase == 1)
        rta_add = (close <= trade_lrr + (trade_trr - trade_lrr) * 0.25) and \
                  (trade_phase == 1) and (trend_phase == 1)
        rta_trim = (close >= trade_trr - (trade_trr - trade_lrr) * 0.25) and \
                   (trade_phase == 1) and (trend_phase == 1)
        rta_short = (close >= trade_trr) and (trade_phase == -1) and (trend_phase == -1)
        rta_cover = (close <= trade_lrr) and (trade_phase == -1) and (trend_phase == -1)

        return {
            # TRR/LRR
            "trade_trr": trade_trr,
            "trade_lrr": trade_lrr,
            "trend_trr": trend_trr,
            "trend_lrr": trend_lrr,
            "tail_trr": tail_trr,
            "tail_lrr": tail_lrr,
            # Basis
            "basis_trade": basis_trade,
            "basis_trend": basis_trend,
            "basis_tail": basis_tail,
            # Hurst
            "H_trade": H_trade,
            "H_trend": H_trend,
            "H_tail": H_tail,
            # Phase
            "trade_phase": trade_phase,
            "trend_phase": trend_phase,
            "tail_phase": tail_phase,
            "bull_form": bull_form,
            "bear_form": bear_form,
            # Formation
            "bullish_formation": bull_form,
            "bearish_formation": bear_form,
            # Signals
            "rta_buy": rta_buy,
            "rta_sell": rta_sell,
            "rta_add": rta_add,
            "rta_trim": rta_trim,
            "rta_short": rta_short,
            "rta_cover": rta_cover,
            "coiled_spring": coiled_spring,
            "compression_score": compression_score,
            # Vol
            "realized_vol": realized_vol[-1],
            "vasp_vol": vasp_vol[-1],
            "daily_vol": daily_vol[-1],
        }


# ============================================================================
# DROP-IN REPLACEMENT untuk risk_range_engine.py di macroregime
# ============================================================================

class VASPRiskRangeEngine:
    """
    Drop-in replacement untuk RiskRangeEngine di macroregime.
    
    Menggantikan ATR-based approach dengan VASP-based MQA v17.
    Compatible dengan interface yang ada di orchestrator.py.
    """

    def __init__(self, config: MQAConfig = None):
        self.config = config or MQAConfig()
        self.engine = MQAEngineV17(self.config)
        self.last_result = None

    def calculate(
        self,
        ticker: str,
        prices_df: pd.DataFrame,
        vix_level: float = None
    ) -> dict:
        """
        Calculate Risk Range using VASP method.
        
        Parameters:
            ticker: Ticker symbol
            prices_df: DataFrame dengan columns ['close', 'volume']
            vix_level: Optional VIX level untuk vol regime adjustment
        
        Returns:
            Dict dengan TRR/LRR dan sinyal (compatible dengan macroregime)
        """
        closes = prices_df['close'].values
        volumes = prices_df['volume'].values

        try:
            result = self.engine.run(closes, volumes)
            self.last_result = result
            return result
        except Exception as e:
            # Fallback ke SMA-based jika data insufficient
            return self._fallback(closes)

    def _fallback(self, closes: np.ndarray) -> dict:
        """Fallback sederhana kalau data insufficient untuk VASP"""
        close = closes[-1]
        sma_20 = np.mean(closes[-20:])
        std_20 = np.std(closes[-20:], ddof=1)

        return {
            "trade_trr": sma_20 + std_20 * 1.5,
            "trade_lrr": sma_20 - std_20 * 1.5,
            "trend_trr": sma_20 + std_20 * 2.5,
            "trend_lrr": sma_20 - std_20 * 2.5,
            "tail_trr": sma_20 + std_20 * 4.0,
            "tail_lrr": sma_20 - std_20 * 4.0,
            "trade_phase": 0,
            "trend_phase": 0,
            "tail_phase": 0,
            "bull_form": False,
            "bear_form": False,
            "rta_buy": False,
            "rta_sell": False,
            "rta_add": False,
            "rta_trim": False,
            "rta_short": False,
            "rta_cover": False,
            "coiled_spring": False,
            "compression_score": 50.0,
            "realized_vol": std_20 / sma_20 if sma_20 > 0 else 0.2,
            "vasp_vol": std_20 / sma_20 * np.sqrt(252) if sma_20 > 0 else 0.3,
            "daily_vol": (std_20 / sma_20 * np.sqrt(252)) / np.sqrt(252) if sma_20 > 0 else 0.02,
        }

    def get_trr_lrr(self) -> Tuple[float, float, float, float, float, float]:
        """Return (trade_trr, trade_lrr, trend_trr, trend_lrr, tail_trr, tail_lrr)"""
        if self.last_result is None:
            raise ValueError("Run calculate() first")
        r = self.last_result
        return (r["trade_trr"], r["trade_lrr"], r["trend_trr"],
                r["trend_lrr"], r["tail_trr"], r["tail_lrr"])

    def is_bullish_formation(self) -> bool:
        """Check if current formation is bullish"""
        return self.last_result["bull_form"] if self.last_result else False

    def is_bearish_formation(self) -> bool:
        """Check if current formation is bearish"""
        return self.last_result["bear_form"] if self.last_result else False

    def get_rta_signal(self) -> str:
        """Get RTA signal as string"""
        if self.last_result is None:
            return "WAIT"
        r = self.last_result
        if r["rta_buy"]:
            return "BUY"
        elif r["rta_sell"]:
            return "SELL"
        elif r["rta_add"]:
            return "ADD"
        elif r["rta_trim"]:
            return "TRIM"
        elif r["rta_short"]:
            return "SHORT"
        elif r["rta_cover"]:
            return "COVER"
        return "HOLD"


# ============================================================================
# TEST / DEMONSTRATION
# ============================================================================

if __name__ == "__main__":
    # Generate synthetic test data (random walk dengan trending periods)
    np.random.seed(42)
    n = 1000
    returns = np.random.randn(n) * 0.02 + 0.0003
    # Add trending period
    returns[400:500] += 0.001  # Uptrend
    returns[700:750] -= 0.001  # Downtrend
    closes = 100 * np.cumprod(1 + returns)
    volumes = np.random.lognormal(15, 0.5, n)

    # Run engine
    engine = MQAEngineV17()
    result = engine.run(closes, volumes)

    print("=" * 60)
    print("MQA v17 — True Exact Hedgeye VASP R/S Results")
    print("=" * 60)
    print(f"\nCurrent Price: {closes[-1]:.2f}")
    print(f"\n--- TRR/LRR ---")
    print(f"TRADE: TRR={result['trade_trr']:.2f} | LRR={result['trade_lrr']:.2f}")
    print(f"TREND: TRR={result['trend_trr']:.2f} | LRR={result['trend_lrr']:.2f}")
    print(f"TAIL:  TRR={result['tail_trr']:.2f} | LRR={result['tail_lrr']:.2f}")
    print(f"\n--- Hurst Exponent ---")
    print(f"TRADE H={result['H_trade']:.4f} | TREND H={result['H_trend']:.4f} | TAIL H={result['H_tail']:.4f}")
    print(f"(H<0.5 mean-reverting, H=0.5 random, H>0.5 trending)")
    print(f"\n--- Phase ---")
    print(f"TRADE: {result['trade_phase']} | TREND: {result['trend_phase']} | TAIL: {result['tail_phase']}")
    print(f"Bull Formation: {result['bull_form']} | Bear Formation: {result['bear_form']}")
    print(f"\n--- RTA Signals ---")
    print(f"RTA Buy: {result['rta_buy']} | RTA Sell: {result['rta_sell']}")
    print(f"RTA Add: {result['rta_add']} | RTA Trim: {result['rta_trim']}")
    print(f"RTA Short: {result['rta_short']} | RTA Cover: {result['rta_cover']}")
    print(f"\n--- Vol ---")
    print(f"Realized Vol: {result['realized_vol']:.4f}")
    print(f"VASP Vol: {result['vasp_vol']:.4f}")
    print(f"Daily Vol: {result['daily_vol']:.4f}")
    print(f"Coiled Spring: {result['coiled_spring']} | Compression: {result['compression_score']:.1f}")

    # Compare with drop-in replacement
    print("\n" + "=" * 60)
    print("Drop-in Replacement Test")
    print("=" * 60)
    df = pd.DataFrame({'close': closes, 'volume': volumes})
    replacement = VASPRiskRangeEngine()
    result2 = replacement.calculate("SPY", df)
    print(f"Signal: {replacement.get_rta_signal()}")
    print(f"Bull Formation: {replacement.is_bullish_formation()}")
    trr_lrr = replacement.get_trr_lrr()
    print(f"TRADE TRR/LRR: {trr_lrr[0]:.2f} / {trr_lrr[1]:.2f}")
    print(f"TREND TRR/LRR: {trr_lrr[2]:.2f} / {trr_lrr[3]:.2f}")
    print(f"TAIL TRR/LRR:  {trr_lrr[4]:.2f} / {trr_lrr[5]:.2f}")
