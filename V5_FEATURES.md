# V5 Feature Changes

## Technical analysis

- Dynamic support/resistance zones for 1W, 1M, 3M, 6M and 1Y
- Nearest + major support and resistance
- ATR-aware zone clustering and touch strength
- Volume participation / relative volume
- Rolling VWAP approximation
- ATR14 volatility
- ADX14 trend strength
- Market regime and volatility regime
- Benchmark-relative strength by horizon
- Multi-timeframe trend alignment/confluence
- Breakout/breakdown watch with volume confirmation
- Illustrative target/invalidation/risk-reward context
- Signal confidence renamed/represented as technical signal agreement
- Candlestick pattern backtests with regime-conditioned reliability
- 5Y strategy backtesting endpoint and dashboard

## Beginner UX

- Favorable / caution / risk metric colors
- Explain-this modal for key technical concepts
- Clear distinction between historical return and future directional bias
- Dynamic levels update when the selected horizon changes
- Line/candlestick chart toggle and 1W/1M/3M/6M/1Y chart ranges

## Stock screener

- Separate scan count and displayed-result count
- Up to hundreds of candidates per request
- India: NIFTY 50 / 100 / 500
- US: S&P 500 / NASDAQ 100 / Dow 30
- Fundamental, valuation and technical filters
- RSI, SMA200, volume-breakout and trend filters
- Bulk LLM calls remain disabled for speed and cost control

## Funds / ETFs

- Fund-specific score model rather than stock score reuse
- Sharpe + Sortino
- Rolling-return consistency
- Drawdown and downside volatility
- Benchmark alpha
- Tracking error, correlation and beta
- Expense/AUM filters when source data is available
- India + US fund screening

## News and events

- Clickable full-news links retained
- Importance: HIGH / MEDIUM / LOW
- Sentiment labels
- News categories such as earnings, M&A, regulatory, analyst and capital action
- Upcoming earnings / ex-dividend warnings where provider data exists
- No fabricated macro calendar dates

## Portfolio and monitoring

- INR/USD base-currency normalization for mixed portfolios
- USD/INR conversion used in totals and weights
- Concentration warnings
- Local watchlist
- RSI, breakout/breakdown and event checks

## Safety / interpretation

- Directional bias is probabilistic technical evidence, not a guaranteed forecast
- Signal agreement is not a probability of profit
- Risk/reward levels are illustrative technical references, not personalized trade instructions
- Backtests and pattern hit rates are in-sample historical evidence
