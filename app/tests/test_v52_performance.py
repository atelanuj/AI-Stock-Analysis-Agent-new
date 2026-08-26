import pandas as pd

from app.tools import technical


def _hist(rows=280):
    idx=pd.date_range("2025-01-01",periods=rows,freq="B")
    close=pd.Series([100+i*.1 for i in range(rows)],index=idx,dtype=float)
    return pd.DataFrame({"Open":close-.2,"High":close+.8,"Low":close-.8,"Close":close,"Volume":1_000_000},index=idx)


def test_daily_chart_ranges_reuse_cached_one_year_history(monkeypatch):
    calls=[]
    def fake_history(symbol,market,period="1y",interval="1d",auto_adjust=False):
        calls.append((period,interval,auto_adjust))
        return _hist()
    monkeypatch.setattr(technical,"get_history_df",fake_history)
    rows=technical.get_ohlcv_history("TEST","US","3mo","1d")
    assert rows
    assert calls == [("1y","1d",False)]


def test_intraday_1d_chart_requests_multi_day_intraday_buffer(monkeypatch):
    calls=[]
    def fake_history(symbol,market,period="1y",interval="1d",auto_adjust=False):
        calls.append((period,interval,auto_adjust))
        return _hist(50)
    monkeypatch.setattr(technical,"get_history_df",fake_history)
    technical.get_ohlcv_history("TEST","US","1d","5m")
    assert calls == [("5d","5m",False)]
