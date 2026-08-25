import math
from typing import Any

import pandas as pd
import yfinance as yf

from app.tools.market_data import yahoo_symbol


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
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


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
            found.append({
                "date": date,
                "pattern": name,
                "bias": bias,
                "strength": strength,
                "context": trend,
                "note": note,
            })

        if body_ratio <= 0.10:
            add("Doji", "NEUTRAL", 1, "Indecision; direction needs confirmation from subsequent candles.")

        if f["body"] > 0 and f["lower"] >= 2 * f["body"] and f["upper"] <= 0.6 * f["body"]:
            if trend == "down":
                add("Hammer", "BULLISH", 2, "Potential downside rejection after a decline.")
            elif trend == "up":
                add("Hanging Man", "BEARISH", 2, "Potential exhaustion after an advance; confirmation required.")

        if f["body"] > 0 and f["upper"] >= 2 * f["body"] and f["lower"] <= 0.6 * f["body"]:
            if trend == "down":
                add("Inverted Hammer", "BULLISH", 2, "Possible reversal attempt after a decline.")
            elif trend == "up":
                add("Shooting Star", "BEARISH", 2, "Upper-price rejection after an advance.")

        if body_ratio >= 0.80:
            add("Bullish Marubozu" if f["bull"] else "Bearish Marubozu",
                "BULLISH" if f["bull"] else "BEARISH", 1,
                "Strong one-session directional conviction.")

        if i >= 1:
            p = _candle_features(data.iloc[i - 1])
            if p["bear"] and f["bull"] and f["open"] <= p["close"] and f["close"] >= p["open"]:
                add("Bullish Engulfing", "BULLISH", 3, "Bullish body engulfs the prior bearish body.")
            if p["bull"] and f["bear"] and f["open"] >= p["close"] and f["close"] <= p["open"]:
                add("Bearish Engulfing", "BEARISH", 3, "Bearish body engulfs the prior bullish body.")

        if i >= 2:
            a = _candle_features(data.iloc[i - 2])
            b = _candle_features(data.iloc[i - 1])
            midpoint_a = (a["open"] + a["close"]) / 2
            small_b = b["body"] / b["range"] <= 0.35
            if a["bear"] and small_b and f["bull"] and f["close"] > midpoint_a:
                add("Morning Star", "BULLISH", 3, "Three-candle reversal structure with improving demand.")
            if a["bull"] and small_b and f["bear"] and f["close"] < midpoint_a:
                add("Evening Star", "BEARISH", 3, "Three-candle reversal structure with increasing supply.")

    # Most recent/strongest first.
    found.sort(key=lambda x: (x["date"], x["strength"]), reverse=True)
    return found if max_results is None else found[:max_results]



def backtest_candlestick_patterns(hist: pd.DataFrame, horizon: int = 5) -> dict[str, dict]:
    """Estimate how detected directional patterns behaved historically on the same asset.

    This is an in-sample descriptive backtest, not a guarantee of future performance.
    """
    data = hist[["Open", "High", "Low", "Close"]].dropna().copy()
    if len(data) < 80:
        return {}

    patterns = detect_candlestick_patterns(data, lookback=len(data), max_results=None)
    date_to_pos = {idx.strftime("%Y-%m-%d"): pos for pos, idx in enumerate(data.index)}
    buckets: dict[str, list[float]] = {}
    biases: dict[str, str] = {}

    for pattern in patterns:
        bias = pattern.get("bias")
        if bias not in {"BULLISH", "BEARISH"}:
            continue
        pos = date_to_pos.get(pattern["date"])
        if pos is None or pos + horizon >= len(data):
            continue
        start = float(data["Close"].iloc[pos])
        end = float(data["Close"].iloc[pos + horizon])
        if start <= 0:
            continue
        forward_return = (end / start - 1) * 100
        buckets.setdefault(pattern["pattern"], []).append(forward_return)
        biases[pattern["pattern"]] = bias

    stats = {}
    for name, returns in buckets.items():
        bias = biases[name]
        wins = sum(r > 0 for r in returns) if bias == "BULLISH" else sum(r < 0 for r in returns)
        stats[name] = {
            "bias": bias,
            "horizon_sessions": horizon,
            "occurrences": len(returns),
            "directional_hit_rate_pct": round(wins / len(returns) * 100, 1),
            "average_forward_return_pct": round(sum(returns) / len(returns), 2),
            "median_forward_return_pct": round(float(pd.Series(returns).median()), 2),
            "note": "In-sample historical behavior for this asset; not out-of-sample validation.",
        }
    return stats

def get_ohlcv_history(symbol: str, market: str | None = None, period: str = "6mo", interval: str = "1d") -> list[dict]:
    hist = yf.Ticker(yahoo_symbol(symbol, market)).history(period=period, interval=interval, auto_adjust=False)
    if hist.empty:
        return []
    rows = []
    for idx, row in hist.dropna(subset=["Open", "High", "Low", "Close"]).iterrows():
        rows.append({
            "date": idx.strftime("%Y-%m-%d"),
            "open": round(float(row["Open"]), 4),
            "high": round(float(row["High"]), 4),
            "low": round(float(row["Low"]), 4),
            "close": round(float(row["Close"]), 4),
            "volume": int(row.get("Volume", 0) or 0),
        })
    return rows


def _directional_outlook(technical: dict, patterns: list[dict], close: pd.Series) -> dict:
    bull_votes = 0.0
    bear_votes = 0.0
    reasons: list[str] = []

    if technical.get("above_sma20") is True:
        bull_votes += 1
        reasons.append("Price is above SMA20")
    elif technical.get("above_sma20") is False:
        bear_votes += 1
        reasons.append("Price is below SMA20")

    if technical.get("above_sma50") is True:
        bull_votes += 1.25
        reasons.append("Price is above SMA50")
    elif technical.get("above_sma50") is False:
        bear_votes += 1.25
        reasons.append("Price is below SMA50")

    if technical.get("above_sma200") is True:
        bull_votes += 1.5
        reasons.append("Long-term trend is above SMA200")
    elif technical.get("above_sma200") is False:
        bear_votes += 1.5
        reasons.append("Long-term trend is below SMA200")

    macd, signal = technical.get("macd"), technical.get("macd_signal")
    if macd is not None and signal is not None:
        if macd > signal:
            bull_votes += 1
            reasons.append("MACD is above its signal line")
        else:
            bear_votes += 1
            reasons.append("MACD is below its signal line")

    rsi = technical.get("rsi14")
    if rsi is not None:
        if 50 <= rsi <= 68:
            bull_votes += 0.75
            reasons.append("RSI supports positive momentum without being extremely overbought")
        elif rsi >= 75:
            bear_votes += 0.5
            reasons.append("RSI is overbought, increasing pullback risk")
        elif rsi <= 30:
            bull_votes += 0.4
            reasons.append("RSI is oversold, allowing for a rebound setup")
        elif rsi < 45:
            bear_votes += 0.5

    if len(close) >= 20:
        mom20 = (float(close.iloc[-1]) / float(close.iloc[-20]) - 1) * 100
        if mom20 > 3:
            bull_votes += 1
            reasons.append(f"20-session momentum is positive ({mom20:.1f}%)")
        elif mom20 < -3:
            bear_votes += 1
            reasons.append(f"20-session momentum is negative ({mom20:.1f}%)")
    else:
        mom20 = None

    for idx, p in enumerate(patterns[:5]):
        weight = min(1.5, p.get("strength", 1) * 0.45)
        hist_stat = p.get("historical_5d") or {}
        if hist_stat.get("occurrences", 0) >= 5 and hist_stat.get("directional_hit_rate_pct", 0) >= 55:
            weight *= 1.20
            if idx == 0:
                reasons.append(
                    f"{p.get('pattern')} historically matched its 5-session bias "
                    f"{hist_stat.get('directional_hit_rate_pct')}% of {hist_stat.get('occurrences')} occurrences"
                )
        if p.get("bias") == "BULLISH":
            bull_votes += weight
        elif p.get("bias") == "BEARISH":
            bear_votes += weight

    net = bull_votes - bear_votes
    total = bull_votes + bear_votes
    if net >= 1.5:
        bias = "BULLISH"
    elif net <= -1.5:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    # Confidence is a heuristic signal-strength score, intentionally capped.
    confidence = 50 if total == 0 else min(78, round(50 + (abs(net) / max(total, 1)) * 28))

    return {
        "directional_bias": bias,
        "horizon": "5-10 trading sessions",
        "confidence_pct": confidence,
        "bullish_votes": round(bull_votes, 2),
        "bearish_votes": round(bear_votes, 2),
        "momentum_20d_pct": round(mom20, 2) if mom20 is not None else None,
        "reasons": reasons[:6],
        "note": "Heuristic directional bias, not a probability of profit or guaranteed forecast. Candlestick patterns require confirmation.",
    }



_TIMEFRAME_CONFIG = {
    "1W": {"sessions": 5, "return_threshold": 1.2, "fast_ma": 5, "slow_ma": 20},
    "1M": {"sessions": 21, "return_threshold": 3.0, "fast_ma": 20, "slow_ma": 50},
    "3M": {"sessions": 63, "return_threshold": 6.0, "fast_ma": 20, "slow_ma": 50},
    "6M": {"sessions": 126, "return_threshold": 10.0, "fast_ma": 50, "slow_ma": 100},
    "1Y": {"sessions": 252, "return_threshold": 15.0, "fast_ma": 50, "slow_ma": 200},
}


def _timeframe_bias(close: pd.Series, technical: dict, patterns: list[dict], label: str, cfg: dict) -> dict:
    """Build a heuristic directional bias for a single time horizon.

    Confidence is signal agreement/strength, not a probability of profit.
    """
    close = close.dropna()
    if len(close) < 3:
        return {
            "label": label, "directional_bias": "NEUTRAL", "confidence_pct": 0,
            "lookback_sessions": 0, "return_pct": None,
            "reasons": ["Insufficient price history for this horizon."],
        }

    sessions = min(int(cfg["sessions"]), len(close) - 1)
    start = float(close.iloc[-sessions - 1])
    latest = float(close.iloc[-1])
    horizon_return = ((latest / start) - 1) * 100 if start else 0.0
    threshold = float(cfg["return_threshold"])
    score = 0.0
    reasons: list[str] = []

    if horizon_return >= threshold:
        score += 1.6
        reasons.append(f"{label} price momentum is positive ({horizon_return:.1f}%).")
    elif horizon_return >= threshold * 0.35:
        score += 0.8
        reasons.append(f"{label} price momentum is mildly positive ({horizon_return:.1f}%).")
    elif horizon_return <= -threshold:
        score -= 1.6
        reasons.append(f"{label} price momentum is negative ({horizon_return:.1f}%).")
    elif horizon_return <= -threshold * 0.35:
        score -= 0.8
        reasons.append(f"{label} price momentum is mildly negative ({horizon_return:.1f}%).")
    else:
        reasons.append(f"{label} price momentum is broadly flat ({horizon_return:.1f}%).")

    fast_n = int(cfg["fast_ma"])
    slow_n = int(cfg["slow_ma"])
    if len(close) >= fast_n:
        fast_ma = float(close.tail(fast_n).mean())
        if latest >= fast_ma:
            score += 0.6
            reasons.append(f"Price is above the {fast_n}-session average.")
        else:
            score -= 0.6
            reasons.append(f"Price is below the {fast_n}-session average.")
    if len(close) >= slow_n:
        slow_ma = float(close.tail(slow_n).mean())
        if latest >= slow_ma:
            score += 0.8
        else:
            score -= 0.8

    rsi = technical.get("rsi14")
    if rsi is not None:
        if 50 <= rsi <= 68:
            score += 0.35
        elif rsi < 42:
            score -= 0.35
        elif rsi >= 75:
            score -= 0.25

    macd, macd_signal = technical.get("macd"), technical.get("macd_signal")
    if macd is not None and macd_signal is not None:
        score += 0.35 if macd > macd_signal else -0.35

    # Candle patterns are short-lived signals, so only influence 1W/1M horizons.
    if label in {"1W", "1M"}:
        for pattern in patterns[:3]:
            weight = min(0.55, float(pattern.get("strength", 1)) * 0.18)
            if pattern.get("bias") == "BULLISH":
                score += weight
            elif pattern.get("bias") == "BEARISH":
                score -= weight

    if score >= 1.0:
        bias = "BULLISH"
    elif score <= -1.0:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    confidence = min(85, round(50 + min(abs(score), 4.5) / 4.5 * 35))
    return {
        "label": label,
        "directional_bias": bias,
        "confidence_pct": confidence,
        "signal_strength": round(score, 2),
        "lookback_sessions": sessions,
        "return_pct": round(horizon_return, 2),
        "reasons": reasons[:4],
        "note": "Heuristic multi-horizon technical bias; confidence measures signal agreement, not probability of profit.",
    }


def _multi_horizon_outlook(close: pd.Series, technical: dict, patterns: list[dict]) -> dict[str, dict]:
    return {
        label: _timeframe_bias(close, technical, patterns, label, cfg)
        for label, cfg in _TIMEFRAME_CONFIG.items()
    }

def get_technical(symbol: str, market: str | None = None, include_pattern_backtest: bool = True) -> dict:
    hist = yf.Ticker(yahoo_symbol(symbol, market)).history(period="1y", auto_adjust=True)
    if hist.empty or len(hist) < 50:
        raise ValueError(f"Insufficient technical data for {symbol}")

    close = hist["Close"].dropna()
    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    rsi14 = _rsi(close, 14)
    latest = float(close.iloc[-1])

    base = {
        "price": latest,
        "sma20": _clean(sma20.iloc[-1]),
        "sma50": _clean(sma50.iloc[-1]),
        "sma200": _clean(sma200.iloc[-1]) if len(close) >= 200 else None,
        "rsi14": _clean(rsi14.iloc[-1]),
        "macd": _clean(macd.iloc[-1]),
        "macd_signal": _clean(signal.iloc[-1]),
        "above_sma20": bool(latest > sma20.iloc[-1]) if pd.notna(sma20.iloc[-1]) else None,
        "above_sma50": bool(latest > sma50.iloc[-1]) if pd.notna(sma50.iloc[-1]) else None,
        "above_sma200": bool(latest > sma200.iloc[-1]) if pd.notna(sma200.iloc[-1]) else None,
        "support_20d": round(float(close.tail(20).min()), 4),
        "resistance_20d": round(float(close.tail(20).max()), 4),
    }

    # Use unadjusted OHLC for candle geometry.
    raw_period = "5y" if include_pattern_backtest else "6mo"
    raw_hist = yf.Ticker(yahoo_symbol(symbol, market)).history(period=raw_period, auto_adjust=False)
    recent_raw = raw_hist.tail(140)
    patterns = detect_candlestick_patterns(recent_raw)
    pattern_stats = backtest_candlestick_patterns(raw_hist, horizon=5) if include_pattern_backtest else {}
    for pattern in patterns:
        if pattern["pattern"] in pattern_stats:
            pattern["historical_5d"] = pattern_stats[pattern["pattern"]]
    base["candlestick_patterns"] = patterns
    base["pattern_backtest"] = pattern_stats
    base["trend_outlook"] = _directional_outlook(base, patterns, close)
    base["timeline_biases"] = _multi_horizon_outlook(close, base, patterns)
    return base
