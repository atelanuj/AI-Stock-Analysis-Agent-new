import os
os.environ.setdefault("NVIDIA_API_KEY", "test-key")
"""Test-only fallbacks for optional packages missing in lightweight CI shells.

Docker installs the real packages from requirements.txt. These stubs are used only
when pytest is run in an environment that does not have them installed.
"""
import sys
import types

try:
    import redis  # noqa: F401
except ImportError:
    class _RedisClient:
        def get(self, *_args, **_kwargs): return None
        def setex(self, *_args, **_kwargs): return True
        def ping(self): return True
    sys.modules["redis"] = types.SimpleNamespace(from_url=lambda *_a, **_k: _RedisClient())

try:
    import yfinance  # noqa: F401
except ImportError:
    class _Ticker:
        def __init__(self, symbol): self.symbol = symbol
        def history(self, *args, **kwargs):
            raise RuntimeError("yfinance test stub: history must be monkeypatched")
    sys.modules["yfinance"] = types.SimpleNamespace(Ticker=_Ticker, download=lambda *_a, **_k: None)

try:
    import openai  # noqa: F401
except ImportError:
    class _Completions:
        def create(self, *args, **kwargs):
            raise RuntimeError("openai test stub: completions.create must be monkeypatched")
    class _Chat:
        completions = _Completions()
    class _OpenAI:
        def __init__(self, *args, **kwargs): self.chat = _Chat()
    sys.modules["openai"] = types.SimpleNamespace(OpenAI=_OpenAI)

try:
    import psycopg  # noqa: F401
except ImportError:
    class _Psycopg:
        @staticmethod
        def connect(*args, **kwargs):
            raise RuntimeError("psycopg test stub: database access not available in unit tests")
    sys.modules["psycopg"] = _Psycopg()
