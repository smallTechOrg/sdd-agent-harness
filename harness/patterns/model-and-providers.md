# Pattern: Model & providers (Layer 1)

How the agent gets a runtime LLM. One accessor, `init_chat_model`, behind config — so switching provider
or model is a **config change, never a code change**. **Generate this fresh at build time**, pinning the
*current* `langchain` (and the provider package, e.g. `langchain-anthropic` / `langchain-openai` /
`langchain-google-genai`) — check the latest first; a guessed/old version 404s.

Two model roles (see `harness.md`): **Claude Code** builds the app; the **product runtime LLM** is a
separate, cheap-tier model set in `spec/tech-stack.md`. This file is about the runtime LLM.

## Runtime default = CHEAP tier
Default to a cheap, fast model (Haiku / Gemini-flash class). Escalate per `spec/tech-stack.md` only when a
capability needs it. Cheap-tier IDs (mid-2026 — **verify the latest before pinning**, a stale ID 404s):

| Provider (`APP_LLM_PROVIDER`) | Cheap-tier `APP_LLM_MODEL` | Pin (verify latest) |
|---|---|---|
| `anthropic` | `claude-haiku-4-5-20251001` | `langchain-anthropic` |
| `openai`    | `gpt-5-nano` / `gpt-5-mini` | `langchain-openai` |
| `google_genai` | `gemini-3.5-flash` (or `gemini-2.5-flash`) | `langchain-google-genai` |

Capable tiers for escalation: Anthropic `claude-sonnet-4-6` / `claude-opus-4-8`; OpenAI `gpt-5.4`; Google
`gemini-3.x`. Anthropic's most capable is `claude-fable-5` (premium; different API behavior — thinking
always on, opt-in refusal fallbacks). Always confirm IDs at build time.

## Code — `agent/config.py`
Settings via pydantic-settings, env prefix `APP_`. The runtime model defaults CHEAP. **Three correctness
rules below are copy-verbatim — each one is a silent-failure killer that a green build won't catch.**
```python
from functools import lru_cache
from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # extra="ignore": undeclared .env keys (TEST_DATABASE_URL, CI vars) MUST NOT raise. Without it the app
    # crashes on boot the moment the environment carries one key you didn't declare.
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra="ignore")
    llm_provider: str = "anthropic"
    llm_model: str = "claude-haiku-4-5-20251001"   # CHEAP tier — escalate via spec/tech-stack.md
    llm_api_key: SecretStr = SecretStr("")          # SecretStr: never logged/repr'd; read only at the use boundary
    database_url: str = "sqlite+aiosqlite:///./agent.db"
    port: int = 8001
    max_iterations: int = 6
    price_in: float = 1.0       # USD per 1M input tokens  — set to the chosen model's rate (cost_usd column)
    price_out: float = 5.0      # USD per 1M output tokens — see patterns/persistence.md / interface.md

    # RULE 1 — strip inline `#` comments + surrounding whitespace from EVERY string env value.
    # pydantic-settings does NOT do this: `APP_LLM_API_KEY=sk-xxx # prod key` is read as the literal
    # "sk-xxx # prod key", the build stays green (no call yet), and the real run 401s. Highest-ROI fix.
    @field_validator("llm_provider", "llm_model", "database_url", mode="before")
    @classmethod
    def _strip_inline_comment(cls, v):
        if isinstance(v, str):
            # split on " #" (space-hash) so URLs with a literal '#' fragment survive; then strip whitespace
            return v.split(" #", 1)[0].strip()
        return v

    @field_validator("llm_api_key", mode="before")
    @classmethod
    def _clean_secret(cls, v):
        return v.split(" #", 1)[0].strip() if isinstance(v, str) else v

@lru_cache
def get_settings() -> Settings:                      # cached Settings singleton — the one config accessor
    return Settings()
```

### RULE 2 — validate required config at startup (fail loud, not on the 50th request)
A missing/blank key must crash the boot with a named error, never surface as a mid-run 500 a non-tech user
has to decode. Call this from the FastAPI lifespan (`agent/server.py`) before `init_db()`:
```python
def validate_required_config() -> None:
    """Fail LOUD at boot if config the agent can't run without is missing. One named error, not a 500 later."""
    s = get_settings()
    missing = []
    if not s.llm_api_key.get_secret_value():        # the SecretStr is empty
        missing.append("APP_LLM_API_KEY")
    if not s.llm_model:
        missing.append("APP_LLM_MODEL")
    if missing:
        raise RuntimeError(f"missing required config: {', '.join(missing)} — set them in .env (see README).")
```

### RULE 3 — `get_secret_value()` ONLY at the use boundary
The key is a `SecretStr` everywhere; you unwrap it with `.get_secret_value()` at the single point it's
handed to the provider SDK (in `agent/llm.py` below) — never log it, never `print`/`repr` it, never put it in
a span attribute. `SecretStr` makes an accidental log print `**********` instead of the key.

## Code — `agent/llm.py`
One accessor. Raises clearly if no funded key (a real run requires `APP_LLM_API_KEY` — see `harness.md`).
```python
from langchain.chat_models import init_chat_model
from .config import get_settings

def get_model():
    s = get_settings()
    key = s.llm_api_key.get_secret_value()           # unwrap the SecretStr ONLY here — the use boundary
    if not key:
        raise RuntimeError("APP_LLM_API_KEY is required for a real run (see README / spec/tech-stack.md).")
    return init_chat_model(s.llm_model, model_provider=s.llm_provider, api_key=key)
```
`init_chat_model` dispatches on `model_provider`; the graph binds tools to whatever it returns
(`patterns/react-agent.md`). The rest of the agent never imports a provider SDK — that's the whole point.

## Content coercion — not all providers return plain strings
Some models return `AIMessage.content` as a structured list (parts + metadata) when reasoning or
multi-modal features are active. `str()` on a list gives `"[{'type': ...}]"`, not the text.
Always coerce before string APIs (`finalize_node`, `scan_pii`, guardrails, anywhere you read `.content`):
```python
raw = msg.content
if isinstance(raw, list):
    raw = "\n".join(p["text"] for p in raw if isinstance(p, dict) and p.get("type") == "text")
content: str = raw or ""
```

## Provider switch = config change
Set `APP_LLM_PROVIDER` + `APP_LLM_MODEL` (+ key) in `.env`. No code edits. Install the matching provider
package. Example `.env` swaps:
```
APP_LLM_PROVIDER=anthropic     ; APP_LLM_MODEL=claude-haiku-4-5-20251001
APP_LLM_PROVIDER=openai        ; APP_LLM_MODEL=gpt-5-nano
APP_LLM_PROVIDER=google_genai  ; APP_LLM_MODEL=gemini-3.5-flash
```

## Structured output
For typed extraction / classification / a strict envelope, bind a schema with `.with_structured_output`
instead of parsing free text. Provider-portable (uses native structured-output / tool-calling under the
hood):
```python
from pydantic import BaseModel

class Verdict(BaseModel):
    label: str
    confidence: float

structured = get_model().with_structured_output(Verdict)
result: Verdict = await structured.ainvoke(messages)   # validated instance, not a string
```
Use this for fixed-shape results; keep the tool-calling ReAct loop (`patterns/react-agent.md`) for
open-ended, multi-step work. Don't combine `.with_structured_output` with `.bind_tools` on the same call.

## Prompt caching & extended thinking (provider-specific, optional)
Knobs that cut cost/latency or deepen reasoning. Not portable — gate behind a provider check and skip if
your provider lacks them. Pass through `init_chat_model`'s model kwargs / `.bind`:
- **Prompt caching** (Anthropic): mark a stable prefix (system prompt, tool list, big context) with
  `cache_control: {"type": "ephemeral"}`; repeats bill at ~0.1×. Caching is a prefix match — keep volatile
  bytes (timestamps, IDs) *after* the cached span or they invalidate it. Verify via
  `usage.cache_read_input_tokens`.
- **Extended / adaptive thinking** (Anthropic Opus/Sonnet 4.6+, OpenAI reasoning tiers, Gemini thinking):
  enable adaptive thinking (`thinking={"type": "adaptive"}` on current Anthropic models — `budget_tokens`
  is removed there) for harder reasoning. Costs latency + tokens; reserve for capable-tier escalations, not
  the cheap default.

Token usage from each call lands on `resp.usage_metadata` and is captured into the LLM span
(`patterns/react-agent.md` → `patterns/observability-and-evals.md`) — that's where you watch cost.

## Gate (run it, don't trust it)
The loop tests inject a scripted `FakeModel` with **no key** (`patterns/react-agent.md`) — so the graph is
provider-agnostic and runs in CI offline. Separately, one live smoke run with a funded `APP_LLM_API_KEY`
proves `get_model()` + the configured provider actually work end-to-end (the demo gate →
`workflows/gates.md`). Also assert the config rules deterministically (no key needed):
- **Comment strip** — `APP_LLM_MODEL=foo # note` parses to `"foo"`, not `"foo # note"`.
- **Secret hygiene** — `repr(get_settings())` and `str(settings.llm_api_key)` never reveal the key
  (`SecretStr` masks it); the raw value is only reachable via `.get_secret_value()`.
- **Fail loud** — `validate_required_config()` raises with the missing var named when the key is blank.

> **⚠️ Drive these config tests through ENV VARS (`monkeypatch.setenv` or a tmp `.env`), NEVER init kwargs.**
> `Settings(LLM_API_KEY="sk-x # p")` (or `APP_LLM_API_KEY=...`) is the obvious shortcut and it **silently
> fails**: pydantic-settings maps the `APP_`-prefixed env spelling case-insensitively for *env vars only* — it
> does NOT apply that mapping to Python `__init__` kwargs, so `APP_LLM_API_KEY`/`LLM_API_KEY` passed as a kwarg
> is treated as an undeclared extra and **ignored** (`extra="ignore"`). The `SecretStr` field keeps its empty
> default, the `mode="before"` strip validator never sees your value, and the test asserts `"" == "sk-x"` and
> fails on a *correct* `config.py` — a false-RED. Always go through real env vars. `get_settings()` is
> `@lru_cache`d, so `.cache_clear()` after setting env so the new value is read. Canonical DEMO-2 test:
> ```python
> from agent.config import get_settings
>
> def test_env_comment_strip(monkeypatch):
>     monkeypatch.setenv("APP_LLM_MODEL", "claude-haiku-4-5 # prod model")   # env var, NOT a kwarg
>     monkeypatch.setenv("APP_LLM_API_KEY", "sk-test-123 # prod key")
>     get_settings.cache_clear()                                            # drop the cached singleton
>     s = get_settings()
>     assert s.llm_model == "claude-haiku-4-5"                              # inline comment + space stripped
>     assert s.llm_api_key.get_secret_value() == "sk-test-123"             # SecretStr strip ran on the env value
>     assert "sk-test-123" not in repr(s)                                  # secret stays masked
> ```
