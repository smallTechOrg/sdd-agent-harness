# Pattern: Tools & MCP

**Canonical home for layer 4 (Tools / integration)**
([`../agentic-architecture.md`](../agentic-architecture.md)). How the agent acts on the world: the tool
registry and **MCP** (Model Context Protocol) as the integration standard.

---

## Two kinds of "action"

1. **Code-generating actions** (a pandas/SQL/shell expression the LLM writes) run through the
   **AST safe-executor** — defined once in [`react-agent.md`](react-agent.md) § Action-safety boundary.
   Don't restate it; link.
2. **Tool calls** (a named capability with a typed signature) run through the tool registry below.

Most agents use tools; data-analysis-style agents also use code-generating actions. Both are untrusted
model output and both pass a safety boundary before executing.

## Tool registry

A tool is a **pure, typed function** registered by name:

```python
# tools/<tool>.py  — (inputs) → domain model, no class instantiation
@tool("get_weather", "Current weather for a city.")
def get_weather(city: str) -> WeatherReport: ...
```

- **Typed I/O** — Pydantic in, domain model out. The schema is what the LLM sees; write descriptions for
  the model, not for humans.
- **Only in-scope tools** are put in the prompt each turn (see [`memory-and-context.md`](memory-and-context.md)
  § Context assembly) — a 40-tool dump wastes context and degrades selection.
- **Errors are values, not exceptions** — a tool returns a structured error the loop can observe and
  retry on (`react-agent.md` § Self-correction), never a crash.

## MCP (Model Context Protocol) — the integration standard, everywhere

**Every tool is an MCP tool — internal capabilities as well as external integrations.** Both your own
in-process capabilities and third-party systems (GitHub, Slack, a database, a SaaS API) are exposed as
**MCP servers**, not hand-rolled SDK calls scattered through nodes. Why MCP everywhere: one wire
protocol for the whole tool surface, uniform tool discovery, the same server works across LangGraph /
Claude Agent SDK / other clients, and a single clean trust boundary regardless of where the tool runs.

- **Client side:** the agent connects to MCP servers at startup and registers their tools into the same
  registry. Code lives in `src/<package>/mcp/`.
- **Transports:** `stdio` for local/in-process servers (including your own internal tools), `http`
  (streamable) for remote ones.
- **Servers:** wrap a capability once as an MCP server (in `mcp/servers/` or a separate package) and
  reuse it — internal tools are local `stdio` servers, external ones wrap the integration. Prefer an
  existing official MCP server over writing your own.
- **Auth & secrets:** MCP server credentials follow [`../secret-hygiene.md`](../secret-hygiene.md) —
  never in code, never logged.

## Action-safety for tools

Treat every model-chosen tool call as untrusted input:

- **Validate arguments** against the tool's typed schema before executing — reject extra/mistyped args.
- **Least privilege** — a tool exposes the narrowest capability that does the job (read-only where
  possible; scope tokens per server).
- **Irreversible / high-stakes actions** (send, delete, pay, deploy) route through human-in-the-loop
  approval — see [`guardrails-and-hitl.md`](guardrails-and-hitl.md).

## Phasing

Baseline — tool registry + ≥1 **real MCP tool** behind the action-safety boundary at Phase 1; more
integrations / external MCP servers earn their place. Authority: [`../phases.md`](../phases.md) §
Agentic layers by phase.
