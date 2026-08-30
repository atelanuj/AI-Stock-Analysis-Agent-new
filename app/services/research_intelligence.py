from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Iterable

import numpy as np
import pandas as pd
import yfinance as yf

from app.cache.redis_cache import get_json, set_json
from app.config import settings
from app.tools.data_provider import get_history_df, get_info
from app.tools.market_data import yahoo_symbol
from app.tools.universe import get_stock_universe

# Curated peer defaults are deliberately small. Unknown symbols fall back to
# same-sector names from the configured popular universe when enough metadata exists.
_PEERS = {
    "IN": {
        "TCS": ["INFY", "HCLTECH", "WIPRO", "TECHM"],
        "INFY": ["TCS", "HCLTECH", "WIPRO", "TECHM"],
        "HCLTECH": ["TCS", "INFY", "WIPRO", "TECHM"],
        "RELIANCE": ["ONGC", "IOC", "BPCL", "GAIL"],
        "HDFCBANK": ["ICICIBANK", "KOTAKBANK", "AXISBANK", "SBIN"],
        "ICICIBANK": ["HDFCBANK", "KOTAKBANK", "AXISBANK", "SBIN"],
        "KOTAKBANK": ["HDFCBANK", "ICICIBANK", "AXISBANK", "SBIN"],
        "MARUTI": ["M&M", "TATAMOTORS", "BAJAJ-AUTO", "EICHERMOT"],
        "TATAMOTORS": ["MARUTI", "M&M", "BAJAJ-AUTO", "EICHERMOT"],
        "SUNPHARMA": ["DRREDDY", "CIPLA", "DIVISLAB"],
    },
    "US": {
        "AAPL": ["MSFT", "GOOGL", "AMZN", "META"],
        "MSFT": ["AAPL", "GOOGL", "AMZN", "ORCL"],
        "NVDA": ["AMD", "AVGO", "QCOM", "INTC"],
        "GOOGL": ["META", "AMZN", "MSFT", "AAPL"],
        "AMZN": ["WMT", "COST", "GOOGL", "META"],
        "JPM": ["BAC", "WFC", "C", "GS"],
        "XOM": ["CVX", "COP", "EOG"],
        "TSLA": ["GM", "F", "RIVN"],
    },
}

_SECTOR_PROXIES = {
    "US": {
        "Technology": ("XLK", "Technology Select Sector SPDR"),
        "Financial Services": ("XLF", "Financial Select Sector SPDR"),
        "Healthcare": ("XLV", "Health Care Select Sector SPDR"),
        "Energy": ("XLE", "Energy Select Sector SPDR"),
        "Consumer Cyclical": ("XLY", "Consumer Discretionary Select Sector SPDR"),
        "Consumer Defensive": ("XLP", "Consumer Staples Select Sector SPDR"),
        "Industrials": ("XLI", "Industrial Select Sector SPDR"),
        "Utilities": ("XLU", "Utilities Select Sector SPDR"),
        "Real Estate": ("XLRE", "Real Estate Select Sector SPDR"),
        "Basic Materials": ("XLB", "Materials Select Sector SPDR"),
        "Communication Services": ("XLC", "Communication Services Select Sector SPDR"),
    },
    "IN": {
        "Technology": ("^CNXIT", "NIFTY IT"),
        "Financial Services": ("^NSEBANK", "NIFTY Bank proxy"),
        "Energy": ("^CNXENERGY", "NIFTY Energy"),
        "Consumer Cyclical": ("^CNXAUTO", "NIFTY Auto"),
        "Healthcare": ("^CNXPHARMA", "NIFTY Pharma"),
        "Basic Materials": ("^CNXMETAL", "NIFTY Metal"),
        "Consumer Defensive": ("^CNXFMCG", "NIFTY FMCG"),
    },
}


def _finite(v, digits: int | None = None):
    try:
        n = float(v)
        if not math.isfinite(n):
            return None
        return round(n, digits) if digits is not None else n
    except (TypeError, ValueError, OverflowError):
        return None


def _pct_change(close: pd.Series, sessions: int) -> float | None:
    s = close.dropna().astype(float)
    if len(s) <= sessions or float(s.iloc[-1 - sessions]) == 0:
        return None
    return _finite((float(s.iloc[-1]) / float(s.iloc[-1 - sessions]) - 1) * 100, 2)


def _direct_history(symbol: str, period: str = "1y") -> pd.Series:
    try:
        h = yf.Ticker(symbol).history(period=period, auto_adjust=True, repair=True)
    except Exception:
        try:
            h = yf.Ticker(symbol).history(period=period, auto_adjust=True, repair=False)
        except Exception:
            return pd.Series(dtype=float)
    if h is None or h.empty or "Close" not in h:
        return pd.Series(dtype=float)
    return pd.to_numeric(h["Close"], errors="coerce").dropna()


def _safe_ratio(v, scale_pct: bool = False):
    n = _finite(v)
    if n is None:
        return None
    return round(n * 100, 2) if scale_pct else round(n, 2)


def _peer_row(symbol: str, market: str) -> dict:
    info = get_info(symbol, market)
    hist = get_history_df(symbol, market, "1y", "1d", True)
    close = hist["Close"].dropna() if not hist.empty and "Close" in hist else pd.Series(dtype=float)
    return {
        "symbol": symbol,
        "name": info.get("shortName") or info.get("longName") or symbol,
        "sector": info.get("sector"),
        "market_cap": _finite(info.get("marketCap")),
        "pe": _finite(info.get("trailingPE"), 2),
        "forward_pe": _finite(info.get("forwardPE"), 2),
        "roe_pct": _safe_ratio(info.get("returnOnEquity"), True),
        "revenue_growth_pct": _safe_ratio(info.get("revenueGrowth"), True),
        "profit_margin_pct": _safe_ratio(info.get("profitMargins"), True),
        "debt_to_equity": _finite(info.get("debtToEquity"), 2),
        "return_3m_pct": _pct_change(close, 63),
        "return_1y_pct": _pct_change(close, 252 if len(close) > 252 else max(1, len(close)-1)),
    }


def _same_sector_fallback(symbol: str, market: str, sector: str | None) -> list[str]:
    if not sector:
        return []
    candidates = get_stock_universe(market, "POPULAR")[:35]
    candidates = [x for x in candidates if x != symbol]
    peers: list[str] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(get_info, x, market): x for x in candidates}
        for fut, sym in [(f, s) for f, s in futures.items()]:
            try:
                if (fut.result() or {}).get("sector") == sector:
                    peers.append(sym)
            except Exception:
                continue
            if len(peers) >= 4:
                break
    return peers


def get_peer_comparison(symbol: str, market: str = "IN", peers: Iterable[str] | None = None) -> dict:
    symbol = symbol.upper().strip(); market = market.upper()
    own_info = get_info(symbol, market)
    selected = [p.strip().upper() for p in (peers or []) if p and p.strip() and p.strip().upper() != symbol]
    if not selected:
        selected = list(_PEERS.get(market, {}).get(symbol, []))
    if not selected:
        selected = _same_sector_fallback(symbol, market, own_info.get("sector"))
    selected = selected[:5]
    symbols = [symbol] + selected
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(6, len(symbols) or 1)) as pool:
        futures = [pool.submit(_peer_row, s, market) for s in symbols]
        for fut in futures:
            try: rows.append(fut.result())
            except Exception: pass
    own = next((r for r in rows if r["symbol"] == symbol), None)
    peer_rows = [r for r in rows if r["symbol"] != symbol]
    pe_values = [r["pe"] for r in peer_rows if r.get("pe") and r["pe"] > 0]
    roe_values = [r["roe_pct"] for r in peer_rows if r.get("roe_pct") is not None]
    rel = {
        "pe_vs_peer_median_pct": None,
        "roe_vs_peer_median_pp": None,
        "valuation_label": "UNKNOWN",
        "quality_label": "UNKNOWN",
    }
    if own:
        if own.get("pe") and pe_values:
            median = float(np.median(pe_values))
            diff = (own["pe"] / median - 1) * 100 if median else None
            rel["pe_vs_peer_median_pct"] = _finite(diff, 2)
            rel["valuation_label"] = "CHEAPER" if diff is not None and diff <= -10 else "EXPENSIVE" if diff is not None and diff >= 10 else "IN LINE"
        if own.get("roe_pct") is not None and roe_values:
            diff = own["roe_pct"] - float(np.median(roe_values))
            rel["roe_vs_peer_median_pp"] = _finite(diff, 2)
            rel["quality_label"] = "ABOVE PEERS" if diff >= 3 else "BELOW PEERS" if diff <= -3 else "IN LINE"
    return {
        "symbol": symbol, "market": market, "sector": own_info.get("sector"),
        "rows": rows, "relative": rel,
        "note": "Peer comparison is best-effort and uses a curated or same-sector peer set; verify peers before making valuation conclusions.",
    }


def get_sector_strength(symbol: str, market: str = "IN") -> dict:
    symbol = symbol.upper().strip(); market = market.upper()
    info = get_info(symbol, market); sector = info.get("sector")
    proxy = _SECTOR_PROXIES.get(market, {}).get(sector)
    stock = get_history_df(symbol, market, "1y", "1d", True)
    stock_close = stock["Close"].dropna() if not stock.empty and "Close" in stock else pd.Series(dtype=float)
    market_symbol, market_name = ("^GSPC", "S&P 500") if market == "US" else ("^NSEI", "NIFTY 50")
    market_close = _direct_history(market_symbol)
    sector_close = _direct_history(proxy[0]) if proxy else pd.Series(dtype=float)
    horizons = {"1M": 21, "3M": 63, "6M": 126, "1Y": 252}
    rows = {}
    for label, sessions in horizons.items():
        sr = _pct_change(stock_close, min(sessions, max(1, len(stock_close)-1)))
        mr = _pct_change(market_close, min(sessions, max(1, len(market_close)-1))) if not market_close.empty else None
        xr = _pct_change(sector_close, min(sessions, max(1, len(sector_close)-1))) if not sector_close.empty else None
        rows[label] = {
            "stock_return_pct": sr,
            "sector_return_pct": xr,
            "market_return_pct": mr,
            "stock_vs_sector_pct": _finite(sr-xr, 2) if sr is not None and xr is not None else None,
            "sector_vs_market_pct": _finite(xr-mr, 2) if xr is not None and mr is not None else None,
        }
    three = rows["3M"]
    stock_vs_sector = three.get("stock_vs_sector_pct")
    sector_vs_market = three.get("sector_vs_market_pct")
    classification = "MIXED"
    if stock_vs_sector is not None and sector_vs_market is not None:
        if stock_vs_sector > 0 and sector_vs_market > 0: classification = "STRONG STOCK / STRONG SECTOR"
        elif stock_vs_sector < 0 and sector_vs_market < 0: classification = "WEAK STOCK / WEAK SECTOR"
        elif stock_vs_sector > 0: classification = "STRONG STOCK / WEAK SECTOR"
        else: classification = "WEAK STOCK / STRONG SECTOR"
    return {
        "symbol":symbol, "market":market, "sector":sector,
        "sector_benchmark": proxy[1] if proxy else None, "market_benchmark": market_name,
        "horizons": rows, "classification": classification,
        "note": "Sector proxy availability varies by market. Missing sector data falls back to market context rather than inventing a sector index.",
    }


_STATEMENT_ALIASES = {
    "revenue": ["Total Revenue", "Operating Revenue"],
    "net_income": ["Net Income", "Net Income Common Stockholders"],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
    "total_debt": ["Total Debt"],
    "stockholders_equity": ["Stockholders Equity", "Total Equity Gross Minority Interest"],
    "operating_cashflow": ["Operating Cash Flow", "Total Cash From Operating Activities"],
    "capex": ["Capital Expenditure", "Capital Expenditures"],
    "free_cashflow": ["Free Cash Flow"],
}


def _statement_value(df: pd.DataFrame, aliases: list[str], column):
    if df is None or df.empty:
        return None
    for name in aliases:
        if name in df.index:
            return _finite(df.loc[name, column])
    return None


def get_financial_trends(symbol: str, market: str = "IN", force_refresh: bool = False) -> dict:
    symbol=symbol.upper().strip(); market=market.upper(); ys=yahoo_symbol(symbol,market)
    key=f"research:v8:financials:{market}:{symbol}"
    if not force_refresh:
        cached=get_json(key)
        if cached: return cached
    t=yf.Ticker(ys)
    try: income=t.financials
    except Exception: income=pd.DataFrame()
    try: balance=t.balance_sheet
    except Exception: balance=pd.DataFrame()
    try: cash=t.cashflow
    except Exception: cash=pd.DataFrame()
    cols=[]
    for frame in (income,balance,cash):
        if frame is not None and not frame.empty:
            cols.extend(list(frame.columns))
    unique=sorted(set(pd.Timestamp(c) for c in cols), reverse=False)[-5:]
    rows=[]
    for col_ts in unique:
        def nearest_col(frame):
            if frame is None or frame.empty:return None
            for c in frame.columns:
                if pd.Timestamp(c)==col_ts:return c
            return None
        ic,bc,cc=nearest_col(income),nearest_col(balance),nearest_col(cash)
        revenue=_statement_value(income,_STATEMENT_ALIASES["revenue"],ic) if ic is not None else None
        net=_statement_value(income,_STATEMENT_ALIASES["net_income"],ic) if ic is not None else None
        ebitda=_statement_value(income,_STATEMENT_ALIASES["ebitda"],ic) if ic is not None else None
        debt=_statement_value(balance,_STATEMENT_ALIASES["total_debt"],bc) if bc is not None else None
        equity=_statement_value(balance,_STATEMENT_ALIASES["stockholders_equity"],bc) if bc is not None else None
        ocf=_statement_value(cash,_STATEMENT_ALIASES["operating_cashflow"],cc) if cc is not None else None
        capex=_statement_value(cash,_STATEMENT_ALIASES["capex"],cc) if cc is not None else None
        fcf=_statement_value(cash,_STATEMENT_ALIASES["free_cashflow"],cc) if cc is not None else None
        if fcf is None and ocf is not None and capex is not None: fcf=ocf+capex if capex<0 else ocf-capex
        rows.append({"year":str(col_ts.year),"revenue":revenue,"net_income":net,"ebitda":ebitda,"total_debt":debt,"equity":equity,"operating_cashflow":ocf,"free_cashflow":fcf})
    def cagr(key):
        valid=[(int(r["year"]),r[key]) for r in rows if r.get(key) is not None and r[key]>0]
        if len(valid)<2:return None
        years=valid[-1][0]-valid[0][0]
        return _finite(((valid[-1][1]/valid[0][1])**(1/max(1,years))-1)*100,2) if valid[0][1]>0 else None
    result={"symbol":symbol,"market":market,"rows":rows,"revenue_cagr_pct":cagr("revenue"),"net_income_cagr_pct":cagr("net_income"),"fcf_cagr_pct":cagr("free_cashflow"),"source":"Yahoo Finance financial statements","data_quality":"SINGLE SOURCE","note":"Financial statement history is provider-dependent; reconcile material figures with exchange/company filings before acting."}
    set_json(key,result,ttl=settings.fundamentals_cache_ttl_seconds)
    return result


def get_valuation_scenarios(symbol: str, market: str = "IN") -> dict:
    symbol=symbol.upper().strip(); market=market.upper(); info=get_info(symbol,market)
    price=_finite(info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose"))
    shares=_finite(info.get("sharesOutstanding")); fcf=_finite(info.get("freeCashflow")); eps=_finite(info.get("trailingEps")); pe=_finite(info.get("trailingPE")); growth=_finite(info.get("earningsGrowth") or info.get("revenueGrowth"))
    scenarios=[]
    # Conservative capped assumptions; every assumption is returned to the UI.
    base_growth=max(-0.05,min(0.15,growth if growth is not None else 0.05))
    for name,g_adj,discount,terminal in [("Bear",-0.04,0.13,0.025),("Base",0.0,0.11,0.035),("Bull",0.04,0.095,0.045)]:
        g=max(-0.08,min(0.20,base_growth+g_adj)); per_share=None
        if fcf is not None and fcf>0 and shares and shares>0 and discount>terminal:
            cashflows=[]; current=fcf
            for _ in range(5): current*=1+g; cashflows.append(current)
            pv=sum(cf/((1+discount)**(i+1)) for i,cf in enumerate(cashflows))
            terminal_value=cashflows[-1]*(1+terminal)/(discount-terminal)
            equity_value=pv+terminal_value/((1+discount)**5)
            per_share=equity_value/shares
        scenarios.append({"name":name,"growth_assumption_pct":round(g*100,2),"discount_rate_pct":round(discount*100,2),"terminal_growth_pct":round(terminal*100,2),"dcf_per_share":_finite(per_share,2),"upside_vs_price_pct":_finite((per_share/price-1)*100,2) if per_share and price else None})
    return {"symbol":symbol,"market":market,"current_price":price,"trailing_pe":pe,"eps":eps,"free_cashflow":fcf,"scenarios":scenarios,"method":"Illustrative 5-year FCFF-style equity-value proxy using provider FCF and capped growth assumptions.","warning":"This is not a full investment-bank DCF. Debt, cash, dilution, cyclicality and accounting normalization can materially change fair value."}


def get_research_intelligence(symbol: str, market: str = "IN") -> dict:
    with ThreadPoolExecutor(max_workers=5) as pool:
        fp=pool.submit(get_peer_comparison,symbol,market)
        fs=pool.submit(get_sector_strength,symbol,market)
        ff=pool.submit(get_financial_trends,symbol,market)
        fv=pool.submit(get_valuation_scenarios,symbol,market)
        fo=pool.submit(get_ownership_snapshot,symbol,market)
        return {"symbol":symbol.upper(),"market":market.upper(),"as_of":datetime.now(timezone.utc).isoformat(),"peers":fp.result(),"sector_strength":fs.result(),"financial_trends":ff.result(),"valuation":fv.result(),"ownership":fo.result()}


def get_ownership_snapshot(symbol: str, market: str = "IN", force_refresh: bool = False) -> dict:
    """Best-effort ownership snapshot from the configured public provider.

    This intentionally does not relabel generic Yahoo holder data as Indian
    promoter/FII/DII data. Those categories require a dedicated exchange-grade
    source and are returned only when the provider explicitly exposes them.
    """
    symbol=symbol.upper().strip(); market=market.upper(); key=f"research:v8:ownership:{market}:{symbol}"
    if not force_refresh:
        cached=get_json(key)
        if cached:return cached
    t=yf.Ticker(yahoo_symbol(symbol,market)); major=[]; institutional=[]
    try:
        df=t.major_holders
        if df is not None and not df.empty:
            for _,row in df.head(8).iterrows():
                vals=list(row.values)
                if len(vals)>=2: major.append({"value":str(vals[0]),"label":str(vals[1])})
    except Exception:pass
    try:
        df=t.institutional_holders
        if df is not None and not df.empty:
            for _,row in df.head(10).iterrows():
                institutional.append({
                    "holder":str(row.get("Holder") or row.get("holder") or "Unknown"),
                    "shares":_finite(row.get("Shares") or row.get("shares")),
                    "value":_finite(row.get("Value") or row.get("value")),
                    "pct_held":_safe_ratio(row.get("pctHeld") or row.get("% Out") or row.get("pct_held"), True),
                    "date_reported":str(row.get("Date Reported") or row.get("date_reported") or "")[:10] or None,
                })
    except Exception:pass
    result={"symbol":symbol,"market":market,"major_holders":major,"institutional_holders":institutional,"source":"Yahoo Finance holder tables (best-effort)","note":"For Indian stocks this is not a substitute for official promoter/FII/DII shareholding-pattern filings. Verify ownership changes against exchange/company filings."}
    set_json(key,result,ttl=settings.fundamentals_cache_ttl_seconds);return result
