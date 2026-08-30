# Stock AI Agent V8.2

V8.2 is a non-breaking UX/feature upgrade on top of V8.1 and V7. It keeps the V7 Stocks, Funds, Screener, Portfolio, Watchlist, 1D–1Y technical outlook, V6/V6.1 data-integrity fixes, progressive loading and NVIDIA Nemotron integration, while redesigning the UI into a research-terminal layout and adding Market, Intraday, IPO and research-validation workflows.

## V8 workspaces

### Stocks

- India + US equities
- validated/current quote separated from historical OHLC
- 1D / 1W / 1M / 3M / 6M / 1Y technical horizons
- line/candlestick chart
- RSI, MACD, SMA, VWAP, ATR, ADX, relative volume
- dynamic support/resistance zones
- breakout/breakdown status
- relative strength vs NIFTY 50 / S&P 500
- candlestick-pattern history
- BUY / HOLD / SELL technical research decision
- deterministic target zone, risk-control and invalidation references
- Nemotron stock synthesis
- peer comparison
- stock/sector/market relative performance
- multi-year revenue / earnings / FCF / debt trend table
- transparent Bear / Base / Bull valuation scenarios
- best-effort ownership snapshot with source caveats
- recommendation track record
- ordinary in-sample backtest
- expanding-window walk-forward validation
- custom transparent Strategy Builder
- JSON research-snapshot export

### Market

A dedicated market-context workspace shows:

- India / US market regime
- breadth above SMA20 / SMA50 / SMA200
- NIFTY/S&P and configured sector/index proxies
- 1M and 3M momentum context

This is intentionally contextual. It does not claim that market breadth alone predicts the next move.

### Intraday

Dedicated stock intraday workspace:

- 1m / 5m / 15m / 30m / 60m bars
- exchange-session filtering
- VWAP
- EMA9 / EMA21
- RSI
- MACD
- opening-range high/low
- session high/low
- deterministic BUY / HOLD / SELL research classification
- technical target and risk-control reference
- optional asynchronous Nemotron interpretation

Intraday output is time-sensitive and is not an order or guaranteed price forecast.

### Funds / ETFs

V7's richer fund experience is retained:

- Indian mutual funds via MFAPI
- US mutual funds / ETFs via Yahoo Finance
- 1D, 1M, 3M, 6M, 1Y, 3Y and 5Y performance
- NAV/price history
- benchmark-normalized growth chart
- Sharpe / Sortino
- volatility / downside volatility
- maximum/current drawdown
- rolling-return consistency
- alpha, beta, correlation and tracking error
- expense ratio / AUM when available
- fund score breakdown
- US top-holdings overlap when the provider exposes holdings
- explicit limitation for Indian fund overlap when holdings data is unavailable

### Screener

- India / US stock and fund screeners
- scan-count and result-count controls remain separate
- stock fundamental + technical filters
- fund return / risk / drawdown / expense filters
- rows are clickable
- clicking a stock opens the full Stocks analysis
- clicking a fund opens the full Funds analysis
- AI is intentionally skipped during bulk screening

### IPO Research

Pre-listing research for India and the US.

India sources:

- NSE current/upcoming issue web feeds when reachable
- SEBI Public Issues filings
- if the undocumented NSE web API is blocked, recent SEBI filings remain visible as low-completeness research candidates

US source:

- Nasdaq IPO calendar data

The IPO desk produces a conservative **SUBSCRIBE / WATCH / AVOID** research classification rather than a guaranteed “buy before listing” call. Thin evidence caps aggressiveness. The project intentionally does **not** use grey-market premium/GMP as verified evidence.

For each selected issue, V8 shows available issue dates, price-band/demand evidence, source links, evidence completeness, positives, risks, due diligence and the Nemotron pre-listing view.

### Portfolio

- India + US stocks/funds
- INR / USD base currency
- P&L and weights
- historical volatility
- historical daily VaR 95%
- max drawdown
- sector concentration
- highest pair correlations
- local-only Paper Trade Journal for simulated ideas; it never sends orders

### Watchlist

V7 watchlist behavior is retained and extended through the existing backend checks:

- RSI thresholds
- price-above / price-below triggers
- unusual relative volume
- breakout / breakdown state
- near-term company-event awareness

### V8 Assistant

A contextual help chatbot is available from every workspace. It can explain indicators, app features and the currently selected Stock, Fund, Intraday setup or IPO when that context is available.

It is an educational/research assistant, not a personalized financial adviser.

## Recommendation validation

V8 records technical research calls in PostgreSQL when the technical-decision endpoint is used. The dashboard can later audit those calls against subsequent price history and distinguish:

- target reached
- risk level breached
- still tracking
- current mark-to-market directional outcome

The walk-forward lab separately holds out future historical blocks after configuration selection on prior data. This reduces, but does not eliminate, overfitting risk.

## Data sources and integrity

This remains a research prototype using public/free sources.

### Stocks

- Yahoo Finance/yfinance: historical OHLCV, financial statements, fundamentals, news and events
- India quote validation: NSE India + Yahoo when reachable
- US quote validation: Yahoo + Stooq comparison when reachable
- NIFTY 50 / S&P 500 and sector/index proxies for relative context

### Indian mutual funds

- MFAPI for schemes and NAV history
- benchmark history from Yahoo Finance
- V6 timezone-normalization fix remains enabled

### IPOs

- India: NSE public web feeds + SEBI Public Issues filings
- US: Nasdaq IPO calendar

Public/free providers may be delayed, blocked, rate-limited, incomplete or structurally changed. For production trading, replace them with licensed exchange-grade market, fund, corporate-action, filing, IPO-calendar and news feeds.

## AI model

The project uses NVIDIA's OpenAI-compatible endpoint with:

```text
nvidia/nemotron-3.5-lightning-30b-a3b
```

Numerical technical target/risk levels are calculated deterministically by Python. The LLM is used for synthesis and explanation and is instructed not to invent missing financial values or guaranteed outcomes.

## Run locally

```bash
cp .env.example .env
# set NVIDIA_API_KEY in .env

docker compose down
docker compose build --no-cache api
docker compose up
```

Open:

- Dashboard: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

Expected health version:

```json
{"status":"ok","version":"8.2.0"}
```

## Useful API calls

```bash
# Stock core
curl "http://localhost:8000/analyze/core/TCS?market=IN"

# Technical AI decision
curl "http://localhost:8000/technical/decision/TCS?market=IN&horizon=1D"

# Intraday
curl "http://localhost:8000/intraday/TCS?market=IN&interval=5m"

# Market breadth
curl "http://localhost:8000/market/overview?market=IN"

# Research intelligence
curl "http://localhost:8000/research/TCS?market=IN"

# Walk-forward validation
curl "http://localhost:8000/backtest/walk-forward/TCS?market=IN&period=10y"

# IPO list
curl "http://localhost:8000/ipo/list?market=IN"

# Indian mutual fund
curl "http://localhost:8000/mf/analyze/120503?market=IN"
```

## Important limitations

- No analysis can provide a confirmed future target, guaranteed stop level, listing gain or profit.
- Intraday signals can become obsolete quickly.
- DCF scenarios are simplified and assumptions are exposed in the UI.
- Ownership data is best-effort; Indian promoter/FII/DII patterns should be verified against official exchange/company filings.
- Macro RBI/Fed dates are not fabricated when no reliable macro-calendar feed is configured.
- Indian mutual-fund portfolio overlap is not calculated from MFAPI because MFAPI does not provide holdings.
- The local Docker build intentionally has no login/authentication layer. Add proper authentication, TLS and secrets controls before exposing it to other users or the public internet.
