import pandas as pd

from app.services import mf_analysis


class _FakeTicker:
    def __init__(self, symbol):
        self.symbol = symbol

    def history(self, *args, **kwargs):
        idx = pd.date_range("2024-01-01", periods=80, freq="B", tz="Asia/Kolkata")
        return pd.DataFrame({"Close": [100 + i * 0.2 for i in range(len(idx))]}, index=idx)


def test_indian_mf_benchmark_alignment_handles_tz_aware_index(monkeypatch):
    monkeypatch.setattr(mf_analysis.yf, "Ticker", _FakeTicker)
    history = [
        {"date": d.strftime("%d-%m-%Y"), "nav": 10 + i * 0.03}
        for i, d in enumerate(pd.date_range("2024-01-01", periods=80, freq="B"))
    ]
    result = mf_analysis._benchmark_metrics(history, "IN")
    assert result["name"] == "NIFTY 50"
    assert result.get("aligned_sessions", 0) >= 30
    assert result.get("data_alignment") == "calendar-date normalized"
    assert result.get("comparison_history")
    assert {"date", "fund_index", "benchmark_index"}.issubset(result["comparison_history"][0])
