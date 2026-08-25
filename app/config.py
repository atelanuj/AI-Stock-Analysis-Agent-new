from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    nvidia_api_key: str
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_model: str = "nvidia/nemotron-3.5-lightning-30b-a3b"
    database_url: str = "postgresql://stockai:stockai@postgres:5432/stockai"
    redis_url: str = "redis://redis:6379/0"
    cache_ttl_seconds: int = 300
    ai_temperature: float = 0.3
    ai_top_p: float = 0.95
    ai_max_tokens: int = 8192
    ai_enable_thinking: bool = True
    ai_reasoning_budget: int = 8192
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
