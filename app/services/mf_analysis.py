import math

import numpy as np
import pandas as pd

from app.tools.mutual_funds import get_indian_mf_data, get_us_fund_data


def _history_df(history: list[dict]) -> pd.DataFrame:
    if not history:
        return pd.DataFrame(columns=["nav"])
    df = pd.DataFrame(history).copy()
    df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
    df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
    df = df.dropna(subset=["date", "nav"]).sort_values("date").drop_duplicates("date")
    return df.set_index("date")


def calculate_returns(history: list[dict]) -> dict:
    df = _history_df(history)
    if df.empty:
        return {}

    latest_nav = float(df["nav"].iloc[-1])
    latest_date = df.index[-1]

    def period_return(months: int, annualized: bool = False):
        target = latest_date - pd.DateOffset(months=months)
        past = df[df.index <= target]
        if past.empty:
            return None
        base = float(past["nav"].iloc[-1])
        if base <= 0:
            return None
        total = latest_nav / base - 1
        if annualized and months >= 12:
            years = months / 12
            total = (1 + total) ** (1 / years) - 1
        return round(total * 100, 2)

    values = {
        "1M": period_return(1),
        "3M": period_return(3),
        "6M": period_return(6),
        "1Y": period_return(12),
        "3Y": period_return(36, annualized=True),
        "5Y": period_return(60, annualized=True),
    }
    return {k: v for k, v in values.items() if v is not None}


def calculate_risk_metrics(history: list[dict]) -> dict:
    df = _history_df(history)
    if len(df) < 20:
        return {}

    nav = df["nav"].astype(float)
    daily = nav.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    if daily.empty:
        return {}

    annualized_vol = float(daily.std(ddof=1) * math.sqrt(252) * 100)
    running_peak = nav.cummax()
    drawdown = nav / running_peak - 1
    max_drawdown = float(drawdown.min() * 100)

    positive_days = float((daily > 0).mean() * 100)
    downside = daily[daily < 0]
    downside_vol = float(downside.std(ddof=1) * math.sqrt(252) * 100) if len(downside) > 1 else None

    one_year = nav.tail(253)
    if len(one_year) > 1:
        one_year_peak = one_year.cummax()
        one_year_mdd = float((one_year / one_year_peak - 1).min() * 100)
    else:
        one_year_mdd = None

    return {
        "annualized_volatility_pct": round(annualized_vol, 2),
        "downside_volatility_pct": round(downside_vol, 2) if downside_vol is not None else None,
        "max_drawdown_pct": round(max_drawdown, 2),
        "one_year_max_drawdown_pct": round(one_year_mdd, 2) if one_year_mdd is not None else None,
        "positive_day_ratio_pct": round(positive_days, 2),
    }


def _fund_score(returns: dict, risk: dict, expense_ratio) -> float:
    score = 50.0

    r1 = returns.get("1Y")
    r3 = returns.get("3Y")
    r5 = returns.get("5Y")
    if r1 is not None:
        score += 10 if r1 >= 15 else 5 if r1 >= 8 else -10 if r1 < 0 else 0
    if r3 is not None:
        score += 15 if r3 >= 12 else 8 if r3 >= 8 else -12 if r3 < 0 else 0
    if r5 is not None:
        score += 12 if r5 >= 12 else 6 if r5 >= 8 else -8 if r5 < 0 else 0

    mdd = risk.get("max_drawdown_pct")
    if mdd is not None:
        score += 8 if mdd > -15 else 3 if mdd > -25 else -10 if mdd <= -40 else -4

    vol = risk.get("annualized_volatility_pct")
    if vol is not None:
        score += 5 if vol < 12 else 2 if vol < 20 else -6 if vol > 35 else 0

    try:
        er = float(expense_ratio) if expense_ratio is not None else None
        # Yahoo commonly exposes this as a decimal fraction (e.g. 0.0003 = 0.03%).
        if er is not None:
            er_pct = er * 100 if er <= 1 else er
            score += 3 if er_pct <= 0.30 else -4 if er_pct >= 1.50 else 0
    except (TypeError, ValueError):
        pass

    return round(max(0.0, min(100.0, score)), 1)


def _fund_rating(score: float) -> str:
    if score >= 80:
        return "EXCELLENT"
    if score >= 65:
        return "GOOD"
    if score >= 50:
        return "AVERAGE"
    if score >= 35:
        return "BELOW AVERAGE"
    return "POOR"


def analyze_mutual_fund(identifier: str, market: str) -> dict:
    market = market.upper()
    if market == "IN":
        data = get_indian_mf_data(identifier)
    elif market == "US":
        data = get_us_fund_data(identifier)
    else:
        raise ValueError("market must be IN or US")

    full_history = data.get("history", [])
    returns = calculate_returns(full_history)
    risk_metrics = calculate_risk_metrics(full_history)
    score = _fund_score(returns, risk_metrics, data.get("expense_ratio"))
    rating = _fund_rating(score)

    data["returns"] = returns
    data["risk_metrics"] = risk_metrics
    data["analysis"] = {
        "score": score,
        "rating": rating,
        "summary": (
            f"{market} fund score {score}/100. "
            f"1Y return: {returns.get('1Y', 'N/A')}%; "
            f"3Y annualized: {returns.get('3Y', 'N/A')}%; "
            f"max drawdown: {risk_metrics.get('max_drawdown_pct', 'N/A')}%."
        ),
        "method": "Return, drawdown, volatility and available cost metrics; not a recommendation.",
    }
    data["history"] = full_history[:260]
    return data
