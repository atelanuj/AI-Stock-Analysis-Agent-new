from __future__ import annotations

from copy import deepcopy
import math

from app.agent.client import synthesize_technical_decision
from app.cache.redis_cache import get_json, set_json
from app.config import settings
from app.db.database import save_technical_recommendation
from app.services.analysis import analyze_stock_core

_HORIZONS = {"1D", "1W", "1M", "3M", "6M", "1Y", "3Y", "5Y"}
_WEIGHTS = {"1D": 0.05, "1W": 0.08, "1M": 0.12, "3M": 0.16, "6M": 0.14, "1Y": 0.17, "3Y": 0.14, "5Y": 0.14}


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _bias_value(bias: str) -> int:
    return 1 if bias == "BULLISH" else -1 if bias == "BEARISH" else 0


def _target_and_risk(technical: dict, horizon: str, recommendation: str) -> dict:
    item = technical.get("timeline_biases", {}).get(horizon, {})
    rr = item.get("risk_reward", {}) or {}
    levels = item.get("levels", {}) or {}
    price = float(technical.get("price") or 0)
    atr = float(technical.get("atr14") or (price * 0.02 if price else 0))
    ns = levels.get("nearest_support") or levels.get("major_support") or {}
    nr = levels.get("nearest_resistance") or levels.get("major_resistance") or {}
    ms = levels.get("major_support") or ns
    mr = levels.get("major_resistance") or nr

    direction = "BEARISH" if recommendation == "SELL" else "BULLISH"
    if recommendation == "HOLD":
        selected_bias = item.get("directional_bias", "NEUTRAL")
        alignment = technical.get("trend_alignment", {}).get("dominant", "MIXED")
        direction = "BEARISH" if selected_bias == "BEARISH" or alignment == "BEARISH" else "BULLISH"

    if direction == "BEARISH":
        base_target = rr.get("target_reference")
        if base_target is None or float(base_target) >= price:
            base_target = (ns or ms).get("center") if (ns or ms) else price - 2 * atr
        target_mid = float(base_target)
        target_low = min(target_mid, float((ms or ns).get("low", target_mid - 0.35 * atr)))
        target_high = max(target_mid, float((ns or ms).get("high", target_mid + 0.25 * atr)))
        invalidation = rr.get("invalidation_level")
        if invalidation is None or float(invalidation) <= price:
            invalidation = float((nr or mr).get("high", price + 1.2 * atr))
        stop_reference = float(invalidation) + 0.15 * atr
        reward = max(0.0, price - target_mid)
        risk = max(0.0, stop_reference - price)
    else:
        base_target = rr.get("target_reference")
        if base_target is None or float(base_target) <= price:
            base_target = (nr or mr).get("center") if (nr or mr) else price + 2 * atr
        target_mid = float(base_target)
        target_low = min(target_mid, float((nr or mr).get("low", target_mid - 0.25 * atr)))
        target_high = max(target_mid, float((mr or nr).get("high", target_mid + 0.35 * atr)))
        invalidation = rr.get("invalidation_level")
        if invalidation is None or float(invalidation) >= price:
            invalidation = float((ns or ms).get("low", price - 1.2 * atr))
        stop_reference = float(invalidation) - 0.15 * atr
        reward = max(0.0, target_mid - price)
        risk = max(0.0, price - stop_reference)

    ratio = reward / risk if risk > 0 else None
    return {
        "entry_reference": round(price, 4),
        "target_zone": {"low": round(target_low, 4), "high": round(target_high, 4), "mid": round(target_mid, 4)},
        "risk_control_level": round(stop_reference, 4),
        "invalidation_level": round(float(invalidation), 4),
        "potential_reward_pct": round(reward / price * 100, 2) if price else None,
        "potential_risk_pct": round(risk / price * 100, 2) if price else None,
        "risk_reward_ratio": round(ratio, 2) if ratio is not None else None,
        "setup_direction": direction,
        "note": "Target zone and risk-control level are model-derived technical references, not confirmed future prices or personalized stop-loss advice.",
    }


def _level_candidates(technical: dict, horizon: str, fallback: dict) -> list[dict]:
    """Expose audited price-structure choices for the model to select from."""
    levels = (technical.get("timeline_biases", {}).get(horizon, {}).get("levels", {}) or {})
    candidates: list[dict] = []
    seen: set[tuple[str, float]] = set()

    def add(candidate_id: str, label: str, kind: str, value) -> None:
        try:
            price = float(value)
        except (TypeError, ValueError):
            return
        if not math.isfinite(price) or price <= 0:
            return
        rounded = round(price, 4)
        marker = (kind, rounded)
        if marker in seen:
            return
        seen.add(marker)
        candidates.append({"id": candidate_id, "label": label, "kind": kind, "price": rounded})

    for level_name in ("nearest_support", "major_support", "nearest_resistance", "major_resistance"):
        zone = levels.get(level_name) or {}
        kind = "support" if "support" in level_name else "resistance"
        for bound in ("low", "center", "high"):
            add(f"{level_name}_{bound}", f"{level_name.replace('_', ' ')} {bound}", kind, zone.get(bound))

    selected = technical.get("timeline_biases", {}).get(horizon, {}) or {}
    rr = selected.get("risk_reward", {}) or {}
    add("structure_target_reference", "price-structure target reference", "target_reference", rr.get("target_reference"))
    add("structure_invalidation", "price-structure invalidation", "invalidation", rr.get("invalidation_level"))
    zone = fallback.get("target_zone", {}) or {}
    for bound in ("low", "mid", "high"):
        add(f"fallback_target_{bound}", f"fallback target {bound}", "target_reference", zone.get(bound))
    add("fallback_risk_control", "fallback risk-control level", "invalidation", fallback.get("risk_control_level"))
    return candidates


def _ai_selected_setup(technical: dict, horizon: str, ai: dict, fallback: dict) -> dict:
    """Resolve the model's candidate choices and reject inconsistent levels."""
    candidates = _level_candidates(technical, horizon, fallback)
    by_id = {item["id"]: item for item in candidates}
    target_item = by_id.get(str(ai.get("target_candidate_id") or ""))
    stop_item = by_id.get(str(ai.get("stop_candidate_id") or ""))
    direction = str(ai.get("setup_direction") or fallback.get("setup_direction") or "BULLISH").upper()
    entry = float(fallback.get("entry_reference") or technical.get("price") or 0)

    valid = direction in {"BULLISH", "BEARISH"} and target_item is not None and stop_item is not None and entry > 0
    if valid:
        target = float(target_item["price"])
        stop = float(stop_item["price"])
        valid = (direction == "BULLISH" and target > entry > stop) or (direction == "BEARISH" and target < entry < stop)

    if not valid:
        result = deepcopy(fallback)
        result["level_source"] = "deterministic_fallback"
        result["level_rationale"] = "Nemotron did not return a valid directional pair from the supplied level candidates; validated fallback levels are shown."
        return result

    reward = abs(target - entry)
    risk = abs(entry - stop)
    ratio = reward / risk if risk > 0 else None
    return {
        "entry_reference": round(entry, 4),
        "target_zone": {"low": round(target, 4), "high": round(target, 4), "mid": round(target, 4)},
        "risk_control_level": round(stop, 4),
        "invalidation_level": round(stop, 4),
        "potential_reward_pct": round(reward / entry * 100, 2),
        "potential_risk_pct": round(risk / entry * 100, 2),
        "risk_reward_ratio": round(ratio, 2) if ratio is not None else None,
        "setup_direction": direction,
        "level_source": "ai_selected",
        "target_candidate_id": target_item["id"],
        "stop_candidate_id": stop_item["id"],
        "target_candidate_label": target_item["label"],
        "stop_candidate_label": stop_item["label"],
        "level_rationale": str(ai.get("level_rationale") or "Nemotron selected these levels from validated price-structure candidates."),
        "note": "Target and stop-loss were selected by Nemotron from validated technical levels; they are estimates, not guaranteed prices or personalized advice.",
    }


def build_technical_decision(technical: dict, horizon: str) -> dict:
    horizon = horizon.upper()
    if horizon not in _HORIZONS:
        raise ValueError("horizon must be one of 1D, 1W, 1M, 3M, 6M, 1Y, 3Y, 5Y")

    timelines = technical.get("timeline_biases", {})
    selected = timelines.get(horizon, {})
    weighted_direction = 0.0
    weighted_agreement = 0.0
    for label, weight in _WEIGHTS.items():
        item = timelines.get(label, {})
        agreement = float(item.get("signal_agreement_pct") or 0) / 100.0
        weighted_direction += _bias_value(item.get("directional_bias", "NEUTRAL")) * agreement * weight
        weighted_agreement += agreement * weight

    score = 50.0 + weighted_direction * 34.0
    selected_bias = selected.get("directional_bias", "NEUTRAL")
    selected_agreement = float(selected.get("signal_agreement_pct") or 0)
    score += _bias_value(selected_bias) * max(0.0, selected_agreement - 50.0) * 0.16

    regime = technical.get("market_regime", {}) or {}
    if regime.get("regime") == "TRENDING UP": score += 6
    elif regime.get("regime") == "TRENDING DOWN": score -= 6
    if regime.get("trend_strength") == "STRONG":
        score += 2 * (1 if weighted_direction > 0 else -1 if weighted_direction < 0 else 0)

    rsi = technical.get("rsi14")
    if rsi is not None:
        rsi = float(rsi)
        if 50 <= rsi <= 68: score += 3
        elif rsi < 38: score -= 4
        elif rsi >= 75: score -= 3

    macd, signal = technical.get("macd"), technical.get("macd_signal")
    if macd is not None and signal is not None:
        score += 4 if float(macd) > float(signal) else -4

    if technical.get("above_vwap20") is True: score += 2.5
    elif technical.get("above_vwap20") is False: score -= 2.5

    volume = technical.get("volume", {}) or {}
    rel_vol = volume.get("relative_volume")
    if rel_vol is not None and float(rel_vol) >= 1.3:
        score += 2.5 * (1 if selected_bias == "BULLISH" else -1 if selected_bias == "BEARISH" else 0)

    breakout = selected.get("breakout", {}) or {}
    status = breakout.get("status", "")
    if "CONFIRMED BREAKOUT" in status: score += 7
    elif "CONFIRMED BREAKDOWN" in status: score -= 7
    elif "BREAKOUT WATCH" in status: score += 2
    elif "BREAKDOWN WATCH" in status: score -= 2

    rs = (technical.get("relative_strength", {}).get("horizons", {}).get(horizon) or {})
    rel = rs.get("relative_strength_pct")
    if rel is not None:
        score += max(-5.0, min(5.0, float(rel) * 0.8))

    for pattern in (technical.get("candlestick_patterns") or [])[:4]:
        strength = min(3, int(pattern.get("strength") or 1))
        if pattern.get("bias") == "BULLISH": score += strength * 1.2
        elif pattern.get("bias") == "BEARISH": score -= strength * 1.2

    score = round(_clamp(score), 1)
    if score >= 62 and selected_bias != "BEARISH": recommendation = "BUY"
    elif score <= 38 and selected_bias != "BULLISH": recommendation = "SELL"
    else: recommendation = "HOLD"

    setup = _target_and_risk(technical, horizon, recommendation)
    return {
        "horizon": horizon,
        "technical_score": score,
        "deterministic_recommendation": recommendation,
        "selected_bias": selected_bias,
        "selected_signal_agreement_pct": selected_agreement,
        "all_horizon_alignment": technical.get("trend_alignment", {}),
        "market_regime": regime,
        "relative_strength": rs,
        "breakout": breakout,
        "setup": setup,
        "methodology": [
            "All eight technical horizons (1D, 1W, 1M, 3M, 6M, 1Y, 3Y, 5Y)",
            "Selected-horizon signal agreement and price structure",
            "RSI, MACD, VWAP, ATR, ADX and relative volume",
            "Breakout/breakdown state and dynamic support/resistance zones",
            "Relative strength versus NIFTY 50 or S&P 500",
            "Recent candlestick-pattern direction and strength",
        ],
    }


def get_technical_ai_decision(symbol: str, market: str = "IN", horizon: str = "1M", force_refresh: bool = False) -> dict:
    symbol = symbol.strip().upper(); market = market.upper(); horizon = horizon.upper()
    key = f"analysis:v8:technical-decision:{market}:{symbol}:{horizon}"
    if not force_refresh:
        cached = get_json(key)
        if cached:
            cached["cache"] = "hit"
            return cached

    core = analyze_stock_core(symbol, market=market, force_refresh=force_refresh)
    technical = core["evidence"]["technical"]
    deterministic = build_technical_decision(technical, horizon)
    level_candidates = _level_candidates(technical, horizon, deterministic["setup"])

    payload = {
        "symbol": symbol,
        "market": market,
        "horizon": horizon,
        "technical_evidence": {
            "current_price": technical.get("price"),
            "timeline_biases": technical.get("timeline_biases", {}),
            "trend_alignment": technical.get("trend_alignment", {}),
            "market_regime": technical.get("market_regime", {}),
            "rsi14": technical.get("rsi14"),
            "macd": technical.get("macd"),
            "macd_signal": technical.get("macd_signal"),
            "atr14": technical.get("atr14"),
            "adx14": technical.get("adx14"),
            "vwap20": technical.get("vwap20"),
            "above_vwap20": technical.get("above_vwap20"),
            "volume": technical.get("volume", {}),
            "candlestick_patterns": (technical.get("candlestick_patterns") or [])[:6],
            "relative_strength": technical.get("relative_strength", {}),
        },
        "deterministic_scaffold": deterministic,
        "level_candidates": level_candidates,
    }

    ai_available = True
    try:
        ai = synthesize_technical_decision(payload)
    except Exception as exc:
        ai_available = False
        ai = {
            "recommendation": deterministic["deterministic_recommendation"],
            "confidence": "low",
            "summary": "AI technical synthesis was unavailable; the deterministic technical recommendation is shown.",
            "confirming_signals": [],
            "conflicting_signals": [f"AI synthesis error: {str(exc)[:180]}"],
            "setup_direction": deterministic["setup"]["setup_direction"],
        }

    ai_recommendation = str(ai.get("recommendation", deterministic["deterministic_recommendation"])).upper()
    if ai_recommendation not in {"BUY", "HOLD", "SELL"}:
        ai_recommendation = deterministic["deterministic_recommendation"]

    # A directional BUY/SELL requires agreement between the deterministic
    # technical scaffold and the model synthesis. Conflicts are deliberately
    # downgraded to HOLD rather than pretending the evidence is conclusive.
    deterministic_recommendation = deterministic["deterministic_recommendation"]
    recommendation = ai_recommendation if ai_recommendation == deterministic_recommendation else "HOLD"

    # Nemotron selects among audited, real price-structure candidates. Invalid
    # IDs or directionally inconsistent pairs fall back to deterministic levels.
    fallback_setup = _target_and_risk(technical, horizon, recommendation)
    setup = _ai_selected_setup(technical, horizon, ai, fallback_setup)
    result = {
        "symbol": symbol,
        "market": market,
        "horizon": horizon,
        "recommendation": recommendation,
        "ai_recommendation": ai_recommendation,
        "confidence": ai.get("confidence", "low"),
        "summary": ai.get("summary", "Technical decision generated from supplied evidence."),
        "confirming_signals": ai.get("confirming_signals", []),
        "conflicting_signals": ai.get("conflicting_signals", []),
        "technical_score": deterministic["technical_score"],
        "deterministic_recommendation": deterministic_recommendation,
        "consensus": ai_recommendation == deterministic_recommendation,
        "setup": setup,
        "methodology": deterministic["methodology"],
        "ai_available": ai_available,
        "cache": "miss",
        "disclaimer": "Technical research only. BUY/HOLD/SELL is not personalized financial advice. Nemotron selects target and stop-loss from validated technical candidates; these remain estimates, never confirmed future prices.",
    }
    set_json(key, result, ttl=settings.ai_cache_ttl_seconds)
    save_technical_recommendation(symbol, market, horizon, {**result, "ai": ai})
    return result
