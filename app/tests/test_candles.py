import sys
import types
import pandas as pd

sys.modules.setdefault("yfinance", types.SimpleNamespace())

from app.tools.technical import detect_candlestick_patterns, _multi_horizon_outlook, _risk_reward


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
    idx = pd.date_range("2025-01-01", periods=260, freq="B")
    close = pd.Series([100 + i * 0.25 + (i % 9 - 4) * 0.15 for i in range(260)], index=idx, dtype=float)
    hist = pd.DataFrame({"High":close+1.2,"Low":close-1.1,"Close":close}, index=idx)
    technical = {"rsi14":58.0,"macd":2.0,"macd_signal":1.0,"volume":{"relative_volume":1.4}}
    result = _multi_horizon_outlook(close, technical, [], hist, 2.0)
    assert list(result.keys()) == ["1D","1W","1M","3M","6M","1Y"]
    assert result["1D"]["lookback_sessions"] == 1
    assert result["1W"]["lookback_sessions"] == 5
    assert result["1M"]["lookback_sessions"] == 21
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
