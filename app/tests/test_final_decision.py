from app.services import final_decision


def _payload():
    return {
        "symbol": "TEST",
        "market": "IN",
        "horizon": "3M",
        "scores": {"overall": 75, "fundamental": 80, "technical": 72, "valuation": 60, "risk": 70},
        "market_data": {"current_price": 100},
        "fundamentals": {"return_on_equity": 0.18},
        "technical": {"rsi14": 58, "volume": {"relative_volume": 1.4}},
        "next_candle_prediction": {"direction": "BULLISH", "confidence_pct": 55},
        "technical_decision": {"recommendation": "BUY", "setup": {"risk_reward_ratio": 2.0}},
        "stock_synthesis": {"rating": "BUY", "confidence": "medium"},
        "news": [],
        "events": {},
    }


def test_final_decision_returns_exact_buy_hold_sell_contract(monkeypatch):
    monkeypatch.setattr(final_decision, "get_json", lambda *a, **k: None)
    monkeypatch.setattr(final_decision, "set_json", lambda *a, **k: None)
    monkeypatch.setattr(final_decision, "synthesize_final_stock_decision", lambda payload: {
        "decision": "BUY",
        "confidence": "medium",
        "summary": "Quality and technical timing align.",
        "key_drivers": ["Strong fundamentals", "Constructive trend"],
        "key_risks": ["Projected candle confidence is moderate"],
    })
    result = final_decision.get_final_stock_decision(_payload(), force_refresh=True)
    assert result["decision"] == "BUY"
    assert result["confidence"] == "medium"
    assert result["source"] == "nemotron_all_evidence"
    assert len(result["key_drivers"]) == 2


def test_final_decision_rejects_noncanonical_ai_label(monkeypatch):
    monkeypatch.setattr(final_decision, "get_json", lambda *a, **k: None)
    monkeypatch.setattr(final_decision, "set_json", lambda *a, **k: None)
    monkeypatch.setattr(final_decision, "synthesize_final_stock_decision", lambda payload: {
        "decision": "STRONG BUY",
        "confidence": "extreme",
        "summary": "Synthetic invalid labels",
        "key_drivers": list(range(8)),
        "key_risks": [],
    })
    result = final_decision.get_final_stock_decision(_payload(), force_refresh=True)
    assert result["decision"] == "HOLD"
    assert result["confidence"] == "low"
    assert len(result["key_drivers"]) == 4
