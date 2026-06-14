"""engines/news_nlp_engine_v3.py — News NLP Engine v3.0
Advanced news analysis: sentiment, urgency, entity extraction, theme clustering.
Uses keyword + heuristic NLP (no external API required).
"""
import logging, re
from typing import Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)

# Enhanced sentiment lexicon
SENTIMENT_LEXICON = {
    "strong_positive": ["surge", "soar", "rally", "bull", "upgrade", "beat", "strong", "growth", "breakthrough", "deal", "partnership", "record", "expansion", "launch", "approve", "buyback", "dividend", "blockbuster", "moon", "rocket", "explode", "parabolic", "outperform", "exceed", "crush", "dominate", "unstoppable"],
    "positive": ["gain", "rise", "up", "higher", "optimistic", "confident", "solid", "robust", "healthy", "improve", "recover", "bounce", "rebound", "momentum", "support", "accumulate"],
    "strong_negative": ["crash", "plunge", "bear", "downgrade", "miss", "weak", "loss", "layoff", "investigation", "fine", "delay", "recall", "debt", "bankrupt", "cut", "short", "sell", "dump", "collapse", "crisis", "disaster", "catastrophe", "implode", "plummet", "tank", "nosedive", "freefall"],
    "negative": ["fall", "drop", "down", "lower", "pessimistic", "concern", "worry", "risk", "threat", "pressure", "decline", "deteriorate", "slide", "retreat", "resistance", "distribute"],
    "uncertainty": ["volatile", "uncertain", "unclear", "mixed", "cautious", "wait", "pause", "consolidate", "range", "sideways", "indecision", "hesitant"],
}

URGENCY_KEYWORDS = ["breaking", "urgent", "alert", "just", "now", "immediate", "emergency", "critical", "warning", "flash"]

ENTITY_MAP = {
    "companies": ["apple", "microsoft", "google", "amazon", "tesla", "nvidia", "meta", "netflix", "amd", "intel", "qualcomm", "broadcom", "tsmc", "samsung", "jpmorgan", "goldman", "bank of america", "citi", "wells fargo"],
    "people": ["powell", "biden", "trump", "bezos", "musk", "cook", "nadella", "zuckerberg", "buffett", "dimon"],
    "institutions": ["fed", "federal reserve", "sec", "treasury", "imf", "world bank", "ecb", "boj", "pboc"],
    "countries": ["usa", "china", "japan", "germany", "uk", "india", "brazil", "russia", "saudi", "iran", "israel"],
}

THEME_CLUSTERS = {
    "ai": {"keywords": ["ai", "artificial intelligence", "llm", "chatgpt", "agentic", "model", "machine learning", "nvidia", "openai", "anthropic", "gemini", "claude"], "weight": 1.5},
    "semiconductor": {"keywords": ["chip", "semiconductor", "gpu", "cpu", "tsmc", "hbm", "dram", "foundry", "wafer", "asml", "lithography"], "weight": 1.3},
    "energy": {"keywords": ["oil", "gas", "energy", "solar", "renewable", "crude", "power", "grid", "transformer", "lng", "opec"], "weight": 1.2},
    "crypto": {"keywords": ["bitcoin", "crypto", "blockchain", "etf", "ethereum", "btc", "eth", "solana", "defi", "nft"], "weight": 1.2},
    "fed_rates": {"keywords": ["fed", "federal reserve", "rate cut", "rate hike", "powell", "interest rate", "fomc", "dot plot", "terminal rate"], "weight": 1.4},
    "geopolitical": {"keywords": ["war", "sanctions", "china", "taiwan", "trade", "tariff", "middle east", "ukraine", "gaza", "iran", "nato"], "weight": 1.3},
    "biotech": {"keywords": ["fda", "trial", "drug", "vaccine", "biotech", "pharma", "approval", "clinical", "molecule"], "weight": 1.1},
    "ev": {"keywords": ["ev", "electric vehicle", "tesla", "battery", "lithium", "charging", "byd", "rivian", "lucid"], "weight": 1.1},
    "earnings": {"keywords": ["earnings", "revenue", "profit", "eps", "guidance", "beat", "miss", "forecast", "quarterly"], "weight": 1.3},
    "merger": {"keywords": ["merger", "acquisition", "takeover", "deal", "buyout", "spinoff", "ipo", "listing"], "weight": 1.2},
}

class NewsNLPEngine:
    """Advanced NLP analysis for financial news."""

    def __init__(self):
        pass

    def _sentiment_score(self, text: str) -> Dict:
        text_lower = text.lower()
        scores = {"positive": 0, "negative": 0, "uncertainty": 0, "urgency": 0}
        for word in SENTIMENT_LEXICON["strong_positive"]:
            scores["positive"] += text_lower.count(word) * 2
        for word in SENTIMENT_LEXICON["positive"]:
            scores["positive"] += text_lower.count(word)
        for word in SENTIMENT_LEXICON["strong_negative"]:
            scores["negative"] += text_lower.count(word) * 2
        for word in SENTIMENT_LEXICON["negative"]:
            scores["negative"] += text_lower.count(word)
        for word in SENTIMENT_LEXICON["uncertainty"]:
            scores["uncertainty"] += text_lower.count(word)
        for word in URGENCY_KEYWORDS:
            scores["urgency"] += text_lower.count(word)
        total = scores["positive"] + scores["negative"] + scores["uncertainty"]
        if total == 0:
            return {"score": 0, "magnitude": 0, "urgency": scores["urgency"], "label": "NEUTRAL"}
        net = (scores["positive"] - scores["negative"]) / total
        magnitude = total / max(len(text.split()), 1)
        if net > 0.3:
            label = "VERY_POSITIVE" if scores["positive"] > 5 else "POSITIVE"
        elif net < -0.3:
            label = "VERY_NEGATIVE" if scores["negative"] > 5 else "NEGATIVE"
        elif scores["uncertainty"] > 3:
            label = "UNCERTAIN"
        else:
            label = "NEUTRAL"
        return {"score": round(net, 3), "magnitude": round(min(1.0, magnitude), 3), "urgency": scores["urgency"], "label": label}

    def _extract_entities(self, text: str) -> Dict[str, List[str]]:
        text_lower = text.lower()
        found = {k: [] for k in ENTITY_MAP}
        for category, entities in ENTITY_MAP.items():
            for entity in entities:
                if entity in text_lower:
                    found[category].append(entity.title())
        return {k: list(set(v))[:5] for k, v in found.items()}

    def _extract_themes(self, text: str) -> List[Dict]:
        text_lower = text.lower()
        themes = []
        for theme, config in THEME_CLUSTERS.items():
            score = sum(text_lower.count(kw) for kw in config["keywords"])
            if score > 0:
                themes.append({"theme": theme, "score": score, "weight": config["weight"], "weighted_score": round(score * config["weight"], 2)})
        return sorted(themes, key=lambda x: x["weighted_score"], reverse=True)[:3]

    def _classify_rumor(self, text: str, sentiment: Dict) -> str:
        text_lower = text.lower()
        rumor_indicators = ["reportedly", "rumor", "speculation", "considering", "exploring", "potential", "may", "might", "could", "sources say", "in talks", "approaching", "eyeing", "planning to", "expected to"]
        rumor_score = sum(1 for ri in rumor_indicators if ri in text_lower)
        if rumor_score >= 2 and sentiment["score"] > 0.2:
            return "BULLISH_RUMOR"
        elif rumor_score >= 2 and sentiment["score"] < -0.2:
            return "BEARISH_RUMOR"
        elif rumor_score >= 1:
            return "RUMOR_WATCH"
        elif sentiment["urgency"] >= 2:
            return "URGENT_NEWS"
        elif sentiment["magnitude"] > 0.5 and abs(sentiment["score"]) > 0.3:
            return "STRONG_SENTIMENT"
        return "STANDARD"

    def analyze_headlines(self, headlines: Dict[str, List[dict]]) -> Dict:
        """Analyze all headlines with advanced NLP."""
        ticker_analysis = {}
        emergent_themes = {}
        rumor_alerts = []
        urgent_alerts = []
        for ticker, items in headlines.items():
            if not items:
                continue
            ticker_sentiments = []
            ticker_themes = []
            ticker_entities = {"companies": [], "people": [], "institutions": [], "countries": []}
            for item in items:
                text = item.get("title", "")
                sent = self._sentiment_score(text)
                entities = self._extract_entities(text)
                themes = self._extract_themes(text)
                rumor_type = self._classify_rumor(text, sent)
                ticker_sentiments.append(sent)
                ticker_themes.extend(themes)
                for k, v in entities.items():
                    ticker_entities[k].extend(v)
                if rumor_type in ["BULLISH_RUMOR", "BEARISH_RUMOR"]:
                    rumor_alerts.append({"ticker": ticker, "type": rumor_type, "headline": text, "sentiment": sent["score"]})
                if sent["urgency"] >= 2:
                    urgent_alerts.append({"ticker": ticker, "headline": text, "urgency": sent["urgency"]})
            # Aggregate
            avg_sent = sum(s["score"] for s in ticker_sentiments) / len(ticker_sentiments) if ticker_sentiments else 0
            avg_mag = sum(s["magnitude"] for s in ticker_sentiments) / len(ticker_sentiments) if ticker_sentiments else 0
            total_urgency = sum(s["urgency"] for s in ticker_sentiments)
            # Theme aggregation
            theme_scores = {}
            for t in ticker_themes:
                theme_scores[t["theme"]] = theme_scores.get(t["theme"], 0) + t["weighted_score"]
            top_themes = sorted([{"theme": k, "score": round(v, 2)} for k, v in theme_scores.items()], key=lambda x: x["score"], reverse=True)[:3]
            # Determine front-run signal
            signal = None
            if avg_sent > 0.3 and avg_mag > 0.3 and total_urgency > 2:
                signal = "STRONG_BULLISH_RUMOR"
            elif avg_sent < -0.3 and avg_mag > 0.3 and total_urgency > 2:
                signal = "STRONG_BEARISH_RUMOR"
            elif any(t["theme"] in ["merger", "earnings", "ai"] for t in top_themes) and avg_mag > 0.4:
                signal = "CATALYST_BUILDING"
            elif avg_sent > 0.4:
                signal = "NEWS_MOMENTUM_BUILDING"
            elif avg_sent < -0.4:
                signal = "NEGATIVE_HEADLINE_RISK"
            ticker_analysis[ticker] = {
                "avg_sentiment": round(avg_sent, 3),
                "magnitude": round(avg_mag, 3),
                "urgency": total_urgency,
                "themes": top_themes,
                "entities": {k: list(set(v))[:5] for k, v in ticker_entities.items()},
                "headlines_analyzed": len(items),
                "front_run_signal": signal,
            }
            # Emergent themes
            for t in top_themes:
                if t["theme"] not in emergent_themes:
                    emergent_themes[t["theme"]] = {"mentions": 0, "tickers": [], "avg_sentiment": 0, "headlines": []}
                emergent_themes[t["theme"]]["mentions"] += 1
                emergent_themes[t["theme"]]["tickers"].append(ticker)
                emergent_themes[t["theme"]]["avg_sentiment"] += avg_sent
        # Normalize emergent
        for theme in emergent_themes:
            count = emergent_themes[theme]["mentions"]
            emergent_themes[theme]["avg_sentiment"] = round(emergent_themes[theme]["avg_sentiment"] / count, 2) if count > 0 else 0
            emergent_themes[theme]["tickers"] = list(set(emergent_themes[theme]["tickers"]))[:10]
        return {
            "ticker_specific": ticker_analysis,
            "emergent_narratives": [{"name": k, **v} for k, v in emergent_themes.items()],
            "rumor_watch": sorted(rumor_alerts, key=lambda x: abs(x["sentiment"]), reverse=True)[:20],
            "urgent_alerts": urgent_alerts[:10],
            "analyzed_count": sum(len(v) for v in headlines.values()),
        }


def run_news_nlp(headlines: Dict[str, List[dict]]) -> Dict:
    engine = NewsNLPEngine()
    return engine.analyze_headlines(headlines)
