from datetime import datetime, timezone
import pandas as pd
import yfinance as yf

from app.cache.redis_cache import get_json, set_json
from app.config import settings
from app.tools.data_provider import get_info
from app.tools.market_data import yahoo_symbol


def _to_iso(value):
    if value is None:
        return None
    try:
        if isinstance(value, pd.Timestamp):
            return value.to_pydatetime().isoformat()
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
        return str(value)
    except Exception:
        return str(value)


def _days_until(value):
    try:
        dt = pd.to_datetime(value, utc=True)
        now = pd.Timestamp.now(tz="UTC")
        return int((dt - now).total_seconds() // 86400)
    except Exception:
        return None


def get_corporate_events(symbol: str, market: str | None = None, force_refresh: bool = False) -> dict:
    """Best-effort upcoming company-event awareness from Yahoo Finance.

    Availability varies by ticker. This intentionally reports missing data rather than inventing events.
    """
    ys = yahoo_symbol(symbol, market)
    key = f"yf:v6:events:{ys}"
    if not force_refresh:
        cached = get_json(key)
        if isinstance(cached, dict) and "events" in cached:
            return cached
    ticker = yf.Ticker(ys)
    items = []
    try:
        cal = ticker.calendar
        if isinstance(cal, dict):
            earnings = cal.get("Earnings Date") or cal.get("EarningsDate")
            if isinstance(earnings, (list, tuple)):
                earnings = earnings[0] if earnings else None
            if earnings is not None:
                days = _days_until(earnings)
                if days is None or days >= -1:
                    items.append({
                        "type": "EARNINGS", "title": "Earnings / results", "date": _to_iso(earnings),
                        "days_until": days, "impact": "HIGH", "warning": "Earnings can cause event-driven volatility and invalidate short-term technical setups.",
                    })
            exdiv = cal.get("Ex-Dividend Date") or cal.get("Ex-DividendDate")
            if exdiv is not None:
                days = _days_until(exdiv)
                if days is None or days >= -1:
                    items.append({"type":"DIVIDEND","title":"Ex-dividend date","date":_to_iso(exdiv),"days_until":days,"impact":"MEDIUM","warning":"Price can mechanically adjust around the ex-dividend date."})
    except Exception:
        pass

    try:
        info = get_info(symbol, market, force_refresh=force_refresh)
        exdiv = info.get("exDividendDate")
        if exdiv and not any(x["type"] == "DIVIDEND" for x in items):
            days = _days_until(exdiv)
            if days is None or days >= -1:
                items.append({"type":"DIVIDEND","title":"Ex-dividend date","date":_to_iso(exdiv),"days_until":days,"impact":"MEDIUM","warning":"Price can mechanically adjust around the ex-dividend date."})
    except Exception:
        pass

    items.sort(key=lambda x: (99999 if x.get("days_until") is None else x["days_until"]))
    upcoming = [x for x in items if x.get("days_until") is None or x["days_until"] <= 30]
    result = {
        "events": upcoming,
        "high_impact_soon": any(x.get("impact") == "HIGH" and x.get("days_until") is not None and 0 <= x["days_until"] <= 7 for x in upcoming),
        "note": "Company-event availability depends on the data provider. Macro events such as RBI/Fed meetings are not fabricated when no calendar feed is configured.",
    }
    set_json(key, result, ttl=settings.events_cache_ttl_seconds)
    return result
