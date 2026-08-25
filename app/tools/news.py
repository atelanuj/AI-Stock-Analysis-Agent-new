from datetime import datetime, timezone
from urllib.parse import urlparse
import re
import yfinance as yf

from app.tools.market_data import yahoo_symbol

_HIGH = re.compile(r"earnings|results|profit|loss|guidance|merger|acquisition|acquire|lawsuit|fraud|investigation|regulator|sec\b|sebi\b|fda\b|bankruptcy|default|downgrade|upgrade|layoff|ceo|cfo|dividend|buyback|split|offering", re.I)
_MED = re.compile(r"contract|partnership|launch|product|analyst|rating|target|order|expansion|investment|stake|approval", re.I)
_NEG = re.compile(r"falls|drops|decline|loss|miss|cuts|downgrade|lawsuit|fraud|investigation|warning|weak|default|bankruptcy|layoff", re.I)
_POS = re.compile(r"beats|rises|growth|profit|upgrade|record|wins|approval|buyback|raises guidance|strong|expansion", re.I)


def _extract_url(content: dict, item: dict) -> str | None:
    candidates = [content.get("canonicalUrl"), content.get("clickThroughUrl"), content.get("link"), item.get("link") if isinstance(item, dict) else None]
    for candidate in candidates:
        if isinstance(candidate, dict): candidate = candidate.get("url")
        if isinstance(candidate, str):
            candidate = candidate.strip(); parsed = urlparse(candidate)
            if parsed.scheme in {"http", "https"} and parsed.netloc: return candidate
    return None


def _classify(text: str) -> tuple[str, str, str]:
    text = text or ""
    if _HIGH.search(text): importance = "HIGH"
    elif _MED.search(text): importance = "MEDIUM"
    else: importance = "LOW"
    pos, neg = bool(_POS.search(text)), bool(_NEG.search(text))
    sentiment = "MIXED" if pos and neg else "POSITIVE" if pos else "NEGATIVE" if neg else "NEUTRAL"
    lower = text.lower()
    if any(x in lower for x in ["earnings", "results", "profit", "revenue", "guidance"]): category = "EARNINGS"
    elif any(x in lower for x in ["merger", "acquisition", "acquire", "stake"]): category = "M&A"
    elif any(x in lower for x in ["lawsuit", "regulator", "sec", "sebi", "fda", "investigation"]): category = "REGULATORY"
    elif any(x in lower for x in ["dividend", "buyback", "split", "offering"]): category = "CAPITAL ACTION"
    elif any(x in lower for x in ["analyst", "rating", "target", "upgrade", "downgrade"]): category = "ANALYST"
    else: category = "GENERAL"
    return importance, sentiment, category


def get_news(symbol: str, market: str | None = None, limit: int = 10) -> list[dict]:
    try: items = yf.Ticker(yahoo_symbol(symbol, market)).news or []
    except Exception: items = []
    results = []
    for item in items[:limit]:
        if not isinstance(item, dict): continue
        nested = item.get("content"); content = nested if isinstance(nested, dict) else item
        title = content.get("title"); provider = content.get("provider")
        publisher = provider.get("displayName") if isinstance(provider, dict) else content.get("publisher")
        publish_time = content.get("pubDate") or content.get("providerPublishTime")
        summary = content.get("summary") or content.get("description"); url = _extract_url(content, item)
        if isinstance(publish_time, (int, float)): publish_time = datetime.fromtimestamp(publish_time, tz=timezone.utc).isoformat()
        if title:
            importance, sentiment, category = _classify(f"{title} {summary or ''}")
            results.append({"headline":title,"publisher":publisher,"published_at":publish_time,"summary":summary,"url":url,"importance":importance,"sentiment":sentiment,"category":category})
    return results
