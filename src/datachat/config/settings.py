from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DATACHAT_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = Field(default="sqlite:///./datachat.db")
    gemini_api_key: str = Field(default="")
    llm_model: str = Field(default="gemini-2.5-flash")
    max_iterations: int = Field(default=10)
    max_upload_bytes: int = Field(default=52_428_800)
    log_level: str = Field(default="INFO")

    @property
    def resolved_llm_provider(self) -> str:
        key = self.gemini_api_key.split("#")[0].strip()
        return "gemini" if key else "stub"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
