"""universe_sources.py — dynamic universe sourcing for the Moonshot Radar.

Fixes the hardcoded-list problem: the candidate universe is SOURCED, not handwritten.
  1. Curated seed (moonshot_universe.DOMAINS) — used ONLY to tag node + thesis (overlay).
  2. Thematic ETF holdings — each bottleneck domain's universe = holdings of its ETFs,
     auto-refreshed on rebalance (new names enter automatically).
  3. Full listed symbols — every listed ticker; the screen filters for the hidden ones.
  4. Supply-chain feed (SEAM) — real "supplier-of-X" graphs need FactSet/Bloomberg SPLC
     or NLP on 10-K supplier/customer mentions. NOT fabricated here.
Plus an editable intake (CSV the user appends) → feeds back into the seed overlay.

Deploy: ETF-holdings + listed-symbol fetches hit public provider/exchange endpoints
(no API key). In a restricted sandbox they degrade gracefully (fall back / return []).
"""
from __future__ import annotations
import csv
import io
import urllib.request

# domain → thematic ETFs whose holdings ARE the maintained per-theme universe
THEME_ETFS = {
    "AI compute / semis":          ["SMH", "SOXX"],
    "Power generation & grid":     ["GRID", "PAVE"],
    "Cooling / data center":       ["DTCR", "SRVR"],
    "Uranium / nuclear":           ["URA", "URNM", "NLR"],
    "Copper / critical minerals":  ["COPX", "PICK"],
    "Rare earth / magnets":        ["REMX"],
    "Aerospace / space / defense": ["ARKX", "UFO", "ITA", "XAR"],
    "China decoupling / reshoring":["PAVE"],
    "Cybersecurity / sovereign":   ["CIBR", "BUG"],
}

# provider holdings endpoints (deploy; no key). Global X / SSGA publish daily files.
_HOLDINGS_TPL = {
    "globalx": "https://www.globalxetfs.com/funds/{t}/?download_full_holdings=true",
    "ssga": "https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-{t}.xlsx",
}

# full listed-symbol sources (nasdaqtrader on deploy; GitHub dataset works in sandbox)
_LISTED = {
    "nasdaq": "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
    "other": "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
    "github_sp500": "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv",
}


def _fetch(url, timeout=30):
    try:
        return urllib.request.urlopen(url, timeout=timeout).read().decode("utf-8", "replace")
    except Exception:
        return None


def load_sp500():
    """A maintained universe (S&P 500) from a public GitHub dataset — demonstrable anywhere."""
    txt = _fetch(_LISTED["github_sp500"])
    if not txt:
        return []
    out = []
    for row in csv.DictReader(io.StringIO(txt)):
        s = (row.get("Symbol") or "").strip()
        if s:
            out.append(s.replace(".", "-"))
    return out


def load_listed_symbols():
    """Full US listed universe (deploy: nasdaqtrader). Falls back to S&P 500 if blocked."""
    syms = set()
    for key in ("nasdaq", "other"):
        txt = _fetch(_LISTED[key])
        if not txt:
            continue
        for line in txt.splitlines()[1:]:
            parts = line.split("|")
            if parts and parts[0] and parts[0] not in ("", "File Creation Time"):
                syms.add(parts[0].strip())
    if not syms:
        syms = set(load_sp500())  # graceful fallback when exchange endpoint is blocked
    return sorted(syms)


def load_etf_holdings(etf):
    """Holdings of a thematic ETF (deploy). Returns [] if the endpoint is unavailable."""
    for prov in ("globalx", "ssga"):
        txt = _fetch(_HOLDINGS_TPL[prov].format(t=etf.lower()))
        if not txt:
            continue
        tickers = []
        for row in csv.reader(io.StringIO(txt)):
            for cell in row[:3]:
                c = cell.strip().upper()
                if c.isalpha() and 1 <= len(c) <= 5:
                    tickers.append(c)
                    break
        if tickers:
            return tickers
    return []


def theme_universe(domains=None):
    """Union of holdings across thematic ETFs (deploy) → {ticker: [domains]}."""
    src = THEME_ETFS if domains is None else {d: THEME_ETFS[d] for d in domains if d in THEME_ETFS}
    out = {}
    for dom, etfs in src.items():
        for etf in etfs:
            for t in load_etf_holdings(etf):
                out.setdefault(t, set()).add(dom)
    return {t: sorted(v) for t, v in out.items()}


def load_intake(path):
    """User-appended candidates (CSV with column 'ticker'[, 'node', 'thesis'])."""
    try:
        return [r for r in csv.DictReader(open(path)) if (r.get("ticker") or "").strip()]
    except Exception:
        return []


def build_universe(use_theme=True, use_listed=False, intake_path=None):
    """Assemble the working universe -> {ticker: [sources]}. Node tagging happens in the engine."""
    uni = {}
    if use_theme:
        for t, doms in theme_universe().items():
            uni.setdefault(t, set()).add("etf:" + ",".join(doms))
    if use_listed:
        for t in load_listed_symbols():
            uni.setdefault(t, set()).add("listed")
    if intake_path:
        for r in load_intake(intake_path):
            uni.setdefault(r["ticker"].strip().upper(), set()).add("intake")
    return {t: sorted(s) for t, s in uni.items()}
