from datetime import datetime, timezone
from urllib.parse import urlparse

import yfinance as yf

from app.tools.market_data import yahoo_symbol


def _extract_url(content: dict, item: dict) -> str | None:
    """Handle the URL shapes returned by different yfinance/Yahoo news payloads."""
    candidates = [
        content.get("canonicalUrl"),
        content.get("clickThroughUrl"),
        content.get("link"),
        item.get("link") if isinstance(item, dict) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            candidate = candidate.get("url")
        if isinstance(candidate, str):
            candidate = candidate.strip()
            parsed = urlparse(candidate)
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                return candidate
    return None


def get_news(symbol: str, market: str | None = None, limit: int = 10) -> list[dict]:
    try:
        items = yf.Ticker(yahoo_symbol(symbol, market)).news or []
    except Exception:
        items = []

    results = []
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        nested = item.get("content")
        content = nested if isinstance(nested, dict) else item
        title = content.get("title")
        provider = content.get("provider")
        publisher = provider.get("displayName") if isinstance(provider, dict) else content.get("publisher")
        publish_time = content.get("pubDate") or content.get("providerPublishTime")
        summary = content.get("summary") or content.get("description")
        url = _extract_url(content, item)

        if isinstance(publish_time, (int, float)):
            publish_time = datetime.fromtimestamp(publish_time, tz=timezone.utc).isoformat()

        if title:
            results.append({
                "headline": title,
                "publisher": publisher,
                "published_at": publish_time,
                "summary": summary,
                "url": url,
            })
    return results
