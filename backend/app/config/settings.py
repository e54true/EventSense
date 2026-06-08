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
    # SEC mandates a custom User-Agent that identifies the caller. Format:
    #   "Company Name email@example.com"
    # See: https://www.sec.gov/os/accessing-edgar-data
    sec_user_agent: str = Field(
        default="EventSense dev@example.com",
        description="Identifying User-Agent for SEC EDGAR requests (mandatory)",
    )

    # Watchlist of tickers we poll for prices, earnings, 8-Ks. SPY is mandatory —
    # it's the baseline for excess-return calculations in the validator (Milestone 6).
    default_tickers: str = Field(
        default="NVDA,TSLA,AAPL,MSFT,GOOGL,META,AMZN,SPY,QQQ",
        description="Comma-separated ticker list",
    )

    @property
    def watchlist(self) -> list[str]:
        """Parsed watchlist as a list of uppercase tickers, whitespace-trimmed."""
        return [t.strip().upper() for t in self.default_tickers.split(",") if t.strip()]

    # --- LLM analysis (Milestone 5+) ---
    openai_api_key: str = Field(default="", description="Required for OpenAI analyzer")
    anthropic_api_key: str = Field(
        default="",
        description="Optional — enables the claude-* path in the model router",
    )
    # Model names — env-overridable so we can flip to newer versions without a redeploy.
    llm_default_model: str = Field(default="gpt-4o-mini")
    llm_premium_model: str = Field(default="gpt-4o")
    # Hard daily spend cap. When today's accumulated cost exceeds this, the
    # router downgrades premium tasks to the default model and logs a warning.
    llm_daily_cost_cap_usd: float = Field(default=1.0)
    # How many FETCHED events the analyzer pulls per task run. Keeps long-running
    # tasks bounded so a backlog doesn't hold a worker for 10+ minutes.
    llm_analyzer_batch_size: int = Field(default=20)

    # --- v2 contextual analyzer ---
    # Days of recent events the v2 prompt looks back over when analyzing a new
    # event. 30 covers a full macro cycle (CPI/NFP/GDP all monthly or quarterly)
    # without blowing prompt tokens past the daily cost cap.
    analyzer_lookback_days: int = Field(default=30)
    # Cap on how many recent events get inlined into the v2 prompt. The window
    # query orders by published_at DESC, so this is "most-recent N" not random.
    analyzer_recent_events_cap: int = Field(default=50)
    # Which prompt template the analyzer should render. Kill switch: flip to
    # 'v1' via env (ANALYZER_PROMPT_VERSION=v1) if v2 misbehaves in production,
    # no redeploy needed.
    analyzer_prompt_version: Literal["v1", "v2"] = Field(default="v2")


@lru_cache
def get_settings() -> Settings:
    return Settings()
