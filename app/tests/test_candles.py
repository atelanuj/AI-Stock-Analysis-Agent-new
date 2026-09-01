import sys
import types
import pandas as pd

sys.modules.setdefault("yfinance", types.SimpleNamespace())

from app.tools.technical import detect_candlestick_patterns, predict_next_candle, _multi_horizon_outlook, _risk_reward


def test_detects_bullish_engulfing():
    idx = pd.date_range("2026-01-01", periods=6, freq="D")
    df = pd.DataFrame({"Open":[105,103,101,100,99,96],"High":[106,104,102,101,100,103],"Low":[102,100,98,97,95,95],"Close":[103,101,99,98,96,102]}, index=idx)
    patterns = detect_candlestick_patterns(df, lookback=10)
    assert any(p["pattern"] == "Bullish Engulfing" for p in patterns)


def test_doji_is_neutral():
    idx = pd.date_range("2026-01-01", periods=3, freq="D")
    df = pd.DataFrame({"Open":[100,101,102.0],"High":[102,103,105.0],"Low":[99,100,99.0],"Close":[101,102,102.1]}, index=idx)
    patterns = detect_candlestick_patterns(df)
    assert any(p["pattern"] == "Doji" and p["bias"] == "NEUTRAL" for p in patterns)


def test_multi_horizon_biases_and_dynamic_levels():
    idx = pd.date_range("2021-01-01", periods=1300, freq="B")
    close = pd.Series([100 + i * 0.08 + (i % 9 - 4) * 0.15 for i in range(1300)], index=idx, dtype=float)
    hist = pd.DataFrame({"High":close+1.2,"Low":close-1.1,"Close":close}, index=idx)
    technical = {"rsi14":58.0,"macd":2.0,"macd_signal":1.0,"volume":{"relative_volume":1.4}}
    result = _multi_horizon_outlook(close, technical, [], hist, 2.0)
    assert list(result.keys()) == ["1D","1W","1M","3M","6M","1Y","3Y","5Y"]
    assert result["1D"]["lookback_sessions"] == 1
    assert result["1W"]["lookback_sessions"] == 5
    assert result["1M"]["lookback_sessions"] == 21
    assert result["3Y"]["lookback_sessions"] == 756
    assert result["5Y"]["lookback_sessions"] == 1260
    assert all(0 <= result[h]["signal_agreement_pct"] <= 100 for h in result)
    assert all("levels" in result[h] for h in result)
    assert all("risk_reward" in result[h] for h in result)
    assert all("breakout" in result[h] for h in result)


def test_risk_reward_has_invalidation_and_ratio():
    levels={"nearest_support":{"low":95,"center":96},"nearest_resistance":{"high":110,"center":108},"major_support":None,"major_resistance":None}
    rr=_risk_reward(100,"BULLISH",levels,2)
    assert rr["invalidation_level"] < 100
    assert rr["target_reference"] > 100
    assert rr["risk_reward_ratio"] > 0


def test_next_candle_projection_uses_historical_shape_analogs():
    idx = pd.date_range("2026-01-01", periods=64, freq="B")
    rows = []
    previous = 100.0
    body_pattern = [-0.006, 0.001, 0.009, 0.014]
    for pos, date in enumerate(idx):
        open_price = previous * (1 + (0.001 if pos % 4 == 3 else 0))
        close = open_price * (1 + body_pattern[pos % 4])
        high = max(open_price, close) * 1.004
        low = min(open_price, close) * 0.996
        rows.append({"date": date.strftime("%Y-%m-%d"), "open": open_price, "high": high, "low": low, "close": close, "volume": 1000 + pos})
        previous = close

    projection = predict_next_candle(rows[:-1], "1d")
    assert projection is not None
    assert projection["date"] == rows[-1]["date"]
    assert projection["analogs_used"] > 0
    assert projection["low"] <= min(projection["open"], projection["close"])
    assert projection["high"] >= max(projection["open"], projection["close"])
    assert 35 <= projection["confidence_pct"] <= 85
    assert "historical" in projection["note"].lower()


def test_next_candle_projection_requires_enough_history():
    assert predict_next_candle([], "1d") is None
