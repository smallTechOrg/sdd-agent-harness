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

    # Model routing — logical task → concrete model id (provider-specific).
    # Blank → the provider's default model. Set these to your provider's tiers,
    # e.g. Anthropic: classify=claude-haiku-4-5, tools=claude-sonnet-4-6,
    # reason=claude-opus-4-8; Gemini: classify=gemini-2.5-flash,
    # tools=gemini-2.5-flash, reason=gemini-2.5-pro.
    model_classify: str = Field(default="")
    model_tools: str = Field(default="")
    model_reason: str = Field(default="")

    # Guardrails + per-run budget (hard caps enforced inside the ReAct loop)
    max_input_chars: int = Field(default=20_000)
    react_max_steps: int = Field(default=6)          # loop-of-death cap
    max_cost_usd_per_run: float = Field(default=1.0)
    max_tokens_per_run: int = Field(default=200_000)

    # MCP consumption (optional; tools register into the same registry)
    mcp_server_url: str = Field(default="")
    mcp_server_name: str = Field(default="")
    mcp_auth_token: str = Field(default="")


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
