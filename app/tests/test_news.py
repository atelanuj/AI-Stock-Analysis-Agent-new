import sys
import types
sys.modules.setdefault("yfinance", types.SimpleNamespace())
from app.tools.news import _extract_url, _classify

def test_extracts_clickable_news_url():
    assert _extract_url({"canonicalUrl":{"url":"https://example.com/full-story"}}, {}) == "https://example.com/full-story"

def test_rejects_non_http_news_url():
    assert _extract_url({"canonicalUrl":{"url":"javascript:alert(1)"}}, {}) is None

def test_earnings_news_is_high_impact():
    impact, sentiment, category = _classify("Company earnings profit beats guidance")
    assert impact == "HIGH"
    assert category == "EARNINGS"
    assert sentiment in {"POSITIVE","MIXED"}
