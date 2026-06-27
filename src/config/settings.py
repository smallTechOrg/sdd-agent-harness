from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENT_",
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = Field(default="sqlite:///./data/agent.db")
    log_level: str = Field(default="INFO")

    # LLM provider — auto-detected from whichever key is set if left blank
    llm_provider: str = Field(default="")   # "anthropic" | "gemini"
    llm_model: str = Field(default="gemini-2.5-flash")  # used when AGENT_LLM_MODEL is blank
    llm_timeout_seconds: float = Field(default=30.0)  # per-call timeout on the LLM request

    # Provider keys — set exactly one
    anthropic_api_key: str = Field(default="")
    gemini_api_key: str = Field(default="")

    # DuckDB analytical engine (user data; the privacy boundary)
    duckdb_path: str = Field(default="./data/analytics.duckdb")
    sample_row_count: int = Field(default=5)   # max sample rows sent to the LLM
    result_row_cap: int = Field(default=1000)  # max rows returned from a SELECT


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
