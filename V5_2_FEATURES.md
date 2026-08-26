# V5.2 Changes from V5.1

## Performance architecture

- Progressive stock rendering: technical first, fundamentals second, context third, AI last
- AI no longer blocks the initial Stocks page
- Historical backtest no longer runs automatically
- One cached daily OHLC payload reused by market + technical calculations
- Daily chart ranges reuse the cached 1Y history
- Separate Redis TTLs for history, intraday, fundamentals, news, events, benchmarks and AI
- NIFTY 50 / S&P 500 history cached as shared benchmarks
- Yahoo retry + timeout configuration
- Screener batch-downloads OHLC history and concurrently resolves cached fundamentals
- Stale async UI responses are ignored when the user quickly analyzes another stock

## New 1D coverage

- 1D technical horizon
- 1D past return
- 1D support/resistance context
- 1D risk/reward + breakout context
- 1D relative strength vs benchmark
- 1D chart selector with 5-minute intraday bars
- 1D screener trend-horizon filter
- 1D forward backtest outcome
- 1D mutual-fund/ETF return where data permits
- Watchlist primary bias now exposes 1D context while retaining 1M fields in API output

## UI

- Progressive loading-status chips for technical, fundamentals, chart, news/events, AI and backtest
- Dynamic important levels and risk/reward update with the selected horizon
- Benchmark-delta label follows the selected horizon
- Existing line/candlestick toggle retained

## Compatibility

- `/analyze/{symbol}` still returns the combined response
- New progressive endpoints are additive
- V5.1 NaN-safe backtest handling is retained
- Existing India/US stock/fund, portfolio, news, screener and watchlist features remain
