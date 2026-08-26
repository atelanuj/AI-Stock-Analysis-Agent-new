from concurrent.futures import ThreadPoolExecutor, as_completed

from app.models.api import StockScreenRequest
from app.services.analysis import analyze_stock
from app.tools.data_provider import batch_history, get_benchmark_close
from app.tools.market_data import yahoo_symbol
from app.tools.universe import get_stock_universe


def _matches(request: StockScreenRequest, result: dict) -> bool:
    scores=result["scores"]; f=result["evidence"]["fundamentals"]; t=result["evidence"]["technical"]
    bias=t.get("timeline_biases",{}).get(request.trend_horizon,{}).get("directional_bias","NEUTRAL")
    if scores["overall"] < request.min_overall_score or scores["technical"] < request.min_technical_score: return False
    if request.trend_bias!="ANY" and bias!=request.trend_bias: return False
    if request.min_market_cap is not None and (f.get("market_cap") is None or f["market_cap"] < request.min_market_cap): return False
    pe=f.get("trailing_pe")
    if request.max_pe is not None and (pe is None or pe<=0 or pe>request.max_pe): return False
    roe=f.get("return_on_equity")
    if request.min_roe_pct is not None and (roe is None or roe*100 < request.min_roe_pct): return False
    debt=f.get("debt_to_equity")
    if request.max_debt_to_equity is not None and (debt is None or debt>request.max_debt_to_equity): return False
    rg=f.get("revenue_growth")
    if request.min_revenue_growth_pct is not None and (rg is None or rg*100 < request.min_revenue_growth_pct): return False
    rsi=t.get("rsi14")
    if request.min_rsi is not None and (rsi is None or rsi < request.min_rsi): return False
    if request.max_rsi is not None and (rsi is None or rsi > request.max_rsi): return False
    if request.require_above_sma200 and t.get("above_sma200") is not True: return False
    if request.require_volume_breakout and t.get("timeline_biases",{}).get(request.trend_horizon,{}).get("breakout",{}).get("status") != "CONFIRMED BREAKOUT": return False
    return True


def _row(symbol: str, result: dict, market: str, trend_horizon: str = "1M") -> dict:
    scores=result["scores"]; f=result["evidence"]["fundamentals"]; t=result["evidence"]["technical"]; m=result["evidence"]["market"]
    outlook=t.get("timeline_biases",{}).get(trend_horizon,{}); patterns=t.get("candlestick_patterns",[]); volume=t.get("volume",{})
    return {"symbol":symbol,"company_name":result["company_name"],"market":market,"overall_score":scores["overall"],"fundamental_score":scores["fundamental"],"technical_score":scores["technical"],"valuation_score":scores["valuation"],"risk_score":scores["risk"],"rating":result["deterministic_rating"],"current_price":m["current_price"],"currency":m.get("currency"),"market_cap":f.get("market_cap"),"pe":f.get("trailing_pe"),"roe_pct":round(f["return_on_equity"]*100,2) if f.get("return_on_equity") is not None else None,"revenue_growth_pct":round(f["revenue_growth"]*100,2) if f.get("revenue_growth") is not None else None,"rsi14":t.get("rsi14"),"above_sma200":t.get("above_sma200"),"trend_horizon":trend_horizon,"trend_bias":outlook.get("directional_bias","NEUTRAL"),"signal_agreement_pct":outlook.get("signal_agreement_pct"),"trend_confidence_pct":outlook.get("signal_agreement_pct"),"relative_volume":volume.get("relative_volume"),"breakout_status":outlook.get("breakout",{}).get("status"),"regime":t.get("market_regime",{}).get("regime"),"latest_pattern":patterns[0] if patterns else None}


def screen_stocks(request: StockScreenRequest) -> dict:
    symbols=[s.strip().upper() for s in request.symbols if s.strip()]
    source="CUSTOM"
    if not symbols and request.use_default_universe:
        symbols=get_stock_universe(request.market,request.universe); source=request.universe.upper()
    symbols=list(dict.fromkeys(symbols))[:request.scan_count]
    valid=[]; errors=[]

    # One batched Yahoo history request replaces one history request per stock.
    histories = batch_history(symbols, request.market, period="1y")
    # Warm the shared benchmark cache once before worker threads start.
    try: get_benchmark_close(request.market)
    except Exception: pass

    def work(symbol):
        preloaded = histories.get(yahoo_symbol(symbol, request.market))
        result=analyze_stock(symbol,use_ai=False,market=request.market,history_override=preloaded,validate_quote=False)
        return _row(symbol,result,request.market,request.trend_horizon) if _matches(request,result) else None

    with ThreadPoolExecutor(max_workers=min(12,max(1,len(symbols)))) as pool:
        futures={pool.submit(work,s):s for s in symbols}
        for fut in as_completed(futures):
            s=futures[fut]
            try:
                row=fut.result()
                if row: valid.append(row)
            except Exception as exc: errors.append({"symbol":s,"error":str(exc)})
    valid.sort(key=lambda r:(r["overall_score"],r["technical_score"]),reverse=True)
    returned=valid[:request.result_count]
    return {"asset_type":"STOCK","market":request.market,"universe":source,"requested_scan_count":request.scan_count,"evaluated":len(symbols),"matched":len(valid),"returned":len(returned),"top":returned,"errors":errors,"method":"V7 uses sanitized batched/cached OHLC downloads plus deterministic multi-factor stock screening. Fundamentals are cached and fetched concurrently; AI is skipped during bulk screening. Click a returned row in the UI for the full stock analysis."}
