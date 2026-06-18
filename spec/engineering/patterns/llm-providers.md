# Pattern: Model Layer — Providers & Routing

**Canonical home for layer 1 (Model)** of the stack
([`../agentic-architecture.md`](../agentic-architecture.md)). Provider selection, model routing, and the
model-call features every agent uses. Model identifiers themselves live in
[`../tech-stack.md`](../tech-stack.md) § Models — not here.

---

## Real-first — no stubs

Every model call is real, from Phase 1. There is **no stub provider, no offline mode, no stub-mode
banner, no `provider=auto` resolution**. The API key is a required secret in every environment,
including CI. This keeps the boilerplate honest: what you test is what ships.

- **Local/dev:** the key lives in a gitignored `.env`; the dev server reloads on `.env` change.
- **CI:** the key is a CI secret. Tests call the real model with **loose assertions** (structure +
  non-empty, not exact strings) so normal output variance doesn't flap the build. → [`../phases.md`](../phases.md).
- **Missing key:** fail loudly at startup ([`code-style.md`](../code-style.md) § Universal Rules), never
  silently degrade to a fake response.

## Provider is chosen at intake

The LLM provider is **not** hardcoded — the `agent-builder` asks for it at intake (Anthropic / OpenAI /
Gemini / OpenRouter / other). The tech-designer records the choice in [`../tech-stack.md`](../tech-stack.md)
§ Models. The default recommendation is Anthropic Claude, but it is a question, not an assumption.

## Use the framework-native client

Construct the model with LangChain's `init_chat_model`, not a bespoke `LLMClient` wrapper — it gives one
provider-agnostic interface, so switching provider is a config change, not a code change.

```python
from langchain.chat_models import init_chat_model

# provider + model come from Settings (env), never hardcoded
llm = init_chat_model(settings.llm_model, model_provider=settings.llm_provider)
```

Nodes call this through a thin module-level accessor (so routing + caching config live in one place),
never importing a provider SDK directly.

## Model layer essentials

- **Model routing** — don't send every call to one model. Route by task difficulty: cheap/fast
  (`claude-haiku-4-5-20251001`) for classification, extraction, routing; the default (`claude-sonnet-4-6`)
  for the main loop; the strong model (`claude-opus-4-8`) for hard reasoning and as the eval judge. Make
  the routing explicit and configurable via env. (Routing across multiple models earns its place — a
  single-model baseline is fine to start; see [`../phases.md`](../phases.md).)
- **Structured outputs** — when a node needs typed data, use the provider's structured-output / tool-use
  mode and parse into a Pydantic model — never regex over free text.
- **Prompt caching** — keep the stable prefix (system prompt + tool descriptions) byte-stable so it
  stays cached across turns; this is what makes resending context every turn affordable (see
  [`memory-and-context.md`](memory-and-context.md) § Window management).
- **Extended thinking** — enable for genuinely hard reasoning steps; it trades latency/tokens for
  quality. Don't enable it blanket — it's per-call, on the hard nodes.
- **Errors** — every model call has error handling, retries with backoff on transient failures, and a
  fatal-vs-recoverable boundary the loop can act on ([`react-agent.md`](react-agent.md)).

## Tolerate dirty `.env` values

`pydantic-settings` does **not** strip inline comments. A `.env` line like
`APP_LLM_PROVIDER=anthropic   # anthropic | openai | gemini` arrives as the literal string
`"anthropic   # anthropic | openai | gemini"`. Strip inline `#` comments and surrounding whitespace
before comparing enum-like env values (`provider`, `model`, …) — do it in the settings layer, never
trust the raw field.
