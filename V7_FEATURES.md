# V7 Feature Changes

## Added

- Deep Mutual Fund / ETF detail dashboard for India and US
- Fund multi-horizon clickable return cards
- Fund-vs-benchmark indexed growth chart
- Fund profile: risk band, cost status, consistency status, benchmark status and current drawdown
- Rolling 1Y median/best/worst analysis
- Expanded fund risk, consistency and benchmark metrics
- Clickable/keyboard-accessible Stock screener results
- Clickable/keyboard-accessible Fund screener results
- Full 1D clickable technical horizon alongside 1W/1M/3M/6M/1Y
- Nemotron technical BUY/HOLD/SELL synthesis per selected horizon
- Deterministic technical target zone
- Stop/risk-control reference and invalidation level
- Risk/reward display
- AI-vs-deterministic consensus handling: disagreements become HOLD

## Retained

- V6.1 SciPy/yfinance repair fallback
- MFAPI timezone alignment fix
- NSE/Yahoo India quote validation
- Yahoo/Stooq US quote sanity checking
- sanitized OHLC candles
- 1D 5-minute chart session filtering
- dynamic support/resistance zones
- technical indicators and candlestick detection
- backtesting on demand
- progressive stock loading
- bulk screeners
- portfolio and watchlist

## Safety / interpretation

The target zone and stop/risk-control reference are model-derived technical estimates, not guaranteed or confirmed future prices. Nemotron is not allowed to invent numeric price levels. A directional BUY/SELL requires agreement with the deterministic technical scaffold; conflicting evidence results in HOLD.
