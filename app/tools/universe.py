import csv
import io
from cachetools import TTLCache, cached
import requests
from bs4 import BeautifulSoup

_HEADERS = {"User-Agent": "Mozilla/5.0 StockAIAgent/5.0"}
_cache = TTLCache(maxsize=20, ttl=21600)

_FALLBACK_IN = ["RELIANCE","TCS","HDFCBANK","ICICIBANK","INFY","BHARTIARTL","SBIN","LT","ITC","HINDUNILVR","KOTAKBANK","AXISBANK","BAJFINANCE","MARUTI","SUNPHARMA","TITAN","NTPC","ONGC","WIPRO","HCLTECH","TATAMOTORS","M&M","POWERGRID","ULTRACEMCO","ASIANPAINT"]
_FALLBACK_US = ["AAPL","MSFT","NVDA","AMZN","GOOGL","META","BRK-B","AVGO","TSLA","JPM","LLY","V","WMT","MA","XOM","ORCL","COST","NFLX","AMD","CRM","JNJ","PG","HD","BAC","KO"]


def _nse_csv(filename: str) -> list[str]:
    r = requests.get(f"https://nsearchives.nseindia.com/content/indices/{filename}", headers=_HEADERS, timeout=15); r.raise_for_status()
    rows = csv.DictReader(io.StringIO(r.text)); return [str(row.get("Symbol", "")).strip().upper() for row in rows if row.get("Symbol")]


def _wiki_symbols(url: str, table_id: str | None = None) -> list[str]:
    r = requests.get(url, headers=_HEADERS, timeout=15); r.raise_for_status(); soup = BeautifulSoup(r.text, "html.parser")
    table = soup.find("table", id=table_id) if table_id else soup.find("table", class_="wikitable")
    if not table: return []
    symbols = []
    for tr in table.find_all("tr")[1:]:
        cells = tr.find_all(["td","th"])
        if not cells: continue
        sym = cells[0].get_text(" ", strip=True).replace(".", "-")
        if sym and len(sym) < 12: symbols.append(sym)
    return symbols


@cached(_cache)
def get_stock_universe(market: str, universe: str = "POPULAR") -> list[str]:
    market, universe = market.upper(), universe.upper()
    try:
        if market == "IN":
            if universe == "NIFTY50": return _nse_csv("ind_nifty50list.csv")
            if universe == "NIFTY100": return _nse_csv("ind_nifty100list.csv")
            if universe == "NIFTY500": return _nse_csv("ind_nifty500list.csv")
            return _FALLBACK_IN
        if universe == "SP500":
            return _wiki_symbols("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", "constituents")
        if universe == "NASDAQ100":
            syms = _wiki_symbols("https://en.wikipedia.org/wiki/Nasdaq-100")
            return syms[:100] if syms else _FALLBACK_US
        if universe == "DOW30":
            syms = _wiki_symbols("https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average")
            return syms[:30] if syms else _FALLBACK_US
        return _FALLBACK_US
    except Exception:
        return _FALLBACK_IN if market == "IN" else _FALLBACK_US


def get_default_stock_universe(market: str) -> list[str]:
    return get_stock_universe(market, "POPULAR")


def available_universes(market: str) -> list[dict]:
    if market.upper() == "IN":
        return [{"id":"POPULAR","name":"Popular"},{"id":"NIFTY50","name":"NIFTY 50"},{"id":"NIFTY100","name":"NIFTY 100"},{"id":"NIFTY500","name":"NIFTY 500"}]
    return [{"id":"POPULAR","name":"Popular"},{"id":"SP500","name":"S&P 500"},{"id":"NASDAQ100","name":"NASDAQ 100"},{"id":"DOW30","name":"Dow 30"}]
