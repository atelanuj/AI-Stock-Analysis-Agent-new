from __future__ import annotations

import hashlib
import json

from app.agent.client import synthesize_final_stock_decision
from app.cache.redis_cache import get_json, set_json
from app.config import settings


def _clean_list(value, limit: int = 4) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip()[:220] for item in value if str(item).strip()][:limit]


def get_final_stock_decision(payload: dict, force_refresh: bool = False) -> dict:
    symbol = str(payload.get("symbol") or "").strip().upper()
    market = str(payload.get("market") or "IN").upper()
    horizon = str(payload.get("horizon") or "3M").upper()
    evidence_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    key = f"analysis:v1:final-ai-decision:{market}:{symbol}:{horizon}:{evidence_hash}"
    if not force_refresh:
        cached = get_json(key)
        if cached:
            cached["cache"] = "hit"
            return cached

    ai_available = True
    error = None
    try:
        ai = synthesize_final_stock_decision(payload)
    except Exception as exc:
        ai_available = False
        error = str(exc)[:180]
        technical = str((payload.get("technical_decision") or {}).get("recommendation") or "").upper()
        rating = str((payload.get("stock_synthesis") or {}).get("rating") or "").upper()
        rating_decision = "BUY" if rating in {"STRONG BUY", "BUY", "ACCUMULATE"} else "SELL" if rating in {"SELL", "REDUCE"} else "HOLD"
        decision = technical if technical in {"BUY", "HOLD", "SELL"} else rating_decision
        if technical in {"BUY", "SELL"} and rating_decision in {"BUY", "SELL"} and technical != rating_decision:
            decision = "HOLD"
        ai = {
            "decision": decision,
            "confidence": "low",
            "summary": "The final AI synthesis timed out; the conservative evidence-based classification is shown.",
            "key_drivers": [f"Technical decision: {technical or 'unavailable'}", f"Stock synthesis: {rating or 'unavailable'}"],
            "key_risks": [f"AI synthesis unavailable: {error}"],
        }
    decision = str(ai.get("decision") or "HOLD").upper()
    if decision not in {"BUY", "HOLD", "SELL"}:
        decision = "HOLD"
    confidence = str(ai.get("confidence") or "low").lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = "low"
    result = {
        "symbol": symbol,
        "market": market,
        "horizon": horizon,
        "decision": decision,
        "confidence": confidence,
        "summary": str(ai.get("summary") or "Evidence is mixed; wait for a clearer setup.")[:700],
        "key_drivers": _clean_list(ai.get("key_drivers")),
        "key_risks": _clean_list(ai.get("key_risks")),
        "source": "nemotron_all_evidence" if ai_available else "deterministic_evidence_fallback",
        "ai_available": ai_available,
        "error": error,
        "cache": "miss",
        "disclaimer": "AI research classification only, not personalized investment advice. Market conditions can invalidate the decision, target, stop-loss and candle projection.",
    }
    set_json(key, result, ttl=settings.ai_cache_ttl_seconds)
    return result
