from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENT_",
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )
    database_url: str = Field(default="sqlite:///./data_analysis.db")
    log_level: str = Field(default="INFO")
    llm_provider: str = Field(default="gemini")
    llm_model: str = Field(default="gemini-2.5-flash")
    gemini_api_key: str = Field(default="")
    cost_input_per_1k: float = Field(default=0.000125)
    cost_output_per_1k: float = Field(default=0.000375)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
