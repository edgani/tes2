"""bottleneck_map.py — Bottleneck Ticker Universe & Supply Chain Graph v40.1
Maps tickers to bottleneck layers, catalysts, and correlated assets.
"""

# ═══════════════════════════════════════════════════════════════════
# BOTTLENECK TICKER UNIVERSE
# ═══════════════════════════════════════════════════════════════════
BOTTLENECK_TICKERS = [
    # AI Compute
    "NVDA", "AMD", "AVGO", "TSM", "MU", "SKHYNIX", "COHR", "MRVL", "NXT", "AMPH", "LITE",
    # Power / Cooling
    "VST", "CEG", "BE", "NEE", "D",
    # Raw Materials
    "SCCO", "FCX", "ALB", "MP", "PLS.AX",
    # Oil / Energy
    "CL=F", "USO", "XOM", "CVX", "COP", "OXY", "FANG",
    # Tankers / Shipping
    "FRO", "TK", "INSW", "NAT", "ZIM", "MATX", "DAC",
    # Refining
    "VLO", "MPC", "PSX", "DK",
    # Fertilizer / Ag
    "NTR", "MOS", "CF", "UAN",
    # Defense
    "LMT", "NOC", "RTX", "GD", "BA",
    # Indonesia
    "NCKL.JK", "ANTM.JK", "INCO.JK", "AALI.JK", "LSIP.JK", "SMAR.JK",
    "ADRO.JK", "ITMG.JK", "PTBA.JK", "BBRI.JK", "BMRI.JK", "BBCA.JK", "BBNI.JK", "BRIS.JK",
    "TLKM.JK", "EXCL.JK", "UNTR.JK", "BYAN.JK", "ICBP.JK", "INDF.JK", "KLBF.JK", "PGEO.JK", "WINS.JK",
    # Semiconductors
    "ASML", "LRCX", "AMAT", "KLAC", "ENTG", "MKSI",
    # Uranium
    "CCJ", "UUUU", "UEC", "DNN", "URA",
    # Copper / Grid
    "WIRE", "GNRC", "CHPT", "EVGO",
    # Rare Earth
    "MP", "NEO", "MPCO", "REEMF",
    # Bitcoin / Crypto
    "BTC-USD", "ETH-USD", "SOL-USD", "MSTR", "COIN", "RIOT", "MARA",
    # Container / Logistics
    "UPS", "FDX", "CHRW", "EXPD",
    # LNG / Europe Energy
    "UNG", "LNG", "TELL", "GLNG", "FLNG",
    # Taiwan / China exposure
    "TSM", "UMC", "ASML", "QCOM", "SWKS", "QRVO", "CRWD", "PDD", "BABA", "JD", "NIO", "LI", "XPEV",
    # China Property / Steel
    "BHP", "VALE", "MT", "STLD", "NUE", "CLF", "X", "FCX",
    # Fed Pivot / Rate sensitive
    "TLT", "IEF", "SCHP", "TMF", "TBT", "KRE", "XLF", "BAC", "JPM", "C", "WFC",
    # Water
    "AWK", "CWT", "Xylem", "WTRG", "AQUA",
    # Space / Satellite
    "ASTS", "SPCE", "RKLB", "LMT", "NOC", "RTX", "IRDM", "VSAT",
    # Biotech / GLP-1
    "LLY", "NVO", "DHR", "TECD", "CTLT", "AMPH", "PETQ", "DXCM", "TNDM", "UNH", "CI",
]

# Supply chain edges: upstream -> downstream
SUPPLY_CHAIN_EDGES = {
    "NVDA": ["TSM", "MU", "AVGO", "COHR", "MRVL"],
    "TSM": ["ASML", "LRCX", "AMAT", "KLAC"],
    "MU": ["SKHYNIX"],
    "COHR": ["NXT", "AMPH", "LITE"],
    "MRVL": ["NXT", "AMPH"],
    "NXT": ["AMPH"],
    "VST": ["SCCO", "FCX"],
    "CEG": ["CCJ", "UUUU"],
    "BE": ["GNRC", "WIRE"],
    "CL=F": ["FRO", "TK", "INSW", "NAT"],
    "FRO": ["VLO", "MPC", "PSX"],
    "VLO": ["NTR", "MOS", "CF"],
    "NTR": ["MOS", "CF"],
    "NCKL.JK": ["ANTM.JK", "INCO.JK"],
    "ADRO.JK": ["ITMG.JK", "PTBA.JK"],
    "AALI.JK": ["LSIP.JK", "SMAR.JK"],
    "CCJ": ["UUUU", "UEC", "DNN"],
    "URA": ["NEE", "CEG", "VST"],
    "SCCO": ["FCX", "WIRE", "GNRC"],
    "WIRE": ["CHPT", "EVGO", "BE"],
    "ASML": ["LRCX", "AMAT", "KLAC"],
    "ENTG": ["MKSI"],
    "MP": ["NEO", "MPCO"],
    "BTC-USD": ["MSTR", "COIN", "RIOT", "MARA"],
    "ETH-USD": ["COIN", "SOL-USD"],
    "ZIM": ["MATX", "DAC"],
    # LNG
    "UNG": ["LNG", "TELL", "GLNG", "FLNG"],
    "LNG": ["CEG", "VST", "NEE"],
    # Taiwan blockade
    "TSM": ["NVDA", "QCOM", "SWKS", "QRVO"],
    "ASML": ["TSM", "INTC", "NVDA"],
    # China property
    "BHP": ["VALE", "MT", "STLD"],
    "MT": ["STLD", "NUE", "CLF"],
    # Fed pivot
    "TLT": ["TMF", "SCHP", "IEF"],
    "KRE": ["XLF", "BAC", "JPM"],
    # Water
    "AWK": ["CWT", "WTRG", "AQUA"],
    # Space
    "ASTS": ["RKLB", "IRDM", "VSAT"],
    "SPCE": ["LMT", "NOC"],
    # GLP-1
    "LLY": ["NVO", "DHR", "TECD"],
    "NVO": ["CTLT", "AMPH", "PETQ"],
    "AMPH": ["DXCM", "TNDM"],
}

# Reverse lookup
DOWNSTREAM_MAP = {}
for upstream, downstreams in SUPPLY_CHAIN_EDGES.items():
    for d in downstreams:
        DOWNSTREAM_MAP.setdefault(d, []).append(upstream)

# ═══════════════════════════════════════════════════════════════════
# BOTTLENECK METADATA
# ═══════════════════════════════════════════════════════════════════
BOTTLENECK_META = {
    "NVDA": {"layer": "AI GPU", "priority": "P0", "bottleneck": "CoWoS capacity", "catalyst": "Blackwell ramp Q3", "thesis": "Every $1 GPU pulls $3-5 infrastructure. CoWoS/HBM constrained.", "correlates_with": ["TSM", "MU", "AVGO", "VST"]},
    "AMD": {"layer": "AI GPU", "priority": "P1", "bottleneck": "MI300 yield", "catalyst": "MI350 2026", "thesis": "Alternative AI chip play. Memory bandwidth gap vs NVDA.", "correlates_with": ["TSM", "MU"]},
    "TSM": {"layer": "Foundry", "priority": "P0", "bottleneck": "3nm capacity", "catalyst": "AZ fab 2027", "thesis": "Monopoly on advanced nodes. Geopolitical tail risk.", "correlates_with": ["ASML", "NVDA", "AVGO"]},
    "MU": {"layer": "Memory / HBM", "priority": "P0", "bottleneck": "HBM3E yield", "catalyst": "HBM4 2026", "thesis": "HBM supply inelastic. 3-5x content per AI server.", "correlates_with": ["SKHYNIX", "TSM", "NVDA"]},
    "AVGO": {"layer": "Networking / ASIC", "priority": "P1", "bottleneck": "Tomahawk 6 supply", "catalyst": "Custom AI ASICs", "thesis": "Networking + custom silicon for hyperscalers.", "correlates_with": ["MRVL", "COHR"]},
    "COHR": {"layer": "Optics", "priority": "P1", "bottleneck": "800G/1.6T capacity", "catalyst": "L-band expansion", "thesis": "Data center interconnect bottleneck. CPO transition.", "correlates_with": ["MRVL", "LITE", "NXT"]},
    "MRVL": {"layer": "Networking / DSP", "priority": "P1", "bottleneck": "PAM4 DSP supply", "catalyst": "CPO integration", "thesis": "Optical DSP leader. AI cluster scaling driver.", "correlates_with": ["COHR", "AVGO", "NXT"]},
    "NXT": {"layer": "CPO / Connectors", "priority": "P0", "bottleneck": "Co-packaged optics", "catalyst": "1.6T CPO 2027", "thesis": "Leopold bottleneck: CPO is the last mile of AI infra.", "correlates_with": ["AMPH", "COHR", "MRVL"]},
    "AMPH": {"layer": "CPO / Connectors", "priority": "P1", "bottleneck": "High-speed connector capacity", "catalyst": "224G PAM4", "thesis": "Backplane + optical connector play. Undervalued vs buildout.", "correlates_with": ["NXT", "COHR"]},
    "VST": {"layer": "Power / Utility", "priority": "P0", "bottleneck": "Interconnection queue", "catalyst": "Data center PPA backlog", "thesis": "Power is the new oil for AI. Interconnection queue 3-5 years.", "correlates_with": ["CEG", "BE", "SCCO"]},
    "CEG": {"layer": "Power / Nuclear", "priority": "P0", "bottleneck": "Nuclear restart permits", "catalyst": "Three Mile Island restart", "thesis": "Nuclear renaissance for baseload AI power. Uranium demand pull.", "correlates_with": ["CCJ", "VST", "NEE"]},
    "BE": {"layer": "Power / Battery", "priority": "P1", "bottleneck": "Grid-scale storage", "catalyst": "DOE loan guarantees", "thesis": "Grid balancing for renewables + AI load. Battery storage gap.", "correlates_with": ["VST", "GNRC"]},
    "SCCO": {"layer": "Copper Mining", "priority": "P0", "bottleneck": "Grade decline + permit delays", "catalyst": "Chile water restrictions", "thesis": "Copper supercycle: EV + grid + datacenter. 5-7M tonne deficit by 2030.", "correlates_with": ["FCX", "WIRE", "VST"]},
    "FCX": {"layer": "Copper / Gold", "priority": "P1", "bottleneck": "Grasberg transition", "catalyst": "Underground ramp", "thesis": "Diversified copper + gold. Grasberg underground expansion.", "correlates_with": ["SCCO", "GLD"]},
    "ALB": {"layer": "Lithium", "priority": "P2", "bottleneck": "Brine evaporation", "catalyst": "Chile contract renegotiation", "thesis": "Lithium oversupplied short-term. Long-term EV penetration.", "correlates_with": ["SQM", "LAC"]},
    "CL=F": {"layer": "Crude Oil", "priority": "P0", "bottleneck": "Strait of Hormuz", "catalyst": "Iran escalation / OPEC+ spare capacity", "thesis": "15-20% of global supply at risk. VLCC rates + insurance spike.", "correlates_with": ["USO", "XOM", "CVX", "FRO"]},
    "FRO": {"layer": "Tankers / VLCC", "priority": "P0", "bottleneck": "VLCC rates + insurance", "catalyst": "Red Sea / Hormuz disruption", "thesis": "Geopolitical risk premium flows to tanker rates. FRO = pure-play VLCC.", "correlates_with": ["TK", "INSW", "NAT", "CL=F"]},
    "TK": {"layer": "Tankers / Product", "priority": "P1", "bottleneck": "Product tanker fleet age", "catalyst": "Russian shadow fleet sanctions", "thesis": "Product tanker tightness. LR2 rates at multi-year highs.", "correlates_with": ["FRO", "INSW"]},
    "VLO": {"layer": "Refining", "priority": "P1", "bottleneck": "Crack spreads", "catalyst": "Summer driving season", "thesis": "Refining margin expansion on heavy/sour crude discount.", "correlates_with": ["MPC", "PSX", "CL=F"]},
    "NTR": {"layer": "Fertilizer", "priority": "P1", "bottleneck": "Natural gas -> ammonia", "catalyst": "Spring planting demand", "thesis": "Gas-to-fertilizer spread. European gas price = margin driver.", "correlates_with": ["MOS", "CF", "NG=F"]},
    "LMT": {"layer": "Defense", "priority": "P1", "bottleneck": "Munitions replenishment", "catalyst": "NATO 2% GDP target", "thesis": "Multi-year defense upcycle. JASSM + THAAD backlog.", "correlates_with": ["NOC", "RTX", "GD"]},
    "NCKL.JK": {"layer": "Nickel / EV", "priority": "P0", "bottleneck": "Nickel processing quota", "catalyst": "Indonesia export ban escalation", "thesis": "Resource nationalism. HPAL capacity constrained. Battery-grade nickel deficit.", "correlates_with": ["ANTM.JK", "INCO.JK", "ALB"]},
    "ADRO.JK": {"layer": "Coal / Power", "priority": "P1", "bottleneck": "Domestic Market Obligation", "catalyst": "DMO quota enforcement", "thesis": "Coal export volume capped by DMO. Domestic price cap squeezes margins.", "correlates_with": ["ITMG.JK", "PTBA.JK"]},
    "AALI.JK": {"layer": "Palm Oil / CPO", "priority": "P1", "bottleneck": "EU Deforestation Regulation", "catalyst": "EUDR traceability deadline", "thesis": "Supply tightness from EUDR compliance costs. India/China demand resilient.", "correlates_with": ["LSIP.JK", "SMAR.JK"]},
    "BBRI.JK": {"layer": "Banking", "priority": "P1", "bottleneck": "BI rate duration", "catalyst": "Rate cut cycle 2026", "thesis": "High NIM from elevated BI rate. Micro-loan dominance = sticky funding.", "correlates_with": ["BMRI.JK", "BBCA.JK"]},
    "ASML": {"layer": "Lithography", "priority": "P0", "bottleneck": "High-NA EUV delivery", "catalyst": "EXE:5000 2028", "thesis": "Monopoly on sub-2nm lithography. Geopolitical export controls.", "correlates_with": ["TSM", "INTC", "NVDA"]},
    "CCJ": {"layer": "Uranium Mining", "priority": "P0", "bottleneck": "Kazakhstan supply uncertainty", "catalyst": "US SPUT restart / utility contracting", "thesis": "Nuclear renaissance + supply concentration risk. Long-term contracting wave.", "correlates_with": ["UUUU", "UEC", "URA", "CEG"]},
    "MP": {"layer": "Rare Earth", "priority": "P1", "bottleneck": "Separation capacity", "catalyst": "DoD stockpile mandate", "thesis": "Only US rare earth mine. Downstream magnet gap = vertical integration play.", "correlates_with": ["NEO", "MPCO"]},
    "BTC-USD": {"layer": "Crypto / Store of Value", "priority": "P1", "bottleneck": "Exchange balance", "catalyst": "Halving supply squeeze + ETF flows", "thesis": "Post-halving supply shock. Exchange BTC at 5-year low. Whale accumulation.", "correlates_with": ["ETH-USD", "MSTR", "COIN"]},
    "ETH-USD": {"layer": "Crypto / Smart Contract", "priority": "P1", "bottleneck": "L2 fragmentation", "catalyst": "ETH ETF staking approval", "thesis": "Smart contract platform. ETF approval = institutional bid. Staking yield = bond proxy.", "correlates_with": ["BTC-USD", "SOL-USD", "COIN"]},
    "ZIM": {"layer": "Container Shipping", "priority": "P2", "bottleneck": "Red Sea diversion capacity", "catalyst": "Houthi escalation / ceasefire", "thesis": "Red Sea diversion = +15% fleet miles. Rate volatility extreme.", "correlates_with": ["MATX", "DAC"]},
    # LNG
    "UNG": {"layer": "Natural Gas", "priority": "P1", "bottleneck": "LNG export capacity", "catalyst": "Europe refill season + Freeport restart", "thesis": "US LNG export constrained by permit delays. European demand pull.", "correlates_with": ["LNG", "TELL", "CEG"]},
    "LNG": {"layer": "LNG Shipping", "priority": "P1", "bottleneck": "FSRU availability", "catalyst": "German LNG terminal expansion", "thesis": "FSRU = floating regas. Limited fleet. Charter rates at multi-year highs.", "correlates_with": ["GLNG", "FLNG", "UNG"]},
    # Taiwan / China
    "QCOM": {"layer": "Mobile SoC", "priority": "P1", "bottleneck": "TSM advanced node allocation", "catalyst": "AI phone cycle 2026", "thesis": "TSM capacity allocation: AI GPU > mobile SoC. Supply tightness.", "correlates_with": ["TSM", "SWKS", "QRVO"]},
    "SWKS": {"layer": "RF Frontend", "priority": "P2", "bottleneck": "BAW filter capacity", "catalyst": "5G mmWave adoption", "thesis": "RF content per phone increasing. BAW filter supply concentrated.", "correlates_with": ["QCOM", "QRVO"]},
    "BABA": {"layer": "China E-commerce", "priority": "P2", "bottleneck": "Consumer confidence", "catalyst": "Ant Group restructuring", "thesis": "China stimulus + regulatory easing. Valuation discount extreme.", "correlates_with": ["JD", "PDD"]},
    "NIO": {"layer": "China EV", "priority": "P2", "bottleneck": "Battery swap network capex", "catalyst": "EU tariff negotiation", "thesis": "Battery swap = differentiation. EU tariff risk on exports.", "correlates_with": ["LI", "XPEV", "TSLA"]},
    # China property / steel
    "BHP": {"layer": "Iron Ore", "priority": "P1", "bottleneck": "Pilbara grade decline", "catalyst": "China property stimulus", "thesis": "Iron ore price tied to China property floor. 60% of seaborne demand.", "correlates_with": ["VALE", "MT", "FCX"]},
    "VALE": {"layer": "Iron Ore / Nickel", "priority": "P1", "bottleneck": "Brumadinho dam legacy", "catalyst": "S11D expansion", "thesis": "Diversified miner. Iron ore + nickel + copper. Brazil political risk.", "correlates_with": ["BHP", "MT", "NCKL.JK"]},
    "STLD": {"layer": "Steel / Mini-mill", "priority": "P2", "bottleneck": "Scrap supply", "catalyst": "Infrastructure bill spend", "thesis": "Mini-mill = lower carbon. Scrap supply constrained by auto shredder capacity.", "correlates_with": ["NUE", "CLF", "MT"]},
    # Fed pivot
    "TLT": {"layer": "Long Treasury", "priority": "P0", "bottleneck": "Fed duration supply", "catalyst": "Rate cut cycle", "thesis": "Duration play on Fed pivot. Convexity + carry when cuts begin.", "correlates_with": ["IEF", "TMF", "SCHP"]},
    "TMF": {"layer": "3x Long Treasury", "priority": "P2", "bottleneck": "Roll yield decay", "catalyst": "Bull steepener", "thesis": "Levered duration. High decay in chop. Only for tactical holds.", "correlates_with": ["TLT", "TBT"]},
    "KRE": {"layer": "Regional Banks", "priority": "P1", "bottleneck": "CRE exposure", "catalyst": "Rate cut relief", "thesis": "Regional banks = rate sensitivity. CRE mark-to-market pain.", "correlates_with": ["XLF", "BAC", "JPM"]},
    # Water
    "AWK": {"layer": "Water Utility", "priority": "P1", "bottleneck": "Aging infrastructure", "catalyst": "EPA lead rule", "thesis": "Regulated utility = rate base growth. Lead pipe replacement = decade capex.", "correlates_with": ["CWT", "WTRG"]},
    "CWT": {"layer": "Water Utility", "priority": "P2", "bottleneck": "California drought", "catalyst": "Desalination permits", "thesis": "West coast water stress. Desalination = long-term solution.", "correlates_with": ["AWK", "AQUA"]},
    # Space
    "ASTS": {"layer": "Satellite Direct-to-Cell", "priority": "P1", "bottleneck": "Spectrum allocation", "catalyst": "AT&T partnership launch", "thesis": "Space-based cellular = TAM expansion. Regulatory + technical risk.", "correlates_with": ["IRDM", "VSAT"]},
    "RKLB": {"layer": "Launch / Space Systems", "priority": "P1", "bottleneck": "Neutron engine test", "catalyst": "Neutron first flight 2025", "thesis": "Reusable launch = cost curve down. Space systems = vertical integration.", "correlates_with": ["SPCE", "LMT"]},
    "IRDM": {"layer": "Satellite IoT / Voice", "priority": "P1", "bottleneck": "Ground station capacity", "catalyst": "Iridium NEXT completion", "thesis": "Monopoly on satellite voice. IoT = growth vector.", "correlates_with": ["ASTS", "VSAT"]},
    # GLP-1
    "LLY": {"layer": "GLP-1 Drug", "priority": "P0", "bottleneck": "Peptide API capacity", "catalyst": "Mounjaro/Zephyr label expansion", "thesis": "Demand outstrips manufacturing 10:1. Pricing power + volume.", "correlates_with": ["NVO", "DHR", "TECD"]},
    "NVO": {"layer": "GLP-1 Drug", "priority": "P0", "bottleneck": "Wegovy fill-finish", "catalyst": "Obesity Medicare coverage", "thesis": "Wegovy = weight loss standard. Manufacturing bottleneck = margin expansion.", "correlates_with": ["LLY", "CTLT", "AMPH"]},
    "DXCM": {"layer": "CGM / Delivery Device", "priority": "P1", "bottleneck": "Sensor manufacturing", "catalyst": "Stelo OTC launch", "thesis": "CGM = standard of care for diabetes. OTC expansion = TAM 3x.", "correlates_with": ["TNDM", "LLY"]},
    "UNH": {"layer": "Insurance / Coverage", "priority": "P1", "bottleneck": "Obesity classification", "catalyst": "CMS coverage decision", "thesis": "Insurance coverage = GLP-1 demand unlock. UNH = largest private payer.", "correlates_with": ["CI", "LLY", "NVO"]},
}

# ═══════════════════════════════════════════════════════════════════
# CHAIN REACTION DEFINITIONS (v40.1 — 16 chains)
# ═══════════════════════════════════════════════════════════════════
CHAIN_REACTIONS = {
    "AI_COMPUTE_BUILDOUT": {
        "trigger": "AGI by 2027 (Leopold thesis)",
        "confidence": 0.85,
        "source": "Leopold Aschenbrenner / Citrini Research",
        "stages": [
            {"stage": 1, "layer": "AI Models / GPU", "tickers": ["NVDA", "AMD"], "bottleneck": "CoWoS + HBM supply"},
            {"stage": 2, "layer": "Foundry / Wafer", "tickers": ["TSM", "INTC"], "bottleneck": "3nm capacity + AZ fab"},
            {"stage": 3, "layer": "Memory / HBM", "tickers": ["MU", "SKHYNIX"], "bottleneck": "HBM3E yield + TSV capacity"},
            {"stage": 4, "layer": "Semiconductor Equipment", "tickers": ["ASML", "LRCX", "AMAT", "KLAC"], "bottleneck": "High-NA EUV + ALD tools"},
            {"stage": 5, "layer": "Networking / Optics", "tickers": ["AVGO", "MRVL", "COHR", "LITE"], "bottleneck": "800G/1.6T optical + DSP"},
            {"stage": 6, "layer": "CPO / Connectors", "tickers": ["NXT", "AMPH"], "bottleneck": "Co-packaged optics + 224G PAM4"},
            {"stage": 7, "layer": "Power / Cooling", "tickers": ["VST", "CEG", "BE", "NEE"], "bottleneck": "Interconnection queue + nuclear restart"},
            {"stage": 8, "layer": "Raw Materials", "tickers": ["SCCO", "FCX", "ALB", "MP"], "bottleneck": "Copper deficit + lithium brine + rare earth separation"},
        ]
    },
    "MIDEAST_SUPPLY_SHOCK": {
        "trigger": "Iran conflict escalation / Strait of Hormuz closure risk",
        "confidence": 0.70,
        "source": "Geopolitical cascade analysis",
        "stages": [
            {"stage": 1, "layer": "Crude Oil", "tickers": ["CL=F", "USO", "XOM", "CVX", "COP"], "bottleneck": "Strait of Hormuz (15-20% global supply)"},
            {"stage": 2, "layer": "Tankers / Shipping", "tickers": ["FRO", "TK", "INSW", "NAT"], "bottleneck": "VLCC rates + war risk insurance"},
            {"stage": 3, "layer": "Refining / Crack Spreads", "tickers": ["VLO", "MPC", "PSX", "DK"], "bottleneck": "Heavy/sour crude discount + capacity"},
            {"stage": 4, "layer": "Fertilizer / Ammonia", "tickers": ["NTR", "MOS", "CF", "UAN"], "bottleneck": "Natural gas -> ammonia (feedstock cost)"},
            {"stage": 5, "layer": "Agriculture / Food Security", "tickers": ["ZS=F", "ZW=F", "ZC=F"], "bottleneck": "Fertilizer cost pass-through + drought"},
            {"stage": 6, "layer": "Defense / Munitions", "tickers": ["LMT", "NOC", "RTX", "GD"], "bottleneck": "Munitions replenishment + drone supply"},
        ]
    },
    "INDONESIA_RESOURCE_NATIONALISM": {
        "trigger": "Q4 Deflation + export restrictions + downstream mandate",
        "confidence": 0.75,
        "source": "IHSG Specialist + Hedgeye Q4",
        "stages": [
            {"stage": 1, "layer": "Nickel / EV Battery", "tickers": ["NCKL.JK", "ANTM.JK", "INCO.JK"], "bottleneck": "HPAL capacity + export quota"},
            {"stage": 2, "layer": "Palm Oil / CPO", "tickers": ["AALI.JK", "LSIP.JK", "SMAR.JK"], "bottleneck": "EU Deforestation Regulation traceability"},
            {"stage": 3, "layer": "Coal / Domestic Obligation", "tickers": ["ADRO.JK", "ITMG.JK", "PTBA.JK"], "bottleneck": "DMO quota enforcement + price cap"},
            {"stage": 4, "layer": "Banking / NIM", "tickers": ["BBRI.JK", "BMRI.JK", "BBCA.JK", "BBNI.JK"], "bottleneck": "BI rate duration + credit cycle"},
            {"stage": 5, "layer": "Shipping / Logistics", "tickers": ["WINS.JK"], "bottleneck": "Port congestion + toll road tariffs"},
            {"stage": 6, "layer": "Consumer / Pharma", "tickers": ["ICBP.JK", "INDF.JK", "KLBF.JK"], "bottleneck": "Rupiah stability + import cost"},
        ]
    },
    "COPPER_ELECTRIFICATION": {
        "trigger": "EV + grid + datacenter = 5-7M tonne deficit by 2030",
        "confidence": 0.80,
        "source": "Glencore / Wood Mackenzie supply models",
        "stages": [
            {"stage": 1, "layer": "Copper Mining", "tickers": ["SCCO", "FCX", "BHP"], "bottleneck": "Grade decline + water + permit delays"},
            {"stage": 2, "layer": "Wire / Cable", "tickers": ["WIRE", "GNRC"], "bottleneck": "Grid interconnection queue + transformer shortage"},
            {"stage": 3, "layer": "Grid Infrastructure", "tickers": ["VST", "NEE", "D", "BE"], "bottleneck": "Transmission buildout + NIMBY"},
            {"stage": 4, "layer": "EV Charging", "tickers": ["CHPT", "EVGO", "BLNK"], "bottleneck": "Utilization rate + grid connection"},
            {"stage": 5, "layer": "EV OEM", "tickers": ["TSLA", "RIVN", "LCID", "NIO"], "bottleneck": "Copper motor winding + battery cost"},
        ]
    },
    "URANIUM_NUCLEAR_RENAISSANCE": {
        "trigger": "AI power demand + net-zero = nuclear restart + new builds",
        "confidence": 0.75,
        "source": "UxC / Yellow Cake supply-demand model",
        "stages": [
            {"stage": 1, "layer": "Uranium Mining", "tickers": ["CCJ", "UUUU", "UEC", "DNN"], "bottleneck": "Kazakhstan supply concentration + ISR capacity"},
            {"stage": 2, "layer": "Enrichment / Conversion", "tickers": ["URA", "LEU"], "bottleneck": "SWU capacity + Russian sanctions risk"},
            {"stage": 3, "layer": "Nuclear Utilities", "tickers": ["CEG", "VST", "NEE", "EXC"], "bottleneck": "NRC restart permits + waste storage"},
            {"stage": 4, "layer": "SMR / Advanced Reactor", "tickers": ["OKLO", "SMR", "BWXT"], "bottleneck": "NRC licensing + fuel fabrication"},
            {"stage": 5, "layer": "Grid / Backup", "tickers": ["BE", "GNRC"], "bottleneck": "Baseload complement + storage"},
        ]
    },
    "SEMICONDUCTOR_EQUIPMENT": {
        "trigger": "Sub-2nm transition + China embargo = equipment supercycle",
        "confidence": 0.80,
        "source": "SEMI / TechInsights capex tracker",
        "stages": [
            {"stage": 1, "layer": "Lithography", "tickers": ["ASML"], "bottleneck": "High-NA EUV delivery + spare parts"},
            {"stage": 2, "layer": "Deposition / Etch", "tickers": ["LRCX", "AMAT"], "bottleneck": "GAA transistor complexity + chamber lead time"},
            {"stage": 3, "layer": "Metrology / Inspection", "tickers": ["KLAC", "MKSI"], "bottleneck": "EUV mask inspection + yield ramp"},
            {"stage": 4, "layer": "Materials / Chemicals", "tickers": ["ENTG", "CCMP"], "bottleneck": "High-purity chemicals + EUV resist"},
            {"stage": 5, "layer": "Substrate / Advanced Packaging", "tickers": ["AMKR", "INTC"], "bottleneck": "Glass core substrate + RDL capacity"},
        ]
    },
    "RARE_EARTH_DEFENSE": {
        "trigger": "China export controls + DoD stockpile mandate",
        "confidence": 0.70,
        "source": "DoD Critical Minerals Report",
        "stages": [
            {"stage": 1, "layer": "Rare Earth Mining", "tickers": ["MP"], "bottleneck": "Mountain Pass throughput + separation"},
            {"stage": 2, "layer": "Separation / Magnet", "tickers": ["NEO", "MPCO"], "bottleneck": "NdFeB magnet capacity + heavy rare earth sourcing"},
            {"stage": 3, "layer": "Defense / Aerospace", "tickers": ["LMT", "NOC", "RTX", "BA"], "bottleneck": "F-35 motor + missile guidance magnet supply"},
            {"stage": 4, "layer": "EV Motors", "tickers": ["TSLA", "NIO", "GM", "F"], "bottleneck": "Permanent magnet motor vs induction switch"},
        ]
    },
    "RED_SEA_CONTAINER_CRISIS": {
        "trigger": "Houthi attacks + cape routing = +15% fleet miles + rate spike",
        "confidence": 0.65,
        "source": "Drewry / Freightos container index",
        "stages": [
            {"stage": 1, "layer": "Container Shipping", "tickers": ["ZIM", "MATX"], "bottleneck": "Red Sea diversion capacity + newbuild delivery"},
            {"stage": 2, "layer": "Air Freight", "tickers": ["UPS", "FDX"], "bottleneck": "Sea-air substitution + e-commerce volume"},
            {"stage": 3, "layer": "Logistics / Brokerage", "tickers": ["CHRW", "EXPD"], "bottleneck": "Rate volatility + carrier contract renegotiation"},
            {"stage": 4, "layer": "Retail Inventory", "tickers": ["AMZN", "WMT", "TGT"], "bottleneck": "Safety stock rebuild + working capital"},
            {"stage": 5, "layer": "Manufacturing", "tickers": ["AAPL", "NKE", "DE"], "bottleneck": "Component lead times + just-in-sea disruption"},
        ]
    },
    "BITCOIN_HALVING_SQUEEZE": {
        "trigger": "Post-halving supply shock + ETF inflows + exchange balance low",
        "confidence": 0.75,
        "source": "Glassnode / Coin Metrics on-chain data",
        "stages": [
            {"stage": 1, "layer": "Bitcoin Mining", "tickers": ["RIOT", "MARA", "CLSK", "BITF"], "bottleneck": "Hashrate competition + energy cost"},
            {"stage": 2, "layer": "Bitcoin Treasury", "tickers": ["MSTR", "TSLA"], "bottleneck": "Corporate adoption + accounting rules"},
            {"stage": 3, "layer": "Exchange / Custody", "tickers": ["COIN", "HOOD"], "bottleneck": "ETF creation/redemption + custody insurance"},
            {"stage": 4, "layer": "Layer 2 / Payments", "tickers": ["BTC-USD", "ETH-USD", "SOL-USD"], "bottleneck": "Lightning adoption + fee market"},
            {"stage": 5, "layer": "Mining Equipment", "tickers": ["NVDA", "AMD"], "bottleneck": "ASIC supply + immersion cooling"},
        ]
    },
    "BIOTECH_GLP1_SUPPLY": {
        "trigger": "GLP-1 demand outstrips manufacturing capacity 10:1",
        "confidence": 0.70,
        "source": "IQVIA / Evaluate Pharma demand model",
        "stages": [
            {"stage": 1, "layer": "GLP-1 Drug", "tickers": ["LLY", "NVO"], "bottleneck": "Peptide API capacity + fill-finish"},
            {"stage": 2, "layer": "CDMO / Manufacturing", "tickers": ["DHR", "TECD", "CTLT"], "bottleneck": "Sterile injectable capacity + dual-source"},
            {"stage": 3, "layer": "Peptide API", "tickers": ["AMPH", "PETQ"], "bottleneck": "Solid-phase synthesis + resin supply"},
            {"stage": 4, "layer": "Delivery Device", "tickers": ["DXCM", "TNDM"], "bottleneck": "Auto-injector pen + cold chain"},
            {"stage": 5, "layer": "Complications / Insurance", "tickers": ["UNH", "CI"], "bottleneck": "Coverage expansion + obesity classification"},
        ]
    },
    "LNG_EUROPE_ENERGY_CRISIS": {
        "trigger": "Russian pipeline cutoff + winter demand = LNG scramble",
        "confidence": 0.70,
        "source": "IEA / ICIS LNG market report",
        "stages": [
            {"stage": 1, "layer": "US Natural Gas", "tickers": ["UNG", "USO"], "bottleneck": "LNG export permit delays + pipeline capacity"},
            {"stage": 2, "layer": "LNG Shipping / FSRU", "tickers": ["LNG", "GLNG", "FLNG"], "bottleneck": "FSRU availability + charter rates"},
            {"stage": 3, "layer": "Liquefaction", "tickers": ["TELL", "CEG"], "bottleneck": "FID + offtake agreements"},
            {"stage": 4, "layer": "European Utilities", "tickers": ["NEE", "VST", "D"], "bottleneck": "Grid interconnection + storage fill"},
            {"stage": 5, "layer": "Fertilizer / Chemicals", "tickers": ["NTR", "MOS", "CF"], "bottleneck": "Gas-to-ammonia cost pass-through"},
        ]
    },
    "TAIWAN_STRAIT_BLOCKADE": {
        "trigger": "China escalation / semiconductor supply chain severance",
        "confidence": 0.55,
        "source": "CSIS / RAND wargaming scenarios",
        "stages": [
            {"stage": 1, "layer": "TSMC / Foundry", "tickers": ["TSM", "UMC"], "bottleneck": "Wafer fab + EUV lithography"},
            {"stage": 2, "layer": "Fabless Design", "tickers": ["NVDA", "QCOM", "AMD", "AVGO"], "bottleneck": "Advanced node allocation"},
            {"stage": 3, "layer": "Equipment", "tickers": ["ASML", "LRCX", "AMAT"], "bottleneck": "Spare parts + service engineers"},
            {"stage": 4, "layer": "Materials", "tickers": ["ENTG", "MKSI"], "bottleneck": "High-purity chemicals + gases"},
            {"stage": 5, "layer": "US Defense / Substitution", "tickers": ["INTC", "LMT", "NOC", "RTX"], "bottleneck": "CHIPS Act fab ramp + munitions"},
        ]
    },
    "CHINA_PROPERTY_COLLAPSE": {
        "trigger": "Evergrande contagion + steel demand cliff",
        "confidence": 0.65,
        "source": "Nomura / China steel association",
        "stages": [
            {"stage": 1, "layer": "Iron Ore", "tickers": ["BHP", "VALE", "MT"], "bottleneck": "Seaborne demand 60% China"},
            {"stage": 2, "layer": "Steel", "tickers": ["STLD", "NUE", "CLF", "MT"], "bottleneck": "Blast furnace utilization"},
            {"stage": 3, "layer": "Copper", "tickers": ["SCCO", "FCX"], "bottleneck": "Construction wiring demand"},
            {"stage": 4, "layer": "Cement / Aggregates", "tickers": ["CX", "SUM"], "bottleneck": "Local government financing"},
            {"stage": 5, "layer": "China Banks", "tickers": ["BABA", "JD", "PDD"], "bottleneck": "Consumer confidence + NPLs"},
        ]
    },
    "FED_PIVOT_RATE_CUT_CASCADE": {
        "trigger": "Fed cuts 150bps + QT end = liquidity flood",
        "confidence": 0.60,
        "source": "Hedgeye GIP Model / Fed funds futures",
        "stages": [
            {"stage": 1, "layer": "Long Duration Bonds", "tickers": ["TLT", "IEF", "TMF", "SCHP"], "bottleneck": "Treasury issuance + foreign demand"},
            {"stage": 2, "layer": "Rate-Sensitive Equity", "tickers": ["XLK", "XLY", "QQQ", "IWM"], "bottleneck": "Earnings recession vs multiple expansion"},
            {"stage": 3, "layer": "Regional Banks", "tickers": ["KRE", "XLF", "BAC", "JPM"], "bottleneck": "CRE mark-to-market + NIM compression"},
            {"stage": 4, "layer": "Crypto / Risk", "tickers": ["BTC-USD", "ETH-USD", "COIN"], "bottleneck": "Dollar liquidity + regulatory clarity"},
            {"stage": 5, "layer": "EM / Commodity", "tickers": ["EEM", "XLE", "GLD"], "bottleneck": "DXY collapse + China stimulus"},
        ]
    },
    "WATER_CRISIS_COLORADO_RIVER": {
        "trigger": "Colorado River Compact renegotiation + megadrought",
        "confidence": 0.60,
        "source": "USBR / Arizona State water policy",
        "stages": [
            {"stage": 1, "layer": "Water Utilities", "tickers": ["AWK", "CWT", "WTRG"], "bottleneck": "Rate base growth + lead replacement"},
            {"stage": 2, "layer": "Desalination / Tech", "tickers": ["AQUA"], "bottleneck": "Permit + brine disposal"},
            {"stage": 3, "layer": "Agriculture / Fertilizer", "tickers": ["NTR", "MOS", "CF"], "bottleneck": "Water rights + irrigation cost"},
            {"stage": 4, "layer": "Solar / Power", "tickers": ["NEE", "VST", "CEG"], "bottleneck": "Cooling water for thermal plants"},
            {"stage": 5, "layer": "Real Estate", "tickers": ["AMT", "CCI"], "bottleneck": "Phoenix/Vegas growth constraints"},
        ]
    },
    "SPACE_SATELLITE_BOTTLENECK": {
        "trigger": "LEO congestion + direct-to-cell spectrum rush",
        "confidence": 0.65,
        "source": "FCC / Euroconsult satellite forecast",
        "stages": [
            {"stage": 1, "layer": "Launch", "tickers": ["RKLB", "SPCE"], "bottleneck": "Launch cadence + range capacity"},
            {"stage": 2, "layer": "Satellite Manufacturing", "tickers": ["ASTS", "IRDM", "VSAT"], "bottleneck": "Bus production + solar array supply"},
            {"stage": 3, "layer": "Ground Infrastructure", "tickers": ["AMT", "CCI"], "bottleneck": "Gateway site + backhaul fiber"},
            {"stage": 4, "layer": "Spectrum / Regulation", "tickers": ["T", "VZ", "CMCSA"], "bottleneck": "C-band clearing + interference rules"},
            {"stage": 5, "layer": "Defense / ISR", "tickers": ["LMT", "NOC", "RTX"], "bottleneck": "Classified payload integration"},
        ]
    },
}

def get_bottleneck_tickers():
    return BOTTLENECK_TICKERS

def get_ticker_bottleneck(ticker: str):
    return BOTTLENECK_META.get(ticker.upper(), None)

def get_correlated_tickers(ticker: str):
    meta = get_ticker_bottleneck(ticker)
    if meta:
        return meta.get("correlates_with", [])
    return []

def get_all_by_market(market_type: str = "us_equity"):
    if market_type == "us_equity":
        return [t for t in BOTTLENECK_TICKERS if not t.endswith(".JK") and "=" not in t and "-USD" not in t]
    elif market_type == "commodity":
        return [t for t in BOTTLENECK_TICKERS if "=" in t or t in ["USO", "GLD", "SLV", "UNG"]]
    elif market_type == "forex":
        return [t for t in BOTTLENECK_TICKERS if t.endswith("=X") or t in ["DX-Y.NYB", "UUP"]]
    elif market_type == "crypto":
        return [t for t in BOTTLENECK_TICKERS if "-USD" in t or t in ["MSTR", "COIN", "RIOT", "MARA"]]
    elif market_type == "ihsg":
        return [t for t in BOTTLENECK_TICKERS if t.endswith(".JK")]
    return BOTTLENECK_TICKERS

def get_chain_reaction(name: str):
    return CHAIN_REACTIONS.get(name, None)

def get_all_chain_reactions():
    return CHAIN_REACTIONS
