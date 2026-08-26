# Stock AI Agent V7

V7 builds on the V6.1 data-integrity and SciPy hotfix release. It keeps the India/US Stocks, Funds, Screener, Portfolio, Watchlist, validated quote layer, sanitized OHLC, progressive loading and NVIDIA Nemotron integration, and adds three major workflows:

1. a much deeper Mutual Funds / ETF research dashboard,
2. clickable screener results that open the full matching Stock or Fund analysis,
3. a selected-horizon Technical AI Decision with BUY / HOLD / SELL research output plus deterministic target and risk-control levels.

## V7 Stock technical decision

The Multi-Timeframe Technical Outlook includes clickable:

- 1D
- 1W
- 1M
- 3M
- 6M
- 1Y

Selecting a horizon refreshes its support/resistance zones, relative strength, breakout context and a separate Nemotron technical-decision request.

The decision considers all six technical horizons plus:

- RSI
- MACD
- SMA/trend structure
- VWAP
- ATR
- ADX
- relative volume
- breakout/breakdown state
- dynamic support/resistance zones
- relative strength vs NIFTY 50 or S&P 500
- recent candlestick patterns

The UI displays:

- **BUY / HOLD / SELL** technical action
- deterministic technical score
- AI confidence
- entry reference
- technical target zone
- stop / risk-control reference
- invalidation level
- potential reward/risk
- risk/reward ratio
- confirming and conflicting signals

### Important target/stop design

Nemotron is **not allowed to invent target or stop prices**. Numeric levels are calculated deterministically from the selected horizon's price structure, support/resistance zones and ATR. If the deterministic rules and AI directional suggestion disagree, V7 deliberately downgrades the final action to **HOLD**.

Targets are technical estimates, not confirmed future prices. Risk-control levels are research references, not personalized stop-loss instructions.

## V7 Mutual Funds / ETFs dashboard

Funds now have a detail experience much closer to Stocks, while using fund-specific metrics instead of stock indicators.

### Header and data quality

- fund/scheme name
- category
- fund house
- latest NAV/price and date
- NAV provider
- benchmark provider
- observation coverage
- timezone/date-alignment status

### Multi-horizon returns

- 1D
- 1M
- 3M
- 6M
- 1Y
- 3Y CAGR
- 5Y CAGR

The return cards are clickable and show the selected historical return context.

### Risk / consistency

- annualized volatility
- downside volatility
- maximum drawdown
- current drawdown from peak
- Sharpe ratio
- Sortino ratio
- positive rolling 1Y periods
- positive calendar years
- risk band
- consistency status

### Benchmark analytics

- benchmark name
- fund CAGR over aligned history
- benchmark CAGR
- alpha
- tracking error
- correlation
- beta
- aligned sessions
- normalized fund-vs-benchmark growth chart (both rebased to 100)

### Fund profile

- overall fund score / rating
- return score
- consistency score
- risk score
- cost score
- benchmark score
- drawdown score
- cost status
- benchmark status
- rolling 1Y median / best / worst returns
- research notes explaining important metrics

## Clickable Screener results

Every returned Stock or Fund row is now clickable and keyboard-accessible.

- Click a **Stock** result → V7 switches to Stocks, fills market/symbol, and loads the full stock research page.
- Click a **Fund** result → V7 switches to Funds and loads the full fund research page.

The screener remains optimized for bulk work: AI is still skipped while screening and only runs after opening a detailed stock result.

## V6 / V6.1 data-integrity features retained

### Stocks

- India live quote validation: NSE + Yahoo when reachable
- US quote validation: Yahoo + Stooq sanity check when reachable
- Yahoo/yfinance historical OHLCV with repair support
- duplicate/non-finite/impossible OHLC rejection
- 1D 5-minute latest-populated-session extraction
- quote source, timestamp and discrepancy display

### Indian Mutual Funds

- MFAPI NAV/search
- NIFTY 50 benchmark via Yahoo Finance
- timezone-naive calendar-date normalization before joining NAV and benchmark series

### US Funds / ETFs

- Yahoo Finance/yfinance
- S&P 500 benchmark

## NVIDIA model

```text
nvidia/nemotron-3.5-lightning-30b-a3b
```

via NVIDIA's OpenAI-compatible endpoint.

## Run locally

```bash
cp .env.example .env
# Set NVIDIA_API_KEY in .env

docker compose down
docker compose up --build
```

Open:

- Dashboard: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

Health should report:

```json
{
  "status": "ok",
  "version": "7.0.0"
}
```

## Useful API examples

```bash
# India stock
curl "http://localhost:8000/analyze/core/TCS?market=IN"

# 1D technical AI decision
curl "http://localhost:8000/technical/decision/TCS?market=IN&horizon=1D"

# 3M technical AI decision
curl "http://localhost:8000/technical/decision/TCS?market=IN&horizon=3M"

# Indian mutual fund
curl "http://localhost:8000/mf/analyze/120503?market=IN"

# 1D candles
curl "http://localhost:8000/api/candles/TCS?market=IN&period=1d&interval=5m"
```

## Limitations

This is a research/education application, not an exchange terminal or personalized investment adviser. Public/free providers can be delayed, unavailable, rate-limited or inconsistent. Cross-source validation reduces silent errors but does not create exchange-grade data. For production trading, use licensed real-time market, corporate-action, fund and news feeds.
