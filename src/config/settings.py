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

    # LLM pricing (USD per 1,000,000 tokens) — used to compute per-question cost
    price_input_per_m: float = Field(default=0.10)
    price_output_per_m: float = Field(default=0.40)

    # ── Privacy / context budget ───────────────────────────────────────────
    # Max sample rows sent to the LLM (full data NEVER leaves the machine).
    sample_rows: int = Field(default=20)          # AGENT_SAMPLE_ROWS
    # Conversation turns of history fed back into the prompt.
    history_turns: int = Field(default=6)         # AGENT_HISTORY_TURNS

    # ── Local code execution (sandbox) ─────────────────────────────────────
    exec_timeout_s: int = Field(default=30)       # AGENT_EXEC_TIMEOUT_S
    max_retries: int = Field(default=1)           # AGENT_MAX_RETRIES

    # ── Uploads ────────────────────────────────────────────────────────────
    max_upload_mb: int = Field(default=100)       # AGENT_MAX_UPLOAD_MB


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
