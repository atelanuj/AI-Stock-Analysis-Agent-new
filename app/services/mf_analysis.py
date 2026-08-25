import math
import numpy as np
import pandas as pd
import yfinance as yf

from app.tools.mutual_funds import get_indian_mf_data, get_us_fund_data

_BENCH = {"IN": ("^NSEI", "NIFTY 50"), "US": ("^GSPC", "S&P 500")}


def _history_df(history: list[dict]) -> pd.DataFrame:
    if not history: return pd.DataFrame(columns=["nav"])
    df = pd.DataFrame(history).copy(); df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce"); df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
    return df.dropna(subset=["date","nav"]).sort_values("date").drop_duplicates("date").set_index("date")


def calculate_returns(history: list[dict]) -> dict:
    df = _history_df(history)
    if df.empty: return {}
    latest = float(df["nav"].iloc[-1]); latest_date = df.index[-1]
    def period_return(months: int, annualized: bool=False):
        target = latest_date - pd.DateOffset(months=months); past = df[df.index <= target]
        if past.empty: return None
        base = float(past["nav"].iloc[-1]);
        if base <= 0: return None
        total = latest/base - 1
        if annualized and months >= 12: total = (1+total)**(1/(months/12))-1
        return round(total*100,2)
    vals = {"1M":period_return(1),"3M":period_return(3),"6M":period_return(6),"1Y":period_return(12),"3Y":period_return(36,True),"5Y":period_return(60,True)}
    return {k:v for k,v in vals.items() if v is not None}


def calculate_risk_metrics(history: list[dict]) -> dict:
    df = _history_df(history)
    if len(df)<20: return {}
    nav = df["nav"].astype(float); daily = nav.pct_change().replace([np.inf,-np.inf],np.nan).dropna()
    if daily.empty: return {}
    vol = float(daily.std(ddof=1)*math.sqrt(252)*100); running_peak=nav.cummax(); drawdown=nav/running_peak-1; mdd=float(drawdown.min()*100)
    downside=daily[daily<0]; downside_vol=float(downside.std(ddof=1)*math.sqrt(252)*100) if len(downside)>1 else None
    ann_return=float((nav.iloc[-1]/nav.iloc[0])**(252/max(len(daily),1))-1) if nav.iloc[0]>0 else 0
    sharpe=(ann_return/(daily.std(ddof=1)*math.sqrt(252))) if daily.std(ddof=1)>0 else None
    sortino=(ann_return/(downside.std(ddof=1)*math.sqrt(252))) if len(downside)>1 and downside.std(ddof=1)>0 else None
    rolling_1y=(nav/nav.shift(252)-1).dropna(); consistency=float((rolling_1y>0).mean()*100) if not rolling_1y.empty else None
    yearly=nav.resample("YE").last().pct_change().dropna(); positive_years=float((yearly>0).mean()*100) if not yearly.empty else None
    return {
        "annualized_volatility_pct":round(vol,2),"downside_volatility_pct":round(downside_vol,2) if downside_vol is not None else None,
        "max_drawdown_pct":round(mdd,2),"positive_day_ratio_pct":round(float((daily>0).mean()*100),2),
        "sharpe_ratio":round(float(sharpe),2) if sharpe is not None and np.isfinite(sharpe) else None,
        "sortino_ratio":round(float(sortino),2) if sortino is not None and np.isfinite(sortino) else None,
        "positive_rolling_1y_pct":round(consistency,1) if consistency is not None else None,"positive_calendar_years_pct":round(positive_years,1) if positive_years is not None else None,
    }


def _benchmark_metrics(history: list[dict], market: str) -> dict:
    df=_history_df(history)
    sym,name=_BENCH[market]
    if df.empty: return {"symbol":sym,"name":name}
    start=df.index.min(); end=df.index.max()+pd.Timedelta(days=2)
    try:
        bh=yf.Ticker(sym).history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"), auto_adjust=True)
        bclose=bh["Close"].dropna().rename("benchmark")
    except Exception:
        bclose=pd.Series(dtype=float)
    result={"symbol":sym,"name":name}
    if bclose.empty: return result
    aligned=pd.concat([df["nav"].rename("fund"), bclose],axis=1).dropna()
    if len(aligned)<30: return result
    fr=aligned["fund"].pct_change().dropna(); br=aligned["benchmark"].pct_change().dropna(); rr=pd.concat([fr.rename("f"),br.rename("b")],axis=1).dropna()
    tracking=(rr["f"]-rr["b"]).std(ddof=1)*math.sqrt(252)*100 if len(rr)>2 else None
    corr=rr["f"].corr(rr["b"]) if len(rr)>2 else None; beta=rr["f"].cov(rr["b"])/rr["b"].var() if len(rr)>2 and rr["b"].var()>0 else None
    def cagr(s):
        years=max((s.index[-1]-s.index[0]).days/365.25, 1/365.25); return ((float(s.iloc[-1])/float(s.iloc[0]))**(1/years)-1)*100 if float(s.iloc[0])>0 else None
    fc=cagr(aligned["fund"]); bc=cagr(aligned["benchmark"])
    result.update({"fund_cagr_pct":round(fc,2) if fc is not None else None,"benchmark_cagr_pct":round(bc,2) if bc is not None else None,"alpha_vs_benchmark_pct":round(fc-bc,2) if fc is not None and bc is not None else None,"tracking_error_pct":round(float(tracking),2) if tracking is not None and np.isfinite(tracking) else None,"correlation":round(float(corr),3) if corr is not None and np.isfinite(corr) else None,"beta":round(float(beta),2) if beta is not None and np.isfinite(beta) else None})
    return result


def _expense_pct(value):
    try:
        v=float(value); return v*100 if v<=1 else v
    except (TypeError,ValueError): return None


def _score_breakdown(returns:dict,risk:dict,benchmark:dict,expense_ratio,total_assets) -> dict:
    # 0-100 category scores; generic research heuristics, not category-specific ratings.
    r3=returns.get("3Y"); r5=returns.get("5Y"); r1=returns.get("1Y")
    return_score=50
    for r,w in [(r1,15),(r3,20),(r5,15)]:
        if r is not None: return_score += w if r>=12 else w*.5 if r>=7 else -w*.6 if r<0 else 0
    return_score=max(0,min(100,return_score))
    consistency=risk.get("positive_rolling_1y_pct"); consistency_score=50 if consistency is None else max(0,min(100,consistency))
    mdd=risk.get("max_drawdown_pct"); vol=risk.get("annualized_volatility_pct"); sharpe=risk.get("sharpe_ratio")
    risk_score=70
    if mdd is not None: risk_score += 15 if mdd>-15 else 5 if mdd>-25 else -20 if mdd<=-40 else -8
    if vol is not None: risk_score += 10 if vol<12 else -15 if vol>35 else 0
    if sharpe is not None: risk_score += 10 if sharpe>=1 else 5 if sharpe>=.6 else -8 if sharpe<0 else 0
    risk_score=max(0,min(100,risk_score))
    er=_expense_pct(expense_ratio); cost_score=60 if er is None else 95 if er<=.25 else 80 if er<=.5 else 60 if er<=1 else 35 if er<=1.5 else 15
    alpha=benchmark.get("alpha_vs_benchmark_pct"); track=benchmark.get("tracking_error_pct"); benchmark_score=50
    if alpha is not None: benchmark_score += 25 if alpha>=3 else 12 if alpha>=1 else -15 if alpha<=-2 else 0
    if track is not None and track<1: benchmark_score += 10
    benchmark_score=max(0,min(100,benchmark_score))
    drawdown_score=50 if mdd is None else 90 if mdd>-12 else 75 if mdd>-20 else 55 if mdd>-30 else 25 if mdd>-45 else 10
    overall=return_score*.3+consistency_score*.2+risk_score*.2+cost_score*.1+benchmark_score*.1+drawdown_score*.1
    return {"return":round(return_score,1),"consistency":round(consistency_score,1),"risk":round(risk_score,1),"cost":round(cost_score,1),"benchmark":round(benchmark_score,1),"drawdown":round(drawdown_score,1),"overall":round(overall,1)}


def _fund_rating(score:float)->str:
    return "EXCELLENT" if score>=80 else "GOOD" if score>=65 else "AVERAGE" if score>=50 else "BELOW AVERAGE" if score>=35 else "POOR"


def analyze_mutual_fund(identifier:str, market:str)->dict:
    market=market.upper()
    if market=="IN": data=get_indian_mf_data(identifier)
    elif market=="US": data=get_us_fund_data(identifier)
    else: raise ValueError("market must be IN or US")
    full=data.get("history",[]); returns=calculate_returns(full); risk=calculate_risk_metrics(full); benchmark=_benchmark_metrics(full,market)
    breakdown=_score_breakdown(returns,risk,benchmark,data.get("expense_ratio"),data.get("total_assets")); score=breakdown["overall"]; rating=_fund_rating(score)
    data["returns"]=returns; data["risk_metrics"]=risk; data["benchmark"]=benchmark
    data["analysis"]={"score":score,"rating":rating,"score_breakdown":breakdown,"summary":f"{market} fund score {score}/100. 1Y {returns.get('1Y','N/A')}%; 3Y annualized {returns.get('3Y','N/A')}%; Sharpe {risk.get('sharpe_ratio','N/A')}; benchmark alpha {benchmark.get('alpha_vs_benchmark_pct','N/A')}%.","method":"Fund-specific scoring: returns, consistency, risk, drawdown, costs and benchmark behavior. Not a recommendation."}
    data["history"]=full[:260]
    return data
