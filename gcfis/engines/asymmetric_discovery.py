"""asymmetric_discovery.py — the Moonshot / Asymmetric Discovery engine.

Scores bottleneck candidates on the STRUCTURAL characteristics that preceded past
moonshots — it does NOT predict returns. Framework (from the reference set):
  • Bottleneck migration (Citrini): GPU → networking → power → cooling → edge.
  • Dependency-graph investing (Serenity): irreplaceability, qualification cycles,
    substitution difficulty, supplier layer 3-4.
  • Atoms over bits (Citrini): physical scarcity > software abundance.
  • Engineering + economics (SemiAnalysis/Patel): what is physically possible / sold out.

Asymmetry score (0-100) = weighted blend of six factors. Three are computable now from
price/volume via existing engines (early-adoption, reflexivity, momentum); three need a
live fundamental feed (room-to-run/market-cap, cheap-valuation, under-coverage) and
default to NEUTRAL until wired — flagged honestly, never fabricated.

HONEST BASE RATES: upside tier and success probability move in OPPOSITE directions.
A tier-5 micro-cap may have 500x optionality and a ~lottery base rate. This engine
ranks asymmetry, it does not promise outcomes. Not financial advice.
"""
from __future__ import annotations
from .. data.moonshot_universe import all_candidates, TIER_HEADROOM, DOMAINS  # noqa

# weights are PRIORS (sum=1.0) — validate in the lab, do not treat as truth
_W = {
    "centrality":    0.26,   # how irreplaceable the bottleneck node is (curated, from tier/stage)
    "early":         0.22,   # uncrowded / early adoption (computable: crowding percentile inv)
    "reflexivity":   0.16,   # price↔flow↔narrative feedback potential (computable)
    "undercoverage": 0.16,   # "hidden": low analyst/institutional/social (FEED-GATED)
    "valuation":     0.10,   # cheap vs forward earnings / EV-EBITDA (FEED-GATED)
    "room_to_run":   0.10,   # small cap = more % headroom (FEED-GATED, also sets lottery tier)
}
assert abs(sum(_W.values()) - 1.0) < 1e-9

FAILURE_MODES = [
    "valuation trap: cheap multiple = low growth / cyclicality / peak margin, not a gift",
    "vertical integration: a prime (LMT/NVDA/hyperscaler) internalizes the node",
    "demand cyclicality: capex pauses → supplier inventory correction",
    "execution / dilution: pre-revenue names raise capital and dilute or fail to scale",
    "substitution / next-node migration: the bottleneck moves before you exit",
]


def _centrality(meta):
    """Irreplaceability proxy from curated tier + lifecycle stage. Hidden layer-3/4 nodes
    score higher centrality-asymmetry than crowded tier-1."""
    base = {1: 45, 2: 62, 3: 78, 4: 70, 5: 66}.get(meta["tier"], 60)
    stage_adj = {"emergence": +12, "acceleration": +4, "consensus": -10}.get(meta["stage"], 0)
    hidden_adj = +8 if meta.get("is_hidden") else 0
    crowded_adj = -18 if meta.get("is_crowded") else 0
    return max(0.0, min(100.0, base + stage_adj + hidden_adj + crowded_adj))


def _tier_from_cap(market_cap_usd, curated_tier):
    """If market cap is known, derive the lottery tier from it; else fall back to curated."""
    if market_cap_usd is None:
        return curated_tier
    b = market_cap_usd
    if b >= 1e11: return 1
    if b >= 2e10: return 2
    if b >= 3e9:  return 3
    if b >= 4e8:  return 4
    return 5


def score_candidate(meta, signals=None):
    """meta: row from all_candidates(). signals: optional per-ticker dict with any of
    {crowding_pct(0-100, lower=earlier), reflexivity(0-100), market_cap_usd,
     fwd_pe, peer_fwd_pe, coverage_pct(0-100, lower=less covered)}."""
    s = signals or {}
    centrality = _centrality(meta)
    if meta.get("uncategorized"):
        centrality = min(centrality, 45.0)  # unknown node must EARN rank via signals, not assumed scarcity

    # early adoption: lower crowding percentile => earlier => higher score (computable)
    crowd = s.get("crowding_pct")
    early = (100.0 - crowd) if crowd is not None else 55.0  # neutral-ish default

    # reflexivity potential (computable)
    reflex = s.get("reflexivity")
    reflex = reflex if reflex is not None else 50.0

    # under-coverage (FEED-GATED): lower coverage => more hidden => higher
    cov = s.get("coverage_pct")
    undercov = (100.0 - cov) if cov is not None else (62.0 if meta.get("is_hidden") else 45.0)
    undercov_gated = cov is None

    # cheap valuation (FEED-GATED): forward PE vs peers
    fpe, ppe = s.get("fwd_pe"), s.get("peer_fwd_pe")
    if fpe and ppe and fpe > 0:
        valuation = max(0.0, min(100.0, 50.0 + (ppe - fpe) / ppe * 100.0))
    else:
        valuation = 50.0
    val_gated = not (fpe and ppe)

    # room to run (FEED-GATED): smaller cap => more headroom
    cap = s.get("market_cap_usd")
    if cap is not None:
        room = max(0.0, min(100.0, 100.0 - (max(cap, 1e8) / 1e11) * 100.0))
    else:
        room = {1: 25, 2: 45, 3: 70, 4: 85, 5: 92}.get(meta["tier"], 55)
    room_gated = cap is None

    score = (
        _W["centrality"] * centrality + _W["early"] * early + _W["reflexivity"] * reflex +
        _W["undercoverage"] * undercov + _W["valuation"] * valuation + _W["room_to_run"] * room
    )
    tier = _tier_from_cap(cap, meta["tier"])
    th = TIER_HEADROOM.get(tier, {})
    # confidence: high-upside tiers are LOW confidence by construction (honest)
    conf = {1: "moderate", 2: "moderate", 3: "low", 4: "very low", 5: "lottery"}.get(tier, "low")

    gated = [k for k, g in [("under-coverage", undercov_gated), ("valuation", val_gated),
                            ("room-to-run", room_gated)] if g]
    return {
        "ticker": meta["ticker"], "domain": meta["domain"], "node": meta["node"],
        "framework": meta["framework"], "source": meta["source"], "scarcity": meta["scarcity"],
        "is_hidden": meta.get("is_hidden", False), "is_crowded": meta.get("is_crowded", False),
        "asymmetry": round(score, 1), "tier": tier, "stage": meta["stage"],
        "upside_bucket": th.get("label", "?"), "base_rate": th.get("base_rate", "?"),
        "confidence": conf,
        "factors": {"centrality": round(centrality), "early": round(early), "reflexivity": round(reflex),
                    "undercoverage": round(undercov), "valuation": round(valuation), "room_to_run": round(room)},
        "feed_gated_neutral": gated,  # honesty: these factors are placeholders until feeds wired
    }


def score_uncategorized(ticker, signals=None):
    """Score a name that is NOT in the curated map (came from ETF holdings / listed symbols).
    It has no known bottleneck node, so centrality is capped — it must earn rank via signals."""
    meta = {"ticker": ticker, "domain": "uncategorized", "node": "unclassified — passes screen",
            "framework": "screen", "source": "universe", "tier": 3, "stage": "emergence",
            "scarcity": "not yet mapped to a bottleneck node — investigate / classify",
            "is_hidden": True, "is_crowded": False, "uncategorized": True}
    r = score_candidate(meta, signals)
    r["uncategorized"] = True
    return r


def run_discovery(signals_by_ticker=None, extra_tickers=None, hidden_only=False, min_asymmetry=0.0, top=40):
    """Rank the universe by asymmetry. signals_by_ticker: {ticker: signals dict}.
    extra_tickers: a sourced universe (ETF holdings / listed symbols) — names not in the
    curated map are scored as 'uncategorized' (new candidates to classify).
    Quality-over-quantity: surface the few that clear the bar, not the whole list."""
    sig = signals_by_ticker or {}
    curated = all_candidates(hidden_only=hidden_only)
    rows = [score_candidate(m, sig.get(m["ticker"])) for m in curated]
    if extra_tickers:
        mapped = {m["ticker"] for m in curated}
        for t in extra_tickers:
            if t and t not in mapped:
                rows.append(score_uncategorized(t, sig.get(t)))
    rows = [r for r in rows if r["asymmetry"] >= min_asymmetry]
    rows.sort(key=lambda r: (-r["asymmetry"], r["tier"]))
    rows = rows[:top]
    n_feed = sum(1 for r in rows if not r["feed_gated_neutral"])
    return {
        "candidates": rows,
        "summary": {
            "n": len(rows), "hidden": sum(1 for r in rows if r["is_hidden"]),
            "uncategorized": sum(1 for r in rows if r.get("uncategorized")),
            "domains": sorted({r["domain"] for r in rows}),
            "fully_fed": n_feed, "needs_feed": len(rows) - n_feed,
            "note": "asymmetry is STRUCTURAL, not a return forecast — most tier-4/5 names fail",
        },
        "failure_modes": FAILURE_MODES,
    }
