from __future__ import annotations

import math
import numpy as np
import pandas as pd

from app.tools.data_provider import get_history_df


def _rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d=s.diff(); gain=d.clip(lower=0); loss=-d.clip(upper=0)
    ag=gain.ewm(alpha=1/n,adjust=False,min_periods=n).mean(); al=loss.ewm(alpha=1/n,adjust=False,min_periods=n).mean()
    return 100-(100/(1+ag/al.replace(0,np.nan)))


def _features(hist: pd.DataFrame) -> pd.DataFrame:
    out=hist.copy(); c=out["Close"].astype(float); v=out.get("Volume",pd.Series(0,index=out.index)).fillna(0).astype(float)
    out["sma50"]=c.rolling(50).mean();out["sma200"]=c.rolling(200).mean();out["rsi"]=_rsi(c)
    e12=c.ewm(span=12,adjust=False).mean();e26=c.ewm(span=26,adjust=False).mean();out["macd"]=e12-e26;out["macd_signal"]=out["macd"].ewm(span=9,adjust=False).mean();out["avgvol"]=v.rolling(20).mean();return out


def _signals(df: pd.DataFrame, cfg: dict) -> pd.Series:
    return ((df["Close"]>df["sma200"])&(df["sma50"]>df["sma200"])&(df["rsi"]>=cfg["rsi_low"])&(df["rsi"]<=cfg["rsi_high"])&(df["macd"]>df["macd_signal"])&(df.get("Volume",0)>=df["avgvol"]*cfg["volume_mult"])).fillna(False)


def _evaluate(df: pd.DataFrame, cfg: dict, horizon: int = 10) -> dict:
    sig=_signals(df,cfg).to_numpy(); close=df["Close"].astype(float).to_numpy(); positions=[];last=-999
    for i in np.where(sig)[0]:
        if i-last>=cfg["cooldown"] and i+horizon<len(close):positions.append(int(i));last=int(i)
    rets=[(close[i+horizon]/close[i]-1)*100 for i in positions if close[i]>0 and math.isfinite(close[i+horizon])]
    if not rets:return {"signals":0,"win_rate_pct":None,"average_return_pct":None,"score":-999}
    win=sum(r>0 for r in rets)/len(rets)*100;avg=float(np.mean(rets));score=win+max(-15,min(15,avg*3))
    return {"signals":len(rets),"win_rate_pct":round(win,1),"average_return_pct":round(avg,2),"median_return_pct":round(float(np.median(rets)),2),"score":round(score,2)}


def walk_forward_backtest(symbol: str, market: str = "IN", period: str = "10y") -> dict:
    hist=get_history_df(symbol,market,period=period,interval="1d",auto_adjust=True)
    if hist.empty or len(hist)<600:raise ValueError(f"Need at least ~600 clean daily sessions for walk-forward testing; found {len(hist)}")
    df=_features(hist.dropna(subset=["Close"]).copy())
    configs=[
        {"name":"Balanced","rsi_low":45,"rsi_high":68,"volume_mult":0.8,"cooldown":5},
        {"name":"Momentum","rsi_low":50,"rsi_high":72,"volume_mult":1.0,"cooldown":5},
        {"name":"Conservative","rsi_low":45,"rsi_high":62,"volume_mult":1.1,"cooldown":8},
        {"name":"Broad","rsi_low":40,"rsi_high":70,"volume_mult":0.7,"cooldown":5},
    ]
    # Expanding train window, next ~1 trading year as genuinely unseen test data.
    start_train=max(400,int(len(df)*0.4)); test_size=252; folds=[];cursor=start_train
    while cursor+120<len(df):
        test_end=min(len(df),cursor+test_size);train=df.iloc[:cursor];test=df.iloc[max(0,cursor-220):test_end].copy()
        scored=[(_evaluate(train,cfg),cfg) for cfg in configs];scored.sort(key=lambda x:x[0]["score"],reverse=True);best_train,best_cfg=scored[0]
        # Only score signals whose actual entry sits in the unseen section.
        full_eval=_evaluate(test,best_cfg); test_start_date=df.index[cursor]
        sig=_signals(test,best_cfg); idxs=[i for i in np.where(sig.to_numpy())[0] if test.index[i]>=test_start_date and i+10<len(test)]
        rets=[];last=-999
        for i in idxs:
            if i-last<best_cfg["cooldown"]:continue
            a=float(test["Close"].iloc[i]);b=float(test["Close"].iloc[i+10]);last=i
            if a>0 and math.isfinite(b):rets.append((b/a-1)*100)
        test_stats={"signals":len(rets),"win_rate_pct":round(sum(r>0 for r in rets)/len(rets)*100,1) if rets else None,"average_return_pct":round(float(np.mean(rets)),2) if rets else None,"median_return_pct":round(float(np.median(rets)),2) if rets else None}
        folds.append({"train_end":df.index[cursor-1].strftime("%Y-%m-%d"),"test_start":test_start_date.strftime("%Y-%m-%d"),"test_end":df.index[test_end-1].strftime("%Y-%m-%d"),"selected_configuration":best_cfg["name"],"train":best_train,"test":test_stats})
        cursor+=test_size
    all_signals=sum(f["test"]["signals"] for f in folds); weighted_wins=sum((f["test"]["win_rate_pct"] or 0)*f["test"]["signals"] for f in folds); weighted_avg=sum((f["test"]["average_return_pct"] or 0)*f["test"]["signals"] for f in folds)
    aggregate={"folds":len(folds),"signals":all_signals,"out_of_sample_win_rate_pct":round(weighted_wins/all_signals,1) if all_signals else None,"out_of_sample_average_10d_return_pct":round(weighted_avg/all_signals,2) if all_signals else None}
    return {"symbol":symbol.upper(),"market":market.upper(),"period":period,"method":"Expanding-window configuration selection; each next ~252-session block is held out and evaluated only after configuration selection on prior data.","aggregate":aggregate,"folds":folds,"warning":"Out-of-sample historical results still do not guarantee future performance; fees, slippage and taxes are excluded."}
