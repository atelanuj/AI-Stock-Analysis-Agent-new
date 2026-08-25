# Stock AI Agent V5

V5 is a local India + US investment-research dashboard built with FastAPI, Docker Compose and NVIDIA Nemotron. It extends V4 with multi-timeframe technical context, dynamic price zones, advanced screeners, benchmark-aware fund analysis, portfolio FX normalization, watchlist alerts and transparent backtesting.

> **Important:** This is research/education software, not personalized investment advice. Technical signals, support/resistance levels and historical backtests can fail. Market-data and news quality depend on third-party providers.

## Highlights

### Stocks — India and US

- Fundamental, valuation, technical and risk scoring
- NVIDIA Nemotron research synthesis through NVIDIA's OpenAI-compatible API
- Candlestick and line charts
- Chart periods: 1W / 1M / 3M / 6M / 1Y
- RSI 14, MACD, SMA 20/50/200
- ATR 14, ADX 14, rolling VWAP and relative volume
- Market-regime classification: trending up/down, range-bound or mixed
- Volatility regime
- Relative strength versus NIFTY 50 (India) or S&P 500 (US)
- Dynamic support/resistance **zones per selected horizon**
- Nearest and major support/resistance zones
- Breakout/breakdown watch and volume confirmation
- Illustrative risk/reward and invalidation levels
- Multi-timeframe trend alignment/confluence
- Candlestick detection and stock-specific historical pattern statistics
- Strategy backtesting over historical data
- Clickable news with impact, sentiment and category labels
- Earnings/ex-dividend event warnings where the data provider supplies them
- Beginner-friendly metric colors and “Explain” help

### Stock screener

India universes:

- NIFTY 50
- NIFTY 100
- NIFTY 500
- Popular fallback list

US universes:

- S&P 500
- NASDAQ 100
- Dow 30
- Popular fallback list

The screener separates:

- **Scan count** — how many candidates are evaluated
- **Result count** — maximum matching rows displayed

Filters include:

- Minimum overall / technical score
- Trend direction
- Market cap
- Maximum P/E
- Minimum ROE
- Maximum debt/equity
- Minimum revenue growth
- RSI range
- Price above SMA200
- Confirmed volume breakout

Bulk screening deliberately skips the LLM so hundreds of candidates can be ranked with deterministic calculations without generating hundreds of model calls.

### Mutual funds / ETFs — India and US

Fund scoring is intentionally different from stock scoring. It includes:

- 1M / 3M / 6M / 1Y returns
- 3Y / 5Y annualized return where enough history is available
- Annualized volatility
- Downside volatility
- Maximum drawdown
- Sharpe ratio
- Sortino ratio
- Positive-day ratio
- Positive rolling-1Y consistency
- Positive calendar-year consistency
- Expense ratio / AUM where the provider supplies them
- Benchmark comparison
- Alpha versus benchmark
- Tracking error
- Correlation and beta
- Return / consistency / risk / cost / benchmark / drawdown score components

Generic benchmark defaults:

- India: NIFTY 50
- US: S&P 500

### Portfolio

- Stocks + funds in one portfolio
- India + US holdings
- Base currency: INR or USD
- Live best-effort USD/INR conversion through the market-data provider
- Base-currency market value, cost and P&L
- Position weights
- Concentration warnings
- Weighted quality score

### Watchlist / alerts

V5 includes a local watchlist workflow with checks for:

- RSI high/low thresholds
- Breakout/breakdown conditions
- Upcoming company events when available

The current implementation checks alerts when requested from the UI/API. It is not a background push-notification service.

## Technical outlook semantics

A card such as:

```text
1M
BULLISH
Signal agreement: 78 / 100
Past return: +4.2%
```

means the application's technical evidence is mostly aligned bullish over that horizon. **78/100 is not a 78% probability that the price will rise.**

Each horizon uses a different lookback and therefore gets different price zones:

| Horizon | Approx. sessions | Typical use |
| --- | ---: | --- |
| 1W | 5 | Very short term |
| 1M | 20 | Short-term swing |
| 3M | 60 | Medium term |
| 6M | 120 | Intermediate trend |
| 1Y | ~250 | Long-term trend |

Support/resistance is represented as a **zone**, based on clustered price reactions with an ATR-aware tolerance, rather than simply one exact minimum/maximum price.

## Historical backtesting

V5 includes a transparent long-only example strategy based on:

- Close > SMA200
- SMA50 > SMA200
- RSI in a constructive range
- MACD > signal line
- Volume participation threshold

The API reports 5D / 10D / 20D forward outcomes, win rates and adverse excursion statistics from historical signals. These are **in-sample descriptive results**, not proof of future performance.

Candlestick pattern statistics similarly show historical occurrences, directional hit rates and forward returns, including regime-conditioned samples when available.

## Run locally

### 1. Configure

```bash
cp .env.example .env
```

Set your NVIDIA API key:

```env
NVIDIA_API_KEY=your_nvidia_api_key
```

The default model is:

```env
NVIDIA_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b
```

### 2. Start

```bash
docker compose up --build
```

Open:

```text
http://localhost:8000
```

Swagger:

```text
http://localhost:8000/docs
```

## Useful API examples

### Analyze an Indian stock

```bash
curl "http://localhost:8000/analyze/RELIANCE?market=IN"
```

### Analyze a US stock

```bash
curl "http://localhost:8000/analyze/AAPL?market=US"
```

### Technical analysis

```bash
curl "http://localhost:8000/technical/AAPL?market=US"
```

### Candles + dynamic zones

```bash
curl "http://localhost:8000/api/candles/AAPL?market=US&period=6mo"
```

### Strategy backtest

```bash
curl "http://localhost:8000/backtest/AAPL?market=US&period=5y"
```

### Stock screening

```bash
curl -X POST http://localhost:8000/screen/stocks \
  -H "Content-Type: application/json" \
  -d '{
    "market": "US",
    "universe": "SP500",
    "scan_count": 50,
    "result_count": 50,
    "min_overall_score": 60,
    "max_pe": 35,
    "min_roe_pct": 12,
    "require_above_sma200": true
  }'
```

If 50 valid candidates are available and all 50 pass the filters, V5 can return 50 rows. `evaluated`, `matched` and `returned` are shown separately so there is no hidden top-10 limit.

### Fund screening

```bash
curl -X POST http://localhost:8000/screen/funds \
  -H "Content-Type: application/json" \
  -d '{
    "market": "US",
    "query": "S&P 500",
    "scan_count": 50,
    "result_count": 25,
    "min_score": 55,
    "max_expense_ratio_pct": 0.75
  }'
```

### Mixed portfolio

```bash
curl -X POST http://localhost:8000/portfolio/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "base_currency": "INR",
    "holdings": [
      {"symbol":"TCS","quantity":10,"average_price":3500,"market":"IN","asset_type":"STOCK"},
      {"symbol":"AAPL","quantity":3,"average_price":190,"market":"US","asset_type":"STOCK"}
    ]
  }'
```

## Data sources and limitations

The prototype uses free/public sources such as Yahoo Finance/yfinance, MFAPI and public index constituent pages. These sources can be delayed, incomplete, rate-limited or structurally changed. For production use, replace them with licensed market-data, mutual-fund, corporate-action, macro-calendar and news feeds.

Company event warnings are best-effort. V5 does **not fabricate RBI/Fed dates** when a reliable macro-calendar source is not configured.

The rolling VWAP shown from daily bars is a daily-data approximation. True intraday VWAP requires intraday trade/volume data.

## V5.1 backtest hotfix

The V5.1 package adds a defensive fix for market-data rows containing `NaN`/`Infinity`. Backtest calculations now drop unusable close-price rows, normalize missing volume, ignore non-finite forward-return samples, and recursively sanitize the API payload before FastAPI serializes it. The dashboard also displays the backend's real error detail instead of only showing `Backtest unavailable`.
