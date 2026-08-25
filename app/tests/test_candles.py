import sys
import types
import pandas as pd

sys.modules.setdefault("yfinance", types.SimpleNamespace())

from app.tools.technical import detect_candlestick_patterns


def test_detects_bullish_engulfing():
    idx = pd.date_range("2026-01-01", periods=6, freq="D")
    df = pd.DataFrame(
        {
            "Open": [105, 103, 101, 100, 99, 96],
            "High": [106, 104, 102, 101, 100, 103],
            "Low": [102, 100, 98, 97, 95, 95],
            "Close": [103, 101, 99, 98, 96, 102],
        },
        index=idx,
    )
    patterns = detect_candlestick_patterns(df, lookback=10)
    assert any(p["pattern"] == "Bullish Engulfing" for p in patterns)


def test_doji_is_neutral():
    idx = pd.date_range("2026-01-01", periods=3, freq="D")
    df = pd.DataFrame(
        {
            "Open": [100, 101, 102.0],
            "High": [102, 103, 105.0],
            "Low": [99, 100, 99.0],
            "Close": [101, 102, 102.1],
        },
        index=idx,
    )
    patterns = detect_candlestick_patterns(df)
    assert any(p["pattern"] == "Doji" and p["bias"] == "NEUTRAL" for p in patterns)


def test_multi_horizon_biases_cover_requested_timelines():
    from app.tools.technical import _multi_horizon_outlook

    idx = pd.date_range("2025-01-01", periods=260, freq="B")
    close = pd.Series([100 + i * 0.25 for i in range(260)], index=idx, dtype=float)
    technical = {"rsi14": 58.0, "macd": 2.0, "macd_signal": 1.0}
    result = _multi_horizon_outlook(close, technical, [])

    assert list(result.keys()) == ["1W", "1M", "3M", "6M", "1Y"]
    assert all(result[h]["directional_bias"] in {"BULLISH", "NEUTRAL", "BEARISH"} for h in result)
    assert all(0 <= result[h]["confidence_pct"] <= 85 for h in result)
