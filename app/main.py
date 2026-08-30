from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.db.database import init_db
from app.models.api import FundScreenRequest, PortfolioRequest, StockScreenRequest, WatchlistRequest, ChatRequest, FundOverlapRequest, StrategyBacktestRequest, FinalStockDecisionRequest, RecommendationImportRequest
from app.services.analysis import analyze_stock, analyze_stock_core, analyze_stock_fast, get_stock_ai, get_stock_context
from app.services.candle_prediction import get_ai_candle_prediction
from app.services.backtesting import backtest_stock_strategy
from app.services.fund_screening import screen_funds
from app.services.mf_analysis import analyze_mutual_fund
from app.services.portfolio import analyze_portfolio
from app.services.screening import screen_stocks
from app.services.watchlist import check_watchlist
from app.services.technical_decision import get_technical_ai_decision
from app.services.final_decision import get_final_stock_decision
from app.services.intraday import get_intraday_analysis, get_intraday_ai
from app.services.ipo_analysis import list_ipos, analyze_ipo
from app.services.chatbot import ask_assistant
from app.services.research_intelligence import get_research_intelligence, get_peer_comparison, get_sector_strength, get_financial_trends, get_valuation_scenarios, get_ownership_snapshot
from app.services.walkforward import walk_forward_backtest
from app.services.strategy_builder import backtest_custom_strategy
from app.services.fund_intelligence import compare_fund_overlap, fund_category_context
from app.services.market_overview import get_market_overview
from app.services.portfolio_risk import portfolio_risk_analysis
from app.db.database import import_technical_recommendations, list_technical_recommendations
from app.services.recommendation_history import recommendation_performance
from app.tools.market_data import get_price_history
from app.tools.mutual_funds import search_indian_mf, search_us_funds
from app.tools.technical import get_ohlcv_history, predict_next_candle
from app.tools.universe import available_universes, get_stock_universe


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(); yield


app = FastAPI(
    title="Stock AI Agent V8.2",
    version="8.2.0",
    description="V8.2 technical UX release: V8 research workspace plus IPO UI fixes, intraday technical-analysis improvements, assistant send-button fixes, and light-mode readability updates.",
    lifespan=lifespan,
)

os.makedirs("app/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/")
async def root(): return FileResponse("app/static/index.html")

@app.get("/health")
def health(): return {"status":"ok","version":"8.2.0","data_validation":"NSE/Yahoo for IN; Yahoo/Stooq for US (best-effort)","technical_decision":"Nemotron + deterministic price structure for swing and intraday technical decisions","new":"V8 plus IPO search/UI fixes, improved intraday technical workspace, chatbot send button fix and light-mode readability updates"}

@app.get("/analyze/fast/{symbol}")
def analyze_fast(symbol:str,force_refresh:bool=False,market:str|None=None):
    try:return analyze_stock_fast(symbol.upper(),market=market,force_refresh=force_refresh)
    except ValueError as exc:raise HTTPException(status_code=404,detail=str(exc))
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.get("/analyze/core/{symbol}")
def analyze_core(symbol:str,force_refresh:bool=False,market:str|None=None):
    try:return analyze_stock_core(symbol.upper(),force_refresh=force_refresh,market=market)
    except ValueError as exc:raise HTTPException(status_code=404,detail=str(exc))
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.get("/analyze/context/{symbol}")
def analyze_context(symbol:str,force_refresh:bool=False,market:str|None=None):
    try:return get_stock_context(symbol.upper(),market=market,force_refresh=force_refresh)
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.get("/analyze/ai/{symbol}")
def analyze_ai(symbol:str,force_refresh:bool=False,market:str|None=None):
    try:return get_stock_ai(symbol.upper(),market=market,force_refresh=force_refresh)
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))


@app.post("/analyze/final-decision")
def analyze_final_decision(request:FinalStockDecisionRequest,force_refresh:bool=False):
    try:return get_final_stock_decision(request.model_dump(),force_refresh=force_refresh)
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.get("/analyze/{symbol}")
def analyze(symbol:str,force_refresh:bool=False,market:str|None=None):
    try:return analyze_stock(symbol.upper(),force_refresh=force_refresh,market=market)
    except ValueError as exc:raise HTTPException(status_code=404,detail=str(exc))
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.get("/technical/{symbol}")
def technical(symbol:str,market:str="IN"):
    try:return analyze_stock_core(symbol.upper(),market=market)["evidence"]["technical"]
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.get("/technical/decision/{symbol}")
def technical_decision(symbol:str,market:str="IN",horizon:str="1M",force_refresh:bool=False):
    try:return get_technical_ai_decision(symbol.upper(),market=market,horizon=horizon,force_refresh=force_refresh)
    except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc))
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.get("/api/candles/{symbol}")
def candles(symbol:str,market:str="IN",period:str="6mo",interval:str="1d"):
    try:
        rows = get_ohlcv_history(symbol.upper(), market, period, interval)
        prediction_rows = rows
        if interval == "1d" and len(rows) < 30:
            prediction_rows = get_ohlcv_history(symbol.upper(), market, "1y", "1d")
        prediction = predict_next_candle(prediction_rows, interval)
        return {
            "symbol": symbol.upper(), "market": market.upper(), "period": period, "interval": interval,
            "candles": rows, "bar_count": len(rows),
            "next_candle_prediction": prediction,
            "start": rows[0]["date"] if rows else None, "end": rows[-1]["date"] if rows else None,
            "data_source": "Yahoo Finance OHLC (sanitized; yfinance repair enabled)",
            "quality": "OK" if len(rows) >= (8 if period == "1d" else 2) else "LIMITED",
        }
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.get("/api/candles/ai/{symbol}")
def ai_candle_prediction(symbol:str,market:str="IN",period:str="3mo",interval:str="1d",force_refresh:bool=False):
    try:return get_ai_candle_prediction(symbol,market,period,interval,force_refresh)
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.get("/api/history/{symbol}")
def stock_history(symbol:str,market:str|None=None,period:str="1y"):
    try:return get_price_history(symbol,market,period)
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.get("/backtest/{symbol}")
def backtest(symbol:str,market:str="IN",period:str="5y"):
    try:return backtest_stock_strategy(symbol.upper(),market,period)
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.get("/stocks/universe")
def stock_universe(market:str="IN",universe:str="POPULAR"):
    market=market.upper()
    if market not in {"IN","US"}:raise HTTPException(status_code=400,detail="market must be IN or US")
    return {"market":market,"universe":universe.upper(),"available":available_universes(market),"symbols":get_stock_universe(market,universe)}

@app.post("/screen")
@app.post("/screen/stocks")
def screen(request:StockScreenRequest):
    try:return screen_stocks(request)
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.get("/mf/search")
def mf_search(q:str,market:str="IN",limit:int=20):
    try:return search_indian_mf(q,limit=min(limit,250)) if market.upper()=="IN" else search_us_funds(q,limit=min(limit,250))
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.get("/mf/analyze/{identifier}")
def mf_analyze(identifier:str,market:str="IN"):
    try:return analyze_mutual_fund(identifier,market)
    except ValueError as exc:raise HTTPException(status_code=404,detail=str(exc))
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.post("/screen/funds")
def mf_screen(request:FundScreenRequest):
    try:return screen_funds(request)
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.post("/portfolio/analyze")
def portfolio(request:PortfolioRequest):
    try:return analyze_portfolio(request)
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.post("/watchlist/check")
def watchlist(request:WatchlistRequest):
    try:return check_watchlist(request)
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))


@app.get("/intraday/{symbol}")
def intraday(symbol:str, market:str="IN", interval:str="5m", force_refresh:bool=False):
    try:return get_intraday_analysis(symbol,market,interval,force_refresh)
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.get("/intraday/ai/{symbol}")
def intraday_ai(symbol:str, market:str="IN", interval:str="5m", force_refresh:bool=False):
    try:return get_intraday_ai(symbol,market,interval,force_refresh)
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.get("/ipo/list")
def ipo_list(market:str="IN", month:str|None=None):
    try:return list_ipos(market,month)
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.get("/ipo/analyze/{identifier}")
def ipo_analyze(identifier:str, market:str="IN", force_refresh:bool=False):
    try:return analyze_ipo(identifier,market,force_refresh)
    except ValueError as exc:raise HTTPException(status_code=404,detail=str(exc))
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.post("/chat")
def chat(request:ChatRequest):
    try:return ask_assistant(request.message,request.context_type,request.symbol,request.market,request.identifier)
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.get("/research/{symbol}")
def research(symbol:str, market:str="IN"):
    try:return get_research_intelligence(symbol,market)
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.get("/research/peers/{symbol}")
def research_peers(symbol:str, market:str="IN", peers:str|None=None):
    try:return get_peer_comparison(symbol,market,(peers or "").split(",") if peers else None)
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.get("/research/sector/{symbol}")
def research_sector(symbol:str, market:str="IN"):
    try:return get_sector_strength(symbol,market)
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.get("/research/financials/{symbol}")
def research_financials(symbol:str, market:str="IN", force_refresh:bool=False):
    try:return get_financial_trends(symbol,market,force_refresh)
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.get("/research/valuation/{symbol}")
def research_valuation(symbol:str, market:str="IN"):
    try:return get_valuation_scenarios(symbol,market)
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.get("/research/ownership/{symbol}")
def research_ownership(symbol:str, market:str="IN", force_refresh:bool=False):
    try:return get_ownership_snapshot(symbol,market,force_refresh)
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.get("/backtest/walk-forward/{symbol}")
def walkforward(symbol:str, market:str="IN", period:str="10y"):
    try:return walk_forward_backtest(symbol,market,period)
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.post("/strategy/backtest")
def strategy_backtest(request:StrategyBacktestRequest):
    try:return backtest_custom_strategy(request)
    except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc))
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.get("/recommendations/history")
def recommendation_history(symbol:str|None=None, market:str|None=None, limit:int=50):
    return recommendation_performance(symbol,market,limit)

@app.post("/recommendations/import")
def recommendation_import(request:RecommendationImportRequest):
    try:return import_technical_recommendations([item.model_dump(mode="json") for item in request.items])
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.post("/funds/overlap")
def fund_overlap(request:FundOverlapRequest):
    try:return compare_fund_overlap(request.identifier_a,request.identifier_b,request.market)
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.get("/funds/category/{identifier}")
def fund_category(identifier:str, market:str="IN"):
    try:return fund_category_context(identifier,market)
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.get("/market/overview")
def market_overview(market:str="IN"):
    try:return get_market_overview(market)
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))

@app.post("/portfolio/risk")
def portfolio_risk(request:PortfolioRequest):
    try:return portfolio_risk_analysis(request)
    except Exception as exc:raise HTTPException(status_code=500,detail=str(exc))
