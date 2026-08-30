from __future__ import annotations

import math
import numpy as np
import pandas as pd

from app.models.api import StrategyBacktestRequest
from app.tools.data_provider import get_history_df


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta=series.diff(); gain=delta.clip(lower=0); loss=-delta.clip(upper=0)
    avg_gain=gain.ewm(alpha=1/period,adjust=False,min_periods=period).mean()
    avg_loss=loss.ewm(alpha=1/period,adjust=False,min_periods=period).mean()
    rs=avg_gain/avg_loss.replace(0,np.nan)
    return 100-(100/(1+rs))


def _clean(v, digits=2):
    try:
        n=float(v)
        return round(n,digits) if math.isfinite(n) else None
    except Exception:
        return None


def backtest_custom_strategy(request: StrategyBacktestRequest) -> dict:
    symbol=request.symbol.upper().strip(); market=request.market.upper()
    df=get_history_df(symbol,market,request.period,"1d",True).copy()
    if df.empty or "Close" not in df or len(df)<220:
        raise ValueError("At least ~220 usable daily sessions are required for this strategy test")
    for col in ("Open","High","Low","Close","Volume"):
        if col in df: df[col]=pd.to_numeric(df[col],errors="coerce")
    df=df.dropna(subset=["Close"]); c=df["Close"]
    df["rsi14"]=_rsi(c); df["sma200"]=c.rolling(200).mean();
    macd=c.ewm(span=12,adjust=False).mean()-c.ewm(span=26,adjust=False).mean(); df["macd"]=macd;df["macd_signal"]=macd.ewm(span=9,adjust=False).mean()
    if "Volume" in df:
        vol=df["Volume"].fillna(0);avg20=vol.rolling(20).mean().replace(0,np.nan);df["relative_volume"]=vol/avg20
    else:df["relative_volume"]=np.nan
    cond=pd.Series(True,index=df.index)
    if request.rsi_min is not None:cond&=df["rsi14"]>=request.rsi_min
    if request.rsi_max is not None:cond&=df["rsi14"]<=request.rsi_max
    if request.require_above_sma200:cond&=c>df["sma200"]
    if request.require_macd_bullish:
        cond&=(df["macd"]>df["macd_signal"]) if request.direction=="LONG" else (df["macd"]<df["macd_signal"])
    if request.min_relative_volume is not None:cond&=df["relative_volume"]>=request.min_relative_volume
    # Avoid counting every adjacent day in one persistent regime as a new independent signal.
    entries=cond & ~cond.shift(1,fill_value=False)
    forward=(c.shift(-request.forward_days)/c-1)*100
    returns=forward[entries].replace([np.inf,-np.inf],np.nan).dropna()
    if request.direction=="SHORT":returns=-returns
    wins=returns[returns>0];losses=returns[returns<=0]
    signal_dates=[pd.Timestamp(x).strftime("%Y-%m-%d") for x in returns.index[-20:]]
    buy_hold=(float(c.iloc[-1])/float(c.iloc[0])-1)*100 if float(c.iloc[0]) else None
    return {
        "symbol":symbol,"market":market,"period":request.period,"direction":request.direction,
        "rules":request.model_dump(),"signals":int(len(returns)),
        "win_rate_pct":_clean(len(wins)/len(returns)*100 if len(returns) else None,1),
        "average_forward_return_pct":_clean(returns.mean() if len(returns) else None),
        "median_forward_return_pct":_clean(returns.median() if len(returns) else None),
        "average_win_pct":_clean(wins.mean() if len(wins) else None),
        "average_loss_pct":_clean(losses.mean() if len(losses) else None),
        "best_outcome_pct":_clean(returns.max() if len(returns) else None),
        "worst_outcome_pct":_clean(returns.min() if len(returns) else None),
        "buy_hold_period_return_pct":_clean(buy_hold),"recent_signal_dates":signal_dates,
        "warning":"Historical rule testing is not a forecast. It excludes fees, taxes, slippage, survivorship effects and execution constraints. Adjacent qualifying days are collapsed into one signal.",
    }
