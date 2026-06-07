"""gcfis/core/contracts.py — single typed output schema (kills dict-soup, GCFIS output contract)."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class LayerScore:
    name: str
    value: float            # 0..100
    z: float = 0.0
    delta_z: float = 0.0    # change-centric companion
    confidence: float = 1.0 # down-weight proxies (P4)
    is_real: bool = True
    def as_dict(self): return self.__dict__.copy()

@dataclass
class TickerSignal:
    ticker: str
    theme: str = ""
    meta_score: float = 0.0
    scores: dict = field(default_factory=dict)        # layer -> value
    adoption_stage: str = "UNKNOWN"
    crowding: float = 0.0
    broker_verdict: str = ""
    action: str = "STAND_ASIDE"   # BUILD_LONG / BUILD_SHORT / START_SCALING / STAND_ASIDE
    conviction: float = 0.0       # 0..100 (heuristic prior unless fitted)
    reason: str = ""
    def as_dict(self): return {k: (v.copy() if isinstance(v, dict) else v) for k, v in self.__dict__.items()}
