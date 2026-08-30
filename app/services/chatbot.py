from __future__ import annotations

from app.agent.client import synthesize_chat
from app.services.analysis import analyze_stock_core
from app.services.mf_analysis import analyze_mutual_fund
from app.services.intraday import get_intraday_analysis
from app.services.ipo_analysis import analyze_ipo


def ask_assistant(message:str, context_type:str="GENERAL", symbol:str|None=None, market:str="IN", identifier:str|None=None)->dict:
    context_type=context_type.upper();context={"context_type":context_type,"market":market.upper()}
    if context_type=="STOCK" and symbol:
        try:
            core=analyze_stock_core(symbol.upper(),market=market)
            t=core.get("evidence",{}).get("technical",{})
            context["stock"]={"symbol":symbol.upper(),"company_name":core.get("company_name"),"scores":core.get("scores"),"deterministic_rating":core.get("deterministic_rating"),"market":core.get("evidence",{}).get("market",{}),"technical":{"rsi14":t.get("rsi14"),"macd":t.get("macd"),"macd_signal":t.get("macd_signal"),"timeline_biases":t.get("timeline_biases"),"trend_alignment":t.get("trend_alignment"),"market_regime":t.get("market_regime")}}
        except Exception as exc:context["context_error"]=str(exc)[:160]
    elif context_type=="FUND" and identifier:
        try:
            f=analyze_mutual_fund(identifier,market);context["fund"]={"identifier":identifier,"scheme_name":f.get("scheme_name"),"analysis":f.get("analysis"),"returns":f.get("returns"),"risk_metrics":f.get("risk_metrics"),"benchmark":f.get("benchmark"),"fund_profile":f.get("fund_profile")}
        except Exception as exc:context["context_error"]=str(exc)[:160]
    elif context_type=="INTRADAY" and symbol:
        try:
            i=get_intraday_analysis(symbol.upper(),market,interval="5m")
            context["intraday"]={k:v for k,v in i.items() if k!="bars"}
        except Exception as exc:context["context_error"]=str(exc)[:160]
    elif context_type=="IPO" and identifier:
        try:
            i=analyze_ipo(identifier,market)
            context["ipo"]={"issue":i.get("issue"),"research_score":i.get("research_score"),"ai_analysis":i.get("ai_analysis"),"official_filings":i.get("official_filings")}
        except Exception as exc:context["context_error"]=str(exc)[:160]
    ai_available=True
    try:
        answer=synthesize_chat({"question":message,"context":context})
        text=answer.get("answer") or "I could not generate an answer."; follow=answer.get("follow_ups",[])
    except Exception:
        ai_available=False
        q=message.lower(); glossary={
            "rsi":"RSI is a 0–100 momentum oscillator. V8 treats roughly 45–65 as constructive context; extreme readings can persist and are not standalone buy/sell signals.",
            "support":"Support is a price area where demand previously appeared. V8 uses zones and recalculates them by horizon; a support level can fail.",
            "resistance":"Resistance is a price area where supply previously appeared. V8 uses zones and looks for confirmation before calling a breakout.",
            "backtest":"A backtest applies rules to historical data. V8 also includes walk-forward testing to evaluate rules on held-out historical periods.",
            "vwap":"VWAP is a volume-weighted average price. Intraday V8 compares current price with session VWAP as one participation/context signal.",
            "ipo":"The IPO desk uses SUBSCRIBE/WATCH/AVOID research classifications. It does not guarantee listing gains and does not treat GMP as verified evidence.",
        };text=next((v for k,v in glossary.items() if k in q),"The AI service is unavailable right now. You can still use V8's deterministic metrics, data-quality panels, screeners, backtests and explain buttons.");follow=[]
    return {"answer":text,"follow_ups":follow,"context_type":context_type,"ai_available":ai_available,"disclaimer":"Educational/research assistance only; not personalized investment advice."}
