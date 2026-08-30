from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone

from app.agent.client import synthesize
from app.cache.redis_cache import get_json, set_json
from app.config import settings
from app.db.database import save_analysis
from app.tools.data_provider import get_benchmark_close, get_history_df, get_info
from app.tools.events import get_corporate_events
from app.tools.fundamentals import get_fundamentals
from app.tools.market_data import detect_market, get_market_data
from app.tools.market_validation import get_validated_quote
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


def _resolved_market(symbol: str, market: str | None) -> str:
    return (market or detect_market(symbol)).upper()


def _pending_ai(det: str) -> dict:
    return {
        "rating": det,
        "confidence": "pending",
        "thesis": "AI synthesis is loading separately so market and technical data can appear first.",
        "positives": [], "risks": [], "catalysts": [], "what_to_watch": [],
    }


def analyze_stock_fast(symbol: str, market: str | None = None, force_refresh: bool = False) -> dict:
    """Return price + technical analysis without waiting for Ticker.info/Nemotron."""
    symbol = symbol.strip().upper(); resolved = _resolved_market(symbol, market)
    key = f"analysis:v6:fast:{resolved}:{symbol}"
    if not force_refresh:
        cached = get_json(key)
        if cached:
            cached["cache"] = "hit"
            return cached
    with ThreadPoolExecutor(max_workers=3) as pool:
        f_hist = pool.submit(get_history_df, symbol, resolved, "1y", "1d", False, force_refresh)
        f_bench = pool.submit(get_benchmark_close, resolved, force_refresh)
        f_quote = pool.submit(get_validated_quote, symbol, resolved, None, force_refresh)
        hist = f_hist.result(); benchmark = f_bench.result(); quote_snapshot = f_quote.result()
    market_data = get_market_data(symbol, resolved, hist=hist, info={}, quote_snapshot=quote_snapshot)
    technical = get_technical(symbol, resolved, include_pattern_backtest=False, hist=hist, benchmark_close=benchmark)
    tech_score = technical_score(technical)
    result = {
        "symbol": symbol, "company_name": symbol, "as_of": datetime.now(timezone.utc).isoformat(),
        "scores": {"overall": None, "fundamental": None, "technical": tech_score, "valuation": None, "risk": None},
        "deterministic_rating": "PENDING", "ai_analysis": _pending_ai("PENDING"),
        "evidence": {"symbol":symbol,"market":market_data,"fundamentals":{},"technical":technical,"news":[],"events":{"events":[],"loading":True},"scores":{"technical":tech_score},"deterministic_rating":"PENDING"},
        "cache":"miss", "fast":True,
        "sections":{"technical_core":"ready","fundamentals":"pending","chart":"independent","news_events":"pending","ai":"pending","backtest":"on_demand"},
        "disclaimer":"Research/education only. Technical signals are not guarantees or personalized investment advice.",
    }
    set_json(key, result, ttl=settings.market_history_cache_ttl_seconds)
    return result


def analyze_stock_core(
    symbol: str,
    force_refresh: bool = False,
    market: str | None = None,
    history_override=None,
    info_override: dict | None = None,
    validate_quote: bool = True,
) -> dict:
    """Fast deterministic stock analysis used for progressive rendering.

    V6 fetches daily history, a validated quote, fundamentals info and benchmark history in
    parallel, then reuses those objects for every deterministic calculation.
    """
    symbol = symbol.strip().upper()
    resolved = _resolved_market(symbol, market)
    cache_key = f"analysis:v6:core:{'validated' if validate_quote else 'bulk'}:{resolved}:{symbol}"
    if not force_refresh and history_override is None and info_override is None:
        cached = get_json(cache_key)
        if cached:
            cached["cache"] = "hit"
            return cached

    hist = history_override
    info = info_override
    benchmark = None
    quote_snapshot = None
    jobs = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        if hist is None:
            jobs["hist"] = pool.submit(get_history_df, symbol, resolved, "1y", "1d", False, force_refresh)
        if info is None:
            jobs["info"] = pool.submit(get_info, symbol, resolved, force_refresh)
        jobs["benchmark"] = pool.submit(get_benchmark_close, resolved, force_refresh)
        if validate_quote:
            jobs["quote"] = pool.submit(get_validated_quote, symbol, resolved, None, force_refresh)
        for name, future in jobs.items():
            value = future.result()
            if name == "hist": hist = value
            elif name == "info": info = value
            elif name == "benchmark": benchmark = value
            else: quote_snapshot = value

    market_data = get_market_data(symbol, resolved, hist=hist, info=info, quote_snapshot=quote_snapshot)
    fundamentals = get_fundamentals(symbol, resolved, info=info)
    technical = get_technical(
        symbol, resolved, include_pattern_backtest=False,
        hist=hist, benchmark_close=benchmark,
    )
    scores = {
        "fundamental": fundamental_score(fundamentals),
        "technical": technical_score(technical),
        "valuation": valuation_score(fundamentals),
        "risk": risk_score(fundamentals, market_data),
    }
    scores["overall"] = composite_score(scores)
    det = _rating(scores["overall"])
    evidence = {
        "symbol": symbol,
        "market": market_data,
        "fundamentals": fundamentals,
        "technical": technical,
        "news": [],
        "events": {"events": [], "high_impact_soon": False, "loading": True},
        "scores": scores,
        "deterministic_rating": det,
    }
    result = {
        "symbol": symbol,
        "company_name": market_data["company_name"],
        "as_of": datetime.now(timezone.utc).isoformat(),
        "scores": scores,
        "deterministic_rating": det,
        "ai_analysis": _pending_ai(det),
        "evidence": evidence,
        "cache": "miss",
        "sections": {"core": "ready", "chart": "independent", "news_events": "pending", "ai": "pending", "backtest": "on_demand"},
        "disclaimer": "Research/education only. Technical signals, backtests and event flags are not guarantees or personalized investment advice.",
    }
    if history_override is None and info_override is None:
        set_json(cache_key, result, ttl=settings.market_history_cache_ttl_seconds)
    return result


def get_stock_context(symbol: str, market: str | None = None, force_refresh: bool = False) -> dict:
    symbol = symbol.strip().upper(); resolved = _resolved_market(symbol, market)
    key = f"analysis:v6:context:{resolved}:{symbol}"
    if not force_refresh:
        cached = get_json(key)
        if cached:
            cached["cache"] = "hit"
            return cached
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_news = pool.submit(get_news, symbol, resolved, 10, force_refresh)
        f_events = pool.submit(get_corporate_events, symbol, resolved, force_refresh)
        news = f_news.result(); events = f_events.result()
    result = {"symbol": symbol, "market": resolved, "news": news, "events": events, "cache": "miss"}
    set_json(key, result, ttl=min(settings.news_cache_ttl_seconds, settings.events_cache_ttl_seconds))
    return result


def get_stock_ai(symbol: str, market: str | None = None, force_refresh: bool = False) -> dict:
    symbol = symbol.strip().upper(); resolved = _resolved_market(symbol, market)
    key = f"analysis:v6:ai:{resolved}:{symbol}"
    if not force_refresh:
        cached = get_json(key)
        if cached:
            cached["cache"] = "hit"
            return cached

    core = analyze_stock_core(symbol, force_refresh=force_refresh, market=resolved)
    context = get_stock_context(symbol, market=resolved, force_refresh=force_refresh)
    evidence = deepcopy(core["evidence"])
    evidence["news"] = context.get("news", [])
    evidence["events"] = context.get("events", {})
    det = core["deterministic_rating"]
    ai_available = True
    try:
        ai = synthesize(evidence)
    except Exception as exc:
        ai_available = False
        ai = {
            "rating": det, "confidence": "low",
            "thesis": "AI synthesis unavailable; deterministic scores are shown.",
            "positives": [], "risks": [f"AI synthesis error: {str(exc)[:180]}"],
            "catalysts": [], "what_to_watch": [],
        }
    result = {"symbol": symbol, "market": resolved, "ai_analysis": ai, "ai_available": ai_available, "cache": "miss"}
    set_json(key, result, ttl=settings.ai_cache_ttl_seconds)
    save_analysis(symbol, core["scores"]["overall"], ai.get("rating", det), {**core, "ai_analysis": ai})
    return result


def analyze_stock(
    symbol: str,
    force_refresh: bool = False,
    use_ai: bool = True,
    market: str | None = None,
    history_override=None,
    info_override: dict | None = None,
    validate_quote: bool = True,
) -> dict:
    """Compatibility aggregate endpoint.

    The browser uses the progressive core/context/AI endpoints. Existing API
    consumers can still call /analyze and receive the combined payload.
    """
    core = analyze_stock_core(
        symbol, force_refresh=force_refresh, market=market,
        history_override=history_override, info_override=info_override,
        validate_quote=validate_quote,
    )
    if not use_ai:
        return core

    context = get_stock_context(symbol, market=market, force_refresh=force_refresh)
    ai = get_stock_ai(symbol, market=market, force_refresh=force_refresh)
    result = deepcopy(core)
    result["evidence"]["news"] = context.get("news", [])
    result["evidence"]["events"] = context.get("events", {})
    result["ai_analysis"] = ai.get("ai_analysis", result["ai_analysis"])
    result["sections"].update({"news_events": "ready", "ai": "ready"})
    return result
