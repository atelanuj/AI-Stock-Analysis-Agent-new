# V6 changes from V5.2

## Fixed: Indian mutual funds

V5.2 joined MFAPI's timezone-naive NAV index with a timezone-aware Yahoo benchmark index. Pandas correctly rejected that operation.

V6 now:

- parses MFAPI dates explicitly
- normalizes fund and benchmark timestamps to daily calendar dates
- removes timezone information before joining
- deduplicates normalized dates
- exposes the number of aligned benchmark sessions

This fixes `Cannot join tz-naive with tz-aware DatetimeIndex`.

## Fixed: stock header price accuracy

V5.2 displayed the most recent daily OHLC Close as `current_price`. That can be stale during a market session.

V6 separates **quote** from **historical OHLC**:

- India: NSE quote preferred, Yahoo quote comparison/fallback
- US: Yahoo current quote primary, Stooq EOD comparison
- latest daily close remains an explicit fallback only

The API returns `evidence.market.data_quality` with provider values, timestamps and discrepancy status.

## Fixed: malformed/sparse 1D candles

V6 performs strict OHLC sanitation and uses a multi-day intraday request to locate the latest populated local exchange session. The UI reports the exact number of bars rendered.

## UI changes

- removed the large V5.2 internal loading-stage strip
- added a compact Data Quality strip
- shows source-validation state beside the quote
- shows source values and maximum discrepancy
- shows quote timestamp
- shows candle interval, bar count, source and date range
- keeps line/candle toggle and all 1D/1W/1M/3M/6M/1Y controls
- Indian MF results show NAV and benchmark source information

## Cache separation

V6 uses new cache namespaces so V5.2 stale values are not silently reused.

Interactive validated analysis and bulk screener analysis also use separate core cache keys. The screener intentionally avoids per-stock live cross-validation so large scans remain practical; its price should be interpreted as latest daily OHLC unless the stock is opened in the Stocks page.

## Validation / tests added

- timezone-aware benchmark + timezone-naive MFAPI alignment
- invalid OHLC rejection
- latest intraday session extraction
- official NSE quote preference when cross-validation succeeds
