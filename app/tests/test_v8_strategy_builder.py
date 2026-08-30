import numpy as np
import pandas as pd

from app.models.api import StrategyBacktestRequest
from app.services import strategy_builder


def _history(n=650):
    idx = pd.bdate_range("2023-01-02", periods=n, tz="UTC")
    x = np.arange(n)
    close = 100 + x * 0.08 + np.sin(x / 7) * 4
    open_ = close * (1 + np.sin(x / 13) * 0.001)
    high = np.maximum(open_, close) + 1.2
    low = np.minimum(open_, close) - 1.2
    volume = 1_000_000 + (np.sin(x / 5) + 1) * 250_000
    return pd.DataFrame({"Open":open_,"High":high,"Low":low,"Close":close,"Volume":volume}, index=idx)


def test_custom_strategy_backtest_returns_json_safe_stats(monkeypatch):
    monkeypatch.setattr(strategy_builder, "get_history_df", lambda *a, **k: _history())
    req = StrategyBacktestRequest(symbol="TEST", market="US", period="2y", forward_days=10)
    result = strategy_builder.backtest_custom_strategy(req)
    assert result["symbol"] == "TEST"
    assert result["signals"] >= 0
    assert result["direction"] == "LONG"
    assert result["win_rate_pct"] is None or 0 <= result["win_rate_pct"] <= 100


def test_strategy_short_direction_is_supported(monkeypatch):
    monkeypatch.setattr(strategy_builder, "get_history_df", lambda *a, **k: _history())
    req = StrategyBacktestRequest(symbol="TEST", market="US", direction="SHORT", require_above_sma200=False)
    result = strategy_builder.backtest_custom_strategy(req)
    assert result["direction"] == "SHORT"
