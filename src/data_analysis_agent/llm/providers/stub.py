import re

from data_analysis_agent.llm.providers.base import LLMProvider
from data_analysis_agent.llm.types import LLMResult


class StubLLMProvider(LLMProvider):
    """Offline stub — returns plausible shaped output without any API call."""

    def complete(self, prompt: str) -> LLMResult:
        if "<node:plan_action>" not in prompt:
            text = "(stub) No response — unrecognized node tag in prompt."
        elif "[1] capability:" in prompt:
            text = (
                "FINAL ANSWER: (stub) Based on the query results, the data analysis is complete. "
                "Set DATAANALYSIS_OPENROUTER_API_KEY to get real AI-powered answers."
            )
        else:
            # Parse the actual table name from the schema section
            match = re.search(r"Table:\s+(\w+)\s+—\s+Columns:", prompt)
            table = match.group(1) if match else "data"
            text = (
                f'{{"capability": "run_query", "parameters": '
                f'{{"query": "SELECT COUNT(*) as total_rows FROM {table}"}}}}'
            )

        return LLMResult(
            text=text,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            estimated_cost_usd=0.0,
        )
