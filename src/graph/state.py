from typing import TypedDict


class AgentState(TypedDict, total=False):
    """State for the Pandora analysis graph (see spec/agent.md).

    Carries the question + dataset *profile* (schema/metadata only — never raw
    rows) through code generation, sandboxed execution, and summarisation.
    """

    run_id: str                 # question id (persisted `questions` row)
    dataset_id: str
    dataset_path: str           # Parquet path handed to the sandbox
    profile: dict               # DatasetProfile — the ONLY dataset info given to the LLM
    question: str
    messages: list              # Phase 2: prior-turn summaries (role/content); never raw rows

    code: str | None            # latest generated pandas snippet
    exec_result: dict | None    # sandbox result: {result, chart_spec, ...}
    attempts: int               # retry counter (0 → 1 max in Phase 1)
    last_error: str | None      # fed back to code-gen on retry

    answer_text: str | None     # plain-language summary (markdown)
    chart_spec: dict | None     # {type, x, y, series} for recharts
    summary_table: dict | None  # {columns, rows} capped at MAX_RESULT_ROWS

    usage: dict                 # accumulated {prompt_tokens, completion_tokens, cost_usd}
    status: str                 # "completed" | "failed" | "stuck"
    error: str | None           # terminal user-facing error

    # Phase 4 (deferred — present but unused until then):
    plan: list | None           # ordered steps
    step_index: int             # current plan step
    max_steps: int              # bounded loop cap
