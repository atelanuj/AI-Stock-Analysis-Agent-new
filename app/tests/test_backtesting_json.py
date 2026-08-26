import json
import sys
import types

import numpy as np
import pandas as pd

sys.modules.setdefault("yfinance", types.SimpleNamespace())

from app.services import backtesting


def fake_history(*_args, **_kwargs):
    idx = pd.date_range("2025-01-01", periods=270, freq="B")
    close = pd.Series(np.linspace(100.0, 150.0, len(idx)), index=idx)
    volume = pd.Series(1_000_000.0, index=idx)
    close.iloc[0] = np.nan
    close.iloc[120] = np.nan
    close.iloc[-1] = np.nan
    volume.iloc[80] = np.nan
    return pd.DataFrame({"Close": close, "Volume": volume}, index=idx)


def test_backtest_response_is_strict_json_even_with_nan_history(monkeypatch):
    monkeypatch.setattr(backtesting, "get_history_df", fake_history)
    result = backtesting.backtest_stock_strategy("JSWSTEEL", "IN", "5y")

    # This is the same strict behavior Starlette/FastAPI uses for JSON responses.
    encoded = json.dumps(result, allow_nan=False)
    assert encoded
    assert result["usable_sessions"] == 267
    assert result["buy_and_hold_return_pct"] is not None
    assert "1D" in result["horizons"]
