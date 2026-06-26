"""Graph-adjacent follow-up suggestions (one LLM call, not a graph node).

Per `spec/agent.md` -> "## Graph-adjacent single LLM calls":
`generate_suggestions(question, answer)` -> up to 3 short follow-up questions
(JSON array; `[]` on any failure). Runs in the runner AFTER the graph and its
estimated tokens are added to the run total. Never raises.

The stub provider returns `[]` for the `<node:suggest>` tag.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from llm.client import LLMClient
from observability.events import get_logger

logger = get_logger("graph.suggestions")

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_SUGGEST_PROMPT_PATH = _PROMPTS_DIR / "suggest.md"

# Node tag the stub provider branches on (must match stub.py EXACTLY).
_SUGGEST_TAG = "<node:suggest>"

_MAX_SUGGESTIONS = 3


def _load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token), matching nodes.py's heuristic."""
    return max(1, len(text or "") // 4)


def _coerce_string_list(raw: str) -> list[str]:
    """Parse a JSON array of strings from the model reply (tolerant)."""
    text = (raw or "").strip()
    if not text:
        return []

    if text.startswith("```"):
        text = text.strip("`")
        text = re.sub(r"^[a-zA-Z]*\n", "", text, count=1).strip()

    def _as_list(value) -> list[str] | None:
        if isinstance(value, list):
            return [str(x).strip() for x in value if str(x).strip()]
        return None

    try:
        result = _as_list(json.loads(text))
        if result is not None:
            return result
    except Exception:
        pass

    match = re.search(r"\[.*?\]", text, re.DOTALL)
    if match:
        try:
            result = _as_list(json.loads(match.group(0)))
            if result is not None:
                return result
        except Exception:
            pass
    return []


def generate_suggestions(question: str, answer: str) -> tuple[list[str], int, int]:
    """Propose up to 3 follow-up questions for the just-answered turn.

    Returns `(suggestions, tokens_input, tokens_output)`:
    - `suggestions`: up to 3 short follow-up strings parsed from a JSON array;
      `[]` on ANY failure (never raises).
    - `tokens_input` / `tokens_output`: estimated token counts (~4 chars/token)
      so the runner can add them to the run total. They are estimated even on
      failure (the prompt was still built / the call was still attempted) so the
      run total stays honest; `0` only when nothing was sent.
    """
    if not (question or "").strip() or not (answer or "").strip():
        return [], 0, 0

    try:
        system = _load_prompt(_SUGGEST_PROMPT_PATH)
        prompt = (
            f"{_SUGGEST_TAG}\n\n"
            f"## Question\n{question}\n\n"
            f"## Answer\n{answer}\n\n"
            "Reply with ONLY a JSON array of up to 3 short follow-up questions."
        )
        tokens_input = _estimate_tokens(prompt) + _estimate_tokens(system)
        raw = LLMClient().call_model(prompt, system=system) or ""
        tokens_output = _estimate_tokens(raw)
    except Exception as exc:  # noqa: BLE001 — never raise; suggestions are optional
        logger.warning("suggestions_failed", error=str(exc))
        return [], 0, 0

    suggestions = _coerce_string_list(raw)[:_MAX_SUGGESTIONS]
    logger.info("suggestions_ok", count=len(suggestions))
    return suggestions, tokens_input, tokens_output
