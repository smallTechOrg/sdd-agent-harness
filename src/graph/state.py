from typing import TypedDict


class AgentState(TypedDict, total=False):
    """State for one DataChat turn.

    Raw data rows are deliberately NOT a field here. They exist only transiently
    inside ``run_local_aggregation`` as a pandas DataFrame and on disk at
    ``file_path``. ``aggregate_table`` is the only data-derived payload that ever
    reaches an LLM, and it is aggregated + capped (≤ 50 rows).
    """

    # Identity
    run_id: str                          # set by runner (reuses RunRow id)
    conversation_id: str                 # set by runner; groups chat turns

    # Input
    dataset_id: str                      # which uploaded dataset to query
    file_path: str                       # local path to raw file (data/ only reads this)
    schema: dict                         # {columns: [{name, dtype}], row_count} — no rows
    question: str                        # the user's plain-language question
    history: list                        # [{role, content}, ...] recent turns for context

    # Pipeline data (populated progressively)
    plan: dict | None                    # AggregationPlan from plan_aggregation (LLM)
    aggregate_table: list | None         # small result rows from run_local_aggregation (LOCAL)
    aggregate_columns: list | None       # columns present in the aggregate table

    # Output
    answer: str | None                   # plain-language answer (LLM)
    chart: dict | None                   # ChartSpec {type, title, labels, series} or None

    # Control
    error: str | None                    # set by any node on fatal failure
    status: str | None                   # "completed" | "failed"
