import sys
import types

sys.modules.setdefault("yfinance", types.SimpleNamespace())

from app.tools.news import _extract_url


def test_extracts_clickable_news_url():
    content = {"canonicalUrl": {"url": "https://example.com/full-story"}}
    assert _extract_url(content, {}) == "https://example.com/full-story"


def test_rejects_non_http_news_url():
    content = {"canonicalUrl": {"url": "javascript:alert(1)"}}
    assert _extract_url(content, {}) is None
