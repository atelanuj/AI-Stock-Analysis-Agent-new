from datetime import datetime, timezone
from app.agent.client import synthesize
from app.cache.redis_cache import get_json, set_json
from app.db.database import save_analysis
from app.tools.fundamentals import get_fundamentals
from app.tools.market_data import get_market_data
from app.tools.news import get_news
from app.tools.scoring import composite_score, fundamental_score, risk_score, technical_score, valuation_score
from app.tools.technical import get_technical

def _rating(score: float) -> str:
    if score >= 82: return "STRONG BUY"
    if score >= 72: return "BUY"
    if score >= 62: return "ACCUMULATE"
    if score >= 48: return "HOLD"
    if score >= 38: return "REDUCE"
    return "SELL"

def analyze_stock(symbol: str, force_refresh: bool = False, use_ai: bool = True, market: str | None = None) -> dict:
    symbol = symbol.strip().upper()
    cache_key = f"analysis:v4:{(market or 'AUTO').upper()}:{symbol}:{'ai' if use_ai else 'det'}"
    if not force_refresh:
        cached = get_json(cache_key)
        if cached:
            cached["cache"] = "hit"
            return cached

    market_data = get_market_data(symbol, market)
    fundamentals = get_fundamentals(symbol, market)
    technical = get_technical(symbol, market, include_pattern_backtest=use_ai)
    news = get_news(symbol, market) if use_ai else []
    scores = {
        "fundamental": fundamental_score(fundamentals),
        "technical": technical_score(technical),
        "valuation": valuation_score(fundamentals),
        "risk": risk_score(fundamentals, market_data),
    }
    scores["overall"] = composite_score(scores)
    deterministic_rating = _rating(scores["overall"])
    evidence = {"symbol": symbol, "market": market_data, "fundamentals": fundamentals, "technical": technical, "news": news,
                "scores": scores, "deterministic_rating": deterministic_rating}

    if use_ai:
        try:
            ai = synthesize(evidence)
        except Exception as exc:
            ai = {"rating": deterministic_rating, "confidence": "low",
                  "thesis": "AI synthesis unavailable; deterministic scores are shown.", "positives": [],
                  "risks": [f"AI synthesis error: {str(exc)[:180]}"], "catalysts": [], "what_to_watch": []}
    else:
        ai = {"rating": deterministic_rating, "confidence": "not_applicable",
              "thesis": "AI synthesis disabled for screening.", "positives": [], "risks": [], "catalysts": [], "what_to_watch": []}

    result = {"symbol": symbol, "company_name": market_data["company_name"], "as_of": datetime.now(timezone.utc).isoformat(),
              "scores": scores, "deterministic_rating": deterministic_rating, "ai_analysis": ai, "evidence": evidence,
              "cache": "miss", "disclaimer": "Research/education only. Validate market data before making investment decisions."}
    set_json(cache_key, result)
    if use_ai:
        save_analysis(symbol, scores["overall"], ai.get("rating", deterministic_rating), result)
    return result
