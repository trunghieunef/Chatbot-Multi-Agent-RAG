"""
Backend application configuration.

Loads settings from environment variables with sensible defaults.
"""

from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # App
    APP_NAME: str = "Real Estate Chatbot API"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://admin:realestate_secret_2026@localhost:5432/realestate"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Google Gemini
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-001"
    EMBEDDING_PROVIDER: str = "bge_m3"
    HF_EMBEDDING_MODEL: str = "BAAI/bge-m3"
    EMBEDDING_DIM: int = 1024
    EMBEDDING_BATCH_SIZE: int = 16
    HF_EMBEDDING_DEVICE: str = ""
    CHUNK_SIZE_TOKENS: int = 400
    CHUNK_OVERLAP_TOKENS: int = 80

    # Reranking
    COHERE_API_KEY: str = ""
    RERANK_PROVIDER: str = "cohere"
    RERANK_MODEL: str = "rerank-multilingual-v3.0"
    RERANK_TOP_N: int = 5

    # Internal Agent Service
    AGENT_SERVICE_URL: str = "http://localhost:8100"
    AGENT_INTERNAL_KEY: str = "dev-agent-internal-key"
    AGENT_SERVICE_TIMEOUT_SECONDS: float = 45.0
    CHATBOT_AGENT_SERVICE_ENABLED: bool = False
    CHATBOT_LLM_JUDGE_ENABLED: bool = False
    CHATBOT_MEMORY_ENABLED: bool = True
    CHATBOT_ADMIN_ENABLED: bool = True
    CHATBOT_TRACE_LEVEL: str = "full"
    GEMINI_JUDGE_MODEL: str = "gemini-2.0-flash"

    # Chat quotas
    ANON_CHAT_DAILY_LIMIT: int = 20
    AUTH_CHAT_DAILY_LIMIT: int = 200

    # JWT
    JWT_SECRET_KEY: str = "your-super-secret-jwt-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Geocoding
    GEOCODER_PROVIDER: str = "nominatim"          # 'nominatim' | 'goong'
    GEOCODER_USER_AGENT: str = "realestate-chatbot/0.1 (contact@example.com)"
    GEOCODER_RATE_LIMIT_SECONDS: float = 1.0
    GOONG_API_KEY: str = ""

    # Intent extraction
    INTENT_EXTRACTOR: str = "rule"                # 'rule' | 'gemini'
    GEMINI_INTENT_MODEL: str = "gemini-2.0-flash"

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value):
        if isinstance(value, str) and value.lower() in {"release", "prod", "production"}:
            return False
        return value

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Ignore extra env vars not defined in Settings


@lru_cache
def get_settings() -> Settings:
    return Settings()
