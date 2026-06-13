"""core/contracts.py — full GCFIS per-ticker output contract (Identity/Scores/Institutional/
Options/Macro/Risk/Opportunity/Entry/Conviction). One typed struct, no dict-soup."""
from __future__ import annotations
from dataclasses import dataclass, field

@dataclass
class TickerSignal:
    # Identity
    ticker: str
    theme: str = ""
    subtheme: str = ""
    # decision
    meta_score: float = 0.0
    action: str = "STAND_ASIDE"          # BUILD_LONG / BUILD_SHORT / START_SCALING / STAND_ASIDE
    direction: str = "none"
    conviction: float = 0.0
    # Scores (full panel; absent layers stay None)
    scores: dict = field(default_factory=dict)   # meta_long/meta_short/accumulation/theme/bottleneck/reflexivity/positioning/dealer/confluence
    # Institutional
    adoption_stage: str = "UNKNOWN"
    crowding: float = 0.0
    institutional: dict = field(default_factory=dict)   # revision/ownership_delta/etf_flow
    broker_verdict: str = ""
    # offensive layer values
    bottleneck: float = 0.0
    reflexivity: float = 0.0
    runaway: bool = False
    # Options panel
    options: dict = field(default_factory=dict)   # call_wall/put_wall/gex/gex_sign/vanna/is_real
    # Macro context (stamped per ticker)
    macro: dict = field(default_factory=dict)     # quad/liquidity_regime/fragility/shock_prob/cross_asset_regime
    # Entry (L13)
    entry_type: str = ""
    entry_valid: bool = False
    gamma_regime: str = "unknown"
    entry_px: float = 0.0
    stop: float = 0.0
    target: float = 0.0
    rr: float = 0.0
    # Risk + Opportunity scenarios
    shock_prob: float = 0.0
    opportunity: dict = field(default_factory=dict)   # bear/base/bull/supercycle price targets
    rotation: dict = field(default_factory=dict)   # lead-lag rotation timing (leader/lag/window/strength)
    # decision stack (doc 6) + market structure (doc 5/7) + flow (doc 1/2)
    market: str = ""
    market_mode: str = "MIXED"
    flow: dict = field(default_factory=dict)
    response: dict = field(default_factory=dict)
    bm: dict = field(default_factory=dict)   # BandarMetrics regime readout (idx)
    ev: float | None = None                  # expected value %: p·reward − (1−p)·risk (p=conv/100)
    surge: float | None = None               # doc-20 pre-conditioning score (priors)
    category: str = "WATCH"
    why_now: list = field(default_factory=list)
    whos_trapped: str = ""
    invalidation: dict = field(default_factory=dict)
    execution: dict = field(default_factory=dict)
    # sizing (gated)
    alloc_pct: float = 0.0
    capacity_ok: bool = True
    reason: str = ""
    def as_dict(self): return {k: (v.copy() if isinstance(v, (dict, list)) else v) for k, v in self.__dict__.items()}
