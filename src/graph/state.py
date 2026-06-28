"""The DataChat agent state — the typed dict that flows through the plan-execute
graph (see ``spec/agent.md`` -> "Agent State").

Identity + input fields are set by the runner before the graph is invoked; the
pipeline fields are populated progressively by the nodes. The FULL dataframe is
deliberately NOT a field here — it is loaded from ``file_path`` inside
``node_execute_local`` only, so the data never serializes into a prompt.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    # --- Identity (set at init by the runner) -------------------------------
    message_id: str          # the messages row id (known up front, so it can be streamed)
    dataset_id: str          # the active dataset

    # --- Input (set at init by the runner) ----------------------------------
    question: str            # the user's question
    profile: dict            # schema/dtypes/ranges/missing/sample rows (local, bounded)
    file_path: str           # on-disk path of the full dataset (loaded only in execute_local)
    messages: list           # trimmed prior turns [{role, content}, ...]

    # --- Pipeline data (populated progressively by nodes) -------------------
    plan: str | None             # set by node_plan
    generated_code: str | None   # set by node_generate_code (and on retry)
    result_table: list | dict | None  # set by node_execute_local
    key_numbers: dict | None     # set by node_execute_local
    exec_error: str | None       # set by node_execute_local on exec failure (drives self-correction)
    retry_count: int             # init 0; incremented before a self-correction retry

    # --- Output -------------------------------------------------------------
    answer: str | None           # set by node_synthesize (streamed)

    # --- Observability ------------------------------------------------------
    prompt_tokens: int           # accumulated across LLM nodes
    completion_tokens: int       # accumulated across LLM nodes
    cost_usd: float              # computed from token totals + price env vars

    # --- Control ------------------------------------------------------------
    error: str | None            # set by any node on fatal failure -> handle_error
    status: str | None           # "completed" | "failed" — set by finalize/handle_error

    # --- Private streaming sink (NOT part of any prompt) ---------------------
    # The runner injects an ``emit`` callback so node_synthesize can push token
    # deltas (and step status) to the SSE response as they stream from Gemini.
    # It is intentionally never read into build_llm_context and never persisted.
    _emit: Callable[[str, dict[str, Any]], None] | None

    # The bounded LLM context string assembled by node_profile_context via the
    # build_llm_context chokepoint. Internal plumbing — never persisted.
    _context: str
