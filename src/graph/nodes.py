"""Graph nodes for the Pandora analysis agent (see spec/agent.md).

Pattern #22 (LLM-generated code execution): Gemini writes pandas against the
dataset *profile* (schema/metadata only — NEVER raw rows); the sandbox runs it
on the full data; only the small computed result is summarised back.

Privacy boundary (cardinal): ``generate_code`` and ``summarise`` assemble their
prompts EXCLUSIVELY from the profile dict + question (+ the small exec_result
for summarise). The DataFrame / parquet contents / raw rows are never in scope
at the LLM call site.
"""

import json
import re
from pathlib import Path

from graph.state import AgentState
from llm.client import LLMClient

_PROMPTS = Path(__file__).parent.parent / "prompts"


# ---------------------------------------------------------------------------
# LLM helper — decoupled from the cost-accounting slice's exact return shape.
# ---------------------------------------------------------------------------
def _call_llm(prompt: str, *, system: str | None = None) -> tuple[str, dict | None]:
    """Call the model and normalise the return to ``(text, usage_dict | None)``.

    Tolerates THREE possible shapes from ``LLMClient.call_model`` so this slice
    stays decoupled while the cost-accounting slice upgrades the client:
      * a plain ``str``                         -> (str, None)
      * a ``(text, usage)`` tuple/list          -> (text, _as_usage(usage))
      * an object with ``.text`` / ``.usage``   -> (obj.text, _as_usage(obj.usage))
    """
    raw = LLMClient().call_model(prompt, system=system)

    if isinstance(raw, str):
        return raw, None

    if isinstance(raw, (tuple, list)) and len(raw) >= 2:
        return str(raw[0] or ""), _as_usage(raw[1])

    text = getattr(raw, "text", None)
    if text is not None:
        return str(text), _as_usage(getattr(raw, "usage", None))

    # Unknown shape — coerce to text, no usage.
    return str(raw), None


def _as_usage(usage) -> dict | None:
    """Normalise a usage object/dict to {prompt_tokens, completion_tokens, cost_usd}."""
    if usage is None:
        return None
    if isinstance(usage, dict):
        src = usage
        get = src.get
    else:
        src = usage
        get = lambda k, d=0: getattr(src, k, d)  # noqa: E731

    def _num(*keys):
        for k in keys:
            v = get(k, None)
            if v is not None:
                return v
        return 0

    return {
        "prompt_tokens": int(_num("prompt_tokens", "prompt_token_count", "input_tokens") or 0),
        "completion_tokens": int(
            _num("completion_tokens", "candidates_token_count", "output_tokens") or 0
        ),
        "cost_usd": float(_num("cost_usd", "cost") or 0.0),
    }


def _accumulate_usage(state: AgentState, usage: dict | None) -> dict:
    """Sum a call's usage into the running total; tolerate None."""
    total = dict(state.get("usage") or {"prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0})
    total.setdefault("prompt_tokens", 0)
    total.setdefault("completion_tokens", 0)
    total.setdefault("cost_usd", 0.0)
    if usage:
        total["prompt_tokens"] += int(usage.get("prompt_tokens", 0) or 0)
        total["completion_tokens"] += int(usage.get("completion_tokens", 0) or 0)
        total["cost_usd"] += float(usage.get("cost_usd", 0.0) or 0.0)
    return total


def _load_prompt(name: str) -> str:
    return (_PROMPTS / name).read_text(encoding="utf-8")


_FENCE_RE = re.compile(r"^\s*```(?:python|json)?\s*\n?|\n?```\s*$", re.IGNORECASE)


def _strip_fences(text: str) -> str:
    """Remove a leading/trailing markdown code fence the model may have added."""
    t = (text or "").strip()
    if t.startswith("```"):
        # drop first fence line
        t = re.sub(r"^```[a-zA-Z0-9]*\s*\n?", "", t)
    if t.endswith("```"):
        t = re.sub(r"\n?```\s*$", "", t)
    return t.strip()


def _extract_json_block(text: str) -> dict | None:
    """Pull the LAST ```json ...``` block (or a trailing bare object) from text."""
    if not text:
        return None
    blocks = re.findall(r"```(?:json)?\s*\n?(\{.*?\})\s*```", text, re.DOTALL)
    candidate = blocks[-1] if blocks else None
    if candidate is None:
        # fall back to the last balanced-looking object
        m = re.search(r"(\{.*\})\s*$", text.strip(), re.DOTALL)
        candidate = m.group(1) if m else None
    if not candidate:
        return None
    try:
        return json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None


def _markdown_before_json(text: str) -> str:
    """The answer markdown is everything before the trailing JSON block."""
    if not text:
        return ""
    split = re.split(r"```(?:json)?\s*\n?\{.*", text, maxsplit=1, flags=re.DOTALL)
    return split[0].strip() or text.strip()


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------
def generate_code(state: AgentState) -> AgentState:
    """Ask Gemini for a pandas snippet against the profile (schema only)."""
    try:
        profile = state.get("profile") or {}
        is_retry = bool(state.get("last_error"))
        attempts = state.get("attempts", 0) + (1 if is_retry else 0)
        retry_block = ""
        if is_retry:
            retry_block = (
                "\n## Previous attempt failed — FIX IT\n"
                "Your previous code:\n"
                f"```\n{state.get('code', '')}\n```\n"
                f"It failed with this error:\n{state['last_error']}\n"
                "Return corrected code that avoids that error. Output ONLY the code."
            )

        prompt = (
            _load_prompt("generate_code.md")
            .replace("{profile}", json.dumps(profile, indent=2, default=str))
            .replace("{question}", state.get("question", ""))
            .replace("{retry_block}", retry_block)
        )

        text, usage = _call_llm(prompt)
        code = _strip_fences(text)

        return {
            **state,
            "code": code,
            "attempts": attempts,
            "last_error": None,                       # cleared; validate/execute may re-set
            "usage": _accumulate_usage(state, usage),
        }
    except Exception as exc:  # API/transport error -> terminal
        return {**state, "error": f"Code generation failed: {exc}", "code": state.get("code")}


def validate_code(state: AgentState) -> AgentState:
    """Static guard via the sandbox's validate_code; set last_error on reject."""
    from sandbox.executor import validate_code as _validate

    code = state.get("code") or ""
    err = _validate(code)
    if err:
        return {**state, "last_error": err}
    return {**state, "last_error": None}


def execute_code(state: AgentState) -> AgentState:
    """Run the validated snippet in the sandbox subprocess on the full data."""
    from sandbox.executor import run_code

    result = run_code(state.get("code") or "", state.get("dataset_path") or "")

    if result.get("ok"):
        return {**state, "exec_result": result, "last_error": None}

    kind = result.get("kind", "runtime_error")
    err = result.get("error") or f"Execution failed ({kind})."
    return {**state, "last_error": f"[{kind}] {err}", "exec_result": result}


def summarise(state: AgentState) -> AgentState:
    """Turn the SMALL exec_result + question into a plain-language answer."""
    try:
        exec_result = state.get("exec_result") or {}
        result_payload = exec_result.get("result")
        code_chart = exec_result.get("chart_spec")

        prompt = (
            _load_prompt("summarise.md")
            .replace("{question}", state.get("question", ""))
            .replace("{result}", json.dumps(result_payload, indent=2, default=str)[:8000])
            .replace("{chart_spec}", json.dumps(code_chart, default=str))
        )

        text, usage = _call_llm(prompt)

        answer_text = _markdown_before_json(text)
        parsed = _extract_json_block(text) or {}

        summary_table = parsed.get("summary_table") or _result_to_table(result_payload)
        chart_spec = parsed.get("chart_spec")
        if chart_spec is None:
            chart_spec = code_chart  # fall back to the code's suggestion

        return {
            **state,
            "answer_text": answer_text or "Here is the result of the analysis.",
            "summary_table": summary_table,
            "chart_spec": chart_spec,
            "usage": _accumulate_usage(state, usage),
        }
    except Exception as exc:
        # Summarise failure: return the raw result + a generic note, don't crash.
        exec_result = state.get("exec_result") or {}
        return {
            **state,
            "answer_text": (
                "The analysis ran, but the plain-language summary could not be "
                f"generated ({exc}). The computed result is shown below."
            ),
            "summary_table": _result_to_table(exec_result.get("result")),
            "chart_spec": exec_result.get("chart_spec"),
        }


def handle_error(state: AgentState) -> AgentState:
    """Terminal: build a human 'here's what I tried' message; status=stuck."""
    last_error = state.get("error") or state.get("last_error") or "Unknown error."
    code = state.get("code")
    parts = ["I couldn't answer this one. Here's what I tried:", "", f"Error: {last_error}"]
    if code:
        parts += ["", "Last code attempted:", code]
    return {
        **state,
        "status": "stuck",
        "error": "\n".join(parts),
    }


def finalize(state: AgentState) -> AgentState:
    return {**state, "status": "completed"}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _result_to_table(result) -> dict | None:
    """Best-effort {columns, rows} from the sandbox result payload.

    The sandbox serialises ``result`` as one of:
      * {"type": "table",  "columns": [...], "rows": [[...]], ...}
      * {"type": "scalar", "value": <x>}
    Also tolerates a raw scalar / dict / list-of-records (defensive).
    """
    if result is None:
        return None
    if isinstance(result, dict):
        if result.get("type") == "table" and "columns" in result and "rows" in result:
            return {"columns": result["columns"], "rows": result["rows"]}
        if result.get("type") == "scalar":
            return {"columns": ["result"], "rows": [[result.get("value")]]}
        if "columns" in result and "rows" in result:
            return {"columns": result["columns"], "rows": result["rows"]}
        return {"columns": ["key", "value"], "rows": [[k, v] for k, v in result.items()]}
    if isinstance(result, list) and result and isinstance(result[0], dict):
        columns = list(result[0].keys())
        rows = [[r.get(c) for c in columns] for r in result]
        return {"columns": columns, "rows": rows}
    return {"columns": ["result"], "rows": [[result]]}
