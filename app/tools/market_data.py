import yfinance as yf

# Common US stock symbols for detection heuristic
_KNOWN_US_EXCHANGES = {".OQ", ".N", ".A", ".P"}

def detect_market(symbol: str) -> str:
    """Detect whether a symbol is Indian or US based on suffix and pattern."""
    symbol = symbol.strip().upper()
    if symbol.endswith(".NS") or symbol.endswith(".BO"):
        return "IN"
    if "." in symbol:
        # Has a suffix but not .NS/.BO — treat as explicit (could be US or other)
        return "US"
    # No suffix — use heuristic: Indian NSE symbols are typically all-alpha
    # and often longer. US symbols are 1-5 chars. But this is unreliable,
    # so we default to "IN" for backward compatibility unless market is specified.
    return "IN"

def yahoo_symbol(symbol: str, market: str | None = None) -> str:
    """Convert a user-supplied symbol to a Yahoo Finance ticker.

    Args:
        symbol: Raw stock symbol (e.g., 'RELIANCE', 'AAPL', 'TCS.NS')
        market: 'IN' for Indian, 'US' for US. Auto-detected if None.
    """
    symbol = symbol.strip().upper()
    if market is None:
        market = detect_market(symbol)

    market = market.strip().upper()

    if market == "US":
        # US symbols don't need suffix; strip .NS/.BO if accidentally added
        for suffix in (".NS", ".BO"):
            if symbol.endswith(suffix):
                symbol = symbol[:-len(suffix)]
        return symbol

    # Indian market
    if symbol.endswith(".NS") or symbol.endswith(".BO"):
        return symbol
    return f"{symbol}.NS"

def get_market_data(symbol: str, market: str | None = None) -> dict:
    yahoo_sym = yahoo_symbol(symbol, market)
    resolved_market = market or detect_market(symbol)
    ticker = yf.Ticker(yahoo_sym)
    hist = ticker.history(period="1y", auto_adjust=True)
    if hist.empty:
        raise ValueError(f"No market data found for {symbol} (tried {yahoo_sym})")
    info = ticker.info or {}
    close = hist["Close"].dropna()
    latest, first = float(close.iloc[-1]), float(close.iloc[0])
    currency = info.get("currency", "INR" if resolved_market == "IN" else "USD")
    return {
        "symbol": symbol.upper(),
        "yahoo_symbol": yahoo_sym,
        "market": resolved_market,
        "company_name": info.get("longName") or info.get("shortName") or symbol.upper(),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "currency": currency,
        "current_price": latest,
        "one_year_high": float(close.max()),
        "one_year_low": float(close.min()),
        "one_year_return_pct": ((latest / first) - 1) * 100 if first else None,
        "avg_volume_20d": float(hist["Volume"].tail(20).mean()) if "Volume" in hist else None,
    }

def get_price_history(symbol: str, market: str | None = None, period: str = "1y") -> list[dict]:
    """Return daily close prices for charting."""
    yahoo_sym = yahoo_symbol(symbol, market)
    hist = yf.Ticker(yahoo_sym).history(period=period, auto_adjust=True)
    if hist.empty:
        return []
    close = hist["Close"].dropna()
    return [{"date": d.strftime("%Y-%m-%d"), "price": round(float(p), 2)} for d, p in close.items()]
