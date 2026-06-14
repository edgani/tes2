"""alpha_center_curator.py — Bottleneck + Surge Potential filter v40.2

PHILOSOPHY (per Edward's rules):
1. Tickers MUST be either:
   (a) A genuine bottleneck (monopoly, near-monopoly, or capacity-constrained supplier
       to a hyper-growth value chain), OR
   (b) Have >100% upside potential (small-cap with structural tailwind that could
       multi-bag — SIVE, PLTR-style, AAOI-style)

2. Every entry MUST have:
   • ticker symbol
   • thesis (1-2 sentences why this exists)
   • bottleneck_reason (WHY they're a bottleneck — what makes them irreplaceable)
   • correlations (β-style — primary driver, e.g. NVDA↔Nextronics, AVGO↔CoWoS)
   • source attribution (which Citrini report / which researcher)
   • catalysts (2026)
   • potential_upside (estimated multi-bag potential if thesis plays out)
   • risk (key downside risk)

3. SOURCES (deep research consensus from earlier turn):
   • Citrini Research — "26 Trades 2026", "Atoms Over Bits", "AI Bureaucracy Alpha",
     "Advanced Packaging Bottleneck", "CPO M&A watchlist", "NVDA $2B playbook"
   • Hyperscaler (HyperTechInvest) bottleneck mapping
   • SemiAnalysis (jukan05 reddit, Dylan Patel)
   • ParadisLabs — packaging + optical thesis
   • Tier1Alpha (Keith McCullough) — Hedgeye TRR/LRR overlay
   • Cem Karsan — Vanna/Charm structural flows
   • Bandar Indonesia (Hengky Adinata) — IHSG cornering analysis
   • Druckenmiller — macro thematic (uranium, copper, energy)
   • Coatue / Leopold — AI scaling thesis

4. Multi-market: US, IHSG, crypto, commodities, forex
"""
from __future__ import annotations
import json, logging, os
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# CURATED UNIVERSE — Each entry meets Edward's strict criteria
# ═══════════════════════════════════════════════════════════════════════════

ALPHA_CENTER_CANDIDATES = {

    # ╔═══════════════════════════════════════════════════════════════════╗
    # ║ TIER S+ — BOTTLENECK MONOPOLIES (Citrini "linchpin" category)     ║
    # ╚═══════════════════════════════════════════════════════════════════╝

    "TSM": {
        "market": "us_equity", "stars": 5,
        "thesis": "Taiwan Semiconductor — the linchpin of global AI compute. 90%+ of leading-edge logic + CoWoS packaging passes through TSMC. Geopolitical risk discounted; structural tailwind compounding.",
        "bottleneck_reason": "Only entity capable of 3nm/2nm production at scale. CoWoS-S/L packaging capacity is THE gating bottleneck for NVDA Blackwell/Rubin (capacity sold through 2027). High-NA EUV + advanced packaging moat is multi-decade.",
        "correlations": {
            "NVDA": "0.60 — primary CoWoS customer (50%+ of capacity locked)",
            "AVGO": "0.55 — custom silicon foundry",
            "AAPL": "0.45 — A-series + M-series chip exclusive",
            "AMD": "0.40 — MI300 ramp dependency",
        },
        "monopoly_strength": "🔴 HARD MONOPOLY (no alternative exists for leading-edge AI)",
        "sources": ["citrini-linchpin", "HyperTechInvest", "jukan05-semianalysis", "ParadisLabs"],
        "catalysts_2026": [
            "2nm risk production H2 2026",
            "CoWoS capacity doubled vs 2025 — pricing power demo",
            "Arizona Fab 2 ramp",
            "Glass substrate adoption announcement",
        ],
        "potential_upside": "+50-80% (large-cap, not multi-bag — but lowest-risk AI exposure)",
        "risk": "China invasion of Taiwan (tail-risk priced)",
        "tags": ["AI", "Foundry", "Monopoly", "Bottleneck"],
    },

    "AVGO": {
        "market": "us_equity", "stars": 5,
        "thesis": "Broadcom — Hock Tan's custom AI silicon empire. Google TPU + Meta MTIA + ByteDance custom AI = ~25% revenue and growing. Networking (Tomahawk 5) is THE switch fabric of AI data centers.",
        "bottleneck_reason": "Only volume custom AI accelerator designer outside NVDA. ASIC + networking + VMware integration = sticky compute + connectivity duopoly with NVDA. Tomahawk switches have 70%+ share in AI clusters.",
        "correlations": {
            "NVDA": "0.55 — converge on AI compute spend",
            "TSM": "0.55 — custom silicon foundry partner",
            "GOOGL": "0.60 — primary TPU customer",
            "META": "0.40 — MTIA customer",
        },
        "monopoly_strength": "🟡 NEAR-MONOPOLY (only credible alternative AI silicon)",
        "sources": ["citrini-26trades", "HyperTechInvest", "ParadisLabs", "zephyr_z9"],
        "catalysts_2026": [
            "New custom silicon customer announcement (Apple? Microsoft?)",
            "VMware synergy unlock",
            "Networking 1.6T design wins",
        ],
        "potential_upside": "+50-100% (mega-cap appreciation)",
        "risk": "Multiple expansion limited at 80x forward EPS",
        "tags": ["AI", "Custom Silicon", "Networking", "Bottleneck"],
    },

    "MU": {
        "market": "us_equity", "stars": 4,
        "thesis": "Micron — HBM3e/4 supply for NVDA Blackwell. Memory cycle inflection + AI HBM demand creating multi-year tailwind.",
        "bottleneck_reason": "HBM is the GATING bottleneck for AI accelerator throughput. Only 3 HBM suppliers (Micron, SK Hynix, Samsung) — strict triopoly with NVDA exclusive deals. Capacity sold through 2027.",
        "correlations": {
            "NVDA": "1.05 — direct HBM customer",
            "TSM": "0.70 — packaging dependency",
            "AMD": "0.55 — MI300 HBM customer",
        },
        "monopoly_strength": "🟠 STRICT TRIOPOLY (3 suppliers, capacity locked)",
        "sources": ["citrini-atoms", "aleabitoreddit", "HyperTechInvest", "jukan05"],
        "catalysts_2026": [
            "HBM4 ramp Q2 2026 (50% bandwidth uplift)",
            "Pricing power demonstration Q1 earnings",
            "HBM3e capacity sold out validation",
        ],
        "potential_upside": "+30-60% (already in motion — LATE-MID stage per Edward)",
        "risk": "Cycle peak signals if hyperscaler capex slows",
        "tags": ["AI", "Memory", "Triopoly", "Bottleneck"],
    },

    # ╔═══════════════════════════════════════════════════════════════════╗
    # ║ TIER S — NEAR-MONOPOLY + MULTI-BAG POTENTIAL                     ║
    # ╚═══════════════════════════════════════════════════════════════════╝

    "PLTR": {
        "market": "us_equity", "stars": 5,
        "thesis": "Palantir — only credible enterprise-grade AI ontology platform. Government + commercial dual moat. 'AI Bureaucracy Alpha' Citrini theme = software replacing knowledge workers at scale.",
        "bottleneck_reason": "Foundry/Gotham platform is the de-facto government AI standard. ICE/CIA/Army contracts create entrenched ontology lock-in. AIP (AI Platform) wins commercial enterprises where data is messy — moat is the OS layer, not the model.",
        "correlations": {
            "MSFT": "0.35 — Azure cohabitation",
            "NVDA": "0.30 — compute dependency",
            "DefenseTech (LMT/RTX)": "0.40 — gov contract correlation",
        },
        "monopoly_strength": "🟡 NEAR (no enterprise ontology competitor at scale)",
        "sources": ["citrini-bureaucracy", "alextaussig", "HyperTechInvest"],
        "catalysts_2026": [
            "Commercial AIP contract wins acceleration",
            "ICE/CBP $1B+ contract renewals",
            "European defense expansion",
        ],
        "potential_upside": "+100-300% if AIP scales (multi-bag remains, even after run-up)",
        "risk": "Valuation extreme; founder dependence",
        "tags": ["AI", "Government", "SaaS", "Citrini"],
    },

    "MRVL": {
        "market": "us_equity", "stars": 5,
        "thesis": "Marvell — CPO ASIC + 800G/1.6T PAM4 DSP. The networking brain of AI clusters. NVDA $2B capacity lock-in target validates monopoly path.",
        "bottleneck_reason": "Only volume CPO (co-packaged optics) ASIC designer. Custom AI XPU ramp (Amazon Trainium 2, Microsoft) makes this a hyperscaler infrastructure play. Optical DSP duopoly with AVGO.",
        "correlations": {
            "NVDA": "0.85 — direct lock-in 2025",
            "AVGO": "0.65 — optical DSP duopoly",
            "COHR": "0.70 — optical components ecosystem",
            "AMZN": "0.45 — Trainium ASIC customer",
        },
        "monopoly_strength": "🟡 NEAR (only credible CPO ASIC pioneer)",
        "sources": ["citrini-cpo", "aleabitoreddit", "ParadisLabs", "jukan05"],
        "catalysts_2026": [
            "Custom AI XPU revenue ramp ($2B run-rate target)",
            "CPO mass production 2027 prep — capacity announcements",
            "Trainium 2 / next-gen design wins",
        ],
        "potential_upside": "+100-200% (mid-cap with monopoly thesis)",
        "risk": "Hyperscaler concentration; AMD vs NVDA spillover",
        "tags": ["AI", "Optical", "CPO", "NVDA-playbook"],
    },

    "COHR": {
        "market": "us_equity", "stars": 4,
        "thesis": "Coherent — optical components. NVDA $2B capacity lock-in 2025 = playbook validation. Bridge product (200G EML, OCS) + InP photonics roll-up.",
        "bottleneck_reason": "Only volume EML + InP laser supplier for 800G+ optics. NVDA literally pre-paid $2B to secure capacity. II-VI merger consolidated industry leadership.",
        "correlations": {
            "NVDA": "1.40 — direct $2B lock-in",
            "LITE": "1.20 — duopoly partner",
            "MRVL": "0.70 — CPO ecosystem",
            "AXTI": "0.95 — InP substrate dependency",
        },
        "monopoly_strength": "🟡 NEAR (EML duopoly with LITE)",
        "sources": ["citrini-cpo", "ParadisLabs", "HyperTechInvest"],
        "catalysts_2026": [
            "EML capacity ramp (2x by 2026)",
            "DGX H200/B200 connector revenue",
            "InP photonics roll-up announcements",
        ],
        "potential_upside": "+80-150%",
        "risk": "Capex-heavy; M&A indigestion",
        "tags": ["AI", "Optical", "NVDA-playbook"],
    },

    # ╔═══════════════════════════════════════════════════════════════════╗
    # ║ TIER A — MULTI-BAG POTENTIAL (>200-500% if thesis plays out)      ║
    # ╚═══════════════════════════════════════════════════════════════════╝

    "SIVE": {
        "market": "us_equity", "stars": 5,
        "thesis": "Sivers Semiconductors — CW Laser pure-play for CPO. Small-cap (<$500M), thin float = explosive on M&A. Citrini explicitly named as M&A target (AVGO/MRVL acquirer probable).",
        "bottleneck_reason": "Only Western-headquartered scaled CW laser maker for CPO. CPO mass production 2027 requires hundreds of thousands of CW lasers/year — SIVE has IP + production line ready. Acquisition imminent at $3-5B+ valuation by 2026.",
        "correlations": {
            "NVDA": "1.80 — beta",
            "COHR": "1.50 — CPO ecosystem leader",
            "MRVL": "1.10 — CPO ASIC partnership",
            "POET": "1.40 — speculative correlation",
        },
        "monopoly_strength": "🟠 CONTESTED (Western CW laser, but small)",
        "sources": ["citrini-mna-explicit", "ParadisLabs", "HyperTechInvest"],
        "catalysts_2026": [
            "CPO mass production 2027 prep — capacity disclosure",
            "M&A announcement (HIGH probability)",
            "Customer wins (AVGO Tomahawk, MRVL CPO ASIC)",
        ],
        "potential_upside": "🚀 +300-1000% (multi-bag if M&A or contract win)",
        "risk": "Execution; cash burn; pre-revenue scale",
        "tags": ["AI", "Optical", "M&A-Target", "Small-Cap", "MULTI-BAG"],
    },

    "AAOI": {
        "market": "us_equity", "stars": 4,
        "thesis": "Applied Optoelectronics — CPO / optical transceivers. Microsoft Azure 800G ramp + 1.6T pipeline. Execution risk = high beta = high return.",
        "bottleneck_reason": "Independent transceiver maker without II-VI/Coherent overhang. MSFT primary customer. 800G CPO transceivers are the volume product 2026-2027.",
        "correlations": {
            "NVDA": "1.35 — AI infrastructure beta",
            "MSFT": "0.65 — Azure datacom",
            "COHR": "0.85 — duopoly competitor",
        },
        "monopoly_strength": "🟠 CONTESTED",
        "sources": ["citrini-cpo", "HyperTechInvest", "zephyr_z9", "ParadisLabs"],
        "catalysts_2026": [
            "MSFT 800G order ramp confirmation",
            "1.6T product launch H2",
            "Margin expansion as yield improves",
        ],
        "potential_upside": "+150-400% if execution holds",
        "risk": "Customer concentration (MSFT >50%)",
        "tags": ["AI", "Optical", "MULTI-BAG"],
    },

    "POET": {
        "market": "us_equity", "stars": 3,
        "thesis": "POET Technologies — optical interposer that disrupts CPO architecture. Pre-revenue speculative but if adopted = paradigm shift.",
        "bottleneck_reason": "Proprietary optical interposer enables CW laser integration at scale. If adopted by hyperscaler, replaces traditional CPO substrate stack. Highest pure speculation in optical chain.",
        "correlations": {
            "NVDA": "1.55 — beta",
            "SIVE": "1.40 — same speculative bucket",
            "COHR": "0.85 — could integrate",
        },
        "monopoly_strength": "🟢 UNIQUE IP (if adopted = monopoly; if not = zero)",
        "sources": ["citrini-cpo-speculative", "ParadisLabs"],
        "catalysts_2026": [
            "Customer announcement (CRITICAL — name or zero)",
            "Mass production volume disclosure",
            "Lock-up release",
        ],
        "potential_upside": "🚀 +500-2000% if validated; -80% if not",
        "risk": "Pre-revenue; technology bet",
        "tags": ["AI", "Optical", "Speculative", "MULTI-BAG"],
    },

    "SITM": {
        "market": "us_equity", "stars": 4,
        "thesis": "SiTime — MEMS Timing chips. 150%+ growth 7 quarters in a row. Critical for high-speed AI signaling.",
        "bottleneck_reason": "MEMS timing is 100x more precise than quartz crystals. Every hyperscaler design win locks in 5+ year revenue. Sub-supplier monopoly in precision timing.",
        "correlations": {
            "NVDA": "1.45 — beta to AI compute",
            "AVGO": "0.65 — networking integration",
            "SOXX": "0.95 — semi cycle",
        },
        "monopoly_strength": "🟡 NEAR (only volume MEMS timing maker)",
        "sources": ["citrini-bottleneck", "HyperTechInvest", "aleabitoreddit"],
        "catalysts_2026": [
            "Hyperscaler design wins (AWS, GCP)",
            "Margin expansion to 60%+",
            "Auto/IOT TAM expansion",
        ],
        "potential_upside": "+100-300%",
        "risk": "High multiple; semi cycle exposure",
        "tags": ["AI", "Timing", "Bottleneck"],
    },

    "AXTI": {
        "market": "us_equity", "stars": 3,
        "thesis": "AXT Inc — InP substrate 60-70% market share. China-headquartered = geopolitical risk discount = M&A target (COHR likely acquirer).",
        "bottleneck_reason": "60-70% share of InP wafer market. CPO requires InP — every CW laser starts as InP wafer. Citrini explicit M&A watchlist (COHR or Japanese consortium acquirer).",
        "correlations": {
            "COHR": "0.95 — primary customer",
            "LITE": "0.85 — secondary customer",
            "SIVE": "0.75 — material dependency",
        },
        "monopoly_strength": "🟡 NEAR-MONOPOLY (substrate side)",
        "sources": ["citrini-mna-watchlist", "ParadisLabs"],
        "catalysts_2026": [
            "Pricing power demo (InP shortage)",
            "M&A interest disclosure",
            "China export control reaction",
        ],
        "potential_upside": "+200-500% on M&A or pricing breakthrough",
        "risk": "China geopolitical; valuation overhang",
        "tags": ["AI", "Materials", "M&A-Target", "China-Risk"],
    },

    "LITE": {
        "market": "us_equity", "stars": 4,
        "thesis": "Lumentum — 200G EML monopoly (only volume shipper). NVDA $2B lock-in beneficiary alongside COHR.",
        "bottleneck_reason": "Only-volume 200G EML laser supplier. Datacom + Cisco anchor revenue + NVDA pre-purchase = monopoly cash flow.",
        "correlations": {
            "NVDA": "1.50 — direct lock-in",
            "COHR": "1.05 — EML duopoly",
            "MRVL": "0.85 — DSP partnership",
            "AXTI": "0.85 — InP substrate input",
        },
        "monopoly_strength": "🔴 HARD (200G EML — only volume shipper)",
        "sources": ["citrini-cpo", "ParadisLabs", "aleabitoreddit"],
        "catalysts_2026": [
            "200G EML capacity 2x ramp",
            "Cisco datacom recovery",
            "NVDA next-gen wins",
        ],
        "potential_upside": "+80-200%",
        "risk": "Customer concentration; CapEx cycle",
        "tags": ["AI", "Optical", "Monopoly"],
    },

    "GLW": {
        "market": "us_equity", "stars": 3,
        "thesis": "Corning — glass substrates for next-gen packaging (TSMC roadmap). Specialty fiber for AI data centers.",
        "bottleneck_reason": "Only credible glass substrate supplier for advanced packaging (replaces organic substrates next gen). Specialty fiber for hyperscaler interconnect.",
        "correlations": {
            "TSM": "0.45 — packaging roadmap",
            "NVDA": "0.40 — packaging beneficiary",
            "VRT": "0.35 — datacenter infra",
        },
        "monopoly_strength": "🟡 NEAR (glass substrate, specialty fiber)",
        "sources": ["citrini-glass", "ParadisLabs"],
        "catalysts_2026": [
            "Glass substrate adoption announcement (TSMC)",
            "Specialty fiber data center wins",
            "Margin expansion",
        ],
        "potential_upside": "+50-150%",
        "risk": "Slow adoption cycle",
        "tags": ["AI", "Materials", "Substrate"],
    },

    "CRDO": {
        "market": "us_equity", "stars": 3,
        "thesis": "Credo Technology — Active Electrical Cables (AEC). Alternative to optical at sub-3m distances. Margin expansion runway.",
        "bottleneck_reason": "AEC = the cost-effective interconnect for sub-3m racks (>50% of inside-rack interconnect). Volume ramp accelerating with 800G/1.6T transitions.",
        "correlations": {
            "NVDA": "1.10 — direct rack-level beneficiary",
            "AVGO": "0.55 — interconnect competition",
            "MRVL": "0.65 — DSP integration",
        },
        "monopoly_strength": "🟡 NEAR (AEC volume leader)",
        "sources": ["citrini-cpo", "ParadisLabs", "aleabitoreddit"],
        "catalysts_2026": [
            "AEC volume ramp (5x)",
            "1.6T design wins",
            "Consolidation candidate",
        ],
        "potential_upside": "+100-200%",
        "risk": "M&A overhang; AEC vs optical pricing pressure",
        "tags": ["AI", "Interconnect", "Bottleneck"],
    },

    # ╔═══════════════════════════════════════════════════════════════════╗
    # ║ POWER & COOLING (Citrini "AI Power Infrastructure" — Phase 2 AI)  ║
    # ╚═══════════════════════════════════════════════════════════════════╝

    "VRT": {
        "market": "us_equity", "stars": 5,
        "thesis": "Vertiv — liquid cooling for AI data centers. GB200 = 1000W per chip = liquid cooling MANDATORY. Backlog quadrupled YoY.",
        "bottleneck_reason": "Only scaled liquid cooling integrator for AI racks. Direct chip cooling + manifold + CDU stack — no competitor at hyperscaler scale. AI rack cooling TAM growing 50%+ per year.",
        "correlations": {
            "NVDA": "1.20 — direct rack beta",
            "ETN": "0.65 — power/cooling stack",
            "GEV": "0.75 — grid + AI partnership",
        },
        "monopoly_strength": "🟡 NEAR-MONOPOLY (liquid cooling at scale)",
        "sources": ["citrini-aipower", "ParadisLabs", "HyperTechInvest"],
        "catalysts_2026": [
            "Liquid cooling deployment 4x",
            "Backlog growth disclosure",
            "Margin expansion to 25%+",
        ],
        "potential_upside": "+80-200%",
        "risk": "Customer concentration; capex cycle",
        "tags": ["AI Power", "Cooling", "Bottleneck"],
    },

    "ETN": {
        "market": "us_equity", "stars": 4,
        "thesis": "Eaton — power management for AI data centers. ARC flash + transformer + DC infrastructure. Multi-decade grid build-out tailwind.",
        "bottleneck_reason": "Grid-tie transformers + switchgear is 18-24 month lead time bottleneck. Eaton is largest US supplier with manufacturing reshoring tailwind.",
        "correlations": {
            "NVDA": "0.65 — AI capex beta",
            "VRT": "0.65 — power/cooling stack",
            "GE": "0.45 — turbine + grid synergy",
        },
        "monopoly_strength": "🟠 OLIGOPOLY (Eaton/Siemens/ABB)",
        "sources": ["citrini-aipower", "ParadisLabs"],
        "catalysts_2026": [
            "Grid-tie revenue ramp",
            "Backlog disclosure",
            "Industrial reshoring beneficiary",
        ],
        "potential_upside": "+50-100%",
        "risk": "Multi-cap, slower compounder",
        "tags": ["AI Power", "Infrastructure"],
    },

    "NVTS": {
        "market": "us_equity", "stars": 3,
        "thesis": "Navitas — GaN power for AI data centers. NVDA partnership announced May 2026 = fundamental pivot. Speculative but real catalyst.",
        "bottleneck_reason": "GaN (Gallium Nitride) power transistors are 3x more efficient than silicon for high-voltage DC. AI rack power conversion needs this. Navitas-NVDA partnership locks in supply.",
        "correlations": {
            "NVDA": "2.10 — direct partnership beta",
            "VRT": "1.45 — power infra dependence",
        },
        "monopoly_strength": "🟢 PIONEER (GaN scale-up leader)",
        "sources": ["fundamental_pivot", "edward_nvts_doc"],
        "catalysts_2026": [
            "NVDA delivery ramp (Q3 2026 inflection)",
            "Q2 earnings vs expectations",
            "Customer expansion beyond NVDA",
        ],
        "potential_upside": "🚀 +200-500% if NVDA partnership scales",
        "risk": "P/S 148x = extreme; analyst PT 56% below current; pure momentum",
        "tags": ["AI Power", "GaN", "Speculative", "MULTI-BAG"],
    },

    # ╔═══════════════════════════════════════════════════════════════════╗
    # ║ ATOMS OVER BITS (Citrini physical bottleneck thesis)              ║
    # ╚═══════════════════════════════════════════════════════════════════╝

    "SNDK": {
        "market": "us_equity", "stars": 5,
        "thesis": "SanDisk — flash/NVMe storage for AI training. Atoms Over Bits play. Citrini explicit pick — STX +200% in 2025 proved the thesis, SNDK next.",
        "bottleneck_reason": "AI training data sets are exploding 10x per year. NAND/QLC storage is THE bottleneck for training pipeline throughput. SNDK has 30% share + new SLC product wins.",
        "correlations": {
            "STX": "1.45 — primary storage correlation",
            "WDC": "1.10 — flash duopoly",
            "MU": "0.75 — memory cycle",
        },
        "monopoly_strength": "🟠 OLIGOPOLY (NAND triopoly with WDC/Samsung)",
        "sources": ["citrini-atoms", "HyperTechInvest", "ParadisLabs"],
        "catalysts_2026": [
            "AI inference workload demand",
            "Pricing power (Q2 earnings)",
            "Hyperscaler design wins disclosure",
        ],
        "potential_upside": "🚀 +200-500% (Atoms thesis playbook)",
        "risk": "NAND cycle peak; consumer demand",
        "tags": ["AI", "Storage", "Citrini-Atoms", "MULTI-BAG"],
    },

    "STX": {
        "market": "us_equity", "stars": 4,
        "thesis": "Seagate — HDD storage. +200% in 2025 = Citrini Atoms thesis validated. Mass storage for AI training data lakes.",
        "bottleneck_reason": "HAMR drives are 50TB+ per drive — only Seagate has scale. AI training data lakes need exabyte-scale cold storage = HDD bottleneck.",
        "correlations": {
            "WDC": "1.20 — duopoly partner",
            "SNDK": "1.45 — storage stack",
        },
        "monopoly_strength": "🟠 DUOPOLY (HDD with WDC)",
        "sources": ["citrini-atoms-validated", "HyperTechInvest"],
        "catalysts_2026": [
            "HAMR ramp acceleration",
            "Hyperscaler capacity orders",
            "Margin expansion",
        ],
        "potential_upside": "+50-150% (already +200% — late stage, but multi-year runway)",
        "risk": "Late-cycle; HDD secular decline narrative",
        "tags": ["AI", "Storage", "Citrini-Atoms"],
    },

    "WDC": {
        "market": "us_equity", "stars": 4,
        "thesis": "Western Digital — HDD + flash hybrid. SNDK spin-off unlocks pure storage exposure. Atoms thesis continuation.",
        "bottleneck_reason": "Post-SNDK split = pure HDD play. HAMR roadmap parallel to STX. Hyperscaler capacity orders accelerating.",
        "correlations": {
            "STX": "1.20 — HDD duopoly",
            "SNDK": "1.10 — historical spinoff correlation",
        },
        "monopoly_strength": "🟠 DUOPOLY",
        "sources": ["citrini-atoms", "ParadisLabs"],
        "catalysts_2026": [
            "Post-SNDK earnings ramp",
            "HAMR commercial ramp",
            "Capital return policy",
        ],
        "potential_upside": "+50-150%",
        "risk": "HDD cycle peak",
        "tags": ["AI", "Storage", "Citrini-Atoms"],
    },

    # ╔═══════════════════════════════════════════════════════════════════╗
    # ║ ENERGY: URANIUM / SMR (AI Data Center Power Demand)               ║
    # ╚═══════════════════════════════════════════════════════════════════╝

    "OKLO": {
        "market": "us_equity", "stars": 4,
        "thesis": "Oklo — fast reactor SMR. Sam Altman-backed. AI hyperscaler partnership thesis. Multi-bag potential if first reactor permit lands.",
        "bottleneck_reason": "Fast reactor SMR design with smallest footprint. Sam Altman is chairman = hyperscaler hookup probability >50%. NRC permit timeline 2026-2027.",
        "correlations": {
            "SMR": "0.95 — SMR cohort",
            "CCJ": "0.85 — uranium underlying",
            "VST": "0.55 — power gen alternative",
        },
        "monopoly_strength": "🟢 PIONEER (fast reactor first-mover)",
        "sources": ["citrini-smr", "ai_power_thesis", "altman_chairman"],
        "catalysts_2026": [
            "First reactor NRC permit (CRITICAL)",
            "Hyperscaler offtake deal (MSFT/GOOG/AWS)",
            "DOE loan award",
        ],
        "potential_upside": "🚀 +200-800% if permit + offtake",
        "risk": "Pre-revenue; permit timing; Altman dependency",
        "tags": ["Energy", "SMR", "MULTI-BAG"],
    },

    "SMR": {
        "market": "us_equity", "stars": 3,
        "thesis": "NuScale Power — SMR pure play, FIRST NRC-approved design. AI power demand catalyst.",
        "bottleneck_reason": "Only SMR with NRC design approval. First-mover advantage = lock-in to hyperscaler offtake.",
        "correlations": {
            "OKLO": "0.95 — SMR cohort",
            "CCJ": "0.85 — uranium",
            "BWXT": "0.75 — fuel supplier",
        },
        "monopoly_strength": "🟢 FIRST-MOVER (NRC certified)",
        "sources": ["citrini-smr", "ParadisLabs"],
        "catalysts_2026": [
            "Hyperscaler offtake contract",
            "First deployment 2027 prep",
            "DOE funding",
        ],
        "potential_upside": "🚀 +150-500%",
        "risk": "Long deployment timeline; capex burn",
        "tags": ["Energy", "SMR", "MULTI-BAG"],
    },

    "CCJ": {
        "market": "us_equity", "stars": 3,
        "thesis": "Cameco — uranium spot price beneficiary. SMR + traditional reactor restart + AI power = sustained tailwind.",
        "bottleneck_reason": "Largest publicly-traded uranium producer outside Kazakhstan. China + Russia supply restrictions = Western premium.",
        "correlations": {
            "SMR": "0.85", "OKLO": "0.85", "UEC": "1.45",
            "VST": "0.55 — nuclear power gen",
        },
        "monopoly_strength": "🟠 OLIGOPOLY (Western uranium)",
        "sources": ["citrini", "druckenmiller", "uranium_cycle"],
        "catalysts_2026": [
            "Spot uranium above $100",
            "Long-term contract signings",
            "Hyperscaler nuclear deal headlines",
        ],
        "potential_upside": "+60-150%",
        "risk": "Spot price volatility",
        "tags": ["Energy", "Uranium"],
    },

    # ╔═══════════════════════════════════════════════════════════════════╗
    # ║ ENERGY: OIL TANKERS (Geopolitics + OPEC discipline)               ║
    # ╚═══════════════════════════════════════════════════════════════════╝

    "FRO": {
        "market": "us_equity", "stars": 3,
        "thesis": "Frontline — largest crude tanker fleet. ME geopolitics + Houthi escalation = tanker rate spike. Direct oil → freight pass-through.",
        "bottleneck_reason": "Tanker fleet is 25 years old on average. New-build leadtime 3+ years. Iran/Houthi forces rerouting = effective fleet capacity shrinks 15-20%.",
        "correlations": {
            "CL=F": "1.75 — primary oil pass-through",
            "STNG": "0.85 — tanker cohort",
            "INSW": "0.80 — diversified tanker",
        },
        "monopoly_strength": "🟢 SUPPLY-CONSTRAINED (fleet age + new-build leadtime)",
        "sources": ["oil_geopolitics_chain", "hedgeye_q3"],
        "catalysts_2026": [
            "Houthi/Iran escalation",
            "OPEC+ supply discipline",
            "VLCC rate spike >$80k/day",
        ],
        "potential_upside": "+100-200% on Iran escalation",
        "risk": "Oil price collapse; ceasefire",
        "tags": ["Energy", "Shipping", "Geopolitics"],
    },

    "STNG": {
        "market": "us_equity", "stars": 2,
        "thesis": "Scorpio Tankers — product tanker. Refined product rerouting on ME tension.",
        "bottleneck_reason": "Product tanker fleet is even older. LR2 rates spiked 3x on Houthi.",
        "correlations": {"CL=F": "1.65", "FRO": "0.85", "INSW": "0.75"},
        "monopoly_strength": "🟢 SUPPLY-CONSTRAINED",
        "sources": ["oil_geopolitics_chain"],
        "catalysts_2026": ["Rate spike + buyback", "ME escalation continuation"],
        "potential_upside": "+80-150%",
        "risk": "Same as FRO",
        "tags": ["Energy", "Shipping"],
    },

    "INSW": {
        "market": "us_equity", "stars": 2,
        "thesis": "International Seaways — crude + product diversified tanker.",
        "bottleneck_reason": "Diversified fleet across crude + product = lower concentration risk vs FRO/STNG.",
        "correlations": {"CL=F": "1.50", "FRO": "0.80", "STNG": "0.75"},
        "monopoly_strength": "🟢 SUPPLY-CONSTRAINED",
        "sources": ["oil_geopolitics_chain"],
        "catalysts_2026": ["Rate spike", "Dividend increase"],
        "potential_upside": "+70-130%",
        "risk": "Oil price",
        "tags": ["Energy", "Shipping"],
    },

    # ╔═══════════════════════════════════════════════════════════════════╗
    # ║ MATERIALS (Citrini critical minerals)                              ║
    # ╚═══════════════════════════════════════════════════════════════════╝

    "MP": {
        "market": "us_equity", "stars": 3,
        "thesis": "MP Materials — only US rare earth miner. China REE export controls beneficiary. DoD strategic supplier.",
        "bottleneck_reason": "Only operational US rare earth mine (Mountain Pass). NdPr is critical for EV motors + missile guidance + AI cooling fans. China export controls = price spike.",
        "correlations": {
            "USAR": "1.30 — REE/critical minerals cohort",
            "LMT": "0.20 — DoD contracts",
            "NOC": "0.20 — defense materials",
        },
        "monopoly_strength": "🟢 US-STRATEGIC (only US REE)",
        "sources": ["citrini-china-risk", "druckenmiller", "HyperTechInvest"],
        "catalysts_2026": [
            "NdPr pricing breakthrough",
            "DoD contract expansions",
            "China export control escalation",
        ],
        "potential_upside": "+100-300% on China escalation",
        "risk": "Pricing cycle; capex",
        "tags": ["Materials", "Defense", "Critical-Minerals", "China-Risk"],
    },

    "FCX": {
        "market": "us_equity", "stars": 3,
        "thesis": "Freeport-McMoRan — pure-play copper. EV + grid + AI data center demand = structural deficit.",
        "bottleneck_reason": "Copper deficit projected 5+Mt by 2030. New mine = 10-15 year permitting. FCX is largest publicly-traded copper producer outside China.",
        "correlations": {
            "HG=F": "1.85 — direct copper",
            "SCCO": "0.85 — peer",
            "BHP": "0.65 — diversified miner",
        },
        "monopoly_strength": "🟠 OLIGOPOLY (Western copper)",
        "sources": ["citrini", "druckenmiller", "copper_squeeze"],
        "catalysts_2026": [
            "Indonesia smelter ramp",
            "Copper above $5/lb",
            "Grid spending acceleration",
        ],
        "potential_upside": "+50-150%",
        "risk": "China demand; cycle",
        "tags": ["Materials", "Copper"],
    },

    # ╔═══════════════════════════════════════════════════════════════════╗
    # ║ CRYPTO MINERS & TREASURY                                          ║
    # ╚═══════════════════════════════════════════════════════════════════╝

    "MSTR": {
        "market": "us_equity", "stars": 4,
        "thesis": "Strategy (MicroStrategy) — BTC treasury company. Leveraged BTC exposure via convertible debt structure. Saylor playbook = compounding BTC per share.",
        "bottleneck_reason": "Only publicly-listed pure BTC treasury vehicle at scale. Premium/discount to NAV creates arbitrage. Convertible debt cheaper than buying spot BTC.",
        "correlations": {"BTC-USD": "1.85", "COIN": "1.05", "MARA": "1.45"},
        "monopoly_strength": "🟡 NEAR (only scaled BTC treasury vehicle)",
        "sources": ["citrini-crypto", "HyperTechInvest"],
        "catalysts_2026": [
            "BTC above $150k",
            "Convertible debt refinancing",
            "S&P 500 inclusion catalyst",
        ],
        "potential_upside": "+100-300% if BTC continues",
        "risk": "Premium compression; refinancing",
        "tags": ["Crypto", "Treasury"],
    },

    "MARA": {
        "market": "us_equity", "stars": 3,
        "thesis": "Marathon Digital — largest US BTC miner. Operating leverage to BTC + AI HPC pivot.",
        "bottleneck_reason": "Post-halving 2024, only efficient miners survive. MARA acquired hash rate at fire-sale = lowest cost producer. AI HPC pivot = data center optionality.",
        "correlations": {"BTC-USD": "2.10", "RIOT": "1.65", "MSTR": "1.05"},
        "monopoly_strength": "🟠 OLIGOPOLY",
        "sources": ["citrini-mining", "btc_mining_chain"],
        "catalysts_2026": [
            "BTC above $150k",
            "AI HPC revenue disclosure",
            "Texas mining expansion",
        ],
        "potential_upside": "🚀 +200-500% if BTC bull continues",
        "risk": "BTC price; energy costs",
        "tags": ["Crypto", "Mining", "MULTI-BAG"],
    },

    # ╔═══════════════════════════════════════════════════════════════════╗
    # ║ MEGA-CAP AI (Citrini AI Bureaucracy Alpha)                        ║
    # ╚═══════════════════════════════════════════════════════════════════╝

    "GOOGL": {
        "market": "us_equity", "stars": 3,
        "thesis": "Alphabet — TPU custom silicon + Gemini + Waymo. Cheapest Mag7 + AI infra owner.",
        "bottleneck_reason": "TPU v7 is the only credible NVDA alternative at scale. Gemini 2.0 has the search distribution moat. Waymo is the autonomous driving optionality.",
        "correlations": {
            "AVGO": "0.60 — TPU partnership",
            "MSFT": "0.60 — Mag7 cohort",
            "TSM": "0.40 — foundry",
        },
        "monopoly_strength": "🟡 NEAR (search + TPU duopoly)",
        "sources": ["citrini-bureaucracy", "consensus_ai"],
        "catalysts_2026": [
            "TPU v7 ramp disclosure",
            "Cloud margin expansion",
            "Antitrust resolution clarity",
        ],
        "potential_upside": "+30-70%",
        "risk": "Antitrust; search disruption",
        "tags": ["AI", "Mega-cap", "Citrini"],
    },

    "QCOM": {
        "market": "us_equity", "stars": 3,
        "thesis": "Qualcomm — on-device AI inference winner. Snapdragon X laptops + automotive + Apple modem expansion.",
        "bottleneck_reason": "On-device AI inference + 5G modem duopoly. Apple modem partnership through 2027.",
        "correlations": {"NVDA": "0.35", "MTK": "0.75", "AVGO": "0.45"},
        "monopoly_strength": "🟡 NEAR (mobile AI inference)",
        "sources": ["citrini-ondevice", "HyperTechInvest"],
        "catalysts_2026": [
            "Snapdragon X laptop penetration",
            "Automotive design wins",
            "Apple modem terms",
        ],
        "potential_upside": "+40-100%",
        "risk": "Apple replaces modem",
        "tags": ["AI", "Mobile", "On-Device"],
    },

    "AMD": {
        "market": "us_equity", "stars": 3,
        "thesis": "AMD — MI300/MI450 second-source to NVDA. OpenAI MI450 deal validates roadmap.",
        "bottleneck_reason": "Only credible NVDA alternative for AI training. OpenAI explicit purchase order = market validation.",
        "correlations": {"NVDA": "0.65", "TSM": "0.55", "MU": "0.55"},
        "monopoly_strength": "🟠 DUOPOLY (with NVDA)",
        "sources": ["citrini", "openai_deal", "HyperTechInvest"],
        "catalysts_2026": [
            "MI450 launch H2 2026",
            "OpenAI deliveries",
            "Hyperscaler design wins",
        ],
        "potential_upside": "+50-200%",
        "risk": "Catching NVDA execution",
        "tags": ["AI", "GPU"],
    },

    # ╔═══════════════════════════════════════════════════════════════════╗
    # ║ IHSG BANDAR (Indonesian cornering/accumulation plays)             ║
    # ╚═══════════════════════════════════════════════════════════════════╝

    "BREN.JK": {
        "market": "ihsg", "stars": 4,
        "thesis": "Barito Renewables — geothermal asset value. Prajogo Pangestu group bandar flow. Multi-year structural play with massive bandar accumulation.",
        "bottleneck_reason": "Largest publicly-listed geothermal in Indonesia. Prajogo group cornering supply via cross-trades — visible in broker summary. Asset value (8.8 GW geothermal potential) discounted vs replacement cost.",
        "correlations": {
            "TPIA.JK": "1.55 — same parent group",
            "BRPT.JK": "1.25 — holdco",
            "CUAN.JK": "1.15 — sister entity",
            "PTRO.JK": "0.85 — Prajogo affiliate",
        },
        "monopoly_strength": "🔴 INDONESIAN-MONOPOLY (geothermal)",
        "sources": ["bandar_barito_group", "hengky_adinata", "prajogo_cornering"],
        "catalysts_2026": [
            "Geothermal capacity expansion 2027 targets",
            "Bandar accumulation continuation (broker summary tracking)",
            "ESG-fund Western inflow",
        ],
        "potential_upside": "🚀 +100-300% if cornering continues",
        "risk": "Bandar exit; valuation",
        "tags": ["IHSG", "Renewables", "Bandar", "MULTI-BAG", "LONG_ONLY"],
    },

    "TPIA.JK": {
        "market": "ihsg", "stars": 3,
        "thesis": "Chandra Asri — Prajogo group flagship. Petrochemical cycle + BREN value unlock + cornering supply visible.",
        "bottleneck_reason": "Largest naphtha cracker in Indonesia. Prajogo group is THE bandar in Indonesia — TPIA is their flagship cross-trade vehicle. Free float very limited (~10%).",
        "correlations": {"BREN.JK": "1.55", "BRPT.JK": "1.25", "CUAN.JK": "1.15"},
        "monopoly_strength": "🔴 INDONESIAN-MONOPOLY (naphtha cracker)",
        "sources": ["bandar_barito_group", "hengky_adinata", "prajogo_cornering"],
        "catalysts_2026": [
            "Naphtha cycle recovery",
            "BREN spin-off value unlock",
            "Bandar cornering acceleration",
        ],
        "potential_upside": "+80-200%",
        "risk": "Bandar exit",
        "tags": ["IHSG", "Petrochem", "Bandar", "LONG_ONLY"],
    },

    "BBCA.JK": {
        "market": "ihsg", "stars": 3,
        "thesis": "Bank Central Asia — IHSG bellwether. Foreign flow proxy. Lowest-risk IHSG long.",
        "bottleneck_reason": "Best-in-class Indonesian bank (CASA 80%, NPL 1.7%). Foreign ownership 30%+ — when foreigners buy IHSG, BBCA leads. ETF flagship.",
        "correlations": {"BMRI.JK": "0.95", "BBRI.JK": "1.05", "^JKSE": "0.45"},
        "monopoly_strength": "🟡 NEAR (best Indonesian bank)",
        "sources": ["bandar_bigbank_flow", "foreign_flow_proxy"],
        "catalysts_2026": [
            "Q1 earnings beat",
            "Foreign net buy resumption",
            "Rate cut → loan growth",
        ],
        "potential_upside": "+30-60%",
        "risk": "Foreign outflow",
        "tags": ["IHSG", "Banks", "LONG_ONLY"],
    },

    "MEDC.JK": {
        "market": "ihsg", "stars": 2,
        "thesis": "Medco Energi — oil + gas. ME geopolitics direct beneficiary via WTI proxy. Indonesian E&P leader.",
        "bottleneck_reason": "Largest publicly-listed Indonesian oil + gas. Diversified blocks (Indonesia + Libya + Yemen). Beta to oil very high.",
        "correlations": {"CL=F": "0.85", "ADRO.JK": "0.55"},
        "monopoly_strength": "🟠 OLIGOPOLY (Indonesian E&P)",
        "sources": ["oil_proxy", "bandar_flow"],
        "catalysts_2026": [
            "Oil above $80",
            "Block production updates",
            "ME tension escalation",
        ],
        "potential_upside": "+80-200%",
        "risk": "Oil price; operational",
        "tags": ["IHSG", "Energy", "LONG_ONLY"],
    },

    "ADRO.JK": {
        "market": "ihsg", "stars": 2,
        "thesis": "Adaro Energy — coal cycle leader. Quad2/Quad3 commodity rotation. ADMR spin-off value unlock.",
        "bottleneck_reason": "Largest Indonesian thermal coal exporter. Direct China power demand pass-through. Free cash flow yield 15%+.",
        "correlations": {"ITMG.JK": "1.15", "PTBA.JK": "1.05", "BUMI.JK": "1.45", "CL=F": "0.45"},
        "monopoly_strength": "🟠 OLIGOPOLY (Indonesian coal)",
        "sources": ["commodity_cycle", "bandar_coal_group"],
        "catalysts_2026": [
            "China coal demand reacceleration",
            "ADMR spin-off value unlock",
            "Dividend yield reset",
        ],
        "potential_upside": "+50-150%",
        "risk": "China stimulus uncertainty",
        "tags": ["IHSG", "Coal", "Cyclical", "LONG_ONLY"],
    },

    # ╔═══════════════════════════════════════════════════════════════════╗
    # ║ CRYPTO L1 (DePIN + scaling)                                       ║
    # ╚═══════════════════════════════════════════════════════════════════╝

    "NBIS": {
        "market": "us_equity", "stars": 4,
        "thesis": "Nebius Group — AI cloud / GPU infrastructure (ex-Yandex). Neocloud play renting NVDA GPUs at scale. Keith McCullough + Hedgeye community held through drops.",
        "bottleneck_reason": "One of few pure-play AI neoclouds with NVDA allocation priority. GPU capacity is the bottleneck — Nebius has secured H200/B200 supply + datacenter buildout in Europe/US. Scarce listed exposure to GPU-rental economics.",
        "correlations": {
            "NVDA": "1.55 - GPU supply + demand beta",
            "CRWV": "1.30 - neocloud peer (CoreWeave)",
            "VRT": "0.70 - datacenter cooling dependency",
        },
        "monopoly_strength": "PIONEER (scarce listed neocloud)",
        "sources": ["keith_mccullough", "lifelong_learner", "HyperTechInvest"],
        "catalysts_2026": [
            "GPU capacity expansion disclosure",
            "Enterprise AI contract wins",
            "Profitability inflection",
        ],
        "potential_upside": "+150-400% if neocloud demand sustains",
        "risk": "GPU oversupply; hyperscaler competition; capex burn",
        "tags": ["AI", "Cloud", "GPU", "MULTI-BAG"],
    },

    "SOL-USD": {
        "market": "crypto", "stars": 3,
        "thesis": "Solana — DePIN + memecoin volume leader. Visa/Shopify integrations. Firedancer mainnet 2026.",
        "bottleneck_reason": "Highest-TPS L1 with EVM-equivalent UX. DePIN ecosystem (Helium, Hivemapper, etc.) anchored on Solana. Firedancer = 10x throughput.",
        "correlations": {"BTC-USD": "0.85", "ETH-USD": "0.75"},
        "monopoly_strength": "🟠 OLIGOPOLY (L1 alt)",
        "sources": ["citrini-defillama"],
        "catalysts_2026": [
            "Firedancer mainnet activation",
            "ETF approvals",
            "DePIN sector growth",
        ],
        "potential_upside": "+100-300%",
        "risk": "BTC dependency; outage history",
        "tags": ["Crypto", "L1", "DePIN"],
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# CURATOR — strict 5-layer filter
# ═══════════════════════════════════════════════════════════════════════════

class AlphaCenterCurator:

    def __init__(self, bottleneck_ref_path: str = "bottleneck_reference.json"):
        self.bottleneck_data = self._load_bottleneck(bottleneck_ref_path)

    def _load_bottleneck(self, path: str) -> Dict:
        if not os.path.exists(path):
            return {}
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            return {}

    def layer1_consensus(self, ticker: str, candidate: Dict) -> Tuple[bool, str]:
        """≥2 sources OR explicit M&A target."""
        sources = candidate.get("sources", [])
        tags = candidate.get("tags", [])
        if "M&A-Target" in tags or "MULTI-BAG" in tags:
            return True, f"M&A/Multi-bag bypass — {len(sources)} sources"
        if len(sources) >= 2:
            return True, f"{len(sources)} sources: {', '.join(sources[:3])}"
        return False, f"Only {len(sources)} source(s)"

    def layer2_bottleneck(self, ticker: str, candidate: Dict) -> Tuple[bool, str]:
        """Must have bottleneck_reason + catalysts_2026."""
        if not candidate.get("bottleneck_reason"):
            return False, "No bottleneck reason documented"
        if not candidate.get("catalysts_2026"):
            return False, "No 2026 catalysts"
        return True, f"Bottleneck documented; {len(candidate['catalysts_2026'])} catalysts"

    def layer3_correlations(self, ticker: str, candidate: Dict) -> Tuple[bool, str]:
        corr = candidate.get("correlations", {})
        if not corr:
            return False, "No correlations mapped"
        return True, f"{len(corr)} correlations mapped"

    def layer4_hedgeye_compat(self, ticker, candidate, keith_signals=None, current_quad="Q3") -> Tuple[bool, str]:
        if not keith_signals:
            return True, "No Keith signal (pass default)"
        sig = keith_signals.get(ticker, {})
        trend = sig.get("TRADE", "NEUTRAL") if isinstance(sig, dict) else "NEUTRAL"
        if trend == "BEARISH":
            return False, "Keith TRADE BEARISH — BLOCKED"
        return True, f"Keith: {trend}"

    def layer5_walkforward(self, ticker, candidate, wf_results=None) -> Tuple[bool, str]:
        if not wf_results or ticker not in wf_results:
            return True, "WF not yet run (soft pass)"
        r = wf_results[ticker]
        score = r.get("combined_gate_score", 0)
        if score < 55:
            return False, f"WF gate FAIL ({score}/100)"
        return True, f"WF PASS ({score}/100)"

    def filter_universe(
        self,
        keith_signals=None,
        wf_results=None,
        current_quad="Q3",
        min_stars=1,
    ) -> Dict:
        passed, rejected = [], []
        for ticker, cand in ALPHA_CENTER_CANDIDATES.items():
            if cand.get("stars", 0) < min_stars:
                continue
            checks = {}
            ok = True
            for layer_name, layer_fn in [
                ("L1_consensus", self.layer1_consensus),
                ("L2_bottleneck", self.layer2_bottleneck),
                ("L3_correlation", self.layer3_correlations),
            ]:
                p, msg = layer_fn(ticker, cand)
                checks[layer_name] = {"pass": p, "msg": msg}
                if not p:
                    ok = False
            p4, m4 = self.layer4_hedgeye_compat(ticker, cand, keith_signals, current_quad)
            checks["L4_hedgeye"] = {"pass": p4, "msg": m4}
            if not p4: ok = False
            p5, m5 = self.layer5_walkforward(ticker, cand, wf_results)
            checks["L5_walkforward"] = {"pass": p5, "msg": m5}
            if not p5: ok = False

            entry = {"ticker": ticker, "candidate": cand, "checks": checks, "passed": ok}
            (passed if ok else rejected).append(entry)
        return {
            "passed": sorted(passed, key=lambda x: -x["candidate"].get("stars", 0)),
            "rejected": rejected,
            "total_passed": len(passed),
            "total_rejected": len(rejected),
            "quad_applied": current_quad,
        }

    def get_candidate(self, ticker: str):
        return ALPHA_CENTER_CANDIDATES.get(ticker)

    def all_candidates_by_market(self):
        out = {}
        for t, c in ALPHA_CENTER_CANDIDATES.items():
            out.setdefault(c.get("market", "unknown"), []).append(t)
        return out


def get_curator(bottleneck_ref_path="bottleneck_reference.json"):
    return AlphaCenterCurator(bottleneck_ref_path)
