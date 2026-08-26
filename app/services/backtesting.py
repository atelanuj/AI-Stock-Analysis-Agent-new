import math
import numpy as np
import pandas as pd
from app.tools.data_provider import get_history_df
from app.tools.technical import backtest_candlestick_patterns


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _finite(value, digits: int | None = None):
    """Return a JSON-safe finite Python number, otherwise None."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number):
        return None
    if digits is not None:
        return round(number, digits)
    return number


def _json_safe(value):
    """Recursively remove NaN/Infinity and numpy scalar types from a response."""
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return _finite(value)
    return value


def backtest_stock_strategy(symbol: str, market: str = "IN", period: str = "5y") -> dict:
    hist = get_history_df(symbol, market, period=period, interval="1d", auto_adjust=True)

    if hist.empty or "Close" not in hist.columns:
        raise ValueError(f"No usable price history returned for {symbol}")

    # Some providers occasionally return rows with NaN/Inf prices. Those values can
    # propagate into NumPy statistics and FastAPI then rejects the response because
    # NaN/Infinity are not valid JSON. Clean the series before doing any calculations.
    hist = hist.copy()
    hist["Close"] = pd.to_numeric(hist["Close"], errors="coerce")
    hist["Close"] = hist["Close"].replace([np.inf, -np.inf], np.nan)
    hist = hist.dropna(subset=["Close"])

    if len(hist) < 220:
        raise ValueError(
            f"Insufficient clean history to backtest {symbol}: "
            f"{len(hist)} usable sessions found; at least 220 are required"
        )

    close = hist["Close"].astype(float)
    if "Volume" in hist.columns:
        volume = pd.to_numeric(hist["Volume"], errors="coerce")
        volume = volume.replace([np.inf, -np.inf], np.nan).fillna(0.0).astype(float)
    else:
        volume = pd.Series(0.0, index=hist.index, dtype=float)

    sma200 = close.rolling(200, min_periods=200).mean()
    sma50 = close.rolling(50, min_periods=50).mean()
    rsi = _rsi(close)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    avgvol = volume.rolling(20, min_periods=20).mean()

    # Transparent long-only rules used by the dashboard.
    raw_signal = (
        (close > sma200)
        & (sma50 > sma200)
        & (rsi >= 45)
        & (rsi <= 68)
        & (macd > signal)
        & (volume >= avgvol * 0.8)
    )

    signal_positions: list[int] = []
    last = -999
    for i in np.where(raw_signal.fillna(False).to_numpy())[0]:
        if i - last >= 5:
            signal_positions.append(int(i))
            last = int(i)

    horizon_stats: dict[str, dict] = {}
    for horizon in (1, 5, 10, 20):
        returns: list[float] = []
        adverse: list[float] = []

        for i in signal_positions:
            if i + horizon >= len(close):
                continue

            entry = _finite(close.iloc[i])
            exit_ = _finite(close.iloc[i + horizon])
            if entry is None or exit_ is None or entry <= 0:
                continue

            forward = (exit_ / entry - 1) * 100
            if not math.isfinite(forward):
                continue

            path = (close.iloc[i : i + horizon + 1].astype(float) / entry - 1) * 100
            path = path.replace([np.inf, -np.inf], np.nan).dropna()
            if path.empty:
                continue

            mae = _finite(path.min())
            if mae is None:
                continue

            returns.append(float(forward))
            adverse.append(float(mae))

        if returns:
            wins = sum(r > 0 for r in returns)
            horizon_stats[f"{horizon}D"] = {
                "signals": len(returns),
                "win_rate_pct": _finite(wins / len(returns) * 100, 1),
                "average_return_pct": _finite(np.mean(returns), 2),
                "median_return_pct": _finite(np.median(returns), 2),
                "average_max_adverse_excursion_pct": _finite(np.mean(adverse), 2),
                "worst_max_adverse_excursion_pct": _finite(np.min(adverse), 2),
            }
        else:
            horizon_stats[f"{horizon}D"] = {"signals": 0}

    first_close = _finite(close.iloc[0])
    last_close = _finite(close.iloc[-1])
    buy_hold = None
    if first_close is not None and last_close is not None and first_close > 0:
        buy_hold = _finite((last_close / first_close - 1) * 100, 2)

    pattern_stats = {}
    if all(col in hist.columns for col in ("Open", "High", "Low", "Close")):
        try:
            pattern_stats = backtest_candlestick_patterns(hist, horizon=5)
        except Exception:
            pattern_stats = {}

    result = {
        "symbol": symbol.upper(),
        "market": market.upper(),
        "period": period,
        "usable_sessions": int(len(close)),
        "strategy": {
            "name": "V6 technical confluence long signal",
            "rules": [
                "Close > SMA200",
                "SMA50 > SMA200",
                "RSI 45–68",
                "MACD > signal",
                "Volume >= 0.8× 20D average",
                "5-session signal cooldown",
            ],
        },
        "signal_count": int(len(signal_positions)),
        "horizons": horizon_stats,
        "candlestick_pattern_stats": pattern_stats,
        "buy_and_hold_return_pct": buy_hold,
        "note": (
            "Historical in-sample research only. No fees, tax, slippage or "
            "survivorship-bias adjustment; not a forecast."
        ),
    }

    # Final defensive pass: JSON responses must never contain NaN or Infinity.
    return _json_safe(result)
