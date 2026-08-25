import math
import yfinance as yf
from app.tools.market_data import yahoo_symbol

def _num(value):
    try:
        if value is None:
            return None
        value = float(value)
        return None if math.isnan(value) or math.isinf(value) else value
    except (TypeError, ValueError):
        return None

def get_fundamentals(symbol: str, market: str | None = None) -> dict:
    info = yf.Ticker(yahoo_symbol(symbol, market)).info or {}
    return {
        "market_cap": _num(info.get("marketCap")),
        "enterprise_value": _num(info.get("enterpriseValue")),
        "trailing_pe": _num(info.get("trailingPE")),
        "forward_pe": _num(info.get("forwardPE")),
        "price_to_book": _num(info.get("priceToBook")),
        "enterprise_to_ebitda": _num(info.get("enterpriseToEbitda")),
        "return_on_equity": _num(info.get("returnOnEquity")),
        "return_on_assets": _num(info.get("returnOnAssets")),
        "debt_to_equity": _num(info.get("debtToEquity")),
        "current_ratio": _num(info.get("currentRatio")),
        "quick_ratio": _num(info.get("quickRatio")),
        "profit_margin": _num(info.get("profitMargins")),
        "operating_margin": _num(info.get("operatingMargins")),
        "revenue_growth": _num(info.get("revenueGrowth")),
        "earnings_growth": _num(info.get("earningsGrowth")),
        "earnings_quarterly_growth": _num(info.get("earningsQuarterlyGrowth")),
        "free_cashflow": _num(info.get("freeCashflow")),
        "operating_cashflow": _num(info.get("operatingCashflow")),
        "dividend_yield": _num(info.get("dividendYield")),
        "payout_ratio": _num(info.get("payoutRatio")),
        "beta": _num(info.get("beta")),
    }
