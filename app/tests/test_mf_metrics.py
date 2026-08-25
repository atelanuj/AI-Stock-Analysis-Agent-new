from datetime import datetime, timedelta
import sys
import types

sys.modules.setdefault("yfinance", types.SimpleNamespace())

from app.services.mf_analysis import calculate_returns, calculate_risk_metrics


def synthetic_history(days=1300):
    start = datetime(2021, 1, 1)
    rows = []
    nav = 100.0
    for i in range(days):
        nav *= 1.00025
        d = start + timedelta(days=i)
        rows.append({"date": d.strftime("%d-%m-%Y"), "nav": nav})
    rows.reverse()
    return rows


def test_fund_metrics_exist():
    history = synthetic_history()
    returns = calculate_returns(history)
    risk = calculate_risk_metrics(history)
    assert "1Y" in returns
    assert "3Y" in returns
    assert "annualized_volatility_pct" in risk
    assert "max_drawdown_pct" in risk
