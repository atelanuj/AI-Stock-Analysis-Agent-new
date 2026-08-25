from app.models.api import FundScreenRequest
from app.services.mf_analysis import analyze_mutual_fund
from app.tools.mutual_funds import search_indian_mf, search_us_funds


def _resolve_candidates(request: FundScreenRequest) -> list[str]:
    if request.identifiers:
        return [x.strip() for x in request.identifiers if x.strip()][: request.max_candidates]

    query = (request.query or "").strip()
    if not query:
        # Useful safe defaults rather than trying to scan every fund in a market.
        query = "index" if request.market == "IN" else "S&P 500"

    if request.market == "IN":
        results = search_indian_mf(query, limit=request.max_candidates)
    else:
        results = search_us_funds(query, limit=request.max_candidates)
    return [str(x["identifier"]) for x in results]


def screen_funds(request: FundScreenRequest) -> dict:
    candidates = _resolve_candidates(request)
    valid, errors = [], []

    for identifier in candidates:
        try:
            data = analyze_mutual_fund(identifier, request.market)
            analysis = data["analysis"]
            if analysis["score"] < request.min_score:
                continue
            valid.append({
                "identifier": data.get("identifier", identifier),
                "name": data.get("scheme_name"),
                "market": data.get("market"),
                "quote_type": data.get("quote_type"),
                "category": data.get("scheme_category"),
                "score": analysis["score"],
                "rating": analysis["rating"],
                "current_nav": data.get("current_nav"),
                "currency": data.get("currency"),
                "return_1y_pct": data.get("returns", {}).get("1Y"),
                "return_3y_annualized_pct": data.get("returns", {}).get("3Y"),
                "max_drawdown_pct": data.get("risk_metrics", {}).get("max_drawdown_pct"),
                "annualized_volatility_pct": data.get("risk_metrics", {}).get("annualized_volatility_pct"),
                "expense_ratio": data.get("expense_ratio"),
            })
        except Exception as exc:
            errors.append({"identifier": identifier, "error": str(exc)})

    valid.sort(key=lambda row: row["score"], reverse=True)
    return {
        "asset_type": "FUND",
        "market": request.market,
        "top": valid[: request.top_n],
        "evaluated": len(candidates),
        "errors": errors,
        "note": "V4 screens a bounded candidate set. It intentionally does not brute-force every fund in a market.",
    }
