from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    nvidia_api_key: str
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_model: str = "nvidia/nemotron-3-ultra-550b-a55b"
    database_url: str = "postgresql://stockai:stockai@postgres:5432/stockai"
    redis_url: str = "redis://redis:6379/0"
    cache_ttl_seconds: int = 300
    market_history_cache_ttl_seconds: int = 300
    intraday_cache_ttl_seconds: int = 60
    fundamentals_cache_ttl_seconds: int = 21600
    news_cache_ttl_seconds: int = 900
    events_cache_ttl_seconds: int = 3600
    benchmark_cache_ttl_seconds: int = 900
    ai_cache_ttl_seconds: int = 1800
    market_data_timeout_seconds: int = 10
    quote_timeout_seconds: int = 6
    quote_cache_ttl_seconds: int = 30
    quote_warning_difference_pct: float = 1.5
    market_data_retries: int = 2
    ai_temperature: float = 0.3
    ai_top_p: float = 0.95
    ai_max_tokens: int = 8192
    ai_fast_max_tokens: int = 2048
    ai_request_timeout_seconds: float = 60
    ai_enable_thinking: bool = True
    ai_reasoning_budget: int = 8192
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
