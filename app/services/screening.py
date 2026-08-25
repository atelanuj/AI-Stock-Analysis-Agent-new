from app.models.api import StockScreenRequest
from app.services.analysis import analyze_stock
from app.tools.universe import get_default_stock_universe


def screen_stocks(request: StockScreenRequest) -> dict:
    symbols = [s.strip().upper() for s in request.symbols if s.strip()]
    if not symbols and request.use_default_universe:
        symbols = get_default_stock_universe(request.market)

    symbols = symbols[:50]
    valid, errors = [], []

    for symbol in symbols:
        try:
            result = analyze_stock(symbol, use_ai=False, market=request.market)
            scores = result["scores"]
            outlook = result["evidence"]["technical"].get("trend_outlook", {})
            bias = outlook.get("directional_bias", "NEUTRAL")

            if scores["overall"] < request.min_overall_score:
                continue
            if scores["technical"] < request.min_technical_score:
                continue
            if request.trend_bias != "ANY" and bias != request.trend_bias:
                continue

            patterns = result["evidence"]["technical"].get("candlestick_patterns", [])
            valid.append({
                "symbol": symbol,
                "company_name": result["company_name"],
                "market": request.market,
                "overall_score": scores["overall"],
                "fundamental_score": scores["fundamental"],
                "technical_score": scores["technical"],
                "valuation_score": scores["valuation"],
                "risk_score": scores["risk"],
                "rating": result["deterministic_rating"],
                "current_price": result["evidence"]["market"]["current_price"],
                "currency": result["evidence"]["market"].get("currency"),
                "trend_bias": bias,
                "trend_confidence_pct": outlook.get("confidence_pct"),
                "latest_pattern": patterns[0] if patterns else None,
            })
        except Exception as exc:
            errors.append({"symbol": symbol, "error": str(exc)})

    valid.sort(key=lambda row: (row["overall_score"], row["technical_score"]), reverse=True)
    return {
        "asset_type": "STOCK",
        "market": request.market,
        "top": valid[: request.top_n],
        "evaluated": len(symbols),
        "errors": errors,
        "method": "Deterministic multi-factor scoring plus technical directional bias. AI is skipped during bulk screening.",
    }
