"""AgentState — the working memory carried through the ReAct loop (07-agent-graph.md)."""

from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    # Identity
    run_id: str
    conversation_id: str
    dataset_id: str

    # Context (assembled by node_assemble_context)
    schema_summary: str
    sample_rows: str
    recent_turns: list[dict[str, Any]]
    question: str

    # Pipeline data
    result_table: dict[str, Any] | None
    chart: dict[str, Any] | None
    final_answer: str | None

    # Control
    error: str | None
    early_exit_reason: str | None

    # ReAct loop
    action_history: list[dict[str, Any]]
    iteration_count: int
    last_tool_call: dict[str, Any]

    # Usage accounting (persisted on the run record)
    tokens_input: int
    tokens_output: int
    estimated_cost_usd: float | None
