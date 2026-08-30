from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pandas as pd

from app.db.database import list_technical_recommendations
from app.tools.data_provider import get_history_df


def _target_midpoint(row: dict) -> float | None:
    values = [float(value) for value in (row.get("target_low"), row.get("target_high")) if value is not None]
    return round(sum(values) / len(values), 4) if values else None


def _evaluate(row:dict)->dict:
    out=dict(row)
    out.update({"ai_target": _target_midpoint(row), "ai_stop_loss": row.get("risk_control")})
    try:
        hist=get_history_df(row["symbol"],row["market"],"1y","1d",True)
        if hist.empty:return out
        c=hist["Close"].dropna();current=float(c.iloc[-1]);entry=float(row.get("entry_price") or current);created=pd.Timestamp(row.get("created_at"));idx=pd.DatetimeIndex(c.index)
        if idx.tz is not None:idx=idx.tz_localize(None)
        created=created.tz_localize(None) if created.tzinfo else created
        path=c.copy();path.index=idx;path=path[path.index>=created.normalize()]
        ret=(current/entry-1)*100 if entry else None;rec=row.get("recommendation")
        target_high=row.get("target_high");target_low=row.get("target_low");risk=row.get("risk_control")
        status="OPEN"
        if not path.empty:
            if rec=="BUY":
                if target_low is not None and float(path.max())>=float(target_low):status="TARGET REACHED"
                elif risk is not None and float(path.min())<=float(risk):status="RISK LEVEL BREACHED"
            elif rec=="SELL":
                if target_high is not None and float(path.min())<=float(target_high):status="TARGET REACHED"
                elif risk is not None and float(path.max())>=float(risk):status="RISK LEVEL BREACHED"
            elif rec=="HOLD":status="TRACKING"
        out.update({"current_price":round(current,4),"return_since_call_pct":round(ret,2) if ret is not None else None,"status":status})
    except Exception:pass
    return out


def recommendation_performance(symbol:str|None=None,market:str|None=None,limit:int=30)->dict:
    rows=list_technical_recommendations(symbol,market,limit)
    with ThreadPoolExecutor(max_workers=8) as pool:evaluated=list(pool.map(_evaluate,rows)) if rows else []
    directional=[r for r in evaluated if r.get("recommendation") in {"BUY","SELL"} and r.get("return_since_call_pct") is not None]
    correct=0
    for r in directional:
        ret=r["return_since_call_pct"];correct+=int((r["recommendation"]=="BUY" and ret>0) or (r["recommendation"]=="SELL" and ret<0))
    return {"items":evaluated,"summary":{"records":len(evaluated),"directional_records":len(directional),"directional_mark_to_market_hit_rate_pct":round(correct/len(directional)*100,1) if directional else None,"targets_reached":sum(r.get("status")=="TARGET REACHED" for r in evaluated),"risk_levels_breached":sum(r.get("status")=="RISK LEVEL BREACHED" for r in evaluated)},"note":"This is a live mark-to-market audit of stored research calls, not a clean strategy backtest. Calls are only recorded after V8/V7 technical decisions are requested."}
