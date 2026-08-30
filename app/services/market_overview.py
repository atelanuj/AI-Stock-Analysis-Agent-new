from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import yfinance as yf

from app.cache.redis_cache import get_json,set_json
from app.config import settings
from app.tools.data_provider import batch_history
from app.tools.universe import get_stock_universe

_PROXIES={
 "IN":[("^NSEI","NIFTY 50"),("^NSEBANK","NIFTY Bank"),("^CNXIT","NIFTY IT"),("^CNXAUTO","NIFTY Auto"),("^CNXPHARMA","NIFTY Pharma")],
 "US":[("^GSPC","S&P 500"),("^IXIC","NASDAQ Composite"),("^DJI","Dow Jones"),("XLK","Technology"),("XLF","Financials"),("XLE","Energy")]
}

def _direct(sym):
    try:h=yf.Ticker(sym).history(period="6mo",auto_adjust=True,repair=True)
    except Exception:
        try:h=yf.Ticker(sym).history(period="6mo",auto_adjust=True,repair=False)
        except:return None
    if h is None or h.empty:return None
    c=h["Close"].dropna();
    if len(c)<2:return None
    def ret(n):
        if len(c)<=n:return None
        return round((float(c.iloc[-1])/float(c.iloc[-1-n])-1)*100,2)
    s20=float(c.tail(20).mean()) if len(c)>=20 else None;s50=float(c.tail(50).mean()) if len(c)>=50 else None
    return {"price":round(float(c.iloc[-1]),2),"return_1m_pct":ret(21),"return_3m_pct":ret(63),"above_sma20":float(c.iloc[-1])>s20 if s20 else None,"above_sma50":float(c.iloc[-1])>s50 if s50 else None}

def get_market_overview(market:str="IN")->dict:
    market=market.upper();key=f"market:v8:overview:{market}";c=get_json(key)
    if c:return c
    indices=[]
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs=[(name,pool.submit(_direct,sym)) for sym,name in _PROXIES[market]]
        for name,f in futs:
            try:
                d=f.result()
                if d:indices.append({"name":name,**d})
            except:pass
    symbols=get_stock_universe(market,"NIFTY50" if market=="IN" else "SP500")[:100]
    hist=batch_history(symbols,market,"1y");above20=above50=above200=valid=0
    for df in hist.values():
        if df.empty or "Close" not in df:continue
        s=df["Close"].dropna();
        if len(s)<50:continue
        valid+=1;last=float(s.iloc[-1]);above20+=int(last>float(s.tail(20).mean()));above50+=int(last>float(s.tail(50).mean()));above200+=int(len(s)>=200 and last>float(s.tail(200).mean()))
    breadth={"sample_size":valid,"above_sma20_pct":round(above20/valid*100,1) if valid else None,"above_sma50_pct":round(above50/valid*100,1) if valid else None,"above_sma200_pct":round(above200/valid*100,1) if valid else None}
    b=breadth.get("above_sma50_pct");regime="RISK-ON" if b is not None and b>=65 else "RISK-OFF" if b is not None and b<=35 else "MIXED"
    result={"market":market,"indices":indices,"breadth":breadth,"regime":regime,"note":"Breadth uses the locally available configured universe and can be smaller than the full exchange if provider downloads fail."};set_json(key,result,ttl=settings.benchmark_cache_ttl_seconds);return result
