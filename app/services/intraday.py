from __future__ import annotations

import math
from datetime import timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from app.agent.client import synthesize_intraday_decision
from app.cache.redis_cache import get_json, set_json
from app.config import settings
from app.tools.data_provider import get_history_df
from app.tools.market_validation import get_validated_quote
from app.tools.technical import predict_next_candle

_INTERVALS={"1m":"1m","5m":"5m","15m":"15m","30m":"30m","60m":"60m"}


def _rsi(s:pd.Series,n=14):
    d=s.diff();g=d.clip(lower=0);l=-d.clip(upper=0);ag=g.ewm(alpha=1/n,adjust=False,min_periods=n).mean();al=l.ewm(alpha=1/n,adjust=False,min_periods=n).mean();return 100-100/(1+ag/al.replace(0,np.nan))


def _latest_session(df: pd.DataFrame, market: str) -> pd.DataFrame:
    if df.empty:return df
    tz=ZoneInfo("America/New_York" if market=="US" else "Asia/Kolkata")
    idx=pd.DatetimeIndex(df.index)
    if idx.tz is None:idx=idx.tz_localize("UTC")
    local=idx.tz_convert(tz);tmp=df.copy();tmp["_local_date"]=local.date;tmp["_local_time"]=[t.time() for t in local]
    start=pd.Timestamp("09:30").time() if market=="US" else pd.Timestamp("09:15").time();end=pd.Timestamp("16:00").time() if market=="US" else pd.Timestamp("15:30").time()
    tmp=tmp[(tmp["_local_time"]>=start)&(tmp["_local_time"]<=end)]
    if tmp.empty:return df.tail(100)
    latest=tmp["_local_date"].max();return tmp[tmp["_local_date"]==latest].drop(columns=["_local_date","_local_time"])


def _finite(v,d=2):
    try:n=float(v);return round(n,d) if math.isfinite(n) else None
    except:return None


def _bars_from_frame(frame: pd.DataFrame) -> list[dict]:
    rows=[]
    for idx,row in frame.iterrows():
        volume=_finite(row.get("Volume"),0)
        rows.append({"date":pd.Timestamp(idx).isoformat(),"open":_finite(row.get("Open"),4),"high":_finite(row.get("High"),4),"low":_finite(row.get("Low"),4),"close":_finite(row.get("Close"),4),"volume":int(volume or 0)})
    return rows


def _add_price_candidate(items:list[dict],candidate_id:str,label:str,value)->None:
    price=_finite(value,4)
    if price is None or price<=0:return
    items.append({"id":candidate_id,"label":label,"price":price})


def _intraday_level_candidates(core:dict)->list[dict]:
    price=float(core.get("price") or 0);i=core.get("indicators",{}) or {};o=core.get("opening_range",{}) or {};s=core.get("session",{}) or {};atr=float(i.get("bar_atr") or (price*.003 if price else 0))
    items=[]
    _add_price_candidate(items,"technical_target","deterministic session target",core.get("technical_target"))
    _add_price_candidate(items,"risk_control","deterministic session risk-control",core.get("risk_control"))
    _add_price_candidate(items,"vwap","session VWAP",i.get("vwap"))
    _add_price_candidate(items,"opening_range_high","opening-range high",o.get("high"))
    _add_price_candidate(items,"opening_range_low","opening-range low",o.get("low"))
    _add_price_candidate(items,"session_high","session high",s.get("high"))
    _add_price_candidate(items,"session_low","session low",s.get("low"))
    for multiple in (1.0,1.5,2.0):
        suffix=str(multiple).replace(".","_")
        _add_price_candidate(items,f"price_plus_{suffix}_atr",f"price plus {multiple:g} bar ATR",price+multiple*atr)
        _add_price_candidate(items,f"price_minus_{suffix}_atr",f"price minus {multiple:g} bar ATR",price-multiple*atr)
    return items


def _intraday_candle_candidates(core:dict)->list[dict]:
    price=float(core.get("price") or 0);atr=float((core.get("indicators",{}) or {}).get("bar_atr") or (price*.003 if price else 0));pattern=core.get("next_candle_pattern_projection") or {};bars=core.get("bars") or []
    if pattern.get("date"):next_date=pattern["date"]
    elif bars:
        minutes=int(str(core.get("interval","5m"))[:-1] or 5);next_date=(pd.Timestamp(bars[-1]["date"])+pd.Timedelta(minutes=minutes)).isoformat()
    else:return []
    items=[]
    def add(candidate_id,label,open_price,high,low,close,basis):
        values=[_finite(v,4) for v in (open_price,high,low,close)]
        if any(v is None or v<=0 for v in values):return
        op,hi,lo,cl=values;hi=max(hi,op,cl);lo=min(lo,op,cl);body=abs(cl/op-1)*100 if op else 0;direction="NEUTRAL" if body<.02 else "BULLISH" if cl>op else "BEARISH"
        items.append({"id":candidate_id,"label":label,"date":next_date,"open":op,"high":_finite(hi,4),"low":_finite(lo,4),"close":cl,"direction":direction,"basis":basis})
    if all(pattern.get(k) is not None for k in ("open","high","low","close")):
        add("historical_pattern_analog","historical pattern analog",pattern["open"],pattern["high"],pattern["low"],pattern["close"],pattern.get("method","Closest historical candle-shape analogs"))
    add("bullish_continuation","bullish momentum continuation",price,price+.7*atr,price-.15*atr,price+.45*atr,"Bounded continuation using current bar ATR")
    add("bearish_continuation","bearish momentum continuation",price,price+.15*atr,price-.7*atr,price-.45*atr,"Bounded continuation using current bar ATR")
    add("balanced_consolidation","balanced consolidation",price,price+.3*atr,price-.3*atr,price,"Bounded neutral range using current bar ATR")
    return items


def _resolve_ai_levels(core:dict,ai:dict,candidates:list[dict])->dict:
    by_id={item["id"]:item for item in candidates};target=by_id.get(str(ai.get("target_candidate_id") or ""));stop=by_id.get(str(ai.get("stop_candidate_id") or ""));direction=str(ai.get("setup_direction") or core.get("bias") or "BULLISH").upper();entry=float(core.get("price") or 0)
    valid=direction in {"BULLISH","BEARISH"} and target is not None and stop is not None and entry>0
    if valid:
        tp=float(target["price"]);sp=float(stop["price"]);valid=(direction=="BULLISH" and tp>entry>sp) or (direction=="BEARISH" and tp<entry<sp)
    if not valid:return {"target":core.get("technical_target"),"risk_control":core.get("risk_control"),"setup_direction":core.get("bias"),"level_source":"deterministic_fallback","level_rationale":"AI did not return a valid directional target/stop pair; session-structure fallback levels are shown."}
    return {"target":target["price"],"risk_control":stop["price"],"setup_direction":direction,"level_source":"ai_selected","target_candidate_id":target["id"],"stop_candidate_id":stop["id"],"level_rationale":str(ai.get("level_rationale") or "Nemotron selected these validated intraday levels.")}


def _resolve_ai_candle(core:dict,ai:dict,candidates:list[dict])->dict|None:
    by_id={item["id"]:item for item in candidates};selected=by_id.get(str(ai.get("next_candle_candidate_id") or ""));source="ai_selected"
    if selected is None:
        selected=by_id.get("historical_pattern_analog") or next(iter(candidates),None);source="validated_fallback"
    if selected is None:return None
    result=dict(selected);result["source"]=source;result["confidence"]=str(ai.get("next_candle_confidence") or ai.get("confidence") or "low").lower();result["rationale"]=str(ai.get("candle_rationale") or selected.get("basis") or "Validated intraday scenario.");result["note"]="Nemotron selected this bounded next-candle scenario from validated session candidates; it is not a guaranteed forecast."
    return result


def get_intraday_analysis(symbol:str,market:str="IN",interval:str="5m",force_refresh:bool=False)->dict:
    symbol=symbol.upper();market=market.upper();interval=interval if interval in _INTERVALS else "5m";key=f"intraday:v9:{market}:{symbol}:{interval}"
    if not force_refresh:
        c=get_json(key)
        if c:return c
    period="5d" if interval!="1m" else "5d"
    hist=get_history_df(symbol,market,period=period,interval=interval,auto_adjust=False,force_refresh=force_refresh);session=_latest_session(hist,market)
    if session.empty or len(session)<5:raise ValueError(f"Insufficient intraday bars for {symbol}")
    c=session["Close"].astype(float);h=session["High"].astype(float);l=session["Low"].astype(float);v=session.get("Volume",pd.Series(0,index=session.index)).astype(float);typ=(h+l+c)/3;cumv=v.cumsum().replace(0,np.nan);vwap=(typ*v).cumsum()/cumv
    ema9=c.ewm(span=9,adjust=False).mean();ema21=c.ewm(span=21,adjust=False).mean();rsi=_rsi(c);macd=c.ewm(span=12,adjust=False).mean()-c.ewm(span=26,adjust=False).mean();ms=macd.ewm(span=9,adjust=False).mean()
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1);atr=tr.rolling(min(14,len(tr))).mean()
    # First 30 minutes opening range: number of bars derived from interval.
    minutes=int(interval[:-1]) if interval.endswith("m") else 60;orb_bars=max(1,math.ceil(30/minutes));opening=session.iloc[:orb_bars];orb_high=float(opening["High"].max());orb_low=float(opening["Low"].min());price=float(c.iloc[-1]);session_open=float(session["Open"].iloc[0]);session_high=float(h.max());session_low=float(l.min())
    votes=[]
    votes.append(1 if price>float(vwap.iloc[-1]) else -1);votes.append(1 if float(ema9.iloc[-1])>float(ema21.iloc[-1]) else -1);votes.append(1 if float(macd.iloc[-1])>float(ms.iloc[-1]) else -1);rv=_finite(rsi.iloc[-1])
    if rv is not None:votes.append(1 if 52<=rv<=70 else -1 if rv<42 or rv>78 else 0)
    if price>orb_high:votes.append(1)
    elif price<orb_low:votes.append(-1)
    score=sum(votes);bias="BULLISH" if score>=2 else "BEARISH" if score<=-2 else "NEUTRAL";agreement=round((sum(1 for x in votes if x==(1 if bias=="BULLISH" else -1 if bias=="BEARISH" else 0))/max(1,len(votes)))*100) if bias!="NEUTRAL" else round((1-abs(score)/max(1,len(votes)))*100)
    atrv=float(atr.iloc[-1]) if pd.notna(atr.iloc[-1]) else max((session_high-session_low)/4,price*.003)
    if bias=="BULLISH":target=max(orb_high,price+1.5*atrv);stop=min(float(vwap.iloc[-1]),price-atrv)
    elif bias=="BEARISH":target=min(orb_low,price-1.5*atrv);stop=max(float(vwap.iloc[-1]),price+atrv)
    else:target=price+atrv;stop=price-atrv
    quote=get_validated_quote(symbol,market,None,force_refresh)
    rows=_bars_from_frame(session);history_rows=_bars_from_frame(hist);pattern_projection=predict_next_candle(history_rows,interval)
    result={"symbol":symbol,"market":market,"interval":interval,"bars":rows,"bar_count":len(rows),"price":_finite(quote.get("price") or price,4),"session":{"open":_finite(session_open,4),"high":_finite(session_high,4),"low":_finite(session_low,4),"change_pct":_finite((price/session_open-1)*100,2) if session_open else None},"indicators":{"vwap":_finite(vwap.iloc[-1],4),"ema9":_finite(ema9.iloc[-1],4),"ema21":_finite(ema21.iloc[-1],4),"rsi14":rv,"macd":_finite(macd.iloc[-1],4),"macd_signal":_finite(ms.iloc[-1],4),"bar_atr":_finite(atrv,4)},"opening_range":{"high":_finite(orb_high,4),"low":_finite(orb_low,4),"status":"ABOVE ORB" if price>orb_high else "BELOW ORB" if price<orb_low else "INSIDE ORB"},"bias":bias,"signal_agreement_pct":agreement,"deterministic_action":"BUY" if bias=="BULLISH" and agreement>=55 else "SELL" if bias=="BEARISH" and agreement>=55 else "HOLD","technical_target":_finite(target,4),"risk_control":_finite(stop,4),"next_candle_pattern_projection":pattern_projection,"quote_validation":quote,"note":"Intraday signals use exchange-session bars, VWAP, EMA9/21, RSI, MACD and opening-range structure. They are highly time-sensitive and not guaranteed."}
    set_json(key,result,ttl=settings.intraday_cache_ttl_seconds);return result


def get_intraday_ai(symbol:str,market:str="IN",interval:str="5m",force_refresh:bool=False)->dict:
    core=get_intraday_analysis(symbol,market,interval,force_refresh);key=f"intraday:v9:ai:{market}:{symbol}:{interval}"
    if not force_refresh:
        c=get_json(key)
        if c:return c
    level_candidates=_intraday_level_candidates(core);candle_candidates=_intraday_candle_candidates(core);payload={k:v for k,v in core.items() if k not in {"bars","quote_validation"}};payload["level_candidates"]=level_candidates;payload["candle_candidates"]=candle_candidates
    try:ai=synthesize_intraday_decision(payload)
    except Exception as exc:ai={"recommendation":core["deterministic_action"],"confidence":"low","summary":"AI unavailable; deterministic intraday signal shown.","confirming_signals":[],"risks":[str(exc)[:160]],"setup_direction":core.get("bias")}
    levels=_resolve_ai_levels(core,ai,level_candidates);prediction=_resolve_ai_candle(core,ai,candle_candidates)
    result={"symbol":symbol.upper(),"market":market.upper(),"interval":interval,"deterministic":core["deterministic_action"],"ai":ai,**levels,"next_candle_prediction":prediction,"note":"Nemotron selects target, stop-loss and a bounded next-candle scenario from validated current-session candidates. These are estimates, not guaranteed executable levels or forecasts."};set_json(key,result,ttl=300);return result
