"""Settings — pydantic-settings, env prefix ANALYST_. Cheap runtime tier by default.

Switching provider/model/DB is a config change here, never a code change
(harness/patterns/model-and-providers.md). Every recipe imports get_settings().
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ANALYST_", env_file=".env", extra="ignore")

    # Runtime LLM (the product's model — cheap tier; see spec/tech-stack.md)
    llm_provider: str = "google_genai"
    llm_model: str = "gemini-2.5-flash"
    llm_api_key: str = ""                       # ANALYST_LLM_API_KEY — required for a real run

    # Persistence (the spine + domain metadata) — local-first SQLite -> Postgres at /deploy
    database_url: str = "sqlite+aiosqlite:///./agent.db"
    data_dir: str = "./data"                    # per-dataset DuckDB files live here

    # Serving
    port: int = 8001

    # ReAct loop — 12 covers: list_datasets + up to 6 schema calls + execute_sql + chart + finish
    max_iterations: int = 12

    # run_sql safety caps (the agent's queries are read-only; these bound cost/blast-radius)
    max_query_rows: int = 1000
    query_timeout_s: float = 15.0

    # Multi-turn checkpointer (Phase 3). False -> ephemeral InMemorySaver for the single-turn demo gate.
    durability_enabled: bool = False

    # LLM cost per 1M tokens (for run/session cost tracking)
    llm_input_cost_per_1m: float = 0.15   # Gemini 2.5 Flash input
    llm_output_cost_per_1m: float = 0.60  # Gemini 2.5 Flash output


@lru_cache
def get_settings() -> Settings:                 # cached singleton — the one config accessor
    return Settings()
