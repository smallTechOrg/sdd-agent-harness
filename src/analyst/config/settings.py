import functools
import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ANALYST_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///data/app.db"
    secret_key: str = "dev-secret-key-change-in-production"
    llm_model: str = "gemini-2.5-flash"
    data_dir: str = "data"
    log_level: str = "INFO"
    max_upload_mb: int = 50
    max_result_rows: int = 1000
    query_timeout_s: int = 30

    @property
    def resolved_llm_provider(self) -> str:
        # Read GEMINI_API_KEY directly from env; strip inline # comments
        raw = os.environ.get("GEMINI_API_KEY", "")
        key = raw.strip().split("#")[0].strip()
        return "gemini" if key else "stub"


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
