import json
import re

from data_analysis_agent.llm.providers.base import LLMProvider
from data_analysis_agent.llm.types import LLMResult


class StubLLMProvider(LLMProvider):
    """Offline stub — returns plausibly shaped output without any API call.

    Branches on the ``<node:...>`` tag in the prompt (never on prose keywords). Each sync stage
    echoes identifiers parsed from its prompt so the cascade is self-consistent, and the generated
    tool SQL is a valid zero-parameter SELECT so ``tools/call`` and the agent both work offline.
    """

    def complete(self, prompt: str) -> LLMResult:
        text = _dispatch(prompt)
        return LLMResult(text=text, input_tokens=0, output_tokens=0, total_tokens=0, estimated_cost_usd=0.0)


def _dispatch(prompt: str) -> str:
    if "<node:plan_action>" in prompt:
        return _plan_action_reply(prompt)
    if "<node:sync_title>" in prompt:
        return _sync_title(prompt)
    if "<node:sync_schema>" in prompt:
        return _sync_schema(prompt)
    if "<node:sync_entities>" in prompt:
        return _sync_entities(prompt)
    if "<node:sync_tools>" in prompt:
        return _sync_tools(prompt)
    if "<node:sync_prompts>" in prompt:
        return _sync_prompts(prompt)
    return "(stub) No response — unrecognized node tag in prompt."


def _dataset_name(prompt: str) -> str:
    m = re.search(r"Dataset name:\s+(.+)", prompt)
    return m.group(1).strip() if m else "dataset"


def _tables(prompt: str) -> list[str]:
    """Table names from a ``Table: <name>`` block (sync stages)."""
    return re.findall(r"Table:\s+(\w+)", prompt)


def _plan_action_reply(prompt: str) -> str:
    """Single-level plan reply: a count query on the first server/table, then a final answer."""
    if "[1] tool:" in prompt:
        return (
            "FINAL ANSWER: (stub) Based on the query results, the data analysis is complete. "
            "Set DATAANALYSIS_OPENROUTER_API_KEY to get real AI-powered answers."
        )
    server_match = re.search(r"Tool:\s+(.+)", prompt)
    server = server_match.group(1).strip() if server_match else "data"
    table_match = re.search(r"^    (\w+)\(", prompt, re.MULTILINE)
    table = table_match.group(1) if table_match else "data"
    query = f"SELECT COUNT(*) as total_rows FROM {table}"
    return json.dumps({"tool": server, "arguments": {"query": query}})


def _sync_title(prompt: str) -> str:
    name = _dataset_name(prompt)
    return json.dumps({
        "title": f"(stub) {name}",
        "description": f"(stub) MCP server for dataset '{name}'.",
    })


def _sync_schema(prompt: str) -> str:
    # Canonical FK-edge list; the offline stub infers no relationships (per-table columns live elsewhere).
    return json.dumps({"relationships": []})


def _sync_entities(prompt: str) -> str:
    name = _dataset_name(prompt)
    m = re.search(r"Schema tables:\s+(.+)", prompt)
    tables = [t.strip() for t in m.group(1).split(",")] if m and m.group(1).strip() != "(none)" else []
    entities = [
        {
            "name": t,
            "title": f"(stub) {t}",
            "description": f"(stub) The '{t}' entity.",
            "kind": "primary_entity",
            "uri": f"entity://{name}/{t}",
            "mime_type": "application/json",
        }
        for t in tables
    ]
    return json.dumps({"entities": entities})


def _sync_tools(prompt: str) -> str:
    m = re.search(r"Tables available:\s+(.+)", prompt)
    tables = [t.strip() for t in m.group(1).split(",")] if m and m.group(1).strip() != "(none)" else []
    tools = [
        {
            "name": f"list_{t}",
            "title": f"(stub) List {t}",
            "description": f"(stub) Return rows from '{t}'.",
            "execution": {"sql_template": f"SELECT * FROM {t} LIMIT 100", "parameters": []},
        }
        for t in tables
    ]
    return json.dumps({"tools": tools})


def _sync_prompts(prompt: str) -> str:
    tools = re.findall(r"Tool:\s+(\w+)", prompt)
    prompts = [
        {
            "name": f"explore_{t}",
            "title": f"(stub) Explore {t}",
            "description": f"(stub) Use the '{t}' tool.",
            "arguments": [],
            "template": [{"role": "user", "content": f"Use the '{t}' tool."}],
        }
        for t in tools
    ]
    return json.dumps({"prompts": prompts})
