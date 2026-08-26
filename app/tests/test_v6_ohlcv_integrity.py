import pandas as pd

from app.tools.data_provider import sanitize_ohlcv_frame
from app.tools.technical import _latest_intraday_session


def test_sanitize_ohlcv_drops_impossible_bars():
    idx = pd.date_range("2026-08-25 09:15", periods=3, freq="5min", tz="Asia/Kolkata")
    df = pd.DataFrame({
        "Open": [100, 100, 100],
        "High": [102, 99, 103],  # middle high is impossible
        "Low": [99, 98, 99],
        "Close": [101, 101, 102],
        "Volume": [1000, 1000, 1000],
    }, index=idx)
    clean = sanitize_ohlcv_frame(df)
    assert len(clean) == 2
    assert (clean["High"] >= clean[["Open", "Low", "Close"]].max(axis=1)).all()


def test_latest_intraday_session_uses_latest_populated_day():
    d1 = pd.date_range("2026-08-24 09:15", periods=10, freq="5min", tz="Asia/Kolkata")
    d2 = pd.date_range("2026-08-25 09:15", periods=12, freq="5min", tz="Asia/Kolkata")
    idx = d1.append(d2)
    df = pd.DataFrame({
        "Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.5, "Volume": 1000
    }, index=idx)
    latest = _latest_intraday_session(df, "IN")
    assert len(latest) == 12
    assert {x.date() for x in latest.index} == {d2[0].date()}
