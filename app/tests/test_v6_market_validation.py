from app.tools import market_validation


def test_india_prefers_official_nse_quote(monkeypatch):
    monkeypatch.setattr(market_validation, "get_json", lambda key: None)
    monkeypatch.setattr(market_validation, "set_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(market_validation, "_yahoo_quote", lambda s, m: {
        "source": "Yahoo Finance", "provider": "YAHOO", "price": 100.2, "currency": "INR", "market_state": "REGULAR"
    })
    monkeypatch.setattr(market_validation, "_nse_quote", lambda s: {
        "source": "NSE India", "provider": "NSE", "price": 100.0, "currency": "INR", "market_state": "OPEN"
    })
    result = market_validation.get_validated_quote("TEST", "IN", force_refresh=True)
    assert result["price"] == 100.0
    assert result["provider"] == "NSE"
    assert result["validation_status"] == "VERIFIED"
    assert result["max_difference_pct"] == 0.2
