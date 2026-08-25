# V4 changes from V3

V4 preserves the V3 Docker Compose, FastAPI, Redis, PostgreSQL, India/US stock and fund analysis, screeners, portfolio support, candlestick detection and NVIDIA Nemotron integration.

## UI / usability

- Restored **clickable stock news**. When Yahoo/yfinance returns a valid publisher URL, the whole news card opens the full publisher article in a new tab.
- Added optional publisher/date/summary information to news cards when available.
- Added **traffic-light key metrics** for beginners:
  - green = generally favorable under a generic heuristic
  - yellow = caution / needs context
  - red = unfavorable or higher-risk signal
  - gray = data unavailable / not classified
- Added hover explanations so users can see why P/E, market cap, ROE or RSI received a color.
- Added a legend clarifying that the colors are heuristics, not universal investment rules.
- Fixed dark-mode native dropdown option colors so both **India** and **US** choices stay readable on Windows/Chrome-style native select menus.

## Charts

- Added **Candles / Line** chart toggle.
- Added chart time ranges:
  - 1W
  - 1M
  - 3M
  - 6M
  - 1Y
- Theme changes redraw the Plotly stock chart for readable labels in both dark and light mode.

## Technical outlook

- Retained the original short-horizon trend engine for backwards compatibility.
- Added first-class multi-horizon technical biases for:
  - 1W
  - 1M
  - 3M
  - 6M
  - 1Y
- Each horizon returns:
  - `BULLISH`, `NEUTRAL`, or `BEARISH`
  - signal-agreement confidence
  - horizon lookback return
  - concise supporting reasons
- The UI renders the five horizon cards next to each other and lets the user click a horizon to inspect its reasons.

## Prediction wording

These horizon values are **heuristic directional biases**, not guaranteed forecasts and not probabilities of profit. They combine recent return/momentum, horizon-appropriate moving averages, RSI, MACD, and short-lived candle patterns where relevant.
