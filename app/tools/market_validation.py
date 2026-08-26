"""Best-effort quote validation across independent/public providers.

V6 keeps Yahoo Finance/yfinance for broad OHLC/fundamental coverage but no
longer treats the latest daily Close as an authoritative live quote.  A light
quote snapshot is fetched separately, and where possible compared with an
independent provider:

* India: official NSE quote-equity endpoint (preferred when reachable)
* US: Stooq end-of-day CSV as an independent comparison point
* All markets: Yahoo chart endpoint as the low-latency fallback/current quote

All secondary providers are best-effort.  Provider failure must never make the
analysis endpoint unavailable.
"""
from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor
import io
import math
from datetime import datetime, timezone
from urllib.parse import quote

import requests

from app.cache.redis_cache import get_json, set_json
from app.config import settings
from app.tools.market_data import yahoo_symbol

_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}


def _finite(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _iso_from_epoch(value):
    try:
        if value is None:
            return None
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    except Exception:
        return None


def _pct_diff(a, b):
    a, b = _finite(a), _finite(b)
    if a is None or b is None or b == 0:
        return None
    return abs(a - b) / abs(b) * 100


def _yahoo_quote(symbol: str, market: str) -> dict:
    ys = yahoo_symbol(symbol, market)
    key = f"quote:v6:yahoo:{ys}"
    cached = get_json(key)
    if isinstance(cached, dict) and cached:
        return cached
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(ys, safe='')}"
    params = {
        "range": "1d",
        "interval": "1m",
        "includePrePost": "false",
        "events": "div,splits",
    }
    response = requests.get(url, params=params, timeout=settings.quote_timeout_seconds, headers=_BROWSER_HEADERS)
    response.raise_for_status()
    payload = response.json()
    result = ((payload.get("chart") or {}).get("result") or [None])[0] or {}
    meta = result.get("meta") or {}
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    quote_rows = (indicators.get("quote") or [{}])[0] or {}
    closes = quote_rows.get("close") or []
    last_bar = next(((_finite(c), ts) for c, ts in zip(reversed(closes), reversed(timestamps)) if _finite(c) is not None), (None, None))
    price = _finite(meta.get("regularMarketPrice")) or last_bar[0]
    out = {
        "source": "Yahoo Finance",
        "provider": "YAHOO",
        "price": price,
        "previous_close": _finite(meta.get("chartPreviousClose") or meta.get("previousClose")),
        "currency": meta.get("currency"),
        "exchange": meta.get("exchangeName") or meta.get("fullExchangeName"),
        "exchange_timezone": meta.get("exchangeTimezoneName"),
        "market_state": meta.get("marketState"),
        "as_of": _iso_from_epoch(meta.get("regularMarketTime") or last_bar[1]),
        "is_realtime": True,
    }
    set_json(key, out, ttl=settings.quote_cache_ttl_seconds)
    return out


def _nse_quote(symbol: str) -> dict:
    clean = symbol.strip().upper()
    if clean.endswith(".NS"):
        clean = clean[:-3]
    key = f"quote:v6:nse:{clean}"
    cached = get_json(key)
    if isinstance(cached, dict) and cached:
        return cached

    session = requests.Session()
    session.headers.update({
        **_BROWSER_HEADERS,
        "Referer": f"https://www.nseindia.com/get-quotes/equity?symbol={quote(clean)}",
    })
    # NSE commonly requires cookies from the landing page before API access.
    session.get("https://www.nseindia.com", timeout=settings.quote_timeout_seconds)
    response = session.get(
        "https://www.nseindia.com/api/quote-equity",
        params={"symbol": clean},
        timeout=settings.quote_timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    pi = payload.get("priceInfo") or {}
    metadata = payload.get("metadata") or {}
    out = {
        "source": "NSE India",
        "provider": "NSE",
        "price": _finite(pi.get("lastPrice")),
        "previous_close": _finite(pi.get("previousClose")),
        "open": _finite(pi.get("open")),
        "day_high": _finite((pi.get("intraDayHighLow") or {}).get("max")),
        "day_low": _finite((pi.get("intraDayHighLow") or {}).get("min")),
        "currency": "INR",
        "exchange": "NSE",
        "market_state": metadata.get("status"),
        "as_of": metadata.get("lastUpdateTime") or payload.get("metadata", {}).get("lastUpdateTime"),
        "is_realtime": True,
    }
    if out["price"] is not None:
        set_json(key, out, ttl=settings.quote_cache_ttl_seconds)
    return out


def _stooq_quote(symbol: str) -> dict:
    """Independent US EOD comparison.  This is not treated as an intraday quote."""
    clean = symbol.strip().upper()
    key = f"quote:v6:stooq:{clean}"
    cached = get_json(key)
    if isinstance(cached, dict) and cached:
        return cached
    stooq_symbol = clean.lower()
    if not stooq_symbol.endswith(".us"):
        stooq_symbol = f"{stooq_symbol}.us"
    response = requests.get(
        "https://stooq.com/q/d/l/",
        params={"s": stooq_symbol, "i": "d"},
        timeout=settings.quote_timeout_seconds,
        headers={"User-Agent": _BROWSER_HEADERS["User-Agent"]},
    )
    response.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(response.text)))
    if not rows:
        return {}
    row = rows[-1]
    out = {
        "source": "Stooq",
        "provider": "STOOQ",
        "price": _finite(row.get("Close")),
        "open": _finite(row.get("Open")),
        "day_high": _finite(row.get("High")),
        "day_low": _finite(row.get("Low")),
        "currency": "USD",
        "exchange": "US EOD",
        "market_state": "EOD",
        "as_of": row.get("Date"),
        "is_realtime": False,
    }
    if out["price"] is not None:
        set_json(key, out, ttl=max(settings.quote_cache_ttl_seconds, 900))
    return out


def get_validated_quote(symbol: str, market: str, fallback_price: float | None = None, force_refresh: bool = False) -> dict:
    """Return a preferred quote plus source-comparison metadata.

    Provider requests are concurrent so cross-checking does not double page
    latency. For Indian equities an official NSE last price wins when available.
    For US equities Yahoo's current quote remains primary and Stooq is used as
    an independent EOD sanity check. Large differences are flagged, never
    silently averaged.
    """
    market = (market or "IN").upper()
    cache_key = f"quote:v6:validated:{market}:{symbol.strip().upper()}"
    if not force_refresh:
        cached = get_json(cache_key)
        if isinstance(cached, dict) and cached:
            return cached

    comparisons = []
    errors = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_yahoo = pool.submit(_yahoo_quote, symbol, market)
        f_secondary = pool.submit(_nse_quote if market == "IN" else _stooq_quote, symbol)
        try:
            yahoo = f_yahoo.result() or {}
        except Exception as exc:
            yahoo = {}; errors.append(f"Yahoo quote unavailable: {type(exc).__name__}")
        try:
            secondary = f_secondary.result() or {}
        except Exception as exc:
            secondary = {}; errors.append(f"{'NSE' if market == 'IN' else 'Stooq'} validation unavailable: {type(exc).__name__}")

    if yahoo.get("price") is not None:
        comparisons.append(yahoo)
    if secondary.get("price") is not None:
        comparisons.append(secondary)

    if market == "IN":
        preferred = secondary if secondary.get("price") is not None else yahoo
    else:
        preferred = yahoo if yahoo.get("price") is not None else secondary

    if preferred.get("price") is None and _finite(fallback_price) is not None:
        preferred = {
            "source": "Historical OHLC fallback", "provider": "OHLC_FALLBACK",
            "price": _finite(fallback_price), "as_of": None, "is_realtime": False,
        }
        comparisons.append(preferred)

    primary_price = _finite(preferred.get("price"))
    diffs = []
    for item in comparisons:
        if item is preferred or item.get("price") is None:
            continue
        diff = _pct_diff(item.get("price"), primary_price)
        item["difference_vs_primary_pct"] = round(diff, 3) if diff is not None else None
        # Stooq is EOD. During a live US session its delta is informational, not
        # an accuracy failure. NSE vs Yahoo is a true same-market cross-check.
        live_state = str(preferred.get("market_state") or "").upper()
        stale_eod_comparison = item.get("provider") == "STOOQ" and live_state not in {"CLOSED", "POST", "POSTPOST", "EOD"}
        if diff is not None and not stale_eod_comparison:
            diffs.append(diff)

    max_diff = max(diffs) if diffs else None
    independent_count = len({x.get("provider") for x in comparisons if x.get("provider")})
    if primary_price is None:
        status = "UNAVAILABLE"
    elif independent_count < 2:
        status = "SINGLE_SOURCE"
    elif max_diff is not None and max_diff > settings.quote_warning_difference_pct:
        status = "CHECK"
    else:
        status = "VERIFIED"

    out = {
        "price": primary_price, "source": preferred.get("source") or "Unknown",
        "provider": preferred.get("provider"), "as_of": preferred.get("as_of"),
        "currency": preferred.get("currency"), "market_state": preferred.get("market_state"),
        "validation_status": status,
        "max_difference_pct": round(max_diff, 3) if max_diff is not None else None,
        "sources": comparisons, "errors": errors,
        "note": "Cross-source validation is best-effort. Independent providers can differ due to delay, session state, adjustments or exchange timestamps.",
    }
    set_json(cache_key, out, ttl=settings.quote_cache_ttl_seconds)
    return out
