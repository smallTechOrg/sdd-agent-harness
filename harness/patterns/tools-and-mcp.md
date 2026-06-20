# Pattern: Tools & MCP (Layer 4)

How the agent acts on the world. **Generate this fresh at build time**, pinning the *current*
`langchain-core`, `langchain-mcp-adapters`, and `mcp` (check the latest first — a guessed/old version
404s). The internal-tool code below is proven working; use it verbatim.

## The 3-layer tool model — pick the cheapest that works
| Layer | What | When |
|-------|------|------|
| **1. In-process `@tool` / CLI** | A plain typed Python function in the agent's process. | Default. Internal logic, DB/retrieval, anything you own. No network, no auth, fastest. |
| **2. MCP** | A separate process/server speaking the Model Context Protocol (stdio or streamable-http). | **External integrations only** — a third-party or cross-process capability (GitHub, Slack, a vendor API, another team's service) you don't want to vendor into this codebase. |
| **3. Skills** | A packaged, reusable bundle (prompt + tools + assets) the agent loads on demand. | A whole capability you'll reuse across agents. Earns its place later — see `spec/agent.md`. |

Rule of thumb: **own it and it's in-process → `@tool`. Cross a process/trust boundary → MCP.** Don't
reach for MCP to call your own function; the overhead (serialization, a second process, auth) is pure cost.

**A static-key third-party HTTP API (web search, a vendor REST API) stays IN-PROCESS — it is NOT an MCP
case.** MCP requires OAuth 2.1 and forbids static secrets (§ MCP security below), but most external HTTP APIs
authenticate with a long-lived API key. So a web-search / vendor-REST call is an **async in-process `@tool`**
that reads its key from an `APP_`-prefixed `SecretStr` in `config.py` (e.g. `APP_SEARCH_API_KEY`) — the key
lives in `Settings`, the tool body sends it in the request header, and the **model never sees it** (it gets
the tool name only). MCP (Layer 2) is reserved for **OAuth-protected SaaS** integrations, not "any external
API." Such a tool does network I/O, so it MUST be `async def` and dispatched via `ainvoke` (see below).

```python
# agent/tools.py — a static-key external API as an async in-process @tool (web search shown).
import httpx
from langchain_core.tools import tool
from .config import get_settings

@tool
async def web_search(query: str) -> str:
    """Search the web and return the top results as text the model can cite."""
    s = get_settings()
    key = s.search_api_key.get_secret_value()        # APP_SEARCH_API_KEY: SecretStr, unwrapped only here
    try:
        async with httpx.AsyncClient(timeout=20) as c:   # async I/O → this tool is awaited via ainvoke
            r = await c.get("https://api.example-search.com/v1/search",
                            params={"q": query}, headers={"Authorization": f"Bearer {key}"})
            r.raise_for_status()
        return "\n\n".join(f"[{h['url']}] {h['snippet']}" for h in r.json()["results"][:5]) or "no results"
    except Exception as exc:                          # fail soft — hand the model an error, don't crash the run
        return f"search failed: {type(exc).__name__}: {exc}"
```

## Layer 1 — internal tools, `agent/tools.py` (proven, verbatim)
```python
from langchain_core.tools import tool

CORPUS = {
    "refund": "Refunds are processed within 5 business days to the original payment method.",
    "shipping": "Standard shipping takes 3–5 days; express is next-day before 2pm cutoff.",
}

@tool
def search_docs(query: str) -> str:
    """Search the internal knowledge corpus for a passage relevant to the query."""
    q = query.lower()
    hits = [v for k, v in CORPUS.items() if k in q or any(w in v.lower() for w in q.split())]
    return "\n".join(hits) if hits else "No relevant passage found."

@tool
def write_todos(todos: list[str]) -> str:
    """Record a short ordered plan (the Deep-Agent planning scratchpad). Call before multi-step work."""
    return "Plan recorded:\n" + "\n".join(f"{i+1}. {t}" for i, t in enumerate(todos))

@tool
def finish(answer: str) -> str:
    """Return the final answer to the user and end the run. Call exactly once when done."""
    return answer

TOOLS = [search_docs, write_todos, finish]
TOOL_MAP = {t.name: t for t in TOOLS}
FINISH = "finish"
```
The loop binds `TOOLS`, runs `TOOL_MAP[name]` per call, and treats `FINISH` as termination —
`patterns/react-agent.md`. Tool spans are emitted there too — `patterns/observability-and-evals.md`.

**Writing a good `@tool`:** a typed signature (LangChain derives the schema from annotations), a one-line
docstring the model reads as the description, return a string (or JSON string) the model can reason over,
and **fail soft** — return an error message, don't raise; an unhandled exception kills the run while a
returned `"error: rate limited, retry later"` lets the model recover.

**Any I/O tool MUST be `async def` and is dispatched via `ainvoke`.** A tool that does network/DB/file I/O
(web search, an HTTP API call, a DB query, retrieval) must be an `async def @tool`. The loop's `tools_node`
(`patterns/react-agent.md`) branches on `tool.coroutine` and `await tool.ainvoke(...)` for async tools —
calling the sync `.invoke` on an async `StructuredTool` raises `NotImplementedError: StructuredTool does not
support sync invocation`, which graceful-degradation then swallows as a tool failure *every* iteration, so
the agent never gets results and force-finalizes an empty/wrong answer. Keep pure-compute tools (no I/O)
sync — they run via `.invoke`. `finish` and `write_todos` are sync; `search_docs` over a real index/API is
async (`patterns/retrieval.md`).

## Layer 2 — MCP for external integrations
Use MCP when the capability lives in another process or is owned by someone else. Two transports:
**stdio** (you spawn a local subprocess — a vendor's MCP server binary) and **streamable-http** (a remote
MCP endpoint over HTTP). Load MCP tools as LangChain tools and merge them into `TOOLS` — the ReAct loop is
unchanged.

```python
# agent/mcp_tools.py — pin current langchain-mcp-adapters + mcp before generating.
from langchain_mcp_adapters.client import MultiServerMCPClient
from .config import get_settings

async def load_mcp_tools():
    """Return external tools as LangChain tools, or [] if none are configured."""
    s = get_settings()
    servers = {}
    if s.github_mcp_url:                      # remote, OAuth-protected (no static secret)
        servers["github"] = {
            "transport": "streamable_http",
            "url": s.github_mcp_url,
            "headers": {"Authorization": f"Bearer {await mint_oauth_token('github')}"},
        }
    if s.local_mcp_cmd:                       # local vendor binary over stdio
        servers["local"] = {"transport": "stdio", "command": s.local_mcp_cmd, "args": s.local_mcp_args}
    if not servers:
        return []
    return await MultiServerMCPClient(servers).get_tools()
```
Merge once at startup so `TOOL_MAP` and `bind_tools` see everything:
```python
# in agent/runner.py setup, before build_graph(model)
TOOLS.extend(await load_mcp_tools())
TOOL_MAP.update({t.name: t for t in TOOLS})
```
If `load_mcp_tools()` returns `[]`, the agent runs on internal tools only — MCP is additive, never required
for the demo gate.

## MCP security (non-negotiable for external servers)
MCP crosses a trust boundary, so treat every MCP tool like an outbound API call you don't fully control.
- **OAuth 2.1, no static secrets.** Remote MCP servers authenticate via OAuth 2.1 — short-lived bearer
  tokens minted per session (`mint_oauth_token` above), never a long-lived key pasted into `headers` or
  committed to `.env`. Tokens are audience-bound to the specific MCP resource. Use PKCE for the auth-code
  flow; for service-to-service use the client-credentials flow against your IdP. **If the integration only
  offers a static API key (most third-party HTTP APIs — web search, vendor REST), it is NOT an MCP case: make
  it an async in-process `@tool` with an `APP_`-prefixed `SecretStr` key (Layer 1, above).** MCP is for OAuth
  SaaS, not "anything external."
- **Pin the server identity.** Only connect to MCP URLs/binaries on an allowlist in `spec/tech-stack.md`.
  A streamable-http URL must be HTTPS. Don't let the model choose servers.
- **Audit via OTel — MCP has no standard audit log.** The protocol doesn't define one, so the harness's
  own spans *are* the audit trail: every external tool call is already wrapped in
  `execute_tool.<name>` (`patterns/observability-and-evals.md`) with args and a result preview, persisted
  to the `spans` table and visible at `/traces`. That record — who/what/when, persisted — is your audit.
- **Least privilege.** Request the narrowest OAuth scopes the capability needs; prefer read-only scopes
  unless a write is in the EARS criteria for the capability.

**Tool output must contain everything the model needs for follow-up calls.** If a tool creates or
looks up a record whose internal identifier differs from its user-visible name, include both in the
output. The model reads tool results verbatim and uses them in the next call — a mismatch between
what it sees and what the backend expects is a silent query failure, not an error it can recover from.

## The action-safety boundary
Tools are where an agent stops talking and starts *doing*. Classify every tool and gate the dangerous ones:
- **Read-only** (search, fetch, query) → run freely.
- **Mutating / irreversible / external side-effect** (send email, charge a card, delete, post) → gate it.
  Either keep it idempotent + reversible, or put a human in the loop before it fires —
  `patterns/guardrails-and-hitl.md`. Never let a force-finalize or a runaway loop trigger an unguarded
  irreversible action.
- **No raw secrets to the model.** The model gets a tool *name*, never the API key or token behind it.
  Credentials live in `Settings` / the OAuth exchange; the tool body uses them, the model never sees them.

## Gate (prove it — run it, don't trust it)
Drive the loop with a scripted fake model (no key) that calls a tool then `finish`; assert the tool ran,
its `execute_tool.<name>` span was recorded, and a mutating tool isn't reachable without its gate. MCP
loading is covered by a unit test that stubs `MultiServerMCPClient` so the suite needs no live server.
→ `patterns/react-agent.md` (FakeModel), `workflows/gates.md`.
