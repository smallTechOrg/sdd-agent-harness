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
Settings via pydantic-settings, env prefix `APP_`. The runtime model defaults CHEAP.
```python
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra="ignore")
    llm_provider: str = "anthropic"
    llm_model: str = "claude-haiku-4-5-20251001"   # CHEAP tier — escalate via spec/tech-stack.md
    llm_api_key: str = ""
    database_url: str = "sqlite+aiosqlite:///./agent.db"
    port: int = 8001
    max_iterations: int = 6

@lru_cache
def get_settings() -> Settings:                      # cached Settings singleton — the one config accessor
    return Settings()
```

## Code — `agent/llm.py`
One accessor. Raises clearly if no funded key (a real run requires `APP_LLM_API_KEY` — see `harness.md`).
```python
from langchain.chat_models import init_chat_model
from .config import get_settings

def get_model():
    s = get_settings()
    if not s.llm_api_key:
        raise RuntimeError("APP_LLM_API_KEY is required for a real run (see README / spec/tech-stack.md).")
    return init_chat_model(s.llm_model, model_provider=s.llm_provider, api_key=s.llm_api_key)
```
`init_chat_model` dispatches on `model_provider`; the graph binds tools to whatever it returns
(`patterns/react-agent.md`). The rest of the agent never imports a provider SDK — that's the whole point.

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
`workflows/gates.md`).
