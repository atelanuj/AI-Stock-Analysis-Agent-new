"""Cached Yahoo Finance access for V6.

The goal is to make one stock page reuse the same OHLC/info payload instead of
asking Yahoo repeatedly for market, technical, chart and benchmark data.
"""
from __future__ import annotations

import math
import time
from typing import Iterable

import pandas as pd
import yfinance as yf

from app.cache.redis_cache import get_json, set_json
from app.config import settings
from app.tools.market_data import yahoo_symbol




def _missing_scipy(exc: BaseException) -> bool:
    """Return True when yfinance repair mode failed only because SciPy is absent."""
    seen = set()
    cur = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, ModuleNotFoundError) and getattr(cur, "name", None) == "scipy":
            return True
        if "no module named 'scipy'" in str(cur).lower() or 'no module named "scipy"' in str(cur).lower():
            return True
        cur = getattr(cur, "__cause__", None) or getattr(cur, "__context__", None)
    return False


def _ticker_history_with_repair_fallback(ticker, **kwargs):
    """Prefer yfinance price repair, but never fail the page just because an optional repair dependency is missing."""
    try:
        return ticker.history(repair=True, **kwargs)
    except Exception as exc:
        if not _missing_scipy(exc):
            raise
        return ticker.history(repair=False, **kwargs)


def _download_with_repair_fallback(**kwargs):
    try:
        return yf.download(repair=True, **kwargs)
    except Exception as exc:
        if not _missing_scipy(exc):
            raise
        return yf.download(repair=False, **kwargs)


def _finite(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def sanitize_ohlcv_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize provider OHLCV and discard impossible/malformed bars."""
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    out = out[~out.index.duplicated(keep="last")].sort_index()
    for col in ("Open", "High", "Low", "Close", "Adj Close", "Volume"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
            out.loc[~out[col].map(lambda x: math.isfinite(float(x)) if pd.notna(x) else False), col] = float("nan")
    required = [c for c in ("Open", "High", "Low", "Close") if c in out.columns]
    if len(required) == 4:
        out = out.dropna(subset=required)
        positive = (out[["Open", "High", "Low", "Close"]] > 0).all(axis=1)
        high_ok = out["High"] >= out[["Open", "Low", "Close"]].max(axis=1)
        low_ok = out["Low"] <= out[["Open", "High", "Close"]].min(axis=1)
        out = out[positive & high_ok & low_ok]
    if "Volume" in out.columns:
        out["Volume"] = out["Volume"].fillna(0).clip(lower=0)
    return out


def _frame_payload(df: pd.DataFrame, interval: str = "1d") -> dict:
    if df is None or df.empty:
        return {"rows": []}
    rows = []
    for idx, row in df.iterrows():
        ts = pd.Timestamp(idx)
        item = {"date": ts.strftime("%Y-%m-%d") if interval == "1d" else ts.isoformat()}
        for col in ("Open", "High", "Low", "Close", "Adj Close", "Volume"):
            if col in df.columns:
                val = _finite(row.get(col))
                item[col] = val
        rows.append(item)
    return {"rows": rows}


def _payload_frame(payload: dict | None) -> pd.DataFrame:
    rows = (payload or {}).get("rows") or []
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if "date" not in df.columns:
        return pd.DataFrame()
    sample = str(df["date"].iloc[0]) if not df.empty else ""
    if len(sample) == 10 and sample.count("-") == 2:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    else:
        df["date"] = pd.to_datetime(df["date"], errors="coerce", utc=True)
    df = df.dropna(subset=["date"]).set_index("date")
    for col in ("Open", "High", "Low", "Close", "Adj Close", "Volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _retry(fn, attempts: int | None = None):
    attempts = attempts or settings.market_data_retries
    last_exc = None
    for attempt in range(max(1, attempts)):
        try:
            return fn()
        except Exception as exc:  # provider/network failures are retriable
            last_exc = exc
            if attempt + 1 < attempts:
                time.sleep(0.25 * (2 ** attempt))
    if last_exc:
        raise last_exc


def history_cache_key(yahoo_sym: str, period: str, interval: str, auto_adjust: bool) -> str:
    return f"yf:v6:hist:{yahoo_sym}:{period}:{interval}:{1 if auto_adjust else 0}"


def cache_history_frame(yahoo_sym: str, df: pd.DataFrame, period: str = "1y", interval: str = "1d", auto_adjust: bool = False, ttl: int | None = None):
    if df is None or df.empty:
        return
    if ttl is None:
        ttl = settings.intraday_cache_ttl_seconds if interval != "1d" else settings.market_history_cache_ttl_seconds
    set_json(history_cache_key(yahoo_sym, period, interval, auto_adjust), _frame_payload(df, interval), ttl=ttl)


def get_history_df(symbol: str, market: str | None = None, period: str = "1y", interval: str = "1d", auto_adjust: bool = False, force_refresh: bool = False) -> pd.DataFrame:
    yahoo_sym = yahoo_symbol(symbol, market)
    key = history_cache_key(yahoo_sym, period, interval, auto_adjust)
    if not force_refresh:
        cached = sanitize_ohlcv_frame(_payload_frame(get_json(key)))
        if not cached.empty:
            return cached

    def fetch():
        return _ticker_history_with_repair_fallback(
            yf.Ticker(yahoo_sym),
            period=period,
            interval=interval,
            auto_adjust=auto_adjust,
            timeout=settings.market_data_timeout_seconds,
        )

    hist = _retry(fetch)
    if hist is None:
        hist = pd.DataFrame()
    hist = sanitize_ohlcv_frame(hist)
    cache_history_frame(yahoo_sym, hist, period, interval, auto_adjust)
    return hist


def get_info(symbol: str, market: str | None = None, force_refresh: bool = False) -> dict:
    yahoo_sym = yahoo_symbol(symbol, market)
    key = f"yf:v6:info:{yahoo_sym}"
    if not force_refresh:
        cached = get_json(key)
        if isinstance(cached, dict) and cached:
            return cached

    def fetch():
        return yf.Ticker(yahoo_sym).info or {}

    info = _retry(fetch)
    if info:
        set_json(key, info, ttl=settings.fundamentals_cache_ttl_seconds)
    return info or {}


def get_benchmark_close(market: str, force_refresh: bool = False) -> pd.Series:
    yahoo_sym = "^GSPC" if (market or "IN").upper() == "US" else "^NSEI"
    # Use the provider directly because these already are Yahoo symbols.
    key = history_cache_key(yahoo_sym, "1y", "1d", True)
    if not force_refresh:
        cached = sanitize_ohlcv_frame(_payload_frame(get_json(key)))
        if not cached.empty and "Close" in cached:
            return cached["Close"].dropna()

    def fetch():
        return _ticker_history_with_repair_fallback(
            yf.Ticker(yahoo_sym),
            period="1y", interval="1d", auto_adjust=True,
            timeout=settings.market_data_timeout_seconds,
        )

    try:
        hist = _retry(fetch)
    except Exception:
        return pd.Series(dtype=float)
    hist = sanitize_ohlcv_frame(hist)
    if hist is None or hist.empty or "Close" not in hist:
        return pd.Series(dtype=float)
    cache_history_frame(yahoo_sym, hist, "1y", "1d", True, ttl=settings.benchmark_cache_ttl_seconds)
    return hist["Close"].dropna()


def batch_history(symbols: Iterable[str], market: str, period: str = "1y") -> dict[str, pd.DataFrame]:
    """Download daily history for many symbols in one yfinance request.

    Falls back gracefully: callers can still use get_history_df for any symbol
    missing from the returned mapping.
    """
    raw_symbols = [s.strip().upper() for s in symbols if s and s.strip()]
    yahoo_symbols = [yahoo_symbol(s, market) for s in raw_symbols]
    yahoo_symbols = list(dict.fromkeys(yahoo_symbols))
    if not yahoo_symbols:
        return {}

    result: dict[str, pd.DataFrame] = {}
    missing = []
    for ys in yahoo_symbols:
        cached = sanitize_ohlcv_frame(_payload_frame(get_json(history_cache_key(ys, period, "1d", False))))
        if not cached.empty:
            result[ys] = cached
        else:
            missing.append(ys)

    if not missing:
        return result

    try:
        downloaded = _download_with_repair_fallback(
            tickers=missing,
            period=period,
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=True,
            group_by="ticker",
            timeout=settings.market_data_timeout_seconds,
        )
    except Exception:
        return result

    if downloaded is None or downloaded.empty:
        return result

    if len(missing) == 1 and not isinstance(downloaded.columns, pd.MultiIndex):
        df = sanitize_ohlcv_frame(downloaded.dropna(how="all"))
        if not df.empty:
            result[missing[0]] = df
            cache_history_frame(missing[0], df, period, "1d", False)
        return result

    if isinstance(downloaded.columns, pd.MultiIndex):
        level0 = set(downloaded.columns.get_level_values(0))
        level1 = set(downloaded.columns.get_level_values(1))
        for ys in missing:
            try:
                if ys in level0:
                    df = sanitize_ohlcv_frame(downloaded[ys].dropna(how="all"))
                elif ys in level1:
                    df = sanitize_ohlcv_frame(downloaded.xs(ys, axis=1, level=1).dropna(how="all"))
                else:
                    continue
                if not df.empty:
                    result[ys] = df
                    cache_history_frame(ys, df, period, "1d", False)
            except Exception:
                continue
    return result
