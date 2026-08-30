from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from app.models.api import PortfolioRequest
from app.services.mf_analysis import analyze_mutual_fund
from app.tools.data_provider import get_history_df,get_info


def _fund_series(identifier:str,market:str)->pd.Series:
    f=analyze_mutual_fund(identifier,market);rows=f.get("history") or []
    if not rows:return pd.Series(dtype=float)
    df=pd.DataFrame(rows);df["date"]=pd.to_datetime(df["date"],dayfirst=True,errors="coerce");df["nav"]=pd.to_numeric(df["nav"],errors="coerce");return df.dropna().drop_duplicates("date").sort_values("date").set_index("date")["nav"]


def portfolio_risk_analysis(request:PortfolioRequest)->dict:
    series={};sectors={};weights={}
    # Use current market value proxy from average cost * quantity for risk weights to keep this endpoint light.
    total=sum(h.average_price*h.quantity for h in request.holdings)
    for h in request.holdings:
        ident=h.resolved_identifier();key=f"{h.asset_type}:{h.market}:{ident}";weights[key]=(h.average_price*h.quantity/total) if total else 1/len(request.holdings)
        try:
            if h.asset_type=="FUND":s=_fund_series(ident,h.market);sectors[key]=f"Fund: {analyze_mutual_fund(ident,h.market).get('scheme_category') or 'Other'}"
            else:
                hist=get_history_df(ident,h.market,"1y","1d",True);s=hist["Close"].dropna();sectors[key]=(get_info(ident,h.market) or {}).get("sector") or "Unknown"
            if not s.empty:series[key]=s
        except Exception:continue
    if not series:raise ValueError("No usable historical series for portfolio risk analysis")
    prices=pd.concat(series,axis=1).sort_index().ffill().dropna(how="all");rets=prices.pct_change().dropna(how="all").fillna(0)
    cols=[c for c in rets.columns if c in weights];w=np.array([weights[c] for c in cols],dtype=float);w=w/w.sum();r=rets[cols].to_numpy()@w
    ann_vol=float(np.std(r,ddof=1)*np.sqrt(252)*100) if len(r)>1 else None;cum=np.cumprod(1+r);peak=np.maximum.accumulate(cum);dd=cum/peak-1;maxdd=float(dd.min()*100) if len(dd) else None;var95=float(np.quantile(r,0.05)*100) if len(r) else None
    corr=rets[cols].corr().round(2).fillna(0);corr_rows=[]
    for i,a in enumerate(cols):
        for j,b in enumerate(cols):
            if j>i:corr_rows.append({"a":a,"b":b,"correlation":float(corr.iloc[i,j])})
    sector_weights={}
    for c,weight in zip(cols,w):sector_weights[sectors.get(c,"Unknown")]=sector_weights.get(sectors.get(c,"Unknown"),0)+float(weight)*100
    sector_rows=sorted([{"sector":k,"weight_pct":round(v,2)} for k,v in sector_weights.items()],key=lambda x:x["weight_pct"],reverse=True)
    return {"base_currency":request.base_currency,"annualized_volatility_pct":round(ann_vol,2) if ann_vol is not None else None,"historical_var_95_daily_pct":round(var95,2) if var95 is not None else None,"max_drawdown_pct":round(maxdd,2) if maxdd is not None else None,"sector_concentration":sector_rows,"correlations":sorted(corr_rows,key=lambda x:abs(x["correlation"]),reverse=True)[:20],"largest_sector_weight_pct":sector_rows[0]["weight_pct"] if sector_rows else None,"note":"Historical portfolio risk uses roughly one year of daily data and current cost-based weights. VaR is historical, not a maximum-loss guarantee."}
