from typing import Literal
from pydantic import BaseModel, Field

Market = Literal["IN", "US"]
AssetType = Literal["STOCK", "FUND"]


class StockScreenRequest(BaseModel):
    market: Market = "IN"
    symbols: list[str] = Field(default_factory=list, max_length=500)
    use_default_universe: bool = True
    universe: str = "POPULAR"
    scan_count: int = Field(default=50, ge=1, le=500)
    result_count: int = Field(default=25, ge=1, le=500)
    min_overall_score: float = Field(default=0, ge=0, le=100)
    min_technical_score: float = Field(default=0, ge=0, le=100)
    trend_bias: Literal["ANY", "BULLISH", "NEUTRAL", "BEARISH"] = "ANY"
    trend_horizon: Literal["1D", "1W", "1M", "3M", "6M", "1Y"] = "1M"
    min_market_cap: float | None = Field(default=None, ge=0)
    max_pe: float | None = Field(default=None, gt=0)
    min_roe_pct: float | None = None
    max_debt_to_equity: float | None = Field(default=None, ge=0)
    min_revenue_growth_pct: float | None = None
    min_rsi: float | None = Field(default=None, ge=0, le=100)
    max_rsi: float | None = Field(default=None, ge=0, le=100)
    require_above_sma200: bool = False
    require_volume_breakout: bool = False


ScreenRequest = StockScreenRequest


class FundScreenRequest(BaseModel):
    market: Market = "IN"
    identifiers: list[str] = Field(default_factory=list, max_length=250)
    query: str | None = None
    scan_count: int = Field(default=50, ge=1, le=250)
    result_count: int = Field(default=25, ge=1, le=250)
    min_score: float = Field(default=0, ge=0, le=100)
    min_1y_return_pct: float | None = None
    min_3y_return_pct: float | None = None
    max_drawdown_pct: float | None = None
    max_volatility_pct: float | None = None
    max_expense_ratio_pct: float | None = None
    min_aum: float | None = Field(default=None, ge=0)


class PortfolioHolding(BaseModel):
    identifier: str | None = None
    symbol: str | None = None
    quantity: float = Field(gt=0)
    average_price: float = Field(gt=0)
    market: Market = "IN"
    asset_type: AssetType = "STOCK"

    def resolved_identifier(self) -> str:
        value = self.identifier or self.symbol
        if not value:
            raise ValueError("Each holding requires identifier or symbol")
        return value.strip()


class PortfolioRequest(BaseModel):
    holdings: list[PortfolioHolding] = Field(min_length=1, max_length=100)
    base_currency: Literal["INR", "USD"] = "INR"


class MFSearchRequest(BaseModel):
    query: str = Field(min_length=2)
    market: Market = "IN"


class WatchItem(BaseModel):
    symbol: str
    market: Market = "IN"
    rsi_low: float = 30
    rsi_high: float = 70


class WatchlistRequest(BaseModel):
    items: list[WatchItem] = Field(min_length=1, max_length=100)
