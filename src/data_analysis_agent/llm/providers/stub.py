import json
import re

from data_analysis_agent.llm.providers.base import LLMProvider
from data_analysis_agent.llm.types import LLMResult


class StubLLMProvider(LLMProvider):
    """Offline stub — returns plausibly shaped output without any API call."""

    def complete(self, prompt: str) -> LLMResult:
        """Return canned output shaped by the node tag embedded in the prompt.

        Args:
            prompt: The prompt whose ``<node:...>`` tag selects the response shape.

        Returns:
            A zero-cost :class:`LLMResult` mimicking a real provider's reply.
        """
        if "<node:describe_tool>" in prompt:
            text = _describe_tool_reply(prompt)
        elif "<node:plan_action>" not in prompt:
            text = "(stub) No response — unrecognized node tag in prompt."
        else:
            text = _plan_action_reply(prompt)
        return LLMResult(text=text, input_tokens=0, output_tokens=0, total_tokens=0, estimated_cost_usd=0.0)


def _describe_tool_reply(prompt: str) -> str:
    """Build a stub JSON description response for the describe_tool prompt."""
    name_match = re.search(r"File name: (.+)", prompt)
    table_match = re.search(r"SQL table name: (\w+)", prompt)
    name = name_match.group(1).strip() if name_match else "dataset"
    table = table_match.group(1) if table_match else "data"
    return json.dumps({
        "tool_description": f"(stub) Dataset '{name}' available for SQL analysis.",
        "capability_description": f"(stub) Execute SQL SELECT queries against the '{table}' table.",
    })


def _plan_action_reply(prompt: str) -> str:
    """Build a stub plan_action response: a count query, then a final answer."""
    if "[1] capability:" in prompt:
        return (
            "FINAL ANSWER: (stub) Based on the query results, the data analysis is complete. "
            "Set DATAANALYSIS_OPENROUTER_API_KEY to get real AI-powered answers."
        )
    match = re.search(r"Table:\s+(\w+)\s+—\s+Columns:", prompt)
    table = match.group(1) if match else "data"
    return f'{{"capability": "run_query", "parameters": {{"query": "SELECT COUNT(*) as total_rows FROM {table}"}}}}'
