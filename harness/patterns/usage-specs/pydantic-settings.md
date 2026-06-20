# Usage-spec: pydantic-settings (+ pydantic v2)

**Version: `pydantic-settings` 2.x · `pydantic` 2.x** (verify latest before pinning — a bump REFRESHES this file)
**Stamped: 2026-06**

Guards: `model-and-providers.md` (`agent/config.py`). These three rules are silent-failure killers a green
build won't catch — they map to constitution `C-ENV-STRIP`, `C-ENV-IGNORE`, `C-SECRET-TYPE`.

## The Settings class (the one config accessor)
```python
from functools import lru_cache
from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra="ignore")
    llm_api_key: SecretStr = SecretStr("")
    llm_model:   str = "claude-haiku-4-5-20251001"
    ...

@lru_cache
def get_settings() -> Settings:        # cached singleton — the ONE config accessor
    return Settings()
```
- ✅ `BaseSettings` + `SettingsConfigDict` come from **`pydantic_settings`** (v2 split it out of pydantic
  core). ❌ Do NOT `from pydantic import BaseSettings` — that's the v1 location; it raises in v2.
- ✅ `model_config = SettingsConfigDict(...)` (v2 style). ❌ Not a nested `class Config:` (v1 style).

## RULE — `extra="ignore"` (C-ENV-IGNORE)
- ✅ `extra="ignore"` in `model_config` so undeclared `.env` keys (`TEST_DATABASE_URL`, CI vars) don't raise
  at startup. The default (`extra="forbid"`-ish) crashes the boot the moment the env carries one undeclared
  key — a build-breaker on any real machine.

## RULE — strip inline `#` comments + whitespace (C-ENV-STRIP, highest-ROI)
pydantic-settings does **NOT** strip them: `APP_LLM_API_KEY=sk-xxx # prod key` is read as the literal
`"sk-xxx # prod key"`, the build stays green (no call yet), and the **real run 401s**.
```python
@field_validator("llm_provider", "llm_model", "database_url", mode="before")
@classmethod
def _strip_inline_comment(cls, v):
    return v.split(" #", 1)[0].strip() if isinstance(v, str) else v   # split on SPACE-hash so URL '#frag' survives
```
- ✅ `@field_validator(..., mode="before")` + `@classmethod` (v2 signature). ❌ Not the v1
  `@validator(..., pre=True)` — removed in v2.
- ✅ Split on `" #"` (space-hash), not bare `#`, so a URL with a literal `#fragment` survives. Apply the same
  clean to the secret field (with `mode="before"`).

## RULE — `SecretStr`, unwrap only at the use boundary (C-SECRET-TYPE)
```python
llm_api_key: SecretStr = SecretStr("")
# ... at the ONE use point (agent/llm.py):
key = settings.llm_api_key.get_secret_value()
```
- ✅ Type secrets as `SecretStr`; call `.get_secret_value()` **only** where it's handed to the provider SDK.
  `repr(settings)` / `str(secret)` print `**********`, never the key.
- ❌ Never log/`print`/`repr` the unwrapped value, never put it in a span attribute, never default it to a
  real key in code.

## Fail loud at boot (C-PORT neighbour — model-and-providers.md RULE 2)
```python
def validate_required_config() -> None:
    s = get_settings(); missing = []
    if not s.llm_api_key.get_secret_value(): missing.append("APP_LLM_API_KEY")
    if not s.llm_model: missing.append("APP_LLM_MODEL")
    if missing: raise RuntimeError(f"missing required config: {', '.join(missing)} — set in .env (README).")
```
- Called from the FastAPI lifespan **before** `init_db()` (`fastapi.md`) so a missing key crashes the boot
  with a named error, not a mid-run 500.
