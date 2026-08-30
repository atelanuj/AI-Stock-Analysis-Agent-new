# V8 Feature Summary

V8 keeps V7 as the compatibility base and adds a readability-first research-terminal UI plus the following capabilities.

## New workspaces

- **Market**: market regime, breadth and index/sector proxy momentum.
- **Intraday**: 1m/5m/15m/30m/60m stock analysis with VWAP, EMA9/21, RSI, MACD and opening-range structure.
- **IPO Research**: India + US pre-listing issue desk with official/public source links and conservative SUBSCRIBE/WATCH/AVOID research classification.
- **V8 Assistant**: contextual chat for Stocks, Funds, Intraday, IPO and general feature explanations.

## Stock research upgrades

- peer comparison
- sector vs market relative strength
- 5-year financial trend table when provider statements are available
- transparent Bear/Base/Bull valuation scenarios
- best-effort ownership snapshot
- AI recommendation performance history
- expanding-window walk-forward validation
- custom rule-based Strategy Builder
- downloadable JSON research snapshot

## Risk and portfolio upgrades

- annualized portfolio volatility
- historical 95% daily VaR
- maximum drawdown
- sector concentration
- pairwise correlation warnings
- local-only paper-trade journal

## Fund upgrades retained from V7

- detailed multi-horizon return dashboard
- fund/benchmark comparison
- risk/consistency metrics
- score breakdown
- US holdings overlap where available
- no invented Indian holdings overlap when MFAPI lacks holdings data

## Screener UX

Stock and fund result rows remain directly clickable into the corresponding full research workspace.

## IPO guardrails

The IPO system deliberately avoids a guaranteed BUY call. It uses:

- `SUBSCRIBE`
- `WATCH`
- `AVOID`

Evidence completeness constrains the recommendation. If issue/valuation evidence is thin, a SUBSCRIBE result is blocked/downgraded. No GMP is treated as verified evidence.

## UI redesign

- solid, higher-contrast research cards instead of heavy glass/glow
- sticky compact navigation
- responsive mobile/tablet behavior
- workspace-specific title/subtitle
- clearer information grouping
- dedicated Data Quality surfaces
- contextual floating assistant
- dark/light native dropdown readability preserved

## Existing behavior retained

- V6 quote validation and OHLC sanitation
- V6.1 SciPy/yfinance repair fallback
- V7 technical BUY/HOLD/SELL decision
- 1D/1W/1M/3M/6M/1Y multi-timeframe technical outlook
- dynamic support/resistance zones
- line/candlestick charts
- Stocks/Funds/Screener/Portfolio/Watchlist APIs and UI workflows
- Redis/PostgreSQL/Docker Compose/NVIDIA Nemotron stack
