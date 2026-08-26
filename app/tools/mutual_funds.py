import requests
import yfinance as yf
from cachetools import TTLCache, cached

_search_cache = TTLCache(maxsize=200, ttl=3600)
_mfapi_cache = TTLCache(maxsize=500, ttl=3600)

_HEADERS = {"User-Agent": "Mozilla/5.0 StockAIAgent/7.0"}


@cached(_search_cache)
def _all_indian_funds() -> list[dict]:
    response = requests.get("https://api.mfapi.in/mf", timeout=15, headers=_HEADERS)
    response.raise_for_status()
    return response.json()


def search_indian_mf(query: str, limit: int = 20) -> list[dict]:
    query = query.strip().lower()
    if not query:
        return []
    try:
        results = []
        for fund in _all_indian_funds():
            name = fund.get("schemeName", "")
            if query in name.lower():
                results.append({
                    "identifier": str(fund.get("schemeCode")),
                    "scheme_code": str(fund.get("schemeCode")),
                    "scheme_name": name,
                    "market": "IN",
                    "quote_type": "MUTUALFUND",
                })
                if len(results) >= limit:
                    break
        return results
    except Exception as exc:
        print(f"Error searching Indian MFs: {exc}")
        return []


@cached(_search_cache)
def search_us_funds(query: str, limit: int = 20) -> list[dict]:
    query = query.strip()
    if not query:
        return []
    try:
        response = requests.get(
            "https://query2.finance.yahoo.com/v1/finance/search",
            params={"q": query, "quotesCount": max(limit * 2, 20), "newsCount": 0},
            timeout=15,
            headers=_HEADERS,
        )
        response.raise_for_status()
        data = response.json()
        results = []
        for quote in data.get("quotes", []):
            quote_type = str(quote.get("quoteType", "")).upper()
            if quote_type not in {"ETF", "MUTUALFUND"}:
                continue
            symbol = quote.get("symbol")
            if not symbol:
                continue
            results.append({
                "identifier": symbol,
                "symbol": symbol,
                "scheme_name": quote.get("longname") or quote.get("shortname") or symbol,
                "market": "US",
                "quote_type": quote_type,
            })
            if len(results) >= limit:
                break
        return results
    except Exception as exc:
        print(f"Error searching US funds: {exc}")
        return []


@cached(_mfapi_cache)
def get_indian_mf_data(scheme_code: str) -> dict:
    response = requests.get(f"https://api.mfapi.in/mf/{scheme_code}", timeout=15, headers=_HEADERS)
    response.raise_for_status()
    payload = response.json()
    meta = payload.get("meta", {})
    nav_data = payload.get("data", [])
    if not nav_data:
        raise ValueError(f"No NAV data found for Indian scheme {scheme_code}")

    history = [
        {"date": item["date"], "nav": float(item["nav"])}
        for item in nav_data[:1600]
        if item.get("date") and item.get("nav")
    ]
    return {
        "identifier": str(scheme_code),
        "scheme_code": str(scheme_code),
        "fund_house": meta.get("fund_house"),
        "scheme_type": meta.get("scheme_type"),
        "scheme_category": meta.get("scheme_category"),
        "scheme_name": meta.get("scheme_name"),
        "current_nav": float(nav_data[0]["nav"]),
        "date": nav_data[0]["date"],
        "history": history,
        "market": "IN",
        "currency": "INR",
        "quote_type": "MUTUALFUND",
        "expense_ratio": None,
        "total_assets": None,
    }


def get_us_fund_data(symbol: str) -> dict:
    symbol = symbol.strip().upper()
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="5y", auto_adjust=True)
    if hist.empty:
        raise ValueError(f"No US mutual fund/ETF data found for {symbol}")

    info = ticker.info or {}
    quote_type = str(info.get("quoteType", "")).upper()
    if quote_type and quote_type not in {"ETF", "MUTUALFUND"}:
        raise ValueError(f"{symbol} is reported as {quote_type}, not a mutual fund/ETF")

    close = hist["Close"].dropna()
    history = [{"date": d.strftime("%d-%m-%Y"), "nav": round(float(p), 4)} for d, p in close.items()]
    history.reverse()

    return {
        "identifier": symbol,
        "symbol": symbol,
        "fund_house": info.get("fundFamily") or "Unknown",
        "scheme_type": quote_type or "FUND",
        "scheme_category": info.get("category") or quote_type or "Fund",
        "scheme_name": info.get("longName") or info.get("shortName") or symbol,
        "current_nav": float(close.iloc[-1]),
        "date": history[0]["date"] if history else None,
        "history": history,
        "expense_ratio": info.get("annualReportExpenseRatio"),
        "total_assets": info.get("totalAssets"),
        "yield": info.get("yield"),
        "market": "US",
        "currency": info.get("currency") or "USD",
        "quote_type": quote_type or "FUND",
    }


# Backward-compatible V2 name.
def get_us_etf_data(symbol: str) -> dict:
    return get_us_fund_data(symbol)
