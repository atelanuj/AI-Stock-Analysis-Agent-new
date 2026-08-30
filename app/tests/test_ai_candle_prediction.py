from app.services import candle_prediction


def _rows():
    rows = []
    for index in range(40):
        close = 100 + index * 0.1
        rows.append({
            "date": f"2026-07-{index + 1:02d}",
            "open": close - 0.2,
            "high": close + 0.8,
            "low": close - 0.8,
            "close": close,
            "volume": 1000 + index,
        })
    return rows


def _setup(monkeypatch):
    rows = _rows()
    monkeypatch.setattr(candle_prediction, "get_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(candle_prediction, "set_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(candle_prediction, "get_ohlcv_history", lambda *args, **kwargs: rows)
    monkeypatch.setattr(candle_prediction, "predict_next_candle", lambda *args, **kwargs: {
        "date": "2026-08-10",
        "open": 103.9,
        "high": 104.5,
        "low": 103.4,
        "close": 104.1,
        "direction": "BULLISH",
        "confidence_pct": 52,
    })
    return rows


def test_ai_generated_candle_is_used_when_valid(monkeypatch):
    _setup(monkeypatch)
    monkeypatch.setattr(candle_prediction, "synthesize_candle_prediction", lambda payload: {
        "open": 103.9,
        "high": 105.0,
        "low": 103.5,
        "close": 104.7,
        "confidence_pct": 68,
        "future_closes": [104.7, 105.0, 105.3, 105.6, 105.8],
        "chart_pattern": "Channel Up",
        "rationale": "Momentum remains constructive.",
    })
    result = candle_prediction.get_ai_candle_prediction("TEST", "US", force_refresh=True)
    assert result["ai_available"] is True
    assert result["prediction"]["source"] == "ai_generated"
    assert result["prediction"]["direction"] == "BULLISH"
    assert result["prediction"]["date"] == "2026-08-10"
    assert result["selected_pattern"] == "Channel Up"
    assert result["trend_bias"] == "BULLISH"
    assert len(result["future_trend"]) == 5


def test_invalid_ai_candle_uses_historical_fallback(monkeypatch):
    _setup(monkeypatch)
    monkeypatch.setattr(candle_prediction, "synthesize_candle_prediction", lambda payload: {
        "open": 103.9,
        "high": 90.0,
        "low": 120.0,
        "close": 104.7,
        "confidence_pct": 99,
    })
    result = candle_prediction.get_ai_candle_prediction("TEST", "US", force_refresh=True)
    assert result["ai_available"] is False
    assert result["prediction"]["source"] == "historical_pattern_fallback"


def test_chart_pattern_detector_finds_rising_channel():
    patterns = candle_prediction.detect_chart_patterns(_rows())
    assert patterns
    assert patterns[0]["name"] == "Channel Up"
    assert patterns[0]["bias"] == "BULLISH"
