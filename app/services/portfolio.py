import yfinance as yf

from app.models.api import PortfolioRequest
from app.services.analysis import analyze_stock
from app.services.mf_analysis import analyze_mutual_fund


def _usd_inr() -> float:
    try:
        h=yf.Ticker("USDINR=X").history(period="5d",auto_adjust=True)
        if not h.empty:return float(h["Close"].dropna().iloc[-1])
    except Exception:pass
    return 1.0


def _factor(currency:str,base:str,usd_inr:float)->float:
    currency=currency.upper();base=base.upper()
    if currency==base:return 1.0
    if currency=="USD" and base=="INR":return usd_inr
    if currency=="INR" and base=="USD":return 1/usd_inr if usd_inr else 1.0
    return 1.0


def analyze_portfolio(request: PortfolioRequest) -> dict:
    positions=[]; usd_inr=_usd_inr(); base=request.base_currency; total_mv=0.0; total_cost=0.0
    for holding in request.holdings:
        identifier=holding.resolved_identifier()
        if holding.asset_type=="FUND":
            result=analyze_mutual_fund(identifier,holding.market); price=float(result["current_nav"]); score=float(result["analysis"]["score"]); rating=result["analysis"]["rating"]; risk_score=result["analysis"].get("score_breakdown",{}).get("risk"); name=result.get("scheme_name"); currency=result.get("currency") or ("INR" if holding.market=="IN" else "USD")
        else:
            result=analyze_stock(identifier.upper(),market=holding.market); price=float(result["evidence"]["market"]["current_price"]); score=float(result["scores"]["overall"]); rating=result["ai_analysis"].get("rating",result["deterministic_rating"]); risk_score=result["scores"]["risk"]; name=result.get("company_name"); currency=result["evidence"]["market"].get("currency") or ("INR" if holding.market=="IN" else "USD")
        mv=price*holding.quantity; cost=holding.average_price*holding.quantity; pnl=mv-cost; pnl_pct=pnl/cost*100 if cost else None; factor=_factor(currency,base,usd_inr); mv_base=mv*factor; cost_base=cost*factor
        total_mv+=mv_base;total_cost+=cost_base
        positions.append({"identifier":identifier.upper() if holding.asset_type=="STOCK" else identifier,"name":name,"asset_type":holding.asset_type,"market":holding.market,"currency":currency,"quantity":holding.quantity,"average_price":holding.average_price,"current_price":price,"market_value":round(mv,2),"market_value_base":round(mv_base,2),"cost_value":round(cost,2),"cost_value_base":round(cost_base,2),"pnl":round(pnl,2),"pnl_base":round((mv-cost)*factor,2),"pnl_pct":round(pnl_pct,2) if pnl_pct is not None else None,"overall_score":score,"rating":rating,"risk_score":risk_score})
    for p in positions:p["weight_pct"]=round(p["market_value_base"]/total_mv*100,2) if total_mv else 0
    weighted=sum(p["overall_score"]*p["market_value_base"] for p in positions)/total_mv if total_mv else 0; concentration=max((p["weight_pct"] for p in positions),default=0);warnings=[]
    if concentration>40:warnings.append("Portfolio is highly concentrated in a single holding.")
    elif concentration>25:warnings.append("Portfolio has meaningful single-position concentration.")
    total_pnl=total_mv-total_cost; total_pnl_pct=total_pnl/total_cost*100 if total_cost else None
    return {"summary":{"base_currency":base,"market_value":round(total_mv,2),"cost_value":round(total_cost,2),"total_pnl":round(total_pnl,2),"total_pnl_pct":round(total_pnl_pct,2) if total_pnl_pct is not None else None,"weighted_quality_score":round(weighted,1),"largest_position_weight_pct":concentration,"usd_inr_rate_used":round(usd_inr,4)},"warnings":warnings,"positions":sorted(positions,key=lambda x:x["weight_pct"],reverse=True),"disclaimer":"Research tooling only. FX normalization uses the latest available USD/INR market quote and can differ from executable rates."}
