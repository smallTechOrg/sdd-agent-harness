import os

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
    llm_model: str = Field(default="gemini-2.5-flash")

    # Provider keys — set exactly one
    anthropic_api_key: str = Field(default="")
    gemini_api_key: str = Field(default="")

    # LangSmith tracing
    langchain_api_key: str = Field(default="")
    langchain_tracing_v2: str = Field(default="false")
    langchain_project: str = Field(default="data-analysis-agent")


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def configure_langsmith() -> None:
    """Set standard LangSmith env vars from settings so LangChain picks them up."""
    s = get_settings()
    if s.langchain_api_key:
        os.environ["LANGCHAIN_API_KEY"] = s.langchain_api_key
    os.environ["LANGCHAIN_TRACING_V2"] = s.langchain_tracing_v2
    os.environ["LANGCHAIN_PROJECT"] = s.langchain_project
