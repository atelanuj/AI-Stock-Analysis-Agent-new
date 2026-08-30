from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import yfinance as yf

from app.services.mf_analysis import analyze_mutual_fund
from app.tools.mutual_funds import get_us_fund_data


def _holding_map(symbol:str)->dict[str,float]:
    try:
        fd=yf.Ticker(symbol).funds_data
        top=fd.top_holdings
        if top is None or len(top)==0:return {}
        out={}
        if isinstance(top,pd.DataFrame):
            for idx,row in top.iterrows():
                name=str(idx);weight=None
                for col in top.columns:
                    if "holding" in str(col).lower() or "percent" in str(col).lower() or "weight" in str(col).lower():
                        try:weight=float(row[col]);break
                        except:pass
                if weight is not None and math.isfinite(weight):out[name]=weight
        return out
    except Exception:return {}


def compare_fund_overlap(identifier_a:str,identifier_b:str,market:str="US")->dict:
    market=market.upper()
    if market!="US":
        return {"market":market,"identifier_a":identifier_a,"identifier_b":identifier_b,"available":False,"overlap_pct":None,"common_holdings":[],"note":"Indian MFAPI provides NAV history but not portfolio holdings. V8 does not invent holdings; configure an AMC/AMFI holdings feed to enable Indian fund overlap."}
    a=identifier_a.upper().strip();b=identifier_b.upper().strip()
    with ThreadPoolExecutor(max_workers=2) as pool:
        fa=pool.submit(_holding_map,a);fb=pool.submit(_holding_map,b);ha=fa.result();hb=fb.result()
    common=set(ha)&set(hb);rows=[];overlap=0.0
    for name in common:
        w=min(ha[name],hb[name]);overlap+=w;rows.append({"holding":name,"weight_a":round(ha[name]*100 if ha[name]<=1 else ha[name],2),"weight_b":round(hb[name]*100 if hb[name]<=1 else hb[name],2),"overlap_weight":round(w*100 if w<=1 else w,2)})
    rows.sort(key=lambda x:x["overlap_weight"],reverse=True)
    overlap_pct=overlap*100 if overlap<=1 else overlap
    return {"market":"US","identifier_a":a,"identifier_b":b,"available":bool(ha and hb),"overlap_pct":round(overlap_pct,2) if ha and hb else None,"common_holdings":rows[:25],"classification":"HIGH" if overlap_pct>=60 else "MODERATE" if overlap_pct>=30 else "LOW" if ha and hb else "UNKNOWN","note":"Overlap is calculated from currently available top-holdings data, not the full portfolio, so it can understate total overlap."}


def fund_category_context(identifier:str,market:str="IN")->dict:
    f=analyze_mutual_fund(identifier,market)
    category=f.get("scheme_category") or "Unknown"
    score=(f.get("analysis") or {}).get("score")
    risk=(f.get("fund_profile") or {}).get("risk_band")
    return {"identifier":identifier,"market":market.upper(),"category":category,"score":score,"risk_band":risk,"benchmark_status":(f.get("fund_profile") or {}).get("benchmark_status"),"consistency_status":(f.get("fund_profile") or {}).get("consistency_status"),"note":"V8 category context describes the fund's category and measured profile. It does not claim a category rank unless a complete comparable-universe data feed is available."}
