"""chain_reaction_v2.py — Multi-market Chain Reaction Catalog v40

Expanded from single oil→tanker example to 20+ chains covering:
- Oil shock → Tankers → Shipbuilders → LNG
- NVDA capex → Advanced Packaging → CoWoS → PCB → Cooling
- AI compute → HBM Memory → DRAM equipment
- Iran/geopolitics → Oil → Tankers + Defense materials
- China REE controls → Rare Earths → Defense + Magnets
- Fed cut → REITs + Homebuilders + Long bonds + Gold
- DXY down → EM Equities + Gold + Crypto
- Copper squeeze → Mining + Utility transformers + EV
- NatGas → LNG + Pipeline + Power gen
- Uranium → Small reactors + AI data center power
- Helium crisis → Industrial gas + Semiconductors
- Bitcoin → Miners + Custodians + Treasuries
- Quad shifts → Sector rotation (Hedgeye book)
- IHSG: Bandar accumulation chains (Bakrie/Salim/Barito/Astra groups)
- TSMC packaging crunch → AMD bidding war → OSAT outsourcing

Usage:
    from engines.chain_reaction_v2 import ChainReactionEngine
    cre = ChainReactionEngine()
    impacts = cre.calculate_cascade('CL=F', shock_pct=5.0, current_quad='Q3')
"""
from __future__ import annotations
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ChainLink:
    parent: str
    child: str
    beta: float            # historical pass-through (1.0 = 1:1, 2.0 = amplified)
    lag_days: int          # transmission lag
    direction: str         # SAME | INVERSE
    quad_filter: List[str] = field(default_factory=list)  # active in these quads only (empty = all)
    confidence: str = "MEDIUM"  # LOW | MEDIUM | HIGH
    thesis: str = ""


# ═══════════════════════════════════════════════════════════════════════════
# CHAIN CATALOG — 20+ chains, ~150 transmission edges
# ═══════════════════════════════════════════════════════════════════════════

CHAIN_CATALOG = {

    # ── 1. OIL SHOCK → TANKERS → SHIPBUILDERS ────────────────────────────
    "oil_shock": {
        "primary_driver": "CL=F",
        "thesis": "Oil supply shock (Iran/OPEC/sanctions) → freight rates spike → tanker stocks → shipbuilders → ports",
        "chains": [
            ChainLink("CL=F", "FRO", 1.75, 1, "SAME", confidence="HIGH",
                      thesis="Frontline — largest crude tanker fleet, direct freight rate beneficiary"),
            ChainLink("CL=F", "STNG", 1.65, 1, "SAME", confidence="HIGH",
                      thesis="Scorpio — product tanker, refined product rate spike"),
            ChainLink("CL=F", "INSW", 1.50, 1, "SAME", confidence="HIGH",
                      thesis="International Seaways — diversified crude+product"),
            ChainLink("CL=F", "DHT", 1.55, 1, "SAME", confidence="HIGH"),
            ChainLink("CL=F", "TNK", 1.40, 1, "SAME"),
            ChainLink("CL=F", "TRMD", 1.30, 1, "SAME"),
            ChainLink("CL=F", "ASC", 1.45, 1, "SAME"),
            # Second order — refiners (squeeze)
            ChainLink("CL=F", "VLO", -0.40, 2, "INVERSE",
                      thesis="Refiners hurt initially by crude squeeze"),
            ChainLink("CL=F", "MPC", -0.35, 2, "INVERSE"),
            # Energy producers
            ChainLink("CL=F", "XLE", 0.85, 0, "SAME", confidence="HIGH"),
            ChainLink("CL=F", "XOP", 1.10, 0, "SAME", confidence="HIGH"),
            ChainLink("CL=F", "OIH", 1.20, 1, "SAME", confidence="HIGH"),
            ChainLink("CL=F", "USO", 0.95, 0, "SAME", confidence="HIGH"),
            # Third order — shipbuilders
            ChainLink("FRO", "SBLK", 0.40, 5, "SAME",
                      thesis="Tanker capex → dry bulk + shipbuilder demand"),
            ChainLink("FRO", "GSL", 0.35, 5, "SAME"),
            # IHSG offshore
            ChainLink("CL=F", "PGAS.JK", 0.55, 2, "SAME", quad_filter=["Q2", "Q3"]),
            ChainLink("CL=F", "MEDC.JK", 0.85, 1, "SAME", confidence="HIGH"),
            ChainLink("CL=F", "AKRA.JK", 0.45, 2, "SAME"),
        ],
    },

    # ── 2. NVDA CAPEX → ADVANCED PACKAGING (CoWoS) ───────────────────────
    "nvda_packaging": {
        "primary_driver": "NVDA",
        "thesis": "NVDA Blackwell+Rubin demand → TSMC CoWoS sold out 2026 → OSAT capacity rush (AMKR/ASX/INTC EMIB) → PCB interconnect → liquid cooling",
        "chains": [
            # Direct CoWoS bottleneck
            ChainLink("NVDA", "TSM", 0.60, 0, "SAME", confidence="HIGH",
                      thesis="50%+ TSMC CoWoS capacity locked by NVDA through 2027"),
            ChainLink("NVDA", "AMKR", 1.30, 2, "SAME", confidence="HIGH",
                      thesis="$2.5-3B capex 2026, Arizona expansion, OSAT capacity beneficiary"),
            ChainLink("NVDA", "ASX", 1.25, 2, "SAME", confidence="HIGH",
                      thesis="ASE Technology — projecting AP sales DOUBLE in 2026"),
            ChainLink("NVDA", "INTC", 0.30, 5, "SAME",
                      thesis="EMIB + Foveros 3D — unexpected packaging beneficiary"),
            # Custom silicon / accelerators
            ChainLink("NVDA", "AVGO", 0.55, 1, "SAME", confidence="HIGH",
                      thesis="Custom accelerators + networking — same compute boom"),
            ChainLink("NVDA", "MRVL", 0.85, 1, "SAME", confidence="HIGH",
                      thesis="CPO ASIC, custom silicon — NVDA $2B lock-in target"),
            # HBM Memory
            ChainLink("NVDA", "MU", 1.05, 1, "SAME", confidence="HIGH",
                      thesis="HBM3e/4 — gating factor for B200/GB200"),
            # Optical / CPO (NVDA $2B playbook)
            ChainLink("NVDA", "COHR", 1.40, 2, "SAME", confidence="HIGH",
                      thesis="$2B NVDA capacity lock-in for optical"),
            ChainLink("NVDA", "LITE", 1.50, 2, "SAME", confidence="HIGH",
                      thesis="$2B NVDA lock-in — 200G EML monopoly"),
            ChainLink("NVDA", "SIVE", 1.80, 3, "SAME",
                      thesis="CPO mass production 2027 — same playbook target"),
            ChainLink("NVDA", "AAOI", 1.35, 3, "SAME"),
            ChainLink("NVDA", "POET", 1.55, 4, "SAME"),
            # MEMS Timing
            ChainLink("NVDA", "SITM", 1.45, 3, "SAME",
                      thesis="MEMS timing — 150%+ growth 7q, NVDA buildout"),
            # InP substrates
            ChainLink("NVDA", "AXTI", 1.30, 4, "SAME",
                      thesis="60-70% InP substrate share — CPO substrate"),
            # Glass substrates (advanced packaging next-gen)
            ChainLink("NVDA", "GLW", 0.40, 5, "SAME",
                      thesis="Glass substrates — TSMC roadmap next-gen"),
            # PCB / Interconnect
            ChainLink("NVDA", "CRDO", 1.10, 3, "SAME",
                      thesis="MicroLED + interconnects"),
            ChainLink("NVDA", "TEL", 0.55, 4, "SAME",
                      thesis="Connectors — bandwidth scaling"),
            ChainLink("NVDA", "APH", 0.50, 4, "SAME"),
            # Power / Cooling
            ChainLink("NVDA", "VRT", 1.20, 2, "SAME", confidence="HIGH",
                      thesis="Vertiv — liquid cooling, GB200 1000W per chip"),
            ChainLink("NVDA", "ETN", 0.65, 4, "SAME",
                      thesis="Power electronics — DC infrastructure"),
            # Taiwan PCB
            ChainLink("NVDA", "4915.TW", 1.65, 2, "SAME", confidence="HIGH",
                      thesis="Nextronics — direct NVDA PCB supplier"),
        ],
    },

    # ── 3. IRAN/GEOPOLITICS → DEFENSE + OIL DOUBLE PLAY ──────────────────
    "iran_geopolitics": {
        "primary_driver": "USO",  # use as proxy for ME tension
        "thesis": "Iran/Houthi/sanctions escalation → Oil up + Defense spending + Tankers + Materials",
        "chains": [
            # Oil chain (cascades into oil_shock)
            ChainLink("USO", "CL=F", 0.95, 0, "SAME", confidence="HIGH"),
            # Defense primes
            ChainLink("USO", "LMT", 0.45, 5, "SAME",
                      thesis="Lockheed — Patriot/THAAD demand on ME escalation"),
            ChainLink("USO", "RTX", 0.40, 5, "SAME"),
            ChainLink("USO", "NOC", 0.40, 5, "SAME"),
            ChainLink("USO", "GD", 0.35, 5, "SAME"),
            # Defense materials
            ChainLink("USO", "ATI", 0.50, 7, "SAME",
                      thesis="Allegheny — titanium for missile/aerospace"),
            ChainLink("USO", "KTOS", 0.60, 5, "SAME",
                      thesis="Kratos — small drones, target drones, hypersonic"),
            ChainLink("USO", "TXT", 0.40, 7, "SAME"),
            # Rare materials
            ChainLink("USO", "MP", 0.55, 10, "SAME",
                      thesis="MP Materials — REE for missile guidance"),
            ChainLink("USO", "USAR", 0.65, 10, "SAME"),
            # Cyber security
            ChainLink("USO", "PANW", 0.25, 5, "SAME"),
            ChainLink("USO", "CRWD", 0.25, 5, "SAME"),
        ],
    },

    # ── 4. CHINA REE EXPORT CONTROLS → CRITICAL MINERALS ─────────────────
    "china_ree_control": {
        "primary_driver": "MP",
        "thesis": "China REE export controls → Western miners + processors + magnets + EVs",
        "chains": [
            ChainLink("MP", "USAR", 1.30, 2, "SAME", confidence="HIGH",
                      thesis="US Antimony — rare metal processing"),
            ChainLink("MP", "TMC", 0.85, 5, "SAME",
                      thesis="TMC the metals company — deep sea nodules"),
            ChainLink("MP", "UAMY", 1.20, 3, "SAME"),
            ChainLink("MP", "ASTL", 0.75, 5, "SAME"),
            # Defense
            ChainLink("MP", "LMT", 0.20, 10, "SAME",
                      thesis="Defense primes benefit from REE supply security"),
            ChainLink("MP", "NOC", 0.20, 10, "SAME"),
            # Magnets / EV
            ChainLink("MP", "GM", -0.15, 15, "INVERSE",
                      thesis="EV makers hurt by magnet cost rise"),
            ChainLink("MP", "F", -0.15, 15, "INVERSE"),
        ],
    },

    # ── 5. FED RATE CUT (DOVISH PIVOT) ───────────────────────────────────
    "fed_cut": {
        "primary_driver": "TLT",  # bonds rallying = rate cut expectation
        "thesis": "TLT up → rate cut priced in → REITs, utilities, homebuilders, gold, EM",
        "chains": [
            ChainLink("TLT", "GLD", 0.55, 2, "SAME", confidence="HIGH",
                      thesis="Real rates ↓ → gold ↑"),
            ChainLink("TLT", "GDX", 1.45, 3, "SAME", confidence="HIGH"),
            ChainLink("TLT", "VNQ", 0.85, 5, "SAME", confidence="HIGH",
                      thesis="REITs — duration trade"),
            ChainLink("TLT", "O", 0.95, 5, "SAME"),
            ChainLink("TLT", "XLU", 0.65, 5, "SAME"),
            ChainLink("TLT", "XHB", 1.15, 5, "SAME",
                      thesis="Homebuilders — mortgage rate sensitivity"),
            ChainLink("TLT", "ITB", 1.20, 5, "SAME"),
            # EM
            ChainLink("TLT", "EEM", 0.45, 7, "SAME",
                      thesis="Dovish Fed → USD ↓ → EM equities ↑"),
            ChainLink("TLT", "INDA", 0.35, 7, "SAME"),
            ChainLink("TLT", "EIDO", 0.40, 7, "SAME"),
            # Crypto
            ChainLink("TLT", "BTC-USD", 0.65, 3, "SAME",
                      thesis="Liquidity proxy"),
            # USD inverse
            ChainLink("TLT", "DX-Y.NYB", -0.55, 2, "INVERSE", confidence="HIGH"),
        ],
    },

    # ── 6. DXY DOWN (DOLLAR WEAKNESS) ────────────────────────────────────
    "dxy_down": {
        "primary_driver": "DX-Y.NYB",
        "thesis": "Dollar down → everything priced in USD up",
        "chains": [
            # NEGATIVE direction (DXY DOWN → asset UP)
            ChainLink("DX-Y.NYB", "GC=F", -0.85, 1, "INVERSE", confidence="HIGH"),
            ChainLink("DX-Y.NYB", "SI=F", -1.10, 1, "INVERSE", confidence="HIGH"),
            ChainLink("DX-Y.NYB", "CL=F", -0.45, 2, "INVERSE",
                      thesis="Oil priced in USD"),
            ChainLink("DX-Y.NYB", "HG=F", -0.55, 2, "INVERSE"),
            ChainLink("DX-Y.NYB", "EEM", -0.65, 3, "INVERSE",
                      thesis="EM debt cost ↓ when USD ↓"),
            ChainLink("DX-Y.NYB", "BTC-USD", -0.40, 3, "INVERSE"),
            # Currency pairs
            ChainLink("DX-Y.NYB", "EURUSD=X", -1.00, 0, "INVERSE"),
            ChainLink("DX-Y.NYB", "JPY=X", 0.85, 0, "SAME"),
            # IHSG benefit
            ChainLink("DX-Y.NYB", "^JKSE", -0.45, 5, "INVERSE",
                      thesis="USD ↓ → IDR ↑ → IHSG ↑"),
            ChainLink("DX-Y.NYB", "IDR=X", 0.75, 1, "SAME"),
        ],
    },

    # ── 7. COPPER SUPPLY SQUEEZE ─────────────────────────────────────────
    "copper_squeeze": {
        "primary_driver": "HG=F",
        "thesis": "Copper deficit (mining capex underinvestment, EV+grid demand) → miners, transformers, EV",
        "chains": [
            ChainLink("HG=F", "FCX", 1.85, 1, "SAME", confidence="HIGH",
                      thesis="Freeport — pure-play copper"),
            ChainLink("HG=F", "SCCO", 1.65, 1, "SAME", confidence="HIGH"),
            ChainLink("HG=F", "TECK", 1.35, 2, "SAME"),
            ChainLink("HG=F", "BHP", 0.85, 2, "SAME"),
            ChainLink("HG=F", "RIO", 0.85, 2, "SAME"),
            # Utility transformers (Grid+EV demand)
            ChainLink("HG=F", "GE", 0.45, 5, "SAME"),
            ChainLink("HG=F", "ETN", 0.55, 5, "SAME"),
            ChainLink("HG=F", "HUBB", 0.65, 5, "SAME"),
            ChainLink("HG=F", "POWL", 1.15, 5, "SAME"),
        ],
    },

    # ── 8. NAT GAS → LNG → POWER GEN ─────────────────────────────────────
    "natgas_lng": {
        "primary_driver": "NG=F",
        "thesis": "NatGas spike → LNG exporters + pipeline + power gen (data center demand)",
        "chains": [
            ChainLink("NG=F", "LNG", 0.95, 2, "SAME", confidence="HIGH",
                      thesis="Cheniere — largest LNG exporter"),
            ChainLink("NG=F", "EQT", 1.25, 1, "SAME", confidence="HIGH"),
            ChainLink("NG=F", "AR", 1.45, 1, "SAME"),
            ChainLink("NG=F", "RRC", 1.30, 1, "SAME"),
            ChainLink("NG=F", "CTRA", 1.20, 1, "SAME"),
            # Pipelines
            ChainLink("NG=F", "WMB", 0.55, 3, "SAME"),
            ChainLink("NG=F", "KMI", 0.50, 3, "SAME"),
            ChainLink("NG=F", "ET", 0.65, 3, "SAME"),
            # Data center power
            ChainLink("NG=F", "VST", 0.95, 5, "SAME",
                      thesis="Vistra — gas+nuclear power for AI"),
            ChainLink("NG=F", "TLN", 1.05, 5, "SAME"),
            ChainLink("NG=F", "NRG", 0.75, 5, "SAME"),
        ],
    },

    # ── 9. URANIUM RENAISSANCE (SMR + AI POWER) ──────────────────────────
    "uranium_smr": {
        "primary_driver": "CCJ",
        "thesis": "Small modular reactors + AI data center power demand → uranium miners + SMR developers",
        "chains": [
            ChainLink("CCJ", "UEC", 1.55, 2, "SAME", confidence="HIGH"),
            ChainLink("CCJ", "DNN", 1.45, 2, "SAME"),
            ChainLink("CCJ", "UUUU", 1.35, 3, "SAME"),
            ChainLink("CCJ", "NXE", 1.40, 3, "SAME"),
            # SMR developers
            ChainLink("CCJ", "SMR", 1.85, 5, "SAME", confidence="HIGH",
                      thesis="NuScale Power — SMR pure play"),
            ChainLink("CCJ", "OKLO", 1.95, 5, "SAME",
                      thesis="Oklo — fast reactor design"),
            ChainLink("CCJ", "BWXT", 0.85, 5, "SAME"),
            # AI data center
            ChainLink("CCJ", "VST", 0.55, 5, "SAME"),
            ChainLink("CCJ", "CEG", 0.65, 5, "SAME"),
        ],
    },

    # ── 10. BITCOIN → MINERS + TREASURY HOLDERS ──────────────────────────
    "bitcoin_chain": {
        "primary_driver": "BTC-USD",
        "thesis": "BTC up → miners (operating leverage), MSTR (BTC treasury), COIN (volume)",
        "chains": [
            ChainLink("BTC-USD", "MSTR", 1.85, 1, "SAME", confidence="HIGH",
                      thesis="MicroStrategy — BTC treasury company, leveraged BTC"),
            ChainLink("BTC-USD", "MARA", 2.10, 1, "SAME", confidence="HIGH"),
            ChainLink("BTC-USD", "RIOT", 1.95, 1, "SAME"),
            ChainLink("BTC-USD", "CLSK", 2.15, 1, "SAME"),
            ChainLink("BTC-USD", "HUT", 1.75, 1, "SAME"),
            ChainLink("BTC-USD", "COIN", 1.45, 1, "SAME", confidence="HIGH"),
            ChainLink("BTC-USD", "HOOD", 1.05, 2, "SAME"),
            # ETH proxy
            ChainLink("BTC-USD", "ETH-USD", 1.20, 0, "SAME"),
            # Stablecoin / fintech
            ChainLink("BTC-USD", "SQ", 0.65, 2, "SAME"),
        ],
    },

    # ── 11. SEMICONDUCTOR CYCLE ──────────────────────────────────────────
    "semis_cycle": {
        "primary_driver": "SOXX",
        "thesis": "Semis broad cycle — equipment, design, foundry, memory all moving together",
        "chains": [
            ChainLink("SOXX", "AMAT", 1.15, 1, "SAME", confidence="HIGH"),
            ChainLink("SOXX", "LRCX", 1.20, 1, "SAME", confidence="HIGH"),
            ChainLink("SOXX", "KLAC", 1.10, 1, "SAME"),
            ChainLink("SOXX", "ASML", 1.05, 1, "SAME", confidence="HIGH",
                      thesis="EUV/High-NA monopoly"),
            ChainLink("SOXX", "TER", 1.25, 2, "SAME"),
            ChainLink("SOXX", "ENTG", 1.15, 2, "SAME"),
            ChainLink("SOXX", "FORM", 1.45, 2, "SAME"),
            ChainLink("SOXX", "ACLS", 1.55, 2, "SAME"),
            ChainLink("SOXX", "ONTO", 1.55, 2, "SAME"),
        ],
    },

    # ── 12. QUAD 2 ROTATION (Growth+Inflation accel) ─────────────────────
    "quad2_rotation": {
        "primary_driver": "QUAD2",
        "thesis": "Quad2 = Growth↑ Inflation↑ → energy, financials, commodities, cyclicals, value",
        "chains": [
            # No price-based parent — these are quad-conditional always-on signals
            ChainLink("QUAD2", "XLE", 1.0, 0, "SAME", quad_filter=["Q2"], confidence="HIGH"),
            ChainLink("QUAD2", "XLF", 1.0, 0, "SAME", quad_filter=["Q2"], confidence="HIGH"),
            ChainLink("QUAD2", "XLI", 1.0, 0, "SAME", quad_filter=["Q2"], confidence="HIGH"),
            ChainLink("QUAD2", "XLB", 1.0, 0, "SAME", quad_filter=["Q2"]),
            ChainLink("QUAD2", "IWM", 1.0, 0, "SAME", quad_filter=["Q2"]),
            ChainLink("QUAD2", "EFA", 1.0, 0, "SAME", quad_filter=["Q2"]),
        ],
    },

    # ── 13. QUAD 4 DEFENSIVE ROTATION ────────────────────────────────────
    "quad4_rotation": {
        "primary_driver": "QUAD4",
        "thesis": "Quad4 = Growth↓ Inflation↓ → USD, treasuries, utilities, staples, gold",
        "chains": [
            ChainLink("QUAD4", "UUP", 1.0, 0, "SAME", quad_filter=["Q4"], confidence="HIGH"),
            ChainLink("QUAD4", "TLT", 1.0, 0, "SAME", quad_filter=["Q4"], confidence="HIGH"),
            ChainLink("QUAD4", "XLU", 1.0, 0, "SAME", quad_filter=["Q4"]),
            ChainLink("QUAD4", "XLP", 1.0, 0, "SAME", quad_filter=["Q4"]),
            ChainLink("QUAD4", "GLD", 1.0, 0, "SAME", quad_filter=["Q4"]),
            ChainLink("QUAD4", "JNK", -1.0, 0, "INVERSE", quad_filter=["Q4"],
                      thesis="HY credit blows out in Quad4"),
        ],
    },

    # ── 14. AI POWER INFRASTRUCTURE (Citrini Phase 2) ────────────────────
    "ai_power_infra": {
        "primary_driver": "VRT",
        "thesis": "AI data center power crisis → liquid cooling, transformers, gas turbines, nuclear",
        "chains": [
            ChainLink("VRT", "ETN", 0.65, 2, "SAME", confidence="HIGH",
                      thesis="Power management for data centers"),
            ChainLink("VRT", "NVT", 0.85, 2, "SAME",
                      thesis="nVent — electrical containment"),
            ChainLink("VRT", "PWR", 0.65, 3, "SAME",
                      thesis="Quanta Services — utility infrastructure build"),
            ChainLink("VRT", "MYRG", 0.55, 5, "SAME"),
            ChainLink("VRT", "AROC", 0.45, 5, "SAME"),
            ChainLink("VRT", "GE", 0.55, 5, "SAME",
                      thesis="GE Vernova — gas turbines + grid"),
            ChainLink("VRT", "GEV", 0.95, 3, "SAME", confidence="HIGH"),
            # Cooling specialists
            ChainLink("VRT", "MOD", 0.85, 3, "SAME"),
            ChainLink("VRT", "FTNT", 0.30, 5, "SAME"),
            # Power gen play (cross with natgas chain)
            ChainLink("VRT", "VST", 0.75, 5, "SAME"),
            ChainLink("VRT", "CEG", 0.65, 5, "SAME"),
            ChainLink("VRT", "TLN", 0.85, 5, "SAME"),
            # NVTS pivot (per Edward's NVTS doc — GaN power)
            ChainLink("VRT", "NVTS", 1.45, 3, "SAME",
                      thesis="Navitas GaN — high voltage DC for AI data centers"),
        ],
    },

    # ── 15. ATOMS OVER BITS (Citrini materials thesis) ───────────────────
    "atoms_over_bits": {
        "primary_driver": "STX",  # Seagate (storage = atoms for AI)
        "thesis": "Citrini thesis — physical bottlenecks > software. Storage, materials, packaging.",
        "chains": [
            ChainLink("STX", "WDC", 1.35, 1, "SAME", confidence="HIGH"),
            ChainLink("STX", "SNDK", 1.45, 1, "SAME", confidence="HIGH",
                      thesis="SanDisk — flash, NVMe"),
            ChainLink("STX", "MU", 0.75, 2, "SAME"),
            # Materials
            ChainLink("STX", "SOLS", 0.55, 5, "SAME",
                      thesis="Solstice — HON spinoff, advanced materials"),
            ChainLink("STX", "MTRN", 0.65, 5, "SAME",
                      thesis="Materion — beryllium, specialty materials"),
            ChainLink("STX", "ATI", 0.55, 5, "SAME"),
            # Aerospace aluminum
            ChainLink("STX", "AA", 0.45, 7, "SAME"),
            ChainLink("STX", "CENX", 0.55, 7, "SAME"),
        ],
    },

    # ── 16. IHSG BANDAR — BARITO/PRAJOGO GROUP ───────────────────────────
    "ihsg_barito_group": {
        "primary_driver": "TPIA.JK",
        "thesis": "Barito Pacific (Prajogo Pangestu) group cross-flow — TPIA leads, BREN/CUAN/BRPT follow",
        "chains": [
            ChainLink("TPIA.JK", "BREN.JK", 1.55, 1, "SAME", confidence="HIGH",
                      thesis="Barito Renewables — same parent group"),
            ChainLink("TPIA.JK", "BRPT.JK", 1.25, 1, "SAME",
                      thesis="Barito Pacific holding"),
            ChainLink("TPIA.JK", "CUAN.JK", 1.15, 2, "SAME"),
            ChainLink("TPIA.JK", "PTRO.JK", 0.85, 2, "SAME",
                      thesis="Petrosea — Prajogo affiliate"),
            ChainLink("TPIA.JK", "^JKSE", 0.35, 0, "SAME",
                      thesis="Mega-cap drives index"),
        ],
    },

    # ── 17. IHSG BANDAR — SALIM GROUP ────────────────────────────────────
    "ihsg_salim_group": {
        "primary_driver": "INDF.JK",
        "thesis": "Salim group consumer flow — INDF leads, ICBP/BISI/DLTA follow",
        "chains": [
            ChainLink("INDF.JK", "ICBP.JK", 1.20, 1, "SAME", confidence="HIGH"),
            ChainLink("INDF.JK", "BISI.JK", 0.85, 2, "SAME"),
            ChainLink("INDF.JK", "DLTA.JK", 0.65, 3, "SAME"),
            ChainLink("INDF.JK", "INDR.JK", 0.55, 3, "SAME"),
            ChainLink("INDF.JK", "INKP.JK", 0.45, 3, "SAME"),
        ],
    },

    # ── 18. IHSG BANJIR DOMESTIK — BIG BANK FLOW ─────────────────────────
    "ihsg_bigbank_flow": {
        "primary_driver": "BBCA.JK",
        "thesis": "BBCA leads — BMRI/BBRI/BBNI follow. Foreign flow visible via this rotation.",
        "chains": [
            ChainLink("BBCA.JK", "BMRI.JK", 0.95, 1, "SAME", confidence="HIGH"),
            ChainLink("BBCA.JK", "BBRI.JK", 1.05, 1, "SAME", confidence="HIGH"),
            ChainLink("BBCA.JK", "BBNI.JK", 1.15, 1, "SAME"),
            ChainLink("BBCA.JK", "BRIS.JK", 0.85, 2, "SAME"),
            ChainLink("BBCA.JK", "^JKSE", 0.45, 0, "SAME",
                      thesis="Big 4 banks = ~30% IHSG weight"),
        ],
    },

    # ── 19. IHSG COAL/COMMODITY (when Oil/Coal up) ───────────────────────
    "ihsg_coal_commodity": {
        "primary_driver": "ADRO.JK",
        "thesis": "Coal cycle / commodity bandar — ADRO leads, ITMG/PTBA/BUMI follow",
        "chains": [
            ChainLink("ADRO.JK", "ITMG.JK", 1.15, 1, "SAME", confidence="HIGH"),
            ChainLink("ADRO.JK", "PTBA.JK", 1.05, 1, "SAME"),
            ChainLink("ADRO.JK", "BUMI.JK", 1.45, 2, "SAME",
                      thesis="Bumi Resources — high beta coal"),
            ChainLink("ADRO.JK", "HRUM.JK", 1.25, 2, "SAME"),
            ChainLink("ADRO.JK", "INDY.JK", 1.10, 2, "SAME"),
            # Cross: oil → coal
            ChainLink("CL=F", "ADRO.JK", 0.45, 3, "SAME"),
        ],
    },

    # ── 20. HELIUM CRISIS → INDUSTRIAL GAS + SEMI ────────────────────────
    "helium_crisis": {
        "primary_driver": "APD",
        "thesis": "Helium supply constraint → industrial gas majors + semiconductor process gases",
        "chains": [
            ChainLink("APD", "LIN", 0.85, 1, "SAME", confidence="HIGH",
                      thesis="Linde — industrial gas major"),
            ChainLink("APD", "AIR", 0.95, 1, "SAME"),
            # Semi process gases
            ChainLink("APD", "ENTG", 0.45, 3, "SAME"),
            ChainLink("APD", "MRC", 0.55, 5, "SAME"),
            # Helium specifically
            ChainLink("APD", "AEH", 1.35, 3, "SAME",
                      thesis="Atomic Energy Helium — small-cap helium pure play"),
        ],
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class ChainReactionEngine:
    """Compute multi-order chain reactions from a price shock."""

    def __init__(self):
        # Build reverse lookup: child → list of (chain_name, ChainLink)
        self.child_lookup = {}
        for chain_name, chain_data in CHAIN_CATALOG.items():
            for link in chain_data["chains"]:
                self.child_lookup.setdefault(link.child, []).append((chain_name, link))

    def get_chain_for_parent(self, parent: str) -> List[Dict]:
        """Return all chains where parent is the primary driver."""
        results = []
        for chain_name, chain_data in CHAIN_CATALOG.items():
            if chain_data["primary_driver"] == parent:
                results.append({
                    "chain": chain_name,
                    "thesis": chain_data["thesis"],
                    "links": chain_data["chains"],
                })
        return results

    def calculate_cascade(
        self,
        parent: str,
        shock_pct: float,
        current_quad: str = "Q3",
        max_depth: int = 3,
    ) -> Dict:
        """Calculate expected % move on downstream tickers given parent shock.

        Args:
            parent: source ticker (e.g. 'CL=F')
            shock_pct: shock magnitude (e.g. +5.0 for +5% oil move)
            current_quad: Q1/Q2/Q3/Q4 for quad filter
            max_depth: recursion depth for second/third-order

        Returns:
            {
              'first_order': [{'ticker':..., 'expected_pct':..., 'beta':..., 'lag':...}, ...],
              'second_order': [...],
              'chain_summary': str,
            }
        """
        first_order, second_order, third_order = [], [], []
        visited = {parent}

        def expand(current_ticker, current_shock, depth, source_chain=None):
            if depth > max_depth or current_ticker not in self.child_lookup and not any(
                c["primary_driver"] == current_ticker for c in CHAIN_CATALOG.values()
            ):
                return
            # Find chains where current_ticker is parent
            for chain_name, chain_data in CHAIN_CATALOG.items():
                if chain_data["primary_driver"] != current_ticker:
                    continue
                for link in chain_data["chains"]:
                    if link.child in visited:
                        continue
                    # Quad filter
                    if link.quad_filter and current_quad not in link.quad_filter:
                        continue
                    sign = -1 if link.direction == "INVERSE" else 1
                    expected_pct = current_shock * link.beta * sign
                    item = {
                        "ticker": link.child,
                        "parent": current_ticker,
                        "expected_pct": round(expected_pct, 2),
                        "beta": link.beta,
                        "lag_days": link.lag_days,
                        "direction": link.direction,
                        "confidence": link.confidence,
                        "thesis": link.thesis,
                        "chain": chain_name,
                        "order": depth,
                    }
                    visited.add(link.child)
                    if depth == 1:
                        first_order.append(item)
                    elif depth == 2:
                        second_order.append(item)
                    elif depth == 3:
                        third_order.append(item)
                    # Recurse
                    expand(link.child, expected_pct, depth + 1, chain_name)

        expand(parent, shock_pct, 1)

        # Sort by expected impact magnitude
        first_order.sort(key=lambda x: abs(x["expected_pct"]), reverse=True)
        second_order.sort(key=lambda x: abs(x["expected_pct"]), reverse=True)
        third_order.sort(key=lambda x: abs(x["expected_pct"]), reverse=True)

        return {
            "parent": parent,
            "shock_pct": shock_pct,
            "current_quad": current_quad,
            "first_order": first_order[:20],
            "second_order": second_order[:20],
            "third_order": third_order[:10],
            "total_tickers_impacted": len(first_order) + len(second_order) + len(third_order),
        }

    def get_all_chains(self) -> Dict:
        """Return all chains metadata for UI display."""
        return {
            name: {
                "primary_driver": data["primary_driver"],
                "thesis": data["thesis"],
                "link_count": len(data["chains"]),
                "tickers": [link.child for link in data["chains"]],
            }
            for name, data in CHAIN_CATALOG.items()
        }

    def find_parents_of(self, ticker: str) -> List[Dict]:
        """Reverse lookup — which chains affect this ticker?"""
        if ticker not in self.child_lookup:
            return []
        return [
            {
                "chain": chain_name,
                "parent": CHAIN_CATALOG[chain_name]["primary_driver"],
                "beta": link.beta,
                "lag_days": link.lag_days,
                "direction": link.direction,
                "thesis": link.thesis,
            }
            for chain_name, link in self.child_lookup[ticker]
        ]


# Singleton
_engine_instance = None

def get_chain_engine() -> ChainReactionEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = ChainReactionEngine()
    return _engine_instance


def calculate_cascade(parent: str, shock_pct: float, current_quad: str = "Q3") -> Dict:
    """Convenience wrapper."""
    return get_chain_engine().calculate_cascade(parent, shock_pct, current_quad)
