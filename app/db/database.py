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

CREATE TABLE IF NOT EXISTS technical_recommendations (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    horizon TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    ai_recommendation TEXT,
    technical_score NUMERIC,
    entry_price NUMERIC,
    target_low NUMERIC,
    target_high NUMERIC,
    risk_control NUMERIC,
    invalidation NUMERIC,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tech_rec_symbol_created ON technical_recommendations(symbol, market, created_at DESC);
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

def save_technical_recommendation(symbol: str, market: str, horizon: str, payload: dict):
    try:
        setup=payload.get("setup") or {};tz=setup.get("target_zone") or {};ai=payload.get("ai") or {}
        with psycopg.connect(settings.database_url) as conn:
            with conn.cursor() as cur:
                # Avoid recording the same cached decision repeatedly within 15 minutes.
                cur.execute("""
                    SELECT id FROM technical_recommendations
                    WHERE symbol=%s AND market=%s AND horizon=%s
                      AND created_at > NOW() - INTERVAL '15 minutes'
                    ORDER BY created_at DESC LIMIT 1
                """,(symbol,market,horizon))
                if cur.fetchone(): return
                cur.execute("""
                    INSERT INTO technical_recommendations(
                        symbol,market,horizon,recommendation,ai_recommendation,technical_score,
                        entry_price,target_low,target_high,risk_control,invalidation,payload
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                """,(
                    symbol,market,horizon,payload.get("recommendation"),ai.get("recommendation"),payload.get("technical_score"),
                    setup.get("entry_reference"),tz.get("low"),tz.get("high"),setup.get("risk_control_level"),setup.get("invalidation_level"),json.dumps(payload,default=str)
                ))
            conn.commit()
    except Exception:
        pass

def list_technical_recommendations(symbol: str | None = None, market: str | None = None, limit: int = 50) -> list[dict]:
    try:
        clauses=[];params=[]
        if symbol: clauses.append("symbol=%s");params.append(symbol.upper())
        if market: clauses.append("market=%s");params.append(market.upper())
        where=" WHERE "+" AND ".join(clauses) if clauses else ""
        params.append(min(max(int(limit),1),200))
        with psycopg.connect(settings.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT id,symbol,market,horizon,recommendation,ai_recommendation,technical_score,
                           entry_price,target_low,target_high,risk_control,invalidation,created_at
                    FROM technical_recommendations{where}
                    ORDER BY created_at DESC LIMIT %s
                """,params)
                rows=cur.fetchall()
        cols=["id","symbol","market","horizon","recommendation","ai_recommendation","technical_score","entry_price","target_low","target_high","risk_control","invalidation","created_at"]
        return [{k:(float(v) if k in {"technical_score","entry_price","target_low","target_high","risk_control","invalidation"} and v is not None else v.isoformat() if k=="created_at" and v is not None else v) for k,v in zip(cols,row)} for row in rows]
    except Exception:
        return []
