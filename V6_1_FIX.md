# V6.1 hotfix

- Added `scipy>=1.13,<2` because yfinance `repair=True` can use SciPy.
- Added a defensive repair fallback: if and only if SciPy is unavailable, history/download calls retry with `repair=False`.
- Applied the same fallback to stock OHLC, benchmark OHLC, batch screener downloads, and mutual-fund benchmark history.
- Updated health/UI version to 6.1.0.
- Rebuild the API image after upgrading; an existing V6 Docker image will not gain SciPy until rebuilt.
