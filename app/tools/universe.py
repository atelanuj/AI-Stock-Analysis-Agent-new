POPULAR_STOCKS = {
    "IN": [
        "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "BHARTIARTL",
        "SBIN", "LICI", "HINDUNILVR", "ITC", "LT", "BAJFINANCE", "MARUTI",
        "KOTAKBANK", "SUNPHARMA", "AXISBANK", "M&M", "NTPC", "ONGC", "TITAN",
        "ULTRACEMCO", "ADANIPORTS", "WIPRO", "HCLTECH", "POWERGRID",
    ],
    "US": [
        "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK-B", "AVGO",
        "TSLA", "JPM", "V", "MA", "WMT", "LLY", "ORCL", "NFLX", "COST",
        "AMD", "CRM", "ADBE", "INTC", "QCOM", "DIS", "KO", "PEP",
    ],
}


def get_default_stock_universe(market: str) -> list[str]:
    return list(POPULAR_STOCKS.get(market.upper(), POPULAR_STOCKS["IN"]))
