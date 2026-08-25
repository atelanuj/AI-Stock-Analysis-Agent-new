# Stock AI Agent V4

A local Docker Compose research application for **Indian + US stocks and funds** using FastAPI, Redis, PostgreSQL, Yahoo/yfinance + MFAPI prototyping data sources, and NVIDIA Nemotron synthesis.

V4 builds on V3 with a more beginner-friendly UI, clickable news, line/candlestick chart switching, 1W–1Y chart ranges, and multi-horizon stock trend biases.

## V4 highlights

### Stocks — India + US

- Fundamental, valuation, risk and technical scoring
- NVIDIA `nvidia/nemotron-3.5-lightning-30b-a3b` synthesis through NVIDIA's OpenAI-compatible endpoint
- RSI 14, MACD/signal, SMA 20/50/200 and 20-day support/resistance
- Rule-based candlestick detection and historical pattern context
- Interactive **Candlestick / Line** chart toggle
- Chart windows: **1W, 1M, 3M, 6M, 1Y**
- Multi-horizon technical bias: **1W, 1M, 3M, 6M, 1Y**
- Bias values: `BULLISH`, `NEUTRAL`, `BEARISH`
- Signal-confidence score describes indicator agreement, not probability of profit

### Clickable news

Recent stock news cards are clickable when the data provider supplies a valid URL. Clicking a card opens the **full article on the publisher/Yahoo destination** in a new tab. V4 does not scrape or republish full copyrighted articles inside the app.

### Beginner-friendly key metrics

P/E, Market Cap, ROE and RSI are visually classified:

- **Green** — generally favorable under the generic heuristic
- **Yellow** — caution / needs context
- **Red** — higher-risk or unfavorable reading
- **Gray** — unavailable / unclassified

Hover a metric tile to see the interpretation. Market cap is intentionally described as a **size/liquidity risk proxy**, not proof that a company is a better investment.

### Stock screener — India + US

- Custom symbols or built-in popular-market universe
- Overall/fundamental/technical/valuation/risk scores
- Trend filter and latest candlestick pattern
- AI calls skipped during bulk screening to reduce latency/cost

### Mutual funds / ETFs — India + US

- Indian MF search/NAV history through MFAPI
- US mutual-fund / ETF lookup via Yahoo/yfinance
- 1M, 3M, 6M, 1Y, 3Y and 5Y returns
- Volatility, downside volatility, max drawdown, positive-day ratio
- Expense ratio where available
- Fund screener and portfolio support

## Architecture

```text
Browser UI
   |
FastAPI
   |-- Stock analysis
   |    |-- Market/fundamental/news data
   |    |-- Technical indicators
   |    |-- Candlestick detector + pattern backtest
   |    |-- 1W / 1M / 3M / 6M / 1Y bias engine
   |    |-- Deterministic scoring
   |    `-- NVIDIA Nemotron synthesis
   |
   |-- Stock screener (IN / US)
   |-- Fund analysis + screener (IN / US)
   `-- Mixed stock/fund portfolio analysis

Redis      -> analysis cache
PostgreSQL -> AI stock-analysis history
```

## Run locally

```bash
cp .env.example .env
```

Set your NVIDIA key:

```env
NVIDIA_API_KEY=nvapi-your-key
```

Then:

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

## API examples

Analyze Indian stock:

```bash
curl "http://localhost:8000/analyze/RELIANCE?market=IN"
```

Analyze US stock:

```bash
curl "http://localhost:8000/analyze/AAPL?market=US"
```

Get a 1-week chart payload:

```bash
curl "http://localhost:8000/api/candles/AAPL?market=US&period=5d"
```

Get a 1-year chart payload:

```bash
curl "http://localhost:8000/api/candles/RELIANCE?market=IN&period=1y"
```

`/api/candles/{symbol}` now also returns `timeline_biases` for 1W, 1M, 3M, 6M and 1Y.

## Model configuration

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=NVIDIA_API_KEY,
)
```

Configured model:

```text
nvidia/nemotron-3.5-lightning-30b-a3b
```

Private model reasoning is not returned to the browser or persisted.

## Data and prediction limitations

This is a research prototype, not an exchange-grade trading platform. Yahoo/yfinance and MFAPI can be delayed, incomplete or unavailable.

Technical time-horizon biases are deterministic **heuristics**, not guaranteed forecasts. They use historical momentum, moving averages, RSI, MACD and recent candlestick context. Market regimes can change and historical pattern behavior can fail out of sample.

For trading use, add licensed data, walk-forward/out-of-sample validation, transaction costs, slippage, corporate-action handling and appropriate risk controls.

## Tests

```bash
pytest -q
```

V4 includes offline tests for scoring, candlestick detection, fund metrics and multi-horizon bias generation.
