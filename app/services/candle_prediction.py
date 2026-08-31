from __future__ import annotations

import math
from statistics import median

import pandas as pd

from app.agent.client import synthesize_candle_prediction
from app.cache.redis_cache import get_json, set_json
from app.config import settings
from app.tools.technical import get_ohlcv_history, predict_next_candle


SUPPORTED_CHART_PATTERNS = (
    "Ascending Triangle",
    "Descending Triangle",
    "Symmetrical Triangle",
    "Expanding Triangle",
    "Rising Wedge",
    "Falling Wedge",
    "Channel Up",
    "Channel Down",
    "Rectangle",
    "Double Top",
    "Double Bottom",
    "Triple Top",
    "Triple Bottom",
    "Head and Shoulders",
    "Inverse Head and Shoulders",
    "Bull Flag",
    "Bear Flag",
    "Bull Pennant",
    "Bear Pennant",
    "Cup and Handle",
    "Inverse Cup and Handle",
    "Rounding Bottom",
    "Rounding Top",
)


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

    def add(
        name: str,
        bias: str,
        note: str,
        score: float = confidence,
        structure: tuple[float, float, float, float] | None = None,
        dates: tuple[str, str] | None = None,
    ):
        line = structure or (upper_intercept, last_upper, lower_intercept, last_lower)
        span = dates or (sample[0]["date"], sample[-1]["date"])
        candidates.append({
            "name": name,
            "bias": bias,
            "confidence_pct": round(min(90, max(35, score)), 1),
            "start_date": span[0],
            "end_date": span[1],
            "upper_start": round(line[0], 4),
            "upper_end": round(line[1], 4),
            "lower_start": round(line[2], 4),
            "lower_end": round(line[3], 4),
            "note": note,
        })

    if abs(upper_rate) < flat and lower_rate > directional:
        add("Ascending Triangle", "BULLISH", "Flat resistance with rising support.")
    elif abs(lower_rate) < flat and upper_rate < -directional:
        add("Descending Triangle", "BEARISH", "Flat support with falling resistance.")
    elif upper_rate < -directional and lower_rate > directional:
        recent_move = closes[-1] / closes[max(0, len(closes) // 3)] - 1
        bias = "BULLISH" if recent_move > 0.015 else "BEARISH" if recent_move < -0.015 else "NEUTRAL"
        add("Symmetrical Triangle", bias, "Converging support and resistance; breakout direction still needs price confirmation.")
    elif upper_rate > directional and lower_rate < -directional and last_width > first_width * 1.12:
        midpoint_slope = (upper_slope + lower_slope) / 2
        bias = "BULLISH" if midpoint_slope > price * flat else "BEARISH" if midpoint_slope < -price * flat else "NEUTRAL"
        add("Expanding Triangle", bias, "Support and resistance are widening into a broadening formation with elevated breakout risk.")
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
    peak_tolerance, trough_tolerance = 0.022, 0.022
    if len(peaks) >= 3:
        triple = peaks[-3:]
        values = [point[1] for point in triple]
        valleys = [min(lows[triple[index][0]:triple[index + 1][0] + 1]) for index in range(2)]
        if max(values) / min(values) - 1 <= peak_tolerance and all(valley < min(values) * 0.987 for valley in valleys):
            top = sum(values) / 3
            neckline = sum(valleys) / 2
            add("Triple Top", "BEARISH", "Three comparable swing highs formed above two intervening pullbacks.", 80, (top, top, neckline, neckline), (sample[triple[0][0]]["date"], sample[triple[-1][0]]["date"]))
    if len(troughs) >= 3:
        triple = troughs[-3:]
        values = [point[1] for point in triple]
        rebounds = [max(highs[triple[index][0]:triple[index + 1][0] + 1]) for index in range(2)]
        if max(values) / min(values) - 1 <= trough_tolerance and all(rebound > max(values) * 1.013 for rebound in rebounds):
            floor = sum(values) / 3
            neckline = sum(rebounds) / 2
            add("Triple Bottom", "BULLISH", "Three comparable swing lows formed below two intervening rebounds.", 80, (neckline, neckline, floor, floor), (sample[triple[0][0]]["date"], sample[triple[-1][0]]["date"]))
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

    # Continuation structures use a strong impulse followed by a shorter consolidation.
    tail_size = min(14, max(8, len(sample) // 3))
    impulse_size = min(10, len(sample) - tail_size)
    if impulse_size >= 5:
        tail = sample[-tail_size:]
        tail_highs = [float(row["high"]) for row in tail]
        tail_lows = [float(row["low"]) for row in tail]
        tail_upper_slope, tail_upper_intercept, tail_upper_r2 = _linear_fit(tail_highs)
        tail_lower_slope, tail_lower_intercept, tail_lower_r2 = _linear_fit(tail_lows)
        tail_upper_end = tail_upper_intercept + tail_upper_slope * (tail_size - 1)
        tail_lower_end = tail_lower_intercept + tail_lower_slope * (tail_size - 1)
        tail_lines = (tail_upper_intercept, tail_upper_end, tail_lower_intercept, tail_lower_end)
        tail_dates = (tail[0]["date"], tail[-1]["date"])
        impulse_start = closes[-tail_size - impulse_size]
        impulse_end = closes[-tail_size]
        impulse_move = impulse_end / impulse_start - 1 if impulse_start else 0
        parallel = abs(tail_upper_slope - tail_lower_slope) / price < 0.0007
        converging = tail_upper_slope / price < -directional and tail_lower_slope / price > directional
        tail_fit = (tail_upper_r2 + tail_lower_r2) / 2
        if impulse_move >= 0.025 and parallel and tail_upper_slope < 0 and tail_lower_slope < 0:
            add("Bull Flag", "BULLISH", "A strong upward impulse is followed by a compact downward-sloping channel.", 64 + 14 * tail_fit, tail_lines, tail_dates)
        elif impulse_move <= -0.025 and parallel and tail_upper_slope > 0 and tail_lower_slope > 0:
            add("Bear Flag", "BEARISH", "A strong downward impulse is followed by a compact upward-sloping channel.", 64 + 14 * tail_fit, tail_lines, tail_dates)
        if impulse_move >= 0.025 and converging:
            add("Bull Pennant", "BULLISH", "A strong upward impulse is consolidating inside converging boundaries.", 65 + 14 * tail_fit, tail_lines, tail_dates)
        elif impulse_move <= -0.025 and converging:
            add("Bear Pennant", "BEARISH", "A strong downward impulse is consolidating inside converging boundaries.", 65 + 14 * tail_fit, tail_lines, tail_dates)

    # Rounded structures are intentionally conservative: the middle third must be
    # distinctly below/above both outer thirds, with reasonably similar rims.
    third = len(closes) // 3
    if third >= 5:
        left_avg = sum(closes[:third]) / third
        middle_avg = sum(closes[third:2 * third]) / third
        right_avg = sum(closes[-third:]) / third
        rims_close = abs(left_avg / right_avg - 1) <= 0.045 if right_avg else False
        if rims_close and middle_avg < min(left_avg, right_avg) * 0.965:
            handle_pullback = max(closes[-max(3, third // 2):]) > closes[-1] * 1.008
            name = "Cup and Handle" if handle_pullback else "Rounding Bottom"
            note = "Rounded recovery returned toward the prior rim with a shallow handle pullback." if handle_pullback else "Price formed a broad rounded base and recovered toward its earlier range."
            add(name, "BULLISH", note, 67 if handle_pullback else 61)
        elif rims_close and middle_avg > max(left_avg, right_avg) * 1.035:
            handle_rebound = min(closes[-max(3, third // 2):]) < closes[-1] * 0.992
            name = "Inverse Cup and Handle" if handle_rebound else "Rounding Top"
            note = "Rounded distribution returned toward the prior floor with a shallow rebound." if handle_rebound else "Price formed a broad rounded top and weakened toward its earlier range."
            add(name, "BEARISH", note, 67 if handle_rebound else 61)
    unique = {item["name"]: item for item in candidates}
    return sorted(unique.values(), key=lambda item: item["confidence_pct"], reverse=True)[:6]


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
    key = f"candle-ai:v3:{market}:{symbol}:{period}:{interval}"
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
        return {"symbol": symbol, "market": market, "ai_available": False, "prediction": None, "patterns": patterns, "pattern_catalog": list(SUPPORTED_CHART_PATTERNS), "error": "Insufficient candle history for a validated forecast.", "cache": "miss"}
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
        result = {"symbol": symbol, "market": market, "ai_available": True, "prediction": prediction, "patterns": patterns, "pattern_catalog": list(SUPPORTED_CHART_PATTERNS), "selected_pattern": prediction["selected_pattern"], "future_trend": prediction["future_trend"], "trend_bias": prediction["trend_bias"], "cache": "miss"}
    except Exception as exc:
        result = {"symbol": symbol, "market": market, "ai_available": False, "prediction": fallback, "patterns": patterns, "pattern_catalog": list(SUPPORTED_CHART_PATTERNS), "selected_pattern": patterns[0]["name"] if patterns else "NONE", "future_trend": [], "trend_bias": "UNAVAILABLE", "error": str(exc)[:180], "cache": "miss"}
    set_json(key, result, ttl=settings.ai_cache_ttl_seconds)
    return result
