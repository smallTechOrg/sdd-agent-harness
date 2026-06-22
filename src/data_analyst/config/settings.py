from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _strip_inline(value: str) -> str:
    """Strip inline ``#`` comments and whitespace from a dirty .env value."""
    return value.split("#", 1)[0].strip()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DATA_ANALYST_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = Field(default="sqlite:///./data/metadata.db")
    duckdb_path: str = Field(default="./data/datasets.duckdb")

    gemini_api_key: str = Field(default="")
    llm_provider: str = Field(default="auto")
    llm_model: str = Field(default="gemini-2.5-flash")
    llm_model_escalation: str = Field(default="gemini-2.5-pro")

    sample_rows: int = Field(default=5)
    port: int = Field(default=8001)
    log_level: str = Field(default="INFO")

    @property
    def resolved_llm_provider(self) -> str:
        """auto -> real 'gemini' when a key is set, else 'stub'."""
        provider = _strip_inline(self.llm_provider).lower()
        if provider == "auto":
            return "gemini" if _strip_inline(self.gemini_api_key) else "stub"
        return provider

    @property
    def resolved_gemini_api_key(self) -> str:
        return _strip_inline(self.gemini_api_key)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
