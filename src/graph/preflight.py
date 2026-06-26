"""Pre-flight one-shot LLM calls run BEFORE the ReAct graph.

Per `spec/agent.md` -> "## Pre-flight (before the graph — two one-shot
`LLMClient` calls)". Both run in `runner.run_agent` only when the datasets are
NOT explicit (the `/ask` selector path); explicit `dataset_ids` skip pre-flight.

- `check_clarification` (C26): ambiguous question -> a single clarifying
  question (the run short-circuits, no graph). Otherwise `proceed` -> `None`.
- `select_datasets` (C19): the minimal subset of dataset ids to load, with a
  fall-back to ALL candidates on any parse/empty failure.

Both go through `LLMClient.call_model` (never a provider SDK). Both are
FAIL-OPEN: an LLM error never blocks the user — clarification returns `None`
(proceed) and the selector falls back to all candidates.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from llm.client import LLMClient
from observability.events import get_logger

logger = get_logger("graph.preflight")

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_CLARIFY_PROMPT_PATH = _PROMPTS_DIR / "clarify.md"
_SELECT_PROMPT_PATH = _PROMPTS_DIR / "select.md"

# Node tags the stub provider branches on (must match stub.py EXACTLY).
_CLARIFY_TAG = "<node:clarify>"
_SELECT_TAG = "<node:select>"


def _load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def check_clarification(question: str, schemas: str) -> str | None:
    """C26: pre-flight clarification check.

    Returns `None` to PROCEED (question is answerable as-is), or a single
    clarifying question string when the model judges the question ambiguous.

    Fail-open: any LLM error returns `None` (never block the user). The model is
    told to reply `proceed` or one question; we treat a reply that starts with /
    contains "proceed" as proceed, otherwise the trimmed reply is the question.
    """
    try:
        system = _load_prompt(_CLARIFY_PROMPT_PATH)
        prompt = (
            f"{_CLARIFY_TAG}\n\n"
            f"## Question\n{question}\n\n"
            f"## Available datasets\n{schemas}\n\n"
            "Reply with exactly `proceed` if answerable, otherwise ONE short "
            "clarifying question."
        )
        reply = (LLMClient().call_model(prompt, system=system) or "").strip()
    except Exception as exc:  # noqa: BLE001 — fail-open, never block the user
        logger.warning("clarification_failed_proceeding", error=str(exc))
        return None

    if not reply:
        return None

    normalized = reply.lower().lstrip("`\"' ")
    if normalized.startswith("proceed") or "proceed" in normalized[:16]:
        return None

    # Strip wrapping quotes/backticks the model may add around the question.
    return reply.strip().strip("`").strip('"').strip()


def _coerce_id_list(raw: str) -> list[str]:
    """Parse a JSON array of dataset ids from the model reply (tolerant).

    Handles a bare JSON array, a fenced array, or an array embedded in prose.
    Returns `[]` when nothing parseable is found.
    """
    text = (raw or "").strip()
    if not text:
        return []

    # Strip code fences if present.
    if text.startswith("```"):
        text = text.strip("`")
        # drop an optional leading language tag line
        text = re.sub(r"^[a-zA-Z]*\n", "", text, count=1).strip()

    # Try a direct JSON parse first.
    candidates: list[str] = []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            candidates = [str(x).strip() for x in parsed if str(x).strip()]
            return candidates
    except Exception:
        pass

    # Fall back to the first bracketed array found anywhere in the text.
    match = re.search(r"\[.*?\]", text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except Exception:
            pass
    return []


def select_datasets(
    question: str,
    all_schemas: list[dict],
    candidate_ids: list[str],
) -> tuple[list[str], str]:
    """C19: choose the minimal subset of dataset ids needed for the question.

    `all_schemas` is a list of dicts, each at least `{"id", "filename",
    "columns"}`. The user prompt embeds each as an `id: <id>` line (so the stub's
    id regex finds the first id) plus filename/columns.

    Returns `(selected_ids, reasoning)`:
    - Parse the model's JSON array, intersect with `candidate_ids` (drop
      hallucinated ids, preserve candidate order).
    - On empty / parse failure / LLM error, FALL BACK to ALL `candidate_ids`.
    `reasoning` is a short note persisted as `selector_reasoning`.
    """
    candidate_set = set(candidate_ids)

    schema_block = _format_schema_block(all_schemas)
    try:
        system = _load_prompt(_SELECT_PROMPT_PATH)
        prompt = (
            f"{_SELECT_TAG}\n\n"
            f"## Question\n{question}\n\n"
            f"## Available datasets\n{schema_block}\n\n"
            "Reply with ONLY a JSON array of the dataset ids needed."
        )
        raw = LLMClient().call_model(prompt, system=system) or ""
    except Exception as exc:  # noqa: BLE001 — fail-open: load everything
        logger.warning("selector_failed_using_all", error=str(exc))
        return list(candidate_ids), "Selector unavailable; loaded all candidate datasets."

    parsed_ids = _coerce_id_list(raw)
    # Intersect with candidates, preserving candidate order; drop hallucinations.
    selected = [cid for cid in candidate_ids if cid in set(parsed_ids) & candidate_set]

    if not selected:
        logger.info("selector_empty_using_all", parsed=parsed_ids)
        return list(candidate_ids), (
            "Selector returned no usable ids; loaded all candidate datasets. "
            f"Raw reply: {raw.strip()[:200]}"
        )

    reasoning = (raw or "").strip()[:500] or f"Selected {len(selected)} dataset(s)."
    logger.info("selector_ok", selected=len(selected), candidates=len(candidate_ids))
    return selected, reasoning


def _format_schema_block(all_schemas: list[dict]) -> str:
    """Render the candidate datasets so the model (and the stub regex) can read ids.

    Each dataset becomes:
        id: <id>
        filename: <filename>
        columns: <c1, c2, ...>
    """
    blocks: list[str] = []
    for schema in all_schemas:
        dataset_id = str(schema.get("id", "")).strip()
        filename = str(schema.get("filename", "") or "").strip()
        columns = schema.get("columns") or []
        if isinstance(columns, (list, tuple)):
            cols_text = ", ".join(str(c) for c in columns)
        else:
            cols_text = str(columns)
        notes = str(schema.get("notes", "") or "").strip()
        lines = [f"id: {dataset_id}", f"filename: {filename}", f"columns: {cols_text}"]
        if notes:
            lines.append(f"notes: {notes}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
