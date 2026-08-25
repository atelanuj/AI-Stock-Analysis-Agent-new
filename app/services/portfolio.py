from app.models.api import PortfolioRequest
from app.services.analysis import analyze_stock
from app.services.mf_analysis import analyze_mutual_fund


def analyze_portfolio(request: PortfolioRequest) -> dict:
    positions = []
    total_market_value = 0.0
    total_cost = 0.0

    for holding in request.holdings:
        identifier = holding.resolved_identifier()
        if holding.asset_type == "FUND":
            result = analyze_mutual_fund(identifier, holding.market)
            price = float(result["current_nav"])
            score = float(result["analysis"]["score"])
            rating = result["analysis"]["rating"]
            risk_score = None
            name = result.get("scheme_name")
        else:
            result = analyze_stock(identifier.upper(), market=holding.market)
            price = float(result["evidence"]["market"]["current_price"])
            score = float(result["scores"]["overall"])
            rating = result["ai_analysis"].get("rating", result["deterministic_rating"])
            risk_score = result["scores"]["risk"]
            name = result.get("company_name")

        market_value = price * holding.quantity
        cost_value = holding.average_price * holding.quantity
        pnl = market_value - cost_value
        pnl_pct = (pnl / cost_value * 100) if cost_value else None
        total_market_value += market_value
        total_cost += cost_value

        positions.append({
            "identifier": identifier.upper() if holding.asset_type == "STOCK" else identifier,
            "name": name,
            "asset_type": holding.asset_type,
            "market": holding.market,
            "quantity": holding.quantity,
            "average_price": holding.average_price,
            "current_price": price,
            "market_value": round(market_value, 2),
            "cost_value": round(cost_value, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2) if pnl_pct is not None else None,
            "overall_score": score,
            "rating": rating,
            "risk_score": risk_score,
        })

    for p in positions:
        p["weight_pct"] = round(p["market_value"] / total_market_value * 100, 2) if total_market_value else 0

    weighted_quality = (
        sum(p["overall_score"] * p["market_value"] for p in positions) / total_market_value
        if total_market_value else 0
    )
    concentration = max((p["weight_pct"] for p in positions), default=0)
    warnings = []
    if concentration > 40:
        warnings.append("Portfolio is highly concentrated in a single holding.")
    elif concentration > 25:
        warnings.append("Portfolio has meaningful single-position concentration.")

    currency_markets = sorted({p["market"] for p in positions})
    if len(currency_markets) > 1:
        warnings.append("Portfolio mixes INR and USD assets; totals are not FX-normalized in V4.")

    total_pnl = total_market_value - total_cost
    total_pnl_pct = total_pnl / total_cost * 100 if total_cost else None
    return {
        "summary": {
            "market_value": round(total_market_value, 2),
            "cost_value": round(total_cost, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 2) if total_pnl_pct is not None else None,
            "weighted_quality_score": round(weighted_quality, 1),
            "largest_position_weight_pct": concentration,
        },
        "warnings": warnings,
        "positions": sorted(positions, key=lambda x: x["weight_pct"], reverse=True),
        "disclaimer": "Research tooling only. Mixed-currency totals require FX normalization for a true portfolio total.",
    }
