from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Loaded once and cached via get_settings(). Never instantiate directly in app code —
    always go through get_settings() so tests can override.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Runtime
    environment: Literal["development", "staging", "production"] = "development"

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://eventsense:eventsense@localhost:5432/eventsense",
        description="Async PostgreSQL URL (use postgresql+asyncpg:// scheme)",
    )

    # Redis (broker + cache; unused in Milestone 1 but env var defined for forward compat)
    redis_url: str = Field(default="redis://localhost:6379/0")

    # External APIs
    fred_api_key: str = Field(default="", description="Required for FRED adapter")


@lru_cache
def get_settings() -> Settings:
    return Settings()
