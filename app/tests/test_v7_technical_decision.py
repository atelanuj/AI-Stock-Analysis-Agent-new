from app.services.technical_decision import build_technical_decision


def _levels():
    return {
        "nearest_support": {"low": 96.0, "high": 98.0, "center": 97.0, "touches": 3, "strength": 3},
        "major_support": {"low": 92.0, "high": 95.0, "center": 93.5, "touches": 5, "strength": 5},
        "nearest_resistance": {"low": 108.0, "high": 110.0, "center": 109.0, "touches": 3, "strength": 3},
        "major_resistance": {"low": 114.0, "high": 117.0, "center": 115.5, "touches": 5, "strength": 5},
    }


def _technical(direction="BULLISH"):
    biases = {}
    for h in ["1D", "1W", "1M", "3M", "6M", "1Y"]:
        biases[h] = {
            "directional_bias": direction,
            "signal_agreement_pct": 82,
            "levels": _levels(),
            "risk_reward": {
                "entry_reference": 100.0,
                "target_reference": 109.0 if direction == "BULLISH" else 97.0,
                "invalidation_level": 96.0 if direction == "BULLISH" else 110.0,
            },
            "breakout": {"status": "BREAKOUT WATCH" if direction == "BULLISH" else "BREAKDOWN WATCH"},
        }
    return {
        "price": 100.0,
        "atr14": 2.0,
        "rsi14": 58.0 if direction == "BULLISH" else 37.0,
        "macd": 2.0 if direction == "BULLISH" else -2.0,
        "macd_signal": 1.0 if direction == "BULLISH" else -1.0,
        "above_vwap20": direction == "BULLISH",
        "volume": {"relative_volume": 1.5},
        "market_regime": {"regime": "TRENDING UP" if direction == "BULLISH" else "TRENDING DOWN", "trend_strength": "STRONG"},
        "trend_alignment": {"dominant": direction, "alignment_pct": 100},
        "relative_strength": {"horizons": {h: {"relative_strength_pct": 3.0 if direction == "BULLISH" else -3.0} for h in biases}},
        "candlestick_patterns": [{"bias": direction, "strength": 2, "pattern": "Synthetic"}],
        "timeline_biases": biases,
    }


def test_v7_buy_setup_has_target_above_and_risk_below():
    result = build_technical_decision(_technical("BULLISH"), "1D")
    assert result["deterministic_recommendation"] == "BUY"
    assert result["setup"]["target_zone"]["mid"] > 100
    assert result["setup"]["risk_control_level"] < 100
    assert result["horizon"] == "1D"


def test_v7_sell_setup_has_target_below_and_risk_above():
    result = build_technical_decision(_technical("BEARISH"), "1M")
    assert result["deterministic_recommendation"] == "SELL"
    assert result["setup"]["target_zone"]["mid"] < 100
    assert result["setup"]["risk_control_level"] > 100


def test_ai_rule_disagreement_downgrades_final_action_to_hold(monkeypatch):
    from app.services import technical_decision as td
    technical = _technical("BULLISH")
    monkeypatch.setattr(td, "analyze_stock_core", lambda *a, **k: {"evidence": {"technical": technical}})
    monkeypatch.setattr(td, "synthesize_technical_decision", lambda payload: {
        "recommendation": "SELL",
        "confidence": "medium",
        "summary": "Conflicting synthetic model view",
        "confirming_signals": [],
        "conflicting_signals": ["Synthetic conflict"],
    })
    monkeypatch.setattr(td, "set_json", lambda *a, **k: None)
    result = td.get_technical_ai_decision("TEST", "IN", "1D", force_refresh=True)
    assert result["ai_recommendation"] == "SELL"
    assert result["deterministic_recommendation"] == "BUY"
    assert result["recommendation"] == "HOLD"
    assert result["consensus"] is False


def test_nemotron_selects_target_and_stop_from_validated_candidates(monkeypatch):
    from app.services import technical_decision as td
    technical = _technical("BULLISH")
    monkeypatch.setattr(td, "analyze_stock_core", lambda *a, **k: {"evidence": {"technical": technical}})
    monkeypatch.setattr(td, "synthesize_technical_decision", lambda payload: {
        "recommendation": "BUY",
        "confidence": "high",
        "summary": "Validated bullish setup",
        "confirming_signals": ["Synthetic confirmation"],
        "conflicting_signals": [],
        "setup_direction": "BULLISH",
        "target_candidate_id": "nearest_resistance_center",
        "stop_candidate_id": "nearest_support_low",
        "level_rationale": "Nearest resistance is the objective and support defines risk.",
    })
    monkeypatch.setattr(td, "set_json", lambda *a, **k: None)
    result = td.get_technical_ai_decision("TEST", "IN", "1D", force_refresh=True)
    assert result["setup"]["level_source"] == "ai_selected"
    assert result["setup"]["target_zone"]["mid"] == 109.0
    assert result["setup"]["risk_control_level"] == 96.0
    assert result["setup"]["risk_reward_ratio"] == 2.25


def test_invalid_ai_level_pair_uses_validated_fallback(monkeypatch):
    from app.services import technical_decision as td
    technical = _technical("BULLISH")
    monkeypatch.setattr(td, "analyze_stock_core", lambda *a, **k: {"evidence": {"technical": technical}})
    monkeypatch.setattr(td, "synthesize_technical_decision", lambda payload: {
        "recommendation": "BUY",
        "confidence": "medium",
        "summary": "Invalid synthetic pair",
        "confirming_signals": [],
        "conflicting_signals": [],
        "setup_direction": "BULLISH",
        "target_candidate_id": "nearest_support_center",
        "stop_candidate_id": "nearest_resistance_center",
        "level_rationale": "Intentionally invalid for the test.",
    })
    monkeypatch.setattr(td, "set_json", lambda *a, **k: None)
    result = td.get_technical_ai_decision("TEST", "IN", "1D", force_refresh=True)
    assert result["setup"]["level_source"] == "deterministic_fallback"
    assert result["setup"]["target_zone"]["mid"] > result["setup"]["entry_reference"]
    assert result["setup"]["risk_control_level"] < result["setup"]["entry_reference"]
