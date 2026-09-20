from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8090

    redis_url: str = "redis://127.0.0.1:6379/0"
    search_queue: str = "daleel:search:queue"
    search_workers: int = 2
    job_ttl_seconds: int = 900
    event_poll_ms: int = 250

    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "daleel_app_user"
    mysql_password: str = ""
    mysql_database: str = "daleel_balady"
    mysql_pool_min: int = 1
    mysql_pool_max: int = 6

    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_collection: str = "daleel_search"

    bge_url: str = "http://127.0.0.1:8001"
    bge_model: str = "bge-m3"

    llama_url: str = "http://127.0.0.1:8080"
    llama_model: str = "RightNow-Arabic-0.5B-Turbo"
    llama_timeout_seconds: float = 20
    llama_max_tokens: int = 180

    search_candidates: int = 80
    lexical_candidates: int = 40
    vector_candidates: int = 60
    default_limit: int = 10
    max_limit: int = 30

    lexical_weight: float = 0.45
    semantic_weight: float = 0.35
    geo_weight: float = 0.10
    business_weight: float = 0.10

    geo_full_score_meters: float = 500
    geo_zero_score_meters: float = 25000

    cors_origins: str = "*"


@lru_cache
def get_settings() -> Settings:
    return Settings()
