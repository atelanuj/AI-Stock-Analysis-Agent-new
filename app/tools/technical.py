import math
from collections import defaultdict
from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

from app.tools.market_data import yahoo_symbol


_TIMEFRAME_CONFIG = {
    "1W": {"sessions": 5, "return_threshold": 1.2, "fast_ma": 5, "slow_ma": 20},
    "1M": {"sessions": 21, "return_threshold": 3.0, "fast_ma": 20, "slow_ma": 50},
    "3M": {"sessions": 63, "return_threshold": 6.0, "fast_ma": 20, "slow_ma": 50},
    "6M": {"sessions": 126, "return_threshold": 10.0, "fast_ma": 50, "slow_ma": 100},
    "1Y": {"sessions": 252, "return_threshold": 15.0, "fast_ma": 50, "slow_ma": 200},
}

_BENCHMARKS = {
    "IN": {"symbol": "^NSEI", "name": "NIFTY 50"},
    "US": {"symbol": "^GSPC", "name": "S&P 500"},
}


def _clean(value):
    try:
        value = float(value)
        return None if math.isnan(value) or math.isinf(value) else value
    except (TypeError, ValueError):
        return None


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(hist: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = hist["High"], hist["Low"], hist["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def _adx(hist: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = hist["High"], hist["Low"], hist["Close"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=hist.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=hist.index)
    atr = _atr(hist, period).replace(0, np.nan)
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)) * 100
    return dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def _rolling_vwap(hist: pd.DataFrame, window: int = 20) -> pd.Series:
    typical = (hist["High"] + hist["Low"] + hist["Close"]) / 3
    vol = hist.get("Volume", pd.Series(0, index=hist.index)).astype(float)
    num = (typical * vol).rolling(window).sum()
    den = vol.rolling(window).sum().replace(0, np.nan)
    return num / den


def _trend_before(close: pd.Series, index: int, lookback: int = 5) -> str:
    if index < lookback:
        return "neutral"
    start = float(close.iloc[index - lookback])
    end = float(close.iloc[index - 1])
    if start == 0:
        return "neutral"
    pct = (end / start - 1) * 100
    if pct <= -1.2:
        return "down"
    if pct >= 1.2:
        return "up"
    return "neutral"


def _candle_features(row: pd.Series) -> dict[str, float]:
    o, h, l, c = map(float, (row["Open"], row["High"], row["Low"], row["Close"]))
    rng = max(h - l, 1e-9)
    body = abs(c - o)
    upper = h - max(o, c)
    lower = min(o, c) - l
    return {
        "open": o, "high": h, "low": l, "close": c, "range": rng,
        "body": body, "upper": max(0.0, upper), "lower": max(0.0, lower),
        "bull": c > o, "bear": c < o,
    }


def detect_candlestick_patterns(hist: pd.DataFrame, lookback: int = 20, max_results: int | None = 12) -> list[dict[str, Any]]:
    """Rule-based candlestick detection. Signals are contextual hints, not forecasts."""
    if hist.empty or len(hist) < 3:
        return []
    data = hist[["Open", "High", "Low", "Close"]].dropna().copy()
    close = data["Close"]
    start = max(0, len(data) - lookback)
    found: list[dict[str, Any]] = []

    for i in range(start, len(data)):
        f = _candle_features(data.iloc[i])
        trend = _trend_before(close, i)
        date = data.index[i].strftime("%Y-%m-%d")
        body_ratio = f["body"] / f["range"]

        def add(name: str, bias: str, strength: int, note: str):
            found.append({"date": date, "pattern": name, "bias": bias, "strength": strength, "context": trend, "note": note})

        if body_ratio <= 0.10:
            add("Doji", "NEUTRAL", 1, "Indecision; direction needs confirmation from subsequent candles.")
        if f["body"] > 0 and f["lower"] >= 2 * f["body"] and f["upper"] <= 0.6 * f["body"]:
            if trend == "down": add("Hammer", "BULLISH", 2, "Potential downside rejection after a decline.")
            elif trend == "up": add("Hanging Man", "BEARISH", 2, "Potential exhaustion after an advance; confirmation required.")
        if f["body"] > 0 and f["upper"] >= 2 * f["body"] and f["lower"] <= 0.6 * f["body"]:
            if trend == "down": add("Inverted Hammer", "BULLISH", 2, "Possible reversal attempt after a decline.")
            elif trend == "up": add("Shooting Star", "BEARISH", 2, "Upper-price rejection after an advance.")
        if body_ratio >= 0.80:
            add("Bullish Marubozu" if f["bull"] else "Bearish Marubozu", "BULLISH" if f["bull"] else "BEARISH", 1, "Strong one-session directional conviction.")

        if i >= 1:
            p = _candle_features(data.iloc[i - 1])
            if p["bear"] and f["bull"] and f["open"] <= p["close"] and f["close"] >= p["open"]:
                add("Bullish Engulfing", "BULLISH", 3, "Bullish body engulfs the prior bearish body.")
            if p["bull"] and f["bear"] and f["open"] >= p["close"] and f["close"] <= p["open"]:
                add("Bearish Engulfing", "BEARISH", 3, "Bearish body engulfs the prior bullish body.")

        if i >= 2:
            a = _candle_features(data.iloc[i - 2]); b = _candle_features(data.iloc[i - 1])
            midpoint_a = (a["open"] + a["close"]) / 2
            small_b = b["body"] / b["range"] <= 0.35
            if a["bear"] and small_b and f["bull"] and f["close"] > midpoint_a:
                add("Morning Star", "BULLISH", 3, "Three-candle reversal structure with improving demand.")
            if a["bull"] and small_b and f["bear"] and f["close"] < midpoint_a:
                add("Evening Star", "BEARISH", 3, "Three-candle reversal structure with increasing supply.")

    found.sort(key=lambda x: (x["date"], x["strength"]), reverse=True)
    return found if max_results is None else found[:max_results]


def _simple_regime_at(data: pd.DataFrame, pos: int) -> str:
    if pos < 50:
        return "RANGE"
    close = data["Close"].iloc[:pos + 1]
    latest = float(close.iloc[-1])
    sma20 = float(close.tail(20).mean())
    sma50 = float(close.tail(50).mean())
    if len(close) >= 200:
        sma200 = float(close.tail(200).mean())
        if latest > sma50 > sma200: return "UPTREND"
        if latest < sma50 < sma200: return "DOWNTREND"
    if latest > sma20 > sma50: return "UPTREND"
    if latest < sma20 < sma50: return "DOWNTREND"
    return "RANGE"


def backtest_candlestick_patterns(hist: pd.DataFrame, horizon: int = 5, current_regime: str | None = None) -> dict[str, dict]:
    """In-sample descriptive pattern stats, including regime-conditioned stats."""
    data = hist[["Open", "High", "Low", "Close"]].dropna().copy()
    if len(data) < 80:
        return {}
    patterns = detect_candlestick_patterns(data, lookback=len(data), max_results=None)
    date_to_pos = {idx.strftime("%Y-%m-%d"): pos for pos, idx in enumerate(data.index)}
    buckets: dict[str, list[tuple[float, str]]] = defaultdict(list)
    biases: dict[str, str] = {}

    for pattern in patterns:
        bias = pattern.get("bias")
        if bias not in {"BULLISH", "BEARISH"}: continue
        pos = date_to_pos.get(pattern["date"])
        if pos is None or pos + horizon >= len(data): continue
        start = float(data["Close"].iloc[pos]); end = float(data["Close"].iloc[pos + horizon])
        if start <= 0: continue
        ret = (end / start - 1) * 100
        buckets[pattern["pattern"]].append((ret, _simple_regime_at(data, pos)))
        biases[pattern["pattern"]] = bias

    stats = {}
    for name, values in buckets.items():
        returns = [x[0] for x in values]; bias = biases[name]
        wins = sum(r > 0 for r in returns) if bias == "BULLISH" else sum(r < 0 for r in returns)
        item = {
            "bias": bias, "horizon_sessions": horizon, "occurrences": len(returns),
            "directional_hit_rate_pct": round(wins / len(returns) * 100, 1),
            "average_forward_return_pct": round(float(np.mean(returns)), 2),
            "median_forward_return_pct": round(float(np.median(returns)), 2),
            "note": "In-sample historical behavior for this asset; not out-of-sample validation.",
        }
        if current_regime:
            regime_returns = [r for r, reg in values if reg == current_regime]
            if regime_returns:
                reg_wins = sum(r > 0 for r in regime_returns) if bias == "BULLISH" else sum(r < 0 for r in regime_returns)
                item["current_regime"] = current_regime
                item["regime_occurrences"] = len(regime_returns)
                item["regime_hit_rate_pct"] = round(reg_wins / len(regime_returns) * 100, 1)
                item["regime_avg_forward_return_pct"] = round(float(np.mean(regime_returns)), 2)
        stats[name] = item
    return stats


def get_ohlcv_history(symbol: str, market: str | None = None, period: str = "6mo", interval: str = "1d") -> list[dict]:
    hist = yf.Ticker(yahoo_symbol(symbol, market)).history(period=period, interval=interval, auto_adjust=False)
    if hist.empty: return []
    rows = []
    for idx, row in hist.dropna(subset=["Open", "High", "Low", "Close"]).iterrows():
        rows.append({
            "date": idx.strftime("%Y-%m-%d"), "open": round(float(row["Open"]), 4),
            "high": round(float(row["High"]), 4), "low": round(float(row["Low"]), 4),
            "close": round(float(row["Close"]), 4), "volume": int(row.get("Volume", 0) or 0),
        })
    return rows


def _cluster_price_zones(values: list[tuple[float, int]], latest: float, tolerance: float) -> list[dict]:
    if not values: return []
    clusters: list[dict] = []
    for price, age in sorted(values, key=lambda x: x[0]):
        placed = False
        for c in clusters:
            center = c["sum"] / c["touches"]
            if abs(price - center) <= max(tolerance, center * 0.006):
                c["sum"] += price; c["touches"] += 1; c["prices"].append(price); c["recency"] = min(c["recency"], age); placed = True; break
        if not placed:
            clusters.append({"sum": price, "touches": 1, "prices": [price], "recency": age})
    out = []
    for c in clusters:
        center = c["sum"] / c["touches"]
        half = max(tolerance * 0.45, center * 0.0025)
        score = c["touches"] * 2 + max(0, 4 - c["recency"] / 20)
        out.append({
            "low": round(center - half, 4), "high": round(center + half, 4), "center": round(center, 4),
            "touches": c["touches"], "strength": round(score, 1), "distance_pct": round((center / latest - 1) * 100, 2),
        })
    return out


def _support_resistance_zones(hist: pd.DataFrame, sessions: int, atr_value: float | None) -> dict:
    data = hist.tail(max(5, sessions)).dropna(subset=["High", "Low", "Close"])
    if data.empty: return {"support_zones": [], "resistance_zones": []}
    latest = float(data["Close"].iloc[-1])
    pivot_window = 2 if len(data) < 30 else 3
    lows, highs = [], []
    for i in range(pivot_window, len(data) - pivot_window):
        low = float(data["Low"].iloc[i]); high = float(data["High"].iloc[i])
        if low <= float(data["Low"].iloc[i-pivot_window:i+pivot_window+1].min()): lows.append((low, len(data)-1-i))
        if high >= float(data["High"].iloc[i-pivot_window:i+pivot_window+1].max()): highs.append((high, len(data)-1-i))
    # Guarantee useful levels for short windows.
    lows.extend([(float(data["Low"].min()), 0)])
    highs.extend([(float(data["High"].max()), 0)])
    tolerance = max((atr_value or latest * 0.012) * 0.8, latest * 0.005)
    all_support = [z for z in _cluster_price_zones(lows, latest, tolerance) if z["center"] <= latest * 1.01]
    all_resistance = [z for z in _cluster_price_zones(highs, latest, tolerance) if z["center"] >= latest * 0.99]
    all_support.sort(key=lambda z: z["center"], reverse=True)
    all_resistance.sort(key=lambda z: z["center"])
    nearest_support = all_support[0] if all_support else None
    nearest_resistance = all_resistance[0] if all_resistance else None
    major_support = max(all_support, key=lambda z: z["strength"], default=None)
    major_resistance = max(all_resistance, key=lambda z: z["strength"], default=None)
    return {
        "support_zones": all_support[:4], "resistance_zones": all_resistance[:4],
        "nearest_support": nearest_support, "nearest_resistance": nearest_resistance,
        "major_support": major_support, "major_resistance": major_resistance,
    }


def _market_regime(hist: pd.DataFrame, adx_value: float | None, atr_pct: float | None) -> dict:
    close = hist["Close"].dropna(); latest = float(close.iloc[-1])
    sma20 = float(close.tail(20).mean()) if len(close) >= 20 else latest
    sma50 = float(close.tail(50).mean()) if len(close) >= 50 else latest
    sma200 = float(close.tail(200).mean()) if len(close) >= 200 else None
    daily_vol = float(close.pct_change().tail(20).std() * math.sqrt(252) * 100) if len(close) >= 21 else None
    trend_strength = "STRONG" if (adx_value or 0) >= 25 else "MODERATE" if (adx_value or 0) >= 18 else "WEAK"
    if sma200 is not None and latest > sma50 > sma200 and (adx_value or 0) >= 18:
        regime = "TRENDING UP"
    elif sma200 is not None and latest < sma50 < sma200 and (adx_value or 0) >= 18:
        regime = "TRENDING DOWN"
    elif latest > sma20 > sma50 and (adx_value or 0) >= 20:
        regime = "TRENDING UP"
    elif latest < sma20 < sma50 and (adx_value or 0) >= 20:
        regime = "TRENDING DOWN"
    elif (adx_value or 0) < 18:
        regime = "RANGE-BOUND"
    else:
        regime = "MIXED"
    vol_regime = "HIGH VOLATILITY" if (atr_pct or 0) >= 3.5 or (daily_vol or 0) >= 35 else "LOW VOLATILITY" if (atr_pct or 99) <= 1.3 else "NORMAL VOLATILITY"
    return {"regime": regime, "trend_strength": trend_strength, "adx14": _clean(adx_value), "atr_pct": _clean(atr_pct), "annualized_volatility_20d_pct": round(daily_vol, 2) if daily_vol is not None else None, "volatility_regime": vol_regime}


def _volume_analysis(hist: pd.DataFrame) -> dict:
    volume = hist.get("Volume", pd.Series(dtype=float)).astype(float).dropna()
    if volume.empty: return {}
    current = float(volume.iloc[-1]); avg20 = float(volume.tail(20).mean()) if len(volume) >= 5 else float(volume.mean())
    rel = current / avg20 if avg20 else None
    if rel is None: status = "UNKNOWN"
    elif rel >= 1.5: status = "STRONG"
    elif rel >= 1.0: status = "NORMAL"
    else: status = "WEAK"
    return {"current_volume": int(current), "average_volume_20d": round(avg20), "relative_volume": round(rel, 2) if rel else None, "participation": status}


@lru_cache(maxsize=4)
def _benchmark_history(market: str) -> pd.Series:
    bench = _BENCHMARKS.get((market or "IN").upper(), _BENCHMARKS["IN"])
    try:
        return yf.Ticker(bench["symbol"]).history(period="1y", auto_adjust=True)["Close"].dropna()
    except Exception:
        return pd.Series(dtype=float)


def _relative_strength(close: pd.Series, market: str) -> dict:
    bench = _BENCHMARKS.get((market or "IN").upper(), _BENCHMARKS["IN"])
    bh = _benchmark_history((market or "IN").upper())
    result = {"benchmark_symbol": bench["symbol"], "benchmark_name": bench["name"], "horizons": {}}
    if bh.empty: return result
    for label, cfg in _TIMEFRAME_CONFIG.items():
        n = min(cfg["sessions"], len(close)-1, len(bh)-1)
        if n <= 0: continue
        sr = (float(close.iloc[-1]) / float(close.iloc[-n-1]) - 1) * 100
        br = (float(bh.iloc[-1]) / float(bh.iloc[-n-1]) - 1) * 100
        result["horizons"][label] = {"stock_return_pct": round(sr,2), "benchmark_return_pct": round(br,2), "relative_strength_pct": round(sr-br,2), "status": "OUTPERFORMING" if sr-br > 1 else "UNDERPERFORMING" if sr-br < -1 else "IN LINE"}
    return result


def _timeframe_bias(close: pd.Series, technical: dict, patterns: list[dict], label: str, cfg: dict) -> dict:
    close = close.dropna()
    if len(close) < 3:
        return {"label": label, "directional_bias": "NEUTRAL", "signal_agreement_pct": 0, "confidence_pct": 0, "lookback_sessions": 0, "return_pct": None, "reasons": ["Insufficient price history for this horizon."]}
    sessions = min(int(cfg["sessions"]), len(close) - 1)
    start = float(close.iloc[-sessions - 1]); latest = float(close.iloc[-1]); horizon_return = ((latest / start) - 1) * 100 if start else 0.0
    threshold = float(cfg["return_threshold"]); score = 0.0; reasons = []
    if horizon_return >= threshold: score += 1.6; reasons.append(f"{label} price momentum is positive ({horizon_return:.1f}%).")
    elif horizon_return >= threshold * .35: score += .8; reasons.append(f"{label} price momentum is mildly positive ({horizon_return:.1f}%).")
    elif horizon_return <= -threshold: score -= 1.6; reasons.append(f"{label} price momentum is negative ({horizon_return:.1f}%).")
    elif horizon_return <= -threshold*.35: score -= .8; reasons.append(f"{label} price momentum is mildly negative ({horizon_return:.1f}%).")
    else: reasons.append(f"{label} price momentum is broadly flat ({horizon_return:.1f}%).")
    fast_n, slow_n = int(cfg["fast_ma"]), int(cfg["slow_ma"])
    if len(close) >= fast_n:
        fast_ma = float(close.tail(fast_n).mean()); score += .6 if latest >= fast_ma else -.6; reasons.append(f"Price is {'above' if latest >= fast_ma else 'below'} the {fast_n}-session average.")
    if len(close) >= slow_n:
        slow_ma = float(close.tail(slow_n).mean()); score += .8 if latest >= slow_ma else -.8
    rsi = technical.get("rsi14")
    if rsi is not None:
        if 50 <= rsi <= 68: score += .35
        elif rsi < 42: score -= .35
        elif rsi >= 75: score -= .25
    macd, signal = technical.get("macd"), technical.get("macd_signal")
    if macd is not None and signal is not None: score += .35 if macd > signal else -.35
    volume = technical.get("volume", {})
    if volume.get("relative_volume") is not None and volume["relative_volume"] >= 1.25:
        score += .25 if horizon_return >= 0 else -.25
        reasons.append(f"Volume participation is elevated ({volume['relative_volume']:.2f}× 20D average).")
    if label in {"1W", "1M"}:
        for pattern in patterns[:3]:
            weight = min(.55, float(pattern.get("strength", 1)) * .18)
            if pattern.get("bias") == "BULLISH": score += weight
            elif pattern.get("bias") == "BEARISH": score -= weight
    bias = "BULLISH" if score >= 1 else "BEARISH" if score <= -1 else "NEUTRAL"
    agreement = min(100, round(50 + min(abs(score), 4.5) / 4.5 * 50))
    return {"label": label, "directional_bias": bias, "signal_agreement_pct": agreement, "confidence_pct": agreement, "signal_strength": round(score,2), "lookback_sessions": sessions, "return_pct": round(horizon_return,2), "reasons": reasons[:5], "note": "Signal agreement measures indicator alignment, not probability of profit."}


def _multi_horizon_outlook(close: pd.Series, technical: dict, patterns: list[dict], hist: pd.DataFrame | None = None, atr_value: float | None = None) -> dict[str, dict]:
    if hist is None:
        hist = pd.DataFrame({"High": close, "Low": close, "Close": close}, index=close.index)
    out = {}
    for label, cfg in _TIMEFRAME_CONFIG.items():
        item = _timeframe_bias(close, technical, patterns, label, cfg)
        item["levels"] = _support_resistance_zones(hist, cfg["sessions"], atr_value)
        out[label] = item
    return out


def _trend_alignment(timelines: dict[str, dict]) -> dict:
    biases = [v.get("directional_bias", "NEUTRAL") for v in timelines.values()]
    bull, bear, neutral = biases.count("BULLISH"), biases.count("BEARISH"), biases.count("NEUTRAL")
    dominant = "BULLISH" if bull > bear and bull >= neutral else "BEARISH" if bear > bull and bear >= neutral else "MIXED"
    majority = max(bull, bear, neutral)
    score = round(majority / max(1, len(biases)) * 100)
    return {"dominant": dominant, "alignment_pct": score, "bullish_timeframes": bull, "bearish_timeframes": bear, "neutral_timeframes": neutral, "total_timeframes": len(biases)}


def _breakout_status(price: float, levels: dict, volume: dict, atr_value: float | None) -> dict:
    ns, nr = levels.get("nearest_support"), levels.get("nearest_resistance")
    rel_vol = volume.get("relative_volume") or 0
    atr = atr_value or price * .02
    result = {"status": "NO ACTIVE BREAKOUT", "direction": "NEUTRAL", "volume_confirmed": False, "distance_pct": None}
    if nr:
        res = float(nr["high"]); dist = (res / price - 1) * 100
        if price > res:
            result.update(status="CONFIRMED BREAKOUT" if rel_vol >= 1.3 else "BREAKOUT - LOW VOLUME", direction="BULLISH", volume_confirmed=rel_vol >= 1.3, distance_pct=round(dist,2), level=round(res,4))
            return result
        if 0 <= dist <= max(1.2, atr / price * 100):
            result.update(status="BREAKOUT WATCH", direction="BULLISH", distance_pct=round(dist,2), level=round(res,4))
    if ns:
        sup = float(ns["low"]); dist = (price / sup - 1) * 100
        if price < sup:
            result.update(status="CONFIRMED BREAKDOWN" if rel_vol >= 1.3 else "BREAKDOWN - LOW VOLUME", direction="BEARISH", volume_confirmed=rel_vol >= 1.3, distance_pct=round(-dist,2), level=round(sup,4))
            return result
        if 0 <= dist <= max(1.2, atr / price * 100):
            result.update(status="BREAKDOWN WATCH", direction="BEARISH", distance_pct=round(dist,2), level=round(sup,4))
    return result


def _risk_reward(price: float, bias: str, levels: dict, atr_value: float | None) -> dict:
    atr = atr_value or price * .02
    ns, nr = levels.get("nearest_support"), levels.get("nearest_resistance")
    ms, mr = levels.get("major_support"), levels.get("major_resistance")
    if bias == "BEARISH":
        target = (ns or ms or {}).get("center"); invalidation = (nr or mr or {}).get("high")
        if invalidation is None: invalidation = price + atr * 1.2
        if target is None or target >= price: target = price - atr * 2
        reward, risk = price - float(target), float(invalidation) - price
    else:
        target = (nr or mr or {}).get("center"); invalidation = (ns or ms or {}).get("low")
        if invalidation is None: invalidation = price - atr * 1.2
        if target is None or target <= price: target = price + atr * 2
        reward, risk = float(target) - price, price - float(invalidation)
    ratio = reward / risk if risk > 0 else None
    quality = "GOOD" if ratio and ratio >= 2 else "FAIR" if ratio and ratio >= 1.2 else "POOR"
    return {"entry_reference": round(price,4), "target_reference": round(float(target),4), "invalidation_level": round(float(invalidation),4), "potential_reward_pct": round(reward/price*100,2), "potential_risk_pct": round(risk/price*100,2), "risk_reward_ratio": round(ratio,2) if ratio else None, "quality": quality, "note": "Illustrative technical setup; invalidation is not personalized stop-loss advice."}


def _directional_outlook(technical: dict, patterns: list[dict], close: pd.Series) -> dict:
    timelines = technical.get("timeline_biases", {})
    short = timelines.get("1M") or timelines.get("1W") or {}
    return {"directional_bias": short.get("directional_bias", "NEUTRAL"), "horizon": "1 month reference", "confidence_pct": short.get("signal_agreement_pct", 0), "signal_agreement_pct": short.get("signal_agreement_pct", 0), "reasons": short.get("reasons", []), "note": "Compatibility field. Prefer timeline_biases in V5."}


def get_technical(symbol: str, market: str | None = None, include_pattern_backtest: bool = True) -> dict:
    resolved_market = (market or "IN").upper()
    ticker = yf.Ticker(yahoo_symbol(symbol, resolved_market))
    hist = ticker.history(period="1y", auto_adjust=False)
    if hist.empty or len(hist) < 50:
        raise ValueError(f"Insufficient technical data for {symbol}")
    data = hist.dropna(subset=["High", "Low", "Close"]).copy()
    close = data["Close"].astype(float)
    sma20 = close.rolling(20).mean(); sma50 = close.rolling(50).mean(); sma200 = close.rolling(200).mean()
    ema12 = close.ewm(span=12, adjust=False).mean(); ema26 = close.ewm(span=26, adjust=False).mean(); macd = ema12 - ema26; signal = macd.ewm(span=9, adjust=False).mean()
    rsi14 = _rsi(close, 14); atr14 = _atr(data, 14); adx14 = _adx(data, 14); vwap20 = _rolling_vwap(data, 20)
    latest = float(close.iloc[-1]); atr_value = _clean(atr14.iloc[-1]); atr_pct = atr_value/latest*100 if atr_value and latest else None
    volume = _volume_analysis(data)
    base = {
        "price": latest, "sma20": _clean(sma20.iloc[-1]), "sma50": _clean(sma50.iloc[-1]), "sma200": _clean(sma200.iloc[-1]) if len(close) >= 200 else None,
        "rsi14": _clean(rsi14.iloc[-1]), "macd": _clean(macd.iloc[-1]), "macd_signal": _clean(signal.iloc[-1]),
        "atr14": atr_value, "atr_pct": round(atr_pct,2) if atr_pct is not None else None, "adx14": _clean(adx14.iloc[-1]),
        "vwap20": _clean(vwap20.iloc[-1]), "above_vwap20": bool(latest > vwap20.iloc[-1]) if pd.notna(vwap20.iloc[-1]) else None,
        "above_sma20": bool(latest > sma20.iloc[-1]) if pd.notna(sma20.iloc[-1]) else None,
        "above_sma50": bool(latest > sma50.iloc[-1]) if pd.notna(sma50.iloc[-1]) else None,
        "above_sma200": bool(latest > sma200.iloc[-1]) if pd.notna(sma200.iloc[-1]) else None,
        "volume": volume,
    }
    regime = _market_regime(data, base["adx14"], base["atr_pct"]); base["market_regime"] = regime
    raw_hist = ticker.history(period="5y", auto_adjust=False) if include_pattern_backtest else data
    patterns = detect_candlestick_patterns(raw_hist.tail(140))
    current_simple_regime = "UPTREND" if "UP" in regime["regime"] else "DOWNTREND" if "DOWN" in regime["regime"] else "RANGE"
    pattern_stats = backtest_candlestick_patterns(raw_hist, horizon=5, current_regime=current_simple_regime) if include_pattern_backtest else {}
    for pattern in patterns:
        if pattern["pattern"] in pattern_stats: pattern["historical_5d"] = pattern_stats[pattern["pattern"]]
    base["candlestick_patterns"] = patterns; base["pattern_backtest"] = pattern_stats
    timelines = _multi_horizon_outlook(close, base, patterns, data, atr_value); base["timeline_biases"] = timelines
    base["trend_alignment"] = _trend_alignment(timelines)
    # Backward-compatible 20D fields plus richer horizon levels.
    levels_1m = timelines["1M"]["levels"]
    base["support_20d"] = levels_1m.get("nearest_support", {}).get("center") if levels_1m.get("nearest_support") else round(float(data["Low"].tail(20).min()),4)
    base["resistance_20d"] = levels_1m.get("nearest_resistance", {}).get("center") if levels_1m.get("nearest_resistance") else round(float(data["High"].tail(20).max()),4)
    base["important_levels"] = levels_1m
    base["breakout"] = _breakout_status(latest, levels_1m, volume, atr_value)
    base["risk_reward"] = _risk_reward(latest, timelines["1M"]["directional_bias"], levels_1m, atr_value)
    base["relative_strength"] = _relative_strength(close, resolved_market)
    base["trend_outlook"] = _directional_outlook(base, patterns, close)
    return base
