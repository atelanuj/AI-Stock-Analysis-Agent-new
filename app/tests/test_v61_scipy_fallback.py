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
