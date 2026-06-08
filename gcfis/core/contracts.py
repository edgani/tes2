"""core/contracts.py — single typed per-ticker output (GCFIS output contract, incl. ENTRY)."""
from __future__ import annotations
from dataclasses import dataclass, field

@dataclass
class TickerSignal:
    ticker: str
    theme: str = ""
    meta_score: float = 0.0
    action: str = "STAND_ASIDE"          # BUILD_LONG / BUILD_SHORT / START_SCALING / STAND_ASIDE
    direction: str = "none"
    conviction: float = 0.0
    scores: dict = field(default_factory=dict)   # accumulation/theme/dealer/positioning/...
    adoption_stage: str = "UNKNOWN"
    crowding: float = 0.0
    broker_verdict: str = ""
    # --- ENTRY (L13) ---
    entry_type: str = ""                 # BREAKOUT/PULLBACK/CONTINUATION/MEAN_REVERSION/BREAKDOWN/BOUNCE_SHORT
    entry_valid: bool = False
    gamma_regime: str = "unknown"
    entry_px: float = 0.0
    stop: float = 0.0
    target: float = 0.0
    rr: float = 0.0
    # --- sizing (filled by sizing.py, gated) ---
    alloc_pct: float = 0.0
    capacity_ok: bool = True
    reason: str = ""
    def as_dict(self): return {k: (v.copy() if isinstance(v, dict) else v) for k, v in self.__dict__.items()}
