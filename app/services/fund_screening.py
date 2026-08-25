from concurrent.futures import ThreadPoolExecutor, as_completed
from app.models.api import FundScreenRequest
from app.services.mf_analysis import analyze_mutual_fund
from app.tools.mutual_funds import search_indian_mf, search_us_funds


def _resolve(request: FundScreenRequest)->list[str]:
    if request.identifiers: return [x.strip() for x in request.identifiers if x.strip()][:request.scan_count]
    query=(request.query or "").strip() or ("index" if request.market=="IN" else "S&P 500")
    rows=search_indian_mf(query,limit=request.scan_count) if request.market=="IN" else search_us_funds(query,limit=request.scan_count)
    return [str(x["identifier"]) for x in rows][:request.scan_count]


def _expense_pct(v):
    try:
        x=float(v); return x*100 if x<=1 else x
    except (TypeError,ValueError): return None


def _match(req,data):
    a=data["analysis"]; r=data.get("returns",{}); risk=data.get("risk_metrics",{}); er=_expense_pct(data.get("expense_ratio")); aum=data.get("total_assets")
    if a["score"]<req.min_score:return False
    if req.min_1y_return_pct is not None and (r.get("1Y") is None or r["1Y"]<req.min_1y_return_pct): return False
    if req.min_3y_return_pct is not None and (r.get("3Y") is None or r["3Y"]<req.min_3y_return_pct): return False
    if req.max_drawdown_pct is not None and (risk.get("max_drawdown_pct") is None or abs(risk["max_drawdown_pct"])>abs(req.max_drawdown_pct)): return False
    if req.max_volatility_pct is not None and (risk.get("annualized_volatility_pct") is None or risk["annualized_volatility_pct"]>req.max_volatility_pct): return False
    if req.max_expense_ratio_pct is not None and (er is None or er>req.max_expense_ratio_pct): return False
    if req.min_aum is not None and (aum is None or float(aum)<req.min_aum): return False
    return True


def screen_funds(request:FundScreenRequest)->dict:
    candidates=_resolve(request); valid=[]; errors=[]
    def work(identifier):
        data=analyze_mutual_fund(identifier,request.market)
        if not _match(request,data): return None
        a=data["analysis"];r=data.get("returns",{});risk=data.get("risk_metrics",{});bench=data.get("benchmark",{})
        return {"identifier":data.get("identifier",identifier),"name":data.get("scheme_name"),"market":data.get("market"),"quote_type":data.get("quote_type"),"category":data.get("scheme_category"),"score":a["score"],"score_breakdown":a.get("score_breakdown"),"rating":a["rating"],"current_nav":data.get("current_nav"),"currency":data.get("currency"),"return_1y_pct":r.get("1Y"),"return_3y_annualized_pct":r.get("3Y"),"return_5y_annualized_pct":r.get("5Y"),"sharpe_ratio":risk.get("sharpe_ratio"),"sortino_ratio":risk.get("sortino_ratio"),"max_drawdown_pct":risk.get("max_drawdown_pct"),"annualized_volatility_pct":risk.get("annualized_volatility_pct"),"expense_ratio_pct":_expense_pct(data.get("expense_ratio")),"aum":data.get("total_assets"),"alpha_vs_benchmark_pct":bench.get("alpha_vs_benchmark_pct"),"tracking_error_pct":bench.get("tracking_error_pct")}
    with ThreadPoolExecutor(max_workers=min(6,max(1,len(candidates)))) as pool:
        futures={pool.submit(work,x):x for x in candidates}
        for fut in as_completed(futures):
            identifier=futures[fut]
            try:
                row=fut.result()
                if row:valid.append(row)
            except Exception as exc:errors.append({"identifier":identifier,"error":str(exc)})
    valid.sort(key=lambda x:x["score"],reverse=True); returned=valid[:request.result_count]
    return {"asset_type":"FUND","market":request.market,"requested_scan_count":request.scan_count,"evaluated":len(candidates),"matched":len(valid),"returned":len(returned),"top":returned,"errors":errors,"note":"V5 reports scan, match and return counts separately. Fund ranking uses fund-specific return, consistency, risk, cost, drawdown and benchmark metrics."}
