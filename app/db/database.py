import json
import psycopg
from app.config import settings

DDL = """
CREATE TABLE IF NOT EXISTS analyses (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    overall_score NUMERIC,
    rating TEXT,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_analyses_symbol_created ON analyses(symbol, created_at DESC);
"""

def init_db():
    try:
        with psycopg.connect(settings.database_url) as conn:
            with conn.cursor() as cur: cur.execute(DDL)
            conn.commit()
    except Exception:
        pass

def save_analysis(symbol: str, overall_score: float, rating: str, payload: dict):
    try:
        with psycopg.connect(settings.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO analyses(symbol, overall_score, rating, payload) VALUES (%s, %s, %s, %s::jsonb)",
                            (symbol, overall_score, rating, json.dumps(payload, default=str)))
            conn.commit()
    except Exception:
        pass
