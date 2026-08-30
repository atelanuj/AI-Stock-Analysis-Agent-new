from __future__ import annotations

import math
from statistics import median

import pandas as pd

from app.agent.client import synthesize_candle_prediction
from app.cache.redis_cache import get_json, set_json
from app.config import settings
from app.tools.technical import get_ohlcv_history, predict_next_candle


def _finite(value) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _fallback(rows: list[dict], interval: str) -> dict | None:
    prediction = predict_next_candle(rows, interval)
    if not prediction:
        return None
    result = dict(prediction)
    result["source"] = "historical_pattern_fallback"
    result["rationale"] = result.get("note") or "Closest historical candle-shape analogs."
    return result


def _linear_fit(values: list[float]) -> tuple[float, float, float]:
    count = len(values)
    x_mean = (count - 1) / 2
    y_mean = sum(values) / count
    denominator = sum((index - x_mean) ** 2 for index in range(count)) or 1
    slope = sum((index - x_mean) * (value - y_mean) for index, value in enumerate(values)) / denominator
    intercept = y_mean - slope * x_mean
    total = sum((value - y_mean) ** 2 for value in values)
    residual = sum((value - (intercept + slope * index)) ** 2 for index, value in enumerate(values))
    r_squared = 1 - residual / total if total > 0 else 1
    return slope, intercept, max(0.0, min(1.0, r_squared))


def _swing_points(values: list[float], peaks: bool) -> list[tuple[int, float]]:
    points = []
    for index in range(2, len(values) - 2):
        window = values[index - 2:index + 3]
        if (peaks and values[index] == max(window)) or (not peaks and values[index] == min(window)):
            points.append((index, values[index]))
    return points


def detect_chart_patterns(rows: list[dict], window: int = 40) -> list[dict]:
    clean = [row for row in rows if all(_finite(row.get(name)) is not None for name in ("high", "low", "close"))]
    if len(clean) < 15:
        return []
    sample = clean[-min(window, len(clean)):]
    highs, lows, closes = ([float(row[name]) for row in sample] for name in ("high", "low", "close"))
    upper_slope, upper_intercept, upper_r2 = _linear_fit(highs)
    lower_slope, lower_intercept, lower_r2 = _linear_fit(lows)
    price = closes[-1] or 1
    upper_rate, lower_rate = upper_slope / price, lower_slope / price
    flat, directional = 0.00045, 0.0006
    first_width = max(upper_intercept - lower_intercept, price * 0.001)
    last_upper = upper_intercept + upper_slope * (len(sample) - 1)
    last_lower = lower_intercept + lower_slope * (len(sample) - 1)
    last_width = max(last_upper - last_lower, 0)
    compression = max(0.0, min(1.0, 1 - last_width / first_width))
    confidence = round(min(88, 52 + 14 * ((upper_r2 + lower_r2) / 2) + 18 * compression), 1)
    candidates = []

    def add(name: str, bias: str, note: str, score: float = confidence):
        candidates.append({"name": name, "bias": bias, "confidence_pct": round(min(90, max(35, score)), 1), "start_date": sample[0]["date"], "end_date": sample[-1]["date"], "upper_start": round(upper_intercept, 4), "upper_end": round(last_upper, 4), "lower_start": round(lower_intercept, 4), "lower_end": round(last_lower, 4), "note": note})

    if abs(upper_rate) < flat and lower_rate > directional:
        add("Ascending Triangle", "BULLISH", "Flat resistance with rising support.")
    elif abs(lower_rate) < flat and upper_rate < -directional:
        add("Descending Triangle", "BEARISH", "Flat support with falling resistance.")
    elif upper_rate < -directional and lower_rate > directional:
        add("Symmetrical Triangle", "NEUTRAL", "Converging support and resistance; breakout direction needs confirmation.")
    elif upper_rate > directional and lower_rate > directional:
        if lower_rate - upper_rate > flat:
            add("Rising Wedge", "BEARISH", "Both boundaries rise while the range contracts.")
        else:
            add("Channel Up", "BULLISH", "Price boundaries are rising in a broadly parallel channel.")
    elif upper_rate < -directional and lower_rate < -directional:
        if lower_rate - upper_rate > flat:
            add("Falling Wedge", "BULLISH", "Both boundaries fall while the range contracts.")
        else:
            add("Channel Down", "BEARISH", "Price boundaries are falling in a broadly parallel channel.")
    elif abs(upper_rate) < flat and abs(lower_rate) < flat:
        add("Rectangle", "NEUTRAL", "Price is contained between broadly horizontal boundaries.")

    peaks, troughs = _swing_points(highs, True), _swing_points(lows, False)
    if len(peaks) >= 2:
        left, right = peaks[-2], peaks[-1]
        between = min(lows[left[0]:right[0] + 1]) if right[0] > left[0] else price
        if right[0] - left[0] >= 4 and abs(left[1] / right[1] - 1) <= 0.018 and between < min(left[1], right[1]) * 0.985:
            add("Double Top", "BEARISH", "Two similar swing highs are separated by a meaningful pullback.", 72)
    if len(troughs) >= 2:
        left, right = troughs[-2], troughs[-1]
        between = max(highs[left[0]:right[0] + 1]) if right[0] > left[0] else price
        if right[0] - left[0] >= 4 and abs(left[1] / right[1] - 1) <= 0.018 and between > max(left[1], right[1]) * 1.015:
            add("Double Bottom", "BULLISH", "Two similar swing lows are separated by a meaningful rebound.", 72)
    if len(peaks) >= 3:
        left, head, right = peaks[-3:]
        if head[1] > max(left[1], right[1]) * 1.012 and abs(left[1] / right[1] - 1) <= 0.025:
            add("Head and Shoulders", "BEARISH", "A higher central peak sits between two similar shoulders.", 76)
    if len(troughs) >= 3:
        left, head, right = troughs[-3:]
        if head[1] < min(left[1], right[1]) * 0.988 and abs(left[1] / right[1] - 1) <= 0.025:
            add("Inverse Head and Shoulders", "BULLISH", "A lower central trough sits between two similar shoulders.", 76)
    unique = {item["name"]: item for item in candidates}
    return sorted(unique.values(), key=lambda item: item["confidence_pct"], reverse=True)[:3]


def _future_dates(first_date: str, rows: list[dict], interval: str, count: int) -> list[str]:
    first = pd.Timestamp(first_date)
    dates = [first]
    if interval == "1d":
        for _ in range(1, count):
            dates.append(dates[-1] + pd.offsets.BusinessDay(1))
    else:
        timestamps = pd.to_datetime([row.get("date") for row in rows[-20:]], errors="coerce")
        series = pd.Series(timestamps).dropna().sort_values()
        deltas = series.diff().dropna()
        deltas = deltas[deltas > pd.Timedelta(0)]
        step = deltas.median() if not deltas.empty else pd.Timedelta(minutes=5)
        for _ in range(1, count):
            dates.append(dates[-1] + step)
    return [value.isoformat() if interval != "1d" else value.strftime("%Y-%m-%d") for value in dates]


def _validated_ai_candle(ai: dict, rows: list[dict], fallback: dict | None, interval: str, patterns: list[dict]) -> dict | None:
    if not rows or not fallback or not fallback.get("date"):
        return None
    latest_close = _finite(rows[-1].get("close"))
    if latest_close is None or latest_close <= 0:
        return None
    ranges = [float(row["high"]) - float(row["low"]) for row in rows[-14:] if _finite(row.get("high")) is not None and _finite(row.get("low")) is not None and float(row["high"]) >= float(row["low"])]
    typical_range = median(ranges) if ranges else latest_close * 0.01
    limit = min(latest_close * 0.08, max(typical_range * 3, latest_close * 0.015))
    minimum, maximum = latest_close - limit, latest_close + limit
    values = [_finite(ai.get(name)) for name in ("open", "high", "low", "close")]
    if any(value is None or value <= 0 or value < minimum or value > maximum for value in values):
        return None
    open_price, high, low, close = values
    if high < max(open_price, close) or low > min(open_price, close) or high <= low:
        return None
    confidence = _finite(ai.get("confidence_pct"))
    confidence = round(min(85.0, max(20.0, confidence if confidence is not None else 50.0)), 1)
    body_pct = abs(close / open_price - 1) * 100 if open_price else 0
    direction = "NEUTRAL" if body_pct < 0.05 else "BULLISH" if close > open_price else "BEARISH"
    raw_future = ai.get("future_closes")
    if not isinstance(raw_future, list) or not 3 <= len(raw_future) <= 8:
        return None
    future_values = [_finite(value) for value in raw_future]
    if any(value is None or value <= 0 for value in future_values):
        return None
    future_values[0] = close
    for index, value in enumerate(future_values):
        future_limit = min(latest_close * 0.15, limit * (1 + 0.45 * index))
        if abs(value - latest_close) > future_limit or (index and abs(value - future_values[index - 1]) > limit * 1.25):
            return None
    dates = _future_dates(fallback["date"], rows, interval, len(future_values))
    future_trend = [{"date": date, "price": round(value, 4)} for date, value in zip(dates, future_values)]
    trend_move = (future_values[-1] / latest_close - 1) * 100
    trend_bias = "BULLISH" if trend_move > 0.25 else "BEARISH" if trend_move < -0.25 else "SIDEWAYS"
    pattern_names = {item["name"] for item in patterns}
    selected_pattern = str(ai.get("chart_pattern") or "NONE")
    if selected_pattern not in pattern_names:
        selected_pattern = patterns[0]["name"] if patterns else "NONE"
    result = {
        "date": fallback["date"],
        "open": round(open_price, 4),
        "high": round(high, 4),
        "low": round(low, 4),
        "close": round(close, 4),
        "direction": direction,
        "confidence_pct": confidence,
        "source": "ai_generated",
        "rationale": str(ai.get("rationale") or "AI-generated scenario from recent candle evidence.")[:300],
        "note": "AI-generated next-candle scenario; not a guaranteed price forecast.",
        "interval": interval,
        "future_trend": future_trend,
        "trend_bias": trend_bias,
        "selected_pattern": selected_pattern,
    }
    return result


def get_ai_candle_prediction(symbol: str, market: str = "IN", period: str = "3mo", interval: str = "1d", force_refresh: bool = False) -> dict:
    symbol, market = symbol.upper(), market.upper()
    key = f"candle-ai:v2:{market}:{symbol}:{period}:{interval}"
    if not force_refresh:
        cached = get_json(key)
        if cached:
            cached["cache"] = "hit"
            return cached
    rows = get_ohlcv_history(symbol, market, period, interval)
    prediction_rows = rows
    if interval == "1d" and len(rows) < 30:
        prediction_rows = get_ohlcv_history(symbol, market, "1y", "1d")
    fallback = _fallback(prediction_rows, interval)
    patterns = detect_chart_patterns(prediction_rows)
    if not fallback:
        return {"symbol": symbol, "market": market, "ai_available": False, "prediction": None, "patterns": patterns, "error": "Insufficient candle history for a validated forecast.", "cache": "miss"}
    latest_close = float(prediction_rows[-1]["close"])
    recent = [{name: row.get(name) for name in ("date", "open", "high", "low", "close", "volume")} for row in prediction_rows[-20:]]
    ranges = [float(row["high"]) - float(row["low"]) for row in prediction_rows[-14:] if _finite(row.get("high")) is not None and _finite(row.get("low")) is not None and float(row["high"]) >= float(row["low"])]
    typical_range = median(ranges) if ranges else latest_close * 0.01
    limit = min(latest_close * 0.08, max(typical_range * 3, latest_close * 0.015))
    payload = {"symbol": symbol, "market": market, "period": period, "interval": interval, "latest_close": latest_close, "min_price": round(latest_close - limit, 4), "max_price": round(latest_close + limit, 4), "recent_candles": recent, "historical_pattern_projection": fallback, "detected_pattern_candidates": [{"name": item["name"], "bias": item["bias"], "confidence_pct": item["confidence_pct"], "note": item["note"]} for item in patterns]}
    try:
        ai = synthesize_candle_prediction(payload)
        prediction = _validated_ai_candle(ai, prediction_rows, fallback, interval, patterns)
        if prediction is None:
            raise ValueError("AI returned an invalid or out-of-bounds candle")
        result = {"symbol": symbol, "market": market, "ai_available": True, "prediction": prediction, "patterns": patterns, "selected_pattern": prediction["selected_pattern"], "future_trend": prediction["future_trend"], "trend_bias": prediction["trend_bias"], "cache": "miss"}
    except Exception as exc:
        result = {"symbol": symbol, "market": market, "ai_available": False, "prediction": fallback, "patterns": patterns, "selected_pattern": patterns[0]["name"] if patterns else "NONE", "future_trend": [], "trend_bias": "UNAVAILABLE", "error": str(exc)[:180], "cache": "miss"}
    set_json(key, result, ttl=settings.ai_cache_ttl_seconds)
    return result
