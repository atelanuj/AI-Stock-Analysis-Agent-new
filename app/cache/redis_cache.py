import json
import redis
from app.config import settings

_client = redis.from_url(settings.redis_url, decode_responses=True)

def get_json(key: str):
    try:
        value = _client.get(key)
        return json.loads(value) if value else None
    except Exception:
        return None

def set_json(key: str, value: dict, ttl: int | None = None):
    try:
        _client.setex(key, ttl or settings.cache_ttl_seconds, json.dumps(value, default=str))
    except Exception:
        pass
