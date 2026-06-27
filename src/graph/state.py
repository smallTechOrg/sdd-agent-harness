from typing import TypedDict


class AgentState(TypedDict, total=False):
    # Identity
    run_id: str                          # set by runner at init (QuestionRow id)

    # Input
    dataset_id: str                      # which local dataset to query
    question: str                        # the user's plain-English question
    messages: list                       # chat-turn history (Phase 4 memory)

    # Pipeline data (populated progressively; NONE of the LLM-bound fields hold raw rows)
    schema_summary: dict                 # set by profile_data (cols/types/scalar aggregates)
    compute_plan: dict                   # set by plan_compute (group_by/metric/aggregation)
    aggregate_result: dict               # set by execute_local (bounded grouped result)

    # Output
    answer_text: str                     # set by phrase_answer
    chart_spec: dict                     # set by phrase_answer ({type, x, series})
    status: str                          # "completed" | "failed"

    # Control
    error: str | None                    # set by any node on fatal failure
