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
    llm_model: str = Field(default="")      # uses provider default when blank

    # Provider keys — set exactly one
    anthropic_api_key: str = Field(default="")
    gemini_api_key: str = Field(default="")

    # Analyst capability — CSV profiling, sandbox execution, result caps
    sample_rows: int = Field(default=15)          # rows of the capped sample sent to the LLM (hard cap 20)
    max_upload_bytes: int = Field(default=5_000_000)   # reject CSV bodies larger than this
    max_rows: int = Field(default=200_000)        # reject CSVs with more rows than this
    exec_timeout: int = Field(default=10)         # wall-clock seconds for sandbox execution
    max_result_rows: int = Field(default=1000)    # cap result-table rows; truncate beyond


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
