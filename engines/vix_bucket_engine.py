"""vix_bucket_engine.py - Hedgeye VIX Bucket Position Sizing v39
Exact: 9-19 Investable, 20-29 Chop, 29+ F*ck
"""

def classify_vix_bucket(vix):
    if vix < 9:
        return {"bucket": "INVESTABLE", "label": "Low Vol — Aggressive", "multiplier": 1.2}
    elif vix < 19:
        return {"bucket": "INVESTABLE", "label": "Investable — Normal", "multiplier": 1.0}
    elif vix < 29:
        return {"bucket": "CHOP", "label": "Chop — Reduce Size", "multiplier": 0.5}
    else:
        return {"bucket": "FUCK", "label": "F*ck Bucket — 10% Max", "multiplier": 0.1}

def apply_vix_position_sizing(vix_bucket, base_size):
    return base_size * vix_bucket.get("multiplier", 1.0)
