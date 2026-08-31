from app.services import intraday


def _core():
    return {
        "symbol": "TEST",
        "market": "IN",
        "interval": "5m",
        "price": 100.0,
        "bars": [{"date": "2026-08-28T15:25:00+05:30", "open": 99.5, "high": 100.5, "low": 99.0, "close": 100.0}],
        "bar_count": 1,
        "session": {"high": 102.0, "low": 96.0},
        "indicators": {"vwap": 99.0, "bar_atr": 2.0},
        "opening_range": {"high": 101.0, "low": 97.0},
        "bias": "BULLISH",
        "deterministic_action": "BUY",
        "technical_target": 103.0,
        "risk_control": 98.0,
        "next_candle_pattern_projection": {
            "date": "2026-08-28T15:30:00+05:30",
            "open": 100.0,
            "high": 101.2,
            "low": 99.6,
            "close": 100.8,
            "direction": "BULLISH",
            "method": "Synthetic historical analog",
        },
        "chart_patterns": [{
            "name": "Bull Flag", "bias": "BULLISH", "confidence_pct": 74,
            "start_date": "2026-08-28T14:30:00+05:30", "end_date": "2026-08-28T15:25:00+05:30",
            "upper_start": 101.0, "upper_end": 100.5, "lower_start": 99.5, "lower_end": 99.2,
            "note": "Synthetic continuation pattern",
        }],
        "selected_pattern": "Bull Flag",
        "pattern_catalog": ["Bull Flag", "Bear Flag"],
    }


def test_intraday_ai_selects_validated_target_stop_and_candle(monkeypatch):
    core = _core()
    monkeypatch.setattr(intraday, "get_intraday_analysis", lambda *a, **k: core)
    monkeypatch.setattr(intraday, "get_json", lambda *a, **k: None)
    monkeypatch.setattr(intraday, "set_json", lambda *a, **k: None)
    monkeypatch.setattr(intraday, "synthesize_intraday_decision", lambda payload: {
        "recommendation": "BUY",
        "confidence": "high",
        "summary": "Synthetic bullish continuation",
        "confirming_signals": [],
        "risks": [],
        "setup_direction": "BULLISH",
        "target_candidate_id": "technical_target",
        "stop_candidate_id": "risk_control",
        "chart_pattern": "Bull Flag",
        "next_candle": {"open": 100.0, "high": 101.2, "low": 99.6, "close": 100.8},
        "next_candle_confidence": "medium",
        "level_rationale": "Validated test levels",
        "candle_rationale": "Validated test candle",
    })
    result = intraday.get_intraday_ai("TEST", "IN", "5m", force_refresh=True)
    assert result["ai_available"] is True
    assert result["level_source"] == "ai_selected"
    assert result["target"] == 103.0
    assert result["risk_control"] == 98.0
    assert result["next_candle_prediction"]["source"] == "ai_generated"
    assert result["next_candle_prediction"]["direction"] == "BULLISH"
    assert result["next_candle_prediction"]["confidence"] == "medium"
    assert result["selected_pattern"] == "Bull Flag"
    assert result["pattern_selection_source"] == "ai_selected"


def test_intraday_invalid_ai_choices_use_validated_fallback(monkeypatch):
    core = _core()
    monkeypatch.setattr(intraday, "get_intraday_analysis", lambda *a, **k: core)
    monkeypatch.setattr(intraday, "get_json", lambda *a, **k: None)
    monkeypatch.setattr(intraday, "set_json", lambda *a, **k: None)
    monkeypatch.setattr(intraday, "synthesize_intraday_decision", lambda payload: {
        "recommendation": "BUY",
        "confidence": "low",
        "summary": "Invalid synthetic choices",
        "confirming_signals": [],
        "risks": [],
        "setup_direction": "BULLISH",
        "target_candidate_id": "opening_range_low",
        "stop_candidate_id": "opening_range_high",
        "next_candle": {"open": 100.0, "high": 90.0, "low": 110.0, "close": 100.5},
    })
    result = intraday.get_intraday_ai("TEST", "IN", "5m", force_refresh=True)
    assert result["level_source"] == "deterministic_fallback"
    assert result["target"] == core["technical_target"]
    assert result["risk_control"] == core["risk_control"]
    assert result["next_candle_prediction"]["source"] == "validated_fallback"
    assert result["selected_pattern"] == "Bull Flag"


def test_intraday_ai_failure_is_explicitly_marked_unavailable(monkeypatch):
    core = _core()
    monkeypatch.setattr(intraday, "get_intraday_analysis", lambda *a, **k: core)
    monkeypatch.setattr(intraday, "get_json", lambda *a, **k: None)
    monkeypatch.setattr(intraday, "set_json", lambda *a, **k: None)

    def fail(_payload):
        raise RuntimeError("AI endpoint offline")

    monkeypatch.setattr(intraday, "synthesize_intraday_decision", fail)
    result = intraday.get_intraday_ai("TEST", "IN", "5m", force_refresh=True)
    assert result["ai_available"] is False
    assert result["level_source"] == "deterministic_fallback"
    assert "AI unavailable" in result["ai"]["summary"]
