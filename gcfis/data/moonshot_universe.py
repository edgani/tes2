"""moonshot_universe.py — seed universe for the Asymmetric / Moonshot Radar.

Harvested from the user's reference set: Citrini (bottleneck migration), Serenity
(dependency-graph / supplier layer 3-4), SemiAnalysis/Patel (engineering+economics),
"atoms over bits", the AI→power shift, photonics/HBM/packaging supply chains, the
SpaceX hidden-supplier thesis (ATI/MTRN/PKE/KTOS), uranium/copper/rare-earth, and
the China-decoupling reshoring map.

⚠ THIS IS A RESEARCH SCREEN, NOT ADVICE. Tickers are SEED CANDIDATES grouped by
bottleneck node — not recommendations. No price/valuation/market-cap is asserted here
(those require a live fundamental feed). The higher the upside tier, the LOWER the
base rate: tier-4/5 micro-caps are lottery tickets and most go to zero. Do your own
due diligence. Not financial advice.

Schema per node:
  node           : the bottleneck / scarcity choke point
  tier           : 1 large/crowded ... 5 micro/pre-revenue lottery (upside ↑, base rate ↓)
  stage          : emergence | acceleration | consensus  (narrative lifecycle)
  scarcity       : WHY it is a bottleneck (what cannot scale / be substituted)
  direct         : names with direct revenue exposure to the choke point
  hidden         : layer 3-4 / indirect names the crowd skips (the alpha frontier)
  crowded        : names already consensus (kept for contrast — usually NOT the edge)
"""

# upside headroom + honest base rate per tier (for the engine's tier framing)
TIER_HEADROOM = {
    1: {"label": "1.5–3x", "base_rate": "high",      "note": "large / liquid / already consensus"},
    2: {"label": "3–10x",  "base_rate": "moderate",  "note": "mid-cap, semi-discovered"},
    3: {"label": "10–50x", "base_rate": "low",       "note": "small-cap, under-covered, early"},
    4: {"label": "50–500x","base_rate": "very low",  "note": "micro-cap / early-revenue — most fail"},
    5: {"label": "500x+",  "base_rate": "lottery",   "note": "pre-revenue optionality — most go to zero"},
}

DOMAINS = [
    {"domain": "AI compute / accelerators", "framework": "engineering + economics", "source": "SemiAnalysis / Patel",
     "nodes": [
         {"node": "GPU / accelerator silicon", "tier": 1, "stage": "consensus",
          "scarcity": "leading-edge wafer + design — demand exponential, but already priced",
          "direct": ["NVDA", "AMD", "AVGO", "MRVL"], "hidden": [], "crowded": ["NVDA", "AMD"]},
         {"node": "Advanced packaging & ABF substrate (layer 3-4)", "tier": 3, "stage": "acceleration",
          "scarcity": "CoWoS / HBM stacking + substrate is the throughput wall — multi-year qualify, hard to substitute",
          "direct": ["AMKR", "ONTO", "KLIC", "COHU"], "hidden": ["AEHR", "CAMT", "ACLS", "FORM"], "crowded": []},
         {"node": "Connectivity / retimer / custom-silicon IP", "tier": 2, "stage": "acceleration",
          "scarcity": "rack-scale interconnect can't keep up with compute — irreplaceable glue",
          "direct": ["CRDO", "ALAB"], "hidden": ["MTSI", "SITM"], "crowded": []},
     ]},
    {"domain": "Memory / HBM", "framework": "dependency graph", "source": "Serenity",
     "nodes": [
         {"node": "High-bandwidth memory", "tier": 2, "stage": "acceleration",
          "scarcity": "HBM capacity sold out forward — the memory wall is the real constraint, latency > throughput",
          "direct": ["MU"], "hidden": [], "crowded": ["MU"]},
         {"node": "Memory test & HBM equipment", "tier": 3, "stage": "emergence",
          "scarcity": "HBM stack test/burn-in is a niche choke — few qualified vendors",
          "direct": ["ACLS"], "hidden": ["AEHR", "FORM"], "crowded": []},
     ]},
    {"domain": "Photonics / optical interconnect / CPO", "framework": "dependency graph + atoms over bits", "source": "Serenity / Citrini",
     "nodes": [
         {"node": "Optical transceivers (800G/1.6T)", "tier": 2, "stage": "acceleration",
          "scarcity": "every AI cluster needs exploding optical I/O — capacity + laser supply constrained",
          "direct": ["COHR", "LITE", "AAOI"], "hidden": ["FN", "APLD"], "crowded": ["COHR"]},
         {"node": "Silicon photonics / co-packaged optics", "tier": 4, "stage": "emergence",
          "scarcity": "CPO replaces pluggables at scale — pre-inflection, irreplaceable if it lands",
          "direct": ["POET"], "hidden": ["POET"], "crowded": []},
     ]},
    {"domain": "Power generation & grid (chips → power)", "framework": "bottleneck migration", "source": "Citrini / teortaxes",
     "nodes": [
         {"node": "IPP / nuclear baseload for datacenters", "tier": 1, "stage": "consensus",
          "scarcity": "datacenter power is THE 2026 bottleneck — interconnect queue 4-6yr",
          "direct": ["VST", "CEG", "NRG", "TLN"], "hidden": [], "crowded": ["VST", "CEG"]},
         {"node": "Grid / electrical equipment (transformers, switchgear)", "tier": 2, "stage": "acceleration",
          "scarcity": "transformers + electrical steel are multi-year backordered — the un-virtualizable layer",
          "direct": ["GEV", "ETN", "PWR", "POWL"], "hidden": ["POWL", "NVT", "AYI"], "crowded": ["GEV", "ETN"]},
         {"node": "Behind-the-meter / interconnect / storage", "tier": 3, "stage": "emergence",
          "scarcity": "grid can't connect fast enough — on-site power + storage becomes mandatory",
          "direct": ["SHLS", "FLNC", "BE"], "hidden": ["SHLS", "BE"], "crowded": []},
     ]},
    {"domain": "Cooling / thermal", "framework": "atoms over bits", "source": "Citrini",
     "nodes": [
         {"node": "Liquid cooling (>50kW/rack mandatory)", "tier": 2, "stage": "acceleration",
          "scarcity": "B200-class racks force liquid cooling — thermal is a hard physical limit",
          "direct": ["VRT", "MOD", "NVT"], "hidden": ["MOD"], "crowded": ["VRT"]},
     ]},
    {"domain": "Uranium / nuclear fuel cycle", "framework": "bottleneck migration", "source": "Citrini",
     "nodes": [
         {"node": "Uranium miners", "tier": 2, "stage": "acceleration",
          "scarcity": "structural supply deficit + nuclear restart for AI power",
          "direct": ["CCJ", "UEC", "UUUU", "DNN"], "hidden": ["UEC", "DNN"], "crowded": ["CCJ"]},
         {"node": "Enrichment & small modular reactors", "tier": 4, "stage": "emergence",
          "scarcity": "HALEU enrichment near-monopoly + SMR optionality — pre-revenue, binary",
          "direct": ["LEU", "OKLO", "SMR"], "hidden": ["LEU", "NNE"], "crowded": []},
     ]},
    {"domain": "Copper / critical minerals / rare earth", "framework": "atoms over bits", "source": "Citrini / Gave",
     "nodes": [
         {"node": "Copper (electrification)", "tier": 2, "stage": "acceleration",
          "scarcity": "every datacenter + grid build is copper-intensive — decade-long supply gap",
          "direct": ["FCX", "SCCO", "ERO"], "hidden": ["ERO"], "crowded": ["FCX"]},
         {"node": "Rare earth / permanent magnets", "tier": 3, "stage": "emergence",
          "scarcity": "ex-China magnet supply is strategic + near-absent — reshoring forced",
          "direct": ["MP", "USAR"], "hidden": ["USAR"], "crowded": ["MP"]},
     ]},
    {"domain": "Aerospace / space supply chain (SpaceX picks & shovels)", "framework": "supplier layer 3-4", "source": "user thesis (doc)",
     "nodes": [
         {"node": "Advanced alloys / titanium / superalloys", "tier": 3, "stage": "emergence",
          "scarcity": "launch + defense scaling needs exotic metallurgy — throughput + qualification bottleneck",
          "direct": ["ATI", "HWM", "CRS"], "hidden": ["ATI", "CRS"], "crowded": []},
         {"node": "Engineered materials / beryllium / coatings", "tier": 3, "stage": "emergence",
          "scarcity": "satellites/optics/RF payloads need high-spec materials — niche near-monopoly",
          "direct": ["MTRN"], "hidden": ["MTRN"], "crowded": []},
         {"node": "Aerospace composites", "tier": 4, "stage": "emergence",
          "scarcity": "rocket/satellite structures — ultra-underfollowed small supplier",
          "direct": ["PKE"], "hidden": ["PKE"], "crowded": []},
         {"node": "Defense-space integration / propulsion / drones", "tier": 2, "stage": "acceleration",
          "scarcity": "Starshield + military-space stack overlap — second-order beneficiary",
          "direct": ["KTOS"], "hidden": ["KTOS"], "crowded": ["RKLB", "ASTS", "LUNR"]},
     ]},
    {"domain": "China decoupling / reshoring", "framework": "industrial policy", "source": "Gave / decoupling map",
     "nodes": [
         {"node": "Reshored electrical & automation base", "tier": 3, "stage": "emergence",
          "scarcity": "supply-chain repatriation forces domestic electrical/automation capacity",
          "direct": ["ROK", "AYI", "POWL"], "hidden": ["POWL", "AYI"], "crowded": []},
     ]},
    {"domain": "Sovereign AI / defense compute (optionality)", "framework": "tech + geopolitics", "source": "Thiel / Leopold",
     "nodes": [
         {"node": "Neocloud / sovereign compute buildout", "tier": 4, "stage": "emergence",
          "scarcity": "nation-state + enterprise compute demand — capital-intensive, binary execution",
          "direct": ["APLD", "CRWV", "NBIS"], "hidden": ["APLD", "NBIS"], "crowded": []},
     ]},
]


def all_candidates(hidden_only=False):
    """Flatten the universe into (ticker, node_meta) candidate rows."""
    rows = []
    seen = set()
    for dom in DOMAINS:
        for node in dom["nodes"]:
            pool = node["hidden"] if hidden_only else (node["direct"] + node["hidden"])
            for tkr in pool:
                key = (tkr, node["node"])
                if key in seen:
                    continue
                seen.add(key)
                rows.append({
                    "ticker": tkr, "domain": dom["domain"], "framework": dom["framework"],
                    "source": dom["source"], "node": node["node"], "tier": node["tier"],
                    "stage": node["stage"], "scarcity": node["scarcity"],
                    "is_hidden": tkr in node["hidden"], "is_crowded": tkr in node.get("crowded", []),
                })
    return rows
