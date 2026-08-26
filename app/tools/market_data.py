import math

# Common US stock symbols for detection heuristic
_KNOWN_US_EXCHANGES = {".OQ", ".N", ".A", ".P"}


def detect_market(symbol: str) -> str:
    symbol = symbol.strip().upper()
    if symbol.endswith(".NS") or symbol.endswith(".BO"):
        return "IN"
    if "." in symbol:
        return "US"
    return "IN"


def yahoo_symbol(symbol: str, market: str | None = None) -> str:
    symbol = symbol.strip().upper()
    if market is None:
        market = detect_market(symbol)
    market = market.strip().upper()
    if market == "US":
        for suffix in (".NS", ".BO"):
            if symbol.endswith(suffix):
                symbol = symbol[:-len(suffix)]
        return symbol
    if symbol.endswith(".NS") or symbol.endswith(".BO"):
        return symbol
    return f"{symbol}.NS"


def _finite(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def get_market_data(symbol: str, market: str | None = None, hist=None, info: dict | None = None, quote_snapshot: dict | None = None) -> dict:
    """Build market summary from pre-fetched data when available.

    V6 passes a shared OHLC dataframe, quote snapshot and info object here so the same Yahoo
    payload is not downloaded again by fundamentals/technical modules.
    """
    from app.tools.data_provider import get_history_df, get_info

    resolved_market = (market or detect_market(symbol)).upper()
    yahoo_sym = yahoo_symbol(symbol, resolved_market)
    if hist is None:
        hist = get_history_df(symbol, resolved_market, period="1y", auto_adjust=False)
    if hist is None or hist.empty or "Close" not in hist:
        raise ValueError(f"No market data found for {symbol} (tried {yahoo_sym})")
    if info is None:
        info = get_info(symbol, resolved_market)

    close = hist["Close"].dropna().astype(float)
    if close.empty:
        raise ValueError(f"No usable close-price data found for {symbol}")
    latest_close, first = float(close.iloc[-1]), float(close.iloc[0])
    quality = dict(quote_snapshot or {})
    live_price = _finite(quality.get("price"))
    latest = live_price if live_price is not None else latest_close
    if live_price is None:
        quality.update({
            "price": latest_close, "source": "Yahoo Finance daily OHLC fallback",
            "provider": "OHLC_FALLBACK", "validation_status": "SINGLE_SOURCE",
            "note": "Live/secondary quote unavailable; displayed price is the latest sanitized daily close.",
        })
    currency = quality.get("currency") or (info or {}).get("currency", "INR" if resolved_market == "IN" else "USD")
    volume = hist["Volume"].dropna() if "Volume" in hist else None

    return {
        "symbol": symbol.upper(),
        "yahoo_symbol": yahoo_sym,
        "market": resolved_market,
        "company_name": (info or {}).get("longName") or (info or {}).get("shortName") or symbol.upper(),
        "sector": (info or {}).get("sector"),
        "industry": (info or {}).get("industry"),
        "currency": currency,
        "current_price": latest,
        "latest_daily_close": latest_close,
        "quote_as_of": quality.get("as_of"),
        "quote_source": quality.get("source") or "Yahoo Finance daily OHLC",
        "data_quality": quality,
        "one_year_high": float(hist["High"].dropna().max()) if "High" in hist and not hist["High"].dropna().empty else float(close.max()),
        "one_year_low": float(hist["Low"].dropna().min()) if "Low" in hist and not hist["Low"].dropna().empty else float(close.min()),
        "one_year_return_pct": ((latest_close / first) - 1) * 100 if first else None,
        "avg_volume_20d": float(volume.tail(20).mean()) if volume is not None and not volume.empty else None,
    }


def get_price_history(symbol: str, market: str | None = None, period: str = "1y", interval: str = "1d") -> list[dict]:
    from app.tools.data_provider import get_history_df

    hist = get_history_df(symbol, market, period=period, interval=interval, auto_adjust=True)
    if hist.empty or "Close" not in hist:
        return []
    close = hist["Close"].dropna()
    intraday = interval != "1d"
    return [
        {
            "date": d.isoformat() if intraday else d.strftime("%Y-%m-%d"),
            "price": round(float(p), 4 if intraday else 2),
        }
        for d, p in close.items()
    ]
