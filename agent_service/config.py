from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class AgentSettings(BaseSettings):
    """Settings for the internal Agent Service."""

    model_config = SettingsConfigDict(
        env_file=str(ROOT_ENV_FILE),
        case_sensitive=True,
        extra="ignore",
    )

    SERVICE_NAME: str = "agent-service"
    DEBUG: bool = True

    DATABASE_URL: str = "postgresql+asyncpg://admin:realestate_secret_2026@localhost:5432/realestate"
    REDIS_URL: str = "redis://localhost:6379/0"

    AGENT_INTERNAL_KEY: str = "dev-agent-internal-key"
    AGENT_ALLOW_DEV_INTERNAL_KEY: bool = False
    CHATBOT_TRACE_LEVEL: str = "full"
    AGENT_GRAPH_VERSION: str = "agent-graph-v1"
    AGENT_PROMPT_VERSION: str = "prompts-v1"

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    GEMINI_JUDGE_MODEL: str = "gemini-2.0-flash"

    COHERE_API_KEY: str = ""
    HF_EMBEDDING_MODEL: str = "BAAI/bge-m3"
    EMBEDDING_DIM: int = 1024

    AGENT_REQUEST_TIMEOUT_SECONDS: float = 45.0
    AGENT_LLM_TIMEOUT_SECONDS: float = 30.0
    AGENT_ROUTER_MODE: str = "llm"
    AGENT_QUERY_REWRITE_ENABLED: bool = True
    AGENT_MEMORY_FILTERS_ENABLED: bool = True
    AGENT_SPECIALIST_LLM_ENABLED: bool = True
    AGENT_LLM_CONFIDENCE_THRESHOLD: float = 0.65
    AGENT_LLM_MAX_REWRITES: int = 3
    AGENT_LLM_ROUTER_TIMEOUT_SECONDS: float = 5.0
    AGENT_LLM_QUERY_TIMEOUT_SECONDS: float = 5.0
    AGENT_SPECIALIST_LLM_TIMEOUT_SECONDS: float = 12.0
    AGENT_TOTAL_TIMEOUT_SECONDS: float = 10.0
    AGENT_LLM_MONTHLY_BUDGET_USD: float = 100.0
    AGENT_LLM_COST_TRACKING_ENABLED: bool = True
    AGENT_LLM_INPUT_PRICE_PER_MILLION_USD: float = 0.0
    AGENT_LLM_OUTPUT_PRICE_PER_MILLION_USD: float = 0.0
    AGENT_REACT_ENABLED: bool = True
    AGENT_REACT_MAX_ITERATIONS: int = 2
    AGENT_REACT_CONTROLLER_MODE: str = "llm"
    AGENT_REACT_TIMEOUT_SECONDS: float = 5.0

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value):
        if isinstance(value, str) and value.lower() in {"release", "prod", "production"}:
            return False
        return value

    @field_validator("AGENT_ROUTER_MODE")
    @classmethod
    def validate_router_mode(cls, value: str) -> str:
        allowed = {"rule", "llm", "hybrid"}
        if value not in allowed:
            raise ValueError(f"AGENT_ROUTER_MODE must be one of {sorted(allowed)}")
        return value

    @field_validator("AGENT_REACT_CONTROLLER_MODE")
    @classmethod
    def validate_react_controller_mode(cls, value: str) -> str:
        allowed = {"rule", "llm", "hybrid"}
        if value not in allowed:
            raise ValueError(
                f"AGENT_REACT_CONTROLLER_MODE must be one of {sorted(allowed)}"
            )
        return value

    @model_validator(mode="after")
    def require_explicit_model_for_live_llm(self):
        live_llm_enabled = (
            self.AGENT_ROUTER_MODE != "rule"
            or self.AGENT_QUERY_REWRITE_ENABLED
            or self.AGENT_SPECIALIST_LLM_ENABLED
        )
        if (
            self.GEMINI_API_KEY
            and live_llm_enabled
            and (
                "GEMINI_MODEL" not in self.model_fields_set
                or not self.GEMINI_MODEL.strip()
            )
        ):
            raise ValueError(
                "GEMINI_MODEL must be explicitly configured when live LLM features are enabled."
            )
        return self


@lru_cache
def get_agent_settings() -> AgentSettings:
    return AgentSettings()
