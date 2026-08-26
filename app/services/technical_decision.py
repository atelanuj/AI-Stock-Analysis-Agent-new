from __future__ import annotations

from copy import deepcopy

from app.agent.client import synthesize_technical_decision
from app.cache.redis_cache import get_json, set_json
from app.config import settings
from app.services.analysis import analyze_stock_core

_HORIZONS = {"1D", "1W", "1M", "3M", "6M", "1Y"}
_WEIGHTS = {"1D": 0.08, "1W": 0.12, "1M": 0.18, "3M": 0.22, "6M": 0.18, "1Y": 0.22}


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


def build_technical_decision(technical: dict, horizon: str) -> dict:
    horizon = horizon.upper()
    if horizon not in _HORIZONS:
        raise ValueError("horizon must be one of 1D, 1W, 1M, 3M, 6M, 1Y")

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
            "All six technical horizons (1D, 1W, 1M, 3M, 6M, 1Y)",
            "Selected-horizon signal agreement and price structure",
            "RSI, MACD, VWAP, ATR, ADX and relative volume",
            "Breakout/breakdown state and dynamic support/resistance zones",
            "Relative strength versus NIFTY 50 or S&P 500",
            "Recent candlestick-pattern direction and strength",
        ],
    }


def get_technical_ai_decision(symbol: str, market: str = "IN", horizon: str = "1M", force_refresh: bool = False) -> dict:
    symbol = symbol.strip().upper(); market = market.upper(); horizon = horizon.upper()
    key = f"analysis:v7:technical-decision:{market}:{symbol}:{horizon}"
    if not force_refresh:
        cached = get_json(key)
        if cached:
            cached["cache"] = "hit"
            return cached

    core = analyze_stock_core(symbol, market=market, force_refresh=force_refresh)
    technical = core["evidence"]["technical"]
    deterministic = build_technical_decision(technical, horizon)

    payload = {
        "symbol": symbol,
        "market": market,
        "horizon": horizon,
        "technical_evidence": {
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
    }

    try:
        ai = synthesize_technical_decision(payload)
    except Exception as exc:
        ai = {
            "recommendation": deterministic["deterministic_recommendation"],
            "confidence": "low",
            "summary": "AI technical synthesis was unavailable; the deterministic technical recommendation is shown.",
            "confirming_signals": [],
            "conflicting_signals": [f"AI synthesis error: {str(exc)[:180]}"],
        }

    ai_recommendation = str(ai.get("recommendation", deterministic["deterministic_recommendation"])).upper()
    if ai_recommendation not in {"BUY", "HOLD", "SELL"}:
        ai_recommendation = deterministic["deterministic_recommendation"]

    # A directional BUY/SELL requires agreement between the deterministic
    # technical scaffold and the model synthesis. Conflicts are deliberately
    # downgraded to HOLD rather than pretending the evidence is conclusive.
    deterministic_recommendation = deterministic["deterministic_recommendation"]
    recommendation = ai_recommendation if ai_recommendation == deterministic_recommendation else "HOLD"

    # Numeric target/risk levels are always produced by deterministic
    # price-structure logic after the consensus recommendation is known. The
    # model is never allowed to invent or alter prices.
    setup = _target_and_risk(technical, horizon, recommendation)
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
        "cache": "miss",
        "disclaimer": "Technical research only. BUY/HOLD/SELL is not personalized financial advice. Target zones and risk-control levels are model-derived estimates, never confirmed future prices.",
    }
    set_json(key, result, ttl=settings.ai_cache_ttl_seconds)
    return result
