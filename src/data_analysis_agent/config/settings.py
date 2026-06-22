from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DATAANALYSIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # SQLite (default):    sqlite:///data_analysis.db
    # PostgreSQL:          postgresql+psycopg2://user:pass@host:5432/dbname
    # PostgreSQL requires: uv pip install data-analysis-agent[postgres]
    database_url: str = Field(default="sqlite:///data_analysis.db")
    openrouter_api_key: str = Field(default="")
    llm_model: str = Field(default="google/gemini-2.5-flash")
    log_level: str = Field(default="INFO")
    log_file: str = Field(default="logs/app.log")
    upload_dir: str = Field(default="uploads")
    max_agent_iterations: int = Field(default=10)

    @property
    def resolved_llm_provider(self) -> str:
        """Return ``"openrouter"`` when an API key is configured, else ``"stub"``."""
        key = self.openrouter_api_key.split("#")[0].strip()
        return "openrouter" if key else "stub"


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the process-wide :class:`Settings` singleton, loading env vars once."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
