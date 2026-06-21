# Working with LLMs

Patterns for integrating LLMs into an agent pipeline. Stack-specific gotchas live in
`spec/engineering/code-style.md`; these apply regardless of language or framework.

---

## Provider selection — `provider=auto`

Resolve to the real provider when the API key env var is set, otherwise fall back to the
stub. Setting the key is the only step the user needs — never require a separate config
flag. Add a `resolved_llm_provider` property on your settings object that encapsulates
this logic.

## Model names go stale

A 404 / NOT_FOUND from the LLM API almost always means the model name is wrong or
deprecated.

- Model name must be configurable via env var (e.g. `APPNAME_LLM_MODEL`).
- Verify via the provider's `ListModels` or docs before hardcoding.
- Treat any hardcoded model name as a maintenance liability — flag it when encountered.
- Current safe defaults (2026): Google → `gemini-2.5-flash` · OpenAI → `gpt-4o-mini` · Anthropic → `claude-3-5-haiku-latest`

## Stub design

The skeleton phase must run fully offline — no real API key, no network. Stubs stand in
for all LLM calls.

- **Branch on explicit node tags, not prose.** Each pipeline node injects a unique tag
  (`<node:plan>`, `<node:draft>`, `<node:title>`, …); the stub matches the tag. Matching
  on prose keywords cross-contaminates nodes.
- **Stub outputs must be believable.** Draft-class outputs should be article-shaped
  (paragraphs/headings), not bare bullet lists. Offline demos must look real.
- **Show a visible stub-mode banner.** Every UI surface must display a clear indicator
  when the resolved provider is `stub`. Silent stubs are a bug — the user must always
  know whether they are seeing real or synthetic output.

## Prompts are data, not code

Prompts and templates are data files (e.g. `.md`) loaded at runtime — never inlined as
strings in code. This makes them reviewable, diffable, and editable without a deploy.

## LLM behind a thin client

Never call the provider SDK directly from business logic or pipeline nodes. Wrap it in a
thin client abstraction. This makes the stub swap trivial and keeps nodes pure:
`(state) → state`.

## Error handling

When an LLM pipeline node fails (4xx/5xx, invalid response, timeout), propagate via the
pipeline state's `error` field — do not raise an exception that crashes the pipeline.
Render a graceful error state; log the failure. Every route that calls the pipeline must
handle the `error` field.

## Strip dirty env values

Inline `#` comments and trailing whitespace in `.env` files silently corrupt enum-like
values (provider names, modes). Strip in a `resolved_*` property — never trust the raw
field.
