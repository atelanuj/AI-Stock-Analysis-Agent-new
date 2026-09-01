import pandas as pd

from app.tools import data_provider
from app.tools.data_provider import _ticker_history_with_repair_fallback


class FakeTicker:
    def __init__(self):
        self.calls = []

    def history(self, repair, **kwargs):
        self.calls.append(repair)
        if repair:
            exc = ModuleNotFoundError("No module named 'scipy'")
            exc.name = "scipy"
            raise exc
        return {"ok": True}


def test_yfinance_repair_retries_without_repair_only_for_missing_scipy():
    ticker = FakeTicker()
    result = _ticker_history_with_repair_fallback(ticker, period="1y")
    assert result == {"ok": True}
    assert ticker.calls == [True, False]


class BrokenTicker:
    ticker = "KOTAKBANK.NS"

    def history(self, **kwargs):
        raise RuntimeError("Could not resolve host: guce.yahoo.com")


class ChartResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"chart": {"result": [{
            "timestamp": [1788210900, 1788297300],
            "indicators": {
                "quote": [{"open": [420, 424], "high": [426, 430], "low": [418, 422], "close": [424, 428], "volume": [100, 120]}],
                "adjclose": [{"adjclose": [424, 428]}],
            },
        }], "error": None}}


def test_guce_dns_failure_falls_back_to_public_chart_json(monkeypatch):
    monkeypatch.setattr(data_provider.requests, "get", lambda *args, **kwargs: ChartResponse())
    result = _ticker_history_with_repair_fallback(BrokenTicker(), period="1y", interval="1d", auto_adjust=False)
    assert isinstance(result, pd.DataFrame)
    assert list(result["Close"]) == [424, 428]
