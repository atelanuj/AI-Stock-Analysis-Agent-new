from typing import Literal
from pydantic import BaseModel, Field

Market = Literal["IN", "US"]
AssetType = Literal["STOCK", "FUND"]


class StockScreenRequest(BaseModel):
    market: Market = "IN"
    symbols: list[str] = Field(default_factory=list, max_length=50)
    use_default_universe: bool = True
    top_n: int = Field(default=10, ge=1, le=25)
    min_overall_score: float = Field(default=0, ge=0, le=100)
    min_technical_score: float = Field(default=0, ge=0, le=100)
    trend_bias: Literal["ANY", "BULLISH", "NEUTRAL", "BEARISH"] = "ANY"


# Backward-compatible name used by the V2 endpoint/client.
ScreenRequest = StockScreenRequest


class FundScreenRequest(BaseModel):
    market: Market = "IN"
    identifiers: list[str] = Field(default_factory=list, max_length=30)
    query: str | None = None
    top_n: int = Field(default=10, ge=1, le=20)
    max_candidates: int = Field(default=15, ge=1, le=30)
    min_score: float = Field(default=0, ge=0, le=100)


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
    holdings: list[PortfolioHolding] = Field(min_length=1, max_length=50)


class MFSearchRequest(BaseModel):
    query: str = Field(min_length=2)
    market: Market = "IN"
