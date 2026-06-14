"""config/autonomy_settings.py — 10/10 Autonomy Configuration

All tunable parameters for the self-discovering engine.
Zero hardcoded thresholds in engine logic — everything references this file.
"""
from __future__ import annotations

# ── Price Clustering ─────────────────────────────────────────────
CLUSTER_LOOKBACK = 63                    # trading days
CLUSTER_CORR_THRESHOLD = 0.60            # min Pearson for graph edge
CLUSTER_DTW_THRESHOLD = 0.03             # max DTW distance for strong edge
CLUSTER_MIN_SIZE = 3                     # min tickers per cluster
CLUSTER_BENCHMARK = "SPY"                # RS benchmark

# ── News NLP ──────────────────────────────────────────────────────
NEWS_MAX_PER_TICKER = 8                  # Yahoo RSS items per ticker
NEWS_MAX_THEME_ITEMS = 12                # Google News items per query
NEWS_BATCH_SIZE = 20                     # Yahoo RSS tickers per request
NEWS_NLP_MODE = "transformers"           # "transformers" or "lightweight"
NEWS_USE_FINBERT = True                  # ProsusAI/finbert sentiment
NEWS_USE_ZEROSHOT = True               # facebook/bart-large-mnli classification
NEWS_SUPPLY_KEYWORDS = [                 # auto-detected supply chain signals
    "shortage", "constrained supply", "sole source", "only supplier",
    "limited suppliers", "capacity constrained", "lead time extended",
    "bottleneck", "tight supply", "supply crunch", "backlog",
    "order backlog", "demand exceeds supply", "unable to meet demand",
]

# ── EDGAR Scraping ──────────────────────────────────────────────
EDGAR_RATE_LIMIT_SEC = 0.15            # seconds between requests (SEC polite limit)
EDGAR_MAX_TICKERS_PER_RUN = 20         # cap to avoid long runs
EDGAR_TEXT_LIMIT = 8000                # chars per Item extracted
EDGAR_CONSTRAINT_SCORE_THRESHOLD = 0.50 # min to flag as bottleneck candidate

# ── Supply Chain Graph ──────────────────────────────────────────
GRAPH_MIN_NODES = 3                    # min nodes to run centrality
GRAPH_CENTRALITY_METHODS = ["betweenness", "eigenvector", "degree"]
GRAPH_CHOKEPOINT_BETWEENNESS = 0.15    # min betweenness for chokepoint flag
GRAPH_CHOKEPOINT_ALT_PATHS = 3         # max alternative paths for chokepoint

# ── Leading Indicators ──────────────────────────────────────────
LI_MIN_HISTORY = 30                    # min snapshots to train
LI_FEATURES_Q1 = ["ism_norm", "payrolls_roc", "cpi_roc", "breakeven_delta", "dxy_inv_1m", "vix", "proxy_share"]
LI_FEATURES_Q2 = ["oil_3m", "ppi_yoy", "breakeven_5y", "indpro_roc", "retail_roc", "dxy_inv_1m"]
LI_FEATURES_Q3 = ["claims_delta", "unrate_delta", "ism_delta", "cpi_roc", "oil_3m", "vix", "proxy_share"]
LI_FEATURES_Q4 = ["claims_delta", "housing_yoy", "tlt_1m", "dxy_1m", "vix", "credit_spread_proxy"]
LI_MODEL_ESTIMATORS = 100
LI_MODEL_MAX_DEPTH = 3

# ── Regime Predictor ────────────────────────────────────────────
RP_MIN_TRANSITIONS = 20                # min recorded transitions to train classifier
RP_ENSEMBLE_MAX_WEIGHT = 0.60          # max weight to model (rest is base rate)
RP_FEATURE_KEYS = ["growth_momentum", "inflation_momentum", "policy_score",
                   "growth_level", "inflation_level", "oil_3m", "vix", "dxy_1m"]
RP_CLASSIFIER_ESTIMATORS = 150
RP_CLASSIFIER_MAX_DEPTH = 4

# ── Auto Discovery ────────────────────────────────────────────────
DISCOVERY_MIN_CLUSTER_CONFIDENCE = 0.55
DISCOVERY_MIN_NEWS_MENTIONS = 3
DISCOVERY_MIN_SUPPLY_HITS = 2
DISCOVERY_MAX_CANDIDATES = 50          # cap output to prevent UI overload

# ── Feedback Loop ─────────────────────────────────────────────────
FB_EVALUATION_WINDOW_DAYS = 180        # 6 months
FB_PROMOTE_THRESHOLD = 0.10            # vs benchmark outperformance
FB_DEMOTE_THRESHOLD = -0.10            # absolute underperformance
FB_DB_PATH = ".cache/autonomy_feedback_db.json"

# ── Integration ─────────────────────────────────────────────────
AUTONOMY_ENABLED = True
AUTONOMY_RUN_EDGAR = True              # set False if SEC blocks / too slow
AUTONOMY_USE_TRANSFORMERS = True       # set False for lightweight mode (no GPU)
