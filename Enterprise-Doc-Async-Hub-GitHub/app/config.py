from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://doc:doc@localhost:5432/doc"
    celery_broker_url: str = "amqp://doc:doc@localhost:5672//"
    celery_result_backend: str = "redis://localhost:6379/0"
    storage_dir: Path = Path("data/uploads")
    llm_mode: Literal["mock", "api"] = "mock"
    llm_base_url: str = "https://your-provider.example/v1"
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = "your-model"
    llm_timeout_seconds: float = Field(default=30, gt=0)
    api_token: str = ""
    max_upload_bytes: int = Field(default=50 * 1024 * 1024, gt=0)
    max_text_chars: int = Field(default=200_000, gt=0)
    chunk_chars: int = Field(default=12_000, ge=1000)
    lease_seconds: int = Field(default=300, ge=300)
    max_retries: int = Field(default=3, ge=0, le=3)
    llm_provider: Literal["deepseek", "compatible"] = "deepseek"
    agent_enabled: bool = True
    agent_max_rounds: int = Field(default=6, ge=1, le=10)
    agent_max_tool_calls: int = Field(default=12, ge=1, le=30)
    agent_max_tokens: int = Field(default=64000, ge=1000, le=100000)
    agent_max_seconds: int = Field(default=180, ge=10, le=200)
    llm_max_output_tokens: int = Field(default=1800, ge=256, le=4096)
    # Optional estimates; supplied by operator, never silently treated as actual billed cost.
    input_usd_per_million: float | None = Field(default=None, ge=0)
    output_usd_per_million: float | None = Field(default=None, ge=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
