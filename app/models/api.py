from datetime import datetime
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
    price_above: float | None = Field(default=None, gt=0)
    price_below: float | None = Field(default=None, gt=0)
    min_relative_volume: float | None = Field(default=1.5, ge=0)
    watch_breakouts: bool = True
    event_days: int = Field(default=7, ge=0, le=30)


class WatchlistRequest(BaseModel):
    items: list[WatchItem] = Field(min_length=1, max_length=100)


class RecommendationImportItem(BaseModel):
    created_at: datetime | None = None
    symbol: str = Field(min_length=1, max_length=32)
    market: Market
    horizon: Literal["1D", "1W", "1M", "3M", "6M", "1Y"]
    recommendation: Literal["BUY", "HOLD", "SELL"]
    ai_recommendation: Literal["BUY", "HOLD", "SELL"] | None = None
    technical_score: float | None = Field(default=None, ge=0, le=100)
    entry_price: float | None = Field(default=None, gt=0)
    ai_target: float | None = Field(default=None, gt=0)
    ai_stop_loss: float | None = Field(default=None, gt=0)


class RecommendationImportRequest(BaseModel):
    items: list[RecommendationImportItem] = Field(min_length=1, max_length=500)

class ChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=2000)
    context_type: Literal["GENERAL", "STOCK", "FUND", "IPO", "INTRADAY"] = "GENERAL"
    symbol: str | None = None
    identifier: str | None = None
    market: Market = "IN"


class FundOverlapRequest(BaseModel):
    market: Market = "US"
    identifier_a: str = Field(min_length=1)
    identifier_b: str = Field(min_length=1)


class PeerRequest(BaseModel):
    market: Market = "IN"
    peers: list[str] = Field(default_factory=list, max_length=8)

class StrategyBacktestRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    market: Market = "IN"
    period: Literal["2y", "5y", "10y", "max"] = "5y"
    forward_days: int = Field(default=10, ge=1, le=60)
    rsi_min: float | None = Field(default=45, ge=0, le=100)
    rsi_max: float | None = Field(default=65, ge=0, le=100)
    require_above_sma200: bool = True
    require_macd_bullish: bool = True
    min_relative_volume: float | None = Field(default=None, ge=0)
    direction: Literal["LONG", "SHORT"] = "LONG"


class FinalStockDecisionRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    market: Market = "IN"
    horizon: Literal["1D", "1W", "1M", "3M", "6M", "1Y"] = "3M"
    scores: dict = Field(default_factory=dict)
    market_data: dict = Field(default_factory=dict)
    fundamentals: dict = Field(default_factory=dict)
    technical: dict = Field(default_factory=dict)
    next_candle_prediction: dict | None = None
    technical_decision: dict = Field(default_factory=dict)
    stock_synthesis: dict = Field(default_factory=dict)
    news: list[dict] = Field(default_factory=list, max_length=12)
    events: dict = Field(default_factory=dict)
