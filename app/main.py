from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.db.database import init_db
from app.models.api import FundScreenRequest, PortfolioRequest, StockScreenRequest, WatchlistRequest
from app.services.analysis import analyze_stock, analyze_stock_core, analyze_stock_fast, get_stock_ai, get_stock_context
from app.services.backtesting import backtest_stock_strategy
from app.services.fund_screening import screen_funds
from app.services.mf_analysis import analyze_mutual_fund
from app.services.portfolio import analyze_portfolio
from app.services.screening import screen_stocks
from app.services.watchlist import check_watchlist
from app.services.technical_decision import get_technical_ai_decision
from app.tools.market_data import get_price_history
from app.tools.mutual_funds import search_indian_mf, search_us_funds
from app.tools.technical import get_ohlcv_history
from app.tools.universe import available_universes, get_stock_universe


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(); yield


app = FastAPI(
    title="Stock AI Agent V7",
    version="7.0.0",
    description="V7 validated India/US stock and fund research with deep fund analytics, clickable screeners, multi-horizon technical AI decisions and model-derived risk levels.",
    lifespan=lifespan,
)

os.makedirs("app/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/")
async def root(): return FileResponse("app/static/index.html")

@app.get("/health")
def health(): return {"status":"ok","version":"7.0.0","data_validation":"NSE/Yahoo for IN; Yahoo/Stooq for US (best-effort)","technical_decision":"Nemotron + deterministic technical price structure"}

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
        return {
            "symbol": symbol.upper(), "market": market.upper(), "period": period, "interval": interval,
            "candles": rows, "bar_count": len(rows),
            "start": rows[0]["date"] if rows else None, "end": rows[-1]["date"] if rows else None,
            "data_source": "Yahoo Finance OHLC (sanitized; yfinance repair enabled)",
            "quality": "OK" if len(rows) >= (8 if period == "1d" else 2) else "LIMITED",
        }
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
