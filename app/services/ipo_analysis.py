from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app.agent.client import synthesize_ipo_analysis
from app.cache.redis_cache import get_json, set_json
from app.config import settings

_HEADERS={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36","Accept":"application/json,text/html,*/*","Accept-Language":"en-US,en;q=0.9","Referer":"https://www.nseindia.com/"}


def _num(v):
    if v is None:return None
    try:
        s=str(v).replace(",","").replace("₹","").replace("$","").replace("x","").strip();m=re.search(r"-?\d+(?:\.\d+)?",s)
        return float(m.group()) if m and math.isfinite(float(m.group())) else None
    except:return None


def _flatten(payload):
    if isinstance(payload,list):return payload
    if isinstance(payload,dict):
        for k in ("data","records","rows","upcoming","currentIssue","issues"):
            if isinstance(payload.get(k),list):return payload[k]
    return []


def _nse_get(path:str):
    s=requests.Session();s.headers.update(_HEADERS)
    try:s.get("https://www.nseindia.com/",timeout=8)
    except Exception:pass
    r=s.get("https://www.nseindia.com"+path,timeout=12);r.raise_for_status();return r.json()


def _normalize_in(row:dict,status:str)->dict:
    name=row.get("companyName") or row.get("company") or row.get("issueName") or row.get("name") or row.get("symbol")
    symbol=row.get("symbol") or row.get("ticker") or ""
    sub=_num(row.get("noOfTime") or row.get("subscription") or row.get("timesSubscribed"))
    return {"id":str(symbol or name).strip(),"market":"IN","symbol":str(symbol).strip(),"name":str(name or "Unknown issue").strip(),"status":status,"open_date":row.get("issueStartDate") or row.get("openDate") or row.get("biddingStartDate"),"close_date":row.get("issueEndDate") or row.get("closeDate") or row.get("biddingEndDate"),"listing_date":row.get("listingDate"),"price_band":row.get("priceBand") or row.get("issuePrice") or row.get("priceRange"),"lot_size":_num(row.get("lotSize") or row.get("marketLot")),"issue_size":row.get("issueSize") or row.get("issueSizeInCrores"),"shares_offered":_num(row.get("noOfSharesOffered")),"shares_bid":_num(row.get("noOfsharesBid") or row.get("noOfSharesBid")),"subscription_x":sub,"raw":{k:v for k,v in row.items() if isinstance(v,(str,int,float,bool,type(None)))},"source":"NSE India public issue feed","source_url":"https://www.nseindia.com/market-data/all-upcoming-issues-ipo"}


def _sebi_filings(limit:int=30)->list[dict]:
    key="ipo:v8:sebi-filings"
    c=get_json(key)
    if c:return c
    url="https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=3&smid=0&ssid=15"
    try:
        r=requests.get(url,headers=_HEADERS,timeout=12);r.raise_for_status();soup=BeautifulSoup(r.text,"html.parser");out=[]
        for tr in soup.select("tr"):
            cells=tr.find_all("td")
            if len(cells)<2:continue
            date=cells[0].get_text(" ",strip=True);title=cells[1].get_text(" ",strip=True)
            if not title:continue
            a=cells[1].find("a");href=urljoin(url,a.get("href")) if a and a.get("href") else url
            if any(x in title.upper() for x in ("RHP","DRHP","PROSPECTUS","ABRIDGED")):
                out.append({"date":date,"title":title,"url":href})
            if len(out)>=limit:break
        set_json(key,out,ttl=1800);return out
    except Exception:return []


def list_india_ipos()->dict:
    key="ipo:v8:list:IN";c=get_json(key)
    if c:return c
    current=[];upcoming=[];errors=[]
    try:current=[_normalize_in(x,"OPEN/CURRENT") for x in _flatten(_nse_get("/api/ipo-current-issue"))]
    except Exception as exc:errors.append(f"NSE current issues: {str(exc)[:120]}")
    try:upcoming=[_normalize_in(x,"UPCOMING") for x in _flatten(_nse_get("/api/all-upcoming-issues?category=ipo"))]
    except Exception as exc:errors.append(f"NSE upcoming issues: {str(exc)[:120]}")
    seen=set();issues=[]
    for x in current+upcoming:
        keyid=(x.get("symbol") or x.get("name")).upper()
        if keyid in seen:continue
        seen.add(keyid);issues.append(x)
    filings=_sebi_filings()
    # If NSE's undocumented web API is blocked, keep the IPO desk useful by
    # surfacing recent official SEBI filing entries as low-completeness research
    # candidates. They remain WATCH until stronger issue evidence is available.
    if not issues:
        for f in filings[:20]:
            title=str(f.get("title") or "").strip()
            if not title:continue
            cleaned=re.sub(r"\b(DRHP|RHP|RED HERRING PROSPECTUS|PROSPECTUS|ABRIDGED PROSPECTUS)\b","",title,flags=re.I)
            cleaned=re.sub(r"\s+"," ",cleaned).strip(" -–—:") or title
            issues.append({"id":cleaned,"market":"IN","symbol":"","name":cleaned,"status":"SEBI FILING","open_date":None,"close_date":None,"listing_date":None,"price_band":None,"lot_size":None,"issue_size":None,"subscription_x":None,"source":"SEBI Public Issues filing","source_url":f.get("url"),"filing_title":title})
    result={"market":"IN","issues":issues,"filings":filings,"errors":errors,"sources":["NSE India current/upcoming public issue feeds","SEBI Public Issues filings"],"note":"NSE web APIs are undocumented and may occasionally block automated requests. If they are unavailable, recent SEBI filings are shown as low-completeness candidates. No grey-market premium/GMP is used."};set_json(key,result,ttl=600);return result


def list_us_ipos(month:str|None=None)->dict:
    month=month or datetime.now(timezone.utc).strftime("%Y-%m");key=f"ipo:v8:list:US:{month}";c=get_json(key)
    if c:return c
    url="https://api.nasdaq.com/api/ipo/calendar";issues=[];errors=[]
    try:
        r=requests.get(url,params={"date":month},headers={**_HEADERS,"Referer":"https://www.nasdaq.com/market-activity/ipos"},timeout=12);r.raise_for_status();p=r.json();data=(p or {}).get("data") or {}
        for status,keyname in (("UPCOMING","upcoming"),("PRICED","priced"),("FILINGS","filings")):
            block=data.get(keyname) or {};rows=block.get("rows") if isinstance(block,dict) else block
            for row in rows or []:
                symbol=row.get("symbol") or row.get("proposedTickerSymbol") or "";name=row.get("companyName") or row.get("name") or symbol
                issues.append({"id":str(symbol or name),"market":"US","symbol":symbol,"name":name,"status":status,"open_date":row.get("expectedDate") or row.get("pricedDate"),"close_date":None,"listing_date":row.get("expectedDate"),"price_band":row.get("proposedSharePrice") or row.get("price"),"shares_offered":_num(row.get("sharesOffered")),"deal_size":row.get("dealSize"),"exchange":row.get("proposedExchange"),"raw":row,"source":"Nasdaq IPO Calendar / EDGAR Online","source_url":"https://www.nasdaq.com/market-activity/ipos"})
    except Exception as exc:errors.append(str(exc)[:160])
    result={"market":"US","month":month,"issues":issues,"errors":errors,"sources":["Nasdaq IPO Calendar (calendar data powered by EDGAR Online)"],"note":"Expected US IPO dates can be estimates. Verify SEC filings and exchange announcements."};set_json(key,result,ttl=900);return result


def list_ipos(market:str="IN",month:str|None=None)->dict:return list_us_ipos(month) if market.upper()=="US" else list_india_ipos()


def _score_issue(issue:dict)->dict:
    score=50.0;components={};sub=_num(issue.get("subscription_x"));band=issue.get("price_band");lot=issue.get("lot_size");status=issue.get("status","")
    if sub is not None:
        demand=95 if sub>=20 else 82 if sub>=10 else 70 if sub>=3 else 55 if sub>=1 else 35;score+=(demand-50)*0.35;components["demand"]=demand
    else:components["demand"]=None
    completeness=sum([bool(issue.get("name")),bool(band),bool(issue.get("open_date") or issue.get("listing_date")),bool(issue.get("issue_size") or issue.get("deal_size") or issue.get("shares_offered")),sub is not None, bool(lot)])
    completeness_pct=round(completeness/6*100)
    if completeness_pct<50:score=min(score,59)
    score=max(0,min(100,round(score,1)))
    verdict="SUBSCRIBE" if score>=72 and completeness_pct>=65 else "AVOID" if score<42 and completeness_pct>=50 else "WATCH"
    return {"score":score,"verdict":verdict,"evidence_completeness_pct":completeness_pct,"components":components,"note":"Pre-listing score is intentionally capped when valuation/financial evidence is incomplete. Demand alone is not sufficient for a SUBSCRIBE verdict."}


def analyze_ipo(identifier:str,market:str="IN",force_refresh:bool=False)->dict:
    market=market.upper();key=f"ipo:v8:analysis:{market}:{identifier.upper()}"
    if not force_refresh:
        c=get_json(key)
        if c:return c
    listed=list_ipos(market);ident=identifier.strip().upper();issue=next((x for x in listed.get("issues",[]) if str(x.get("symbol") or "").upper()==ident or str(x.get("id") or "").upper()==ident or ident in str(x.get("name") or "").upper()),None)
    if not issue:raise ValueError(f"IPO {identifier} was not found in the current/upcoming {market} feed")
    if market=="IN" and issue.get("symbol"):
        try:
            detail=_nse_get(f"/api/ipo-detail?symbol={issue['symbol']}")
            issue["subscription_detail"]=detail
        except Exception:pass
    score=_score_issue(issue)
    related=[]
    for f in listed.get("filings",[]):
        name_words=[w for w in re.findall(r"[A-Z0-9]+",str(issue.get("name","")).upper()) if len(w)>3]
        if any(w in f.get("title","").upper() for w in name_words[:3]):related.append(f)
    evidence={"issue":{k:v for k,v in issue.items() if k!="raw"},"score":score,"official_filings":related[:5],"source_notes":listed.get("sources",[])}
    try:ai=synthesize_ipo_analysis(evidence)
    except Exception as exc:ai={"verdict":score["verdict"],"confidence":"low","thesis":"AI IPO synthesis unavailable; deterministic evidence score shown.","positives":[],"risks":[str(exc)[:160]],"due_diligence":["Read the RHP/SEC registration statement before applying."]}
    # Never let AI become more aggressive than the evidence when evidence is thin.
    if score["evidence_completeness_pct"]<50 and str(ai.get("verdict","")).upper()=="SUBSCRIBE":ai["verdict"]="WATCH"
    result={"market":market,"issue":issue,"research_score":score,"ai_analysis":ai,"official_filings":related[:5],"as_of":datetime.now(timezone.utc).isoformat(),"disclaimer":"Pre-listing IPO research is highly uncertain. SUBSCRIBE/WATCH/AVOID is a non-personalized research classification, not a guarantee of allotment, listing gain or profit. No GMP is used."};set_json(key,result,ttl=600);return result
