import json
import re
from datetime import datetime, timezone
from pathlib import Path

from data_analysis.graph.state import AnalysisState, ExecutionStep, ExecutionResult
from data_analysis.llm.gemini_client import get_gemini_client
from data_analysis.tools.code_executor import execute_python_code
from data_analysis.config.settings import get_settings


def _emit(state: AnalysisState, event_type: str, data: dict) -> None:
    """Emit an SSE event if the callback is registered."""
    cb = state.get("_sse_emit")
    if cb:
        cb(event_type, data)


def node_profile_data(state: AnalysisState) -> AnalysisState:
    """Load cached profiles from SQLite for each file_id."""
    try:
        from data_analysis.db.session import create_db_session
        from data_analysis.db.models import UploadedFile

        profiles = []
        data_paths = []

        with create_db_session() as session:
            for file_id in state.get("file_ids", []):
                row = session.get(UploadedFile, file_id)
                if row is None:
                    return {
                        **state,
                        "error": f"File {file_id!r} not found",
                        "checkpoint": "profile_data",
                    }
                profiles.append(json.loads(row.profile_json))
                data_paths.append(row.file_path)

        return {
            **state,
            "profiles": profiles,
            "data_paths": data_paths,
            "checkpoint": "profile_data",
        }
    except Exception as e:
        return {**state, "error": str(e), "checkpoint": "profile_data"}


def node_plan_steps(state: AnalysisState) -> AnalysisState:
    """Call LLM to create a pandas analysis plan + code."""
    try:
        client = get_gemini_client()

        # Build prompt context
        profiles_text = json.dumps(state.get("profiles", []), indent=2)
        history = state.get("execution_history", [])
        recent_history = history[-2:] if len(history) > 2 else history

        history_text = ""
        if recent_history:
            history_text = "\n\nPrevious attempts (fix the errors):\n"
            for step in recent_history:
                history_text += (
                    f"Iteration {step['iteration']}:\n"
                    f"Code: {step['code'][:500]}\n"
                    f"Stdout: {step['stdout'][:500]}\n"
                    f"Stderr: {step['stderr'][:500]}\n"
                )

        prompt = (
            f"User question: {state['question']}\n\n"
            f"Data profiles (CSV files available):\n{profiles_text}"
            f"{history_text}\n\n"
            "Write Python code to answer this question. "
            "Remember to use DATA_PATHS[0] (or DATA_PATHS[n]) to load files."
        )

        system = _load_prompt("plan_steps.md")
        text, in_tok, out_tok = client.generate(prompt, system=system)

        # Parse JSON response
        parsed = _parse_json_response(text)

        needs_clarification = parsed.get("needs_clarification", False)
        clarification_question = parsed.get("clarification_question")
        plan = parsed.get("plan", "")
        code = parsed.get("code") or ""

        # Store the generated code in the plan for execute_code to use
        combined_plan = (
            f"{plan}\n\n```python\n{code}\n```" if code else plan
        )

        return {
            **state,
            "plan": combined_plan,
            "_generated_code": code,
            "needs_clarification": needs_clarification,
            "clarification_question": clarification_question,
            "input_tokens": state.get("input_tokens", 0) + in_tok,
            "output_tokens": state.get("output_tokens", 0) + out_tok,
            "checkpoint": "plan_steps",
        }
    except Exception as e:
        return {
            **state,
            "error": f"plan_steps failed: {e}",
            "checkpoint": "plan_steps",
        }


def node_execute_code(state: AnalysisState) -> AnalysisState:
    """Execute the generated code in a sandboxed subprocess."""
    try:
        # Extract code from the stashed _generated_code or parse it from plan
        code = state.get("_generated_code") or ""
        if not code:
            plan = state.get("plan", "")
            if "```python" in plan:
                code = plan.split("```python")[1].split("```")[0].strip()
            else:
                code = plan

        iteration = state.get("iteration", 0)
        query_run_id = state.get("query_run_id", "unknown")
        data_paths = state.get("data_paths", [])

        result = execute_python_code(code, data_paths, query_run_id, iteration)

        step = ExecutionStep(
            iteration=iteration,
            code=code,
            stdout=result["stdout"],
            stderr=result["stderr"],
            success=result["success"],
            elapsed_s=result["elapsed_s"],
        )

        # Emit code_step SSE event
        _emit(
            state,
            "code_step",
            {
                "type": "code_step",
                "iteration": iteration,
                "code": code,
                "stdout": result["stdout"],
                "stderr": result["stderr"],
                "success": result["success"],
            },
        )

        history = list(state.get("execution_history", []))
        history.append(step)

        last_error = result["stderr"] if not result["success"] else None

        return {
            **state,
            "execution_history": history,
            "last_execution_result": result,
            "last_execution_error": last_error,
            "iteration": iteration + 1,
            "_generated_code": None,  # clear stash for next iteration
            "checkpoint": "execute_code",
        }
    except Exception as e:
        return {
            **state,
            "error": f"execute_code failed: {e}",
            "checkpoint": "execute_code",
        }


def node_inspect_result(state: AnalysisState) -> AnalysisState:
    """LLM evaluates whether the execution result is complete and correct."""
    try:
        last_result = state.get("last_execution_result")
        if not last_result or not last_result.get("success", False):
            # Failed execution — always not complete
            updated_result = {
                **(last_result or {}),
                "complete": False,
                "explanation": "Execution failed",
            }
            return {
                **state,
                "last_execution_result": updated_result,
                "checkpoint": "inspect_result",
            }

        client = get_gemini_client()

        prompt = (
            f"Question: {state['question']}\n\n"
            f"Execution stdout: {last_result.get('stdout', '')[:2000]}\n"
            f"Execution stderr: {last_result.get('stderr', '')}\n"
            f"Success: {last_result.get('success', False)}\n\n"
            'Is this result complete and correct? '
            'Return JSON: {"complete": true/false, "explanation": "..."}'
        )

        system = _load_prompt("inspect_result.md")
        text, in_tok, out_tok = client.generate(prompt, system=system)

        parsed = _parse_json_response(text)
        complete = parsed.get("complete", False)
        explanation = parsed.get("explanation", "")

        updated_result = {**last_result, "complete": complete, "explanation": explanation}

        return {
            **state,
            "last_execution_result": updated_result,
            "input_tokens": state.get("input_tokens", 0) + in_tok,
            "output_tokens": state.get("output_tokens", 0) + out_tok,
            "checkpoint": "inspect_result",
        }
    except Exception as e:
        # Conservative: treat as not complete
        last_result = state.get("last_execution_result") or {}
        updated_result = {
            **last_result,
            "complete": False,
            "explanation": f"inspect failed: {e}",
        }
        return {
            **state,
            "last_execution_result": updated_result,
            "checkpoint": "inspect_result",
        }


def node_synthesize_answer(state: AnalysisState) -> AnalysisState:
    """LLM synthesizes a plain-text answer + Plotly chart from execution results."""
    try:
        client = get_gemini_client()
        s = get_settings()

        # Find the best execution result (last successful, or last overall)
        history = state.get("execution_history", [])
        best_result = None
        for step in reversed(history):
            if step.get("success"):
                best_result = step
                break
        if not best_result and history:
            best_result = history[-1]

        stdout_text = best_result.get("stdout", "") if best_result else ""

        # First 2 profiles max to keep context window manageable
        profiles_text = json.dumps(state.get("profiles", [])[:2], indent=2)

        prompt = (
            f"Question: {state['question']}\n\n"
            f"Data profiles:\n{profiles_text}\n\n"
            f"Best execution result (Python stdout):\n{stdout_text[:3000]}\n\n"
            "Write a plain-text answer and create an appropriate Plotly chart."
        )

        system = _load_prompt("synthesize_answer.md")
        text, in_tok, out_tok = client.generate(prompt, system=system)

        parsed = _parse_json_response(text)
        answer_text = parsed.get("answer_text", "Analysis complete.")
        plotly_chart = parsed.get(
            "plotly_chart", {"data": [], "layout": {"title": "Result"}}
        )

        # Calculate cumulative cost
        total_in = state.get("input_tokens", 0) + in_tok
        total_out = state.get("output_tokens", 0) + out_tok
        cost = (total_in / 1000 * s.cost_input_per_1k) + (
            total_out / 1000 * s.cost_output_per_1k
        )

        # Emit SSE events
        _emit(state, "token", {"type": "token", "text": answer_text})
        _emit(state, "chart", {"type": "chart", "plotly": plotly_chart})
        _emit(
            state,
            "cost",
            {
                "type": "cost",
                "input_tokens": total_in,
                "output_tokens": total_out,
                "cost_usd": round(cost, 6),
            },
        )

        return {
            **state,
            "answer_text": answer_text,
            "plotly_chart": plotly_chart,
            "input_tokens": total_in,
            "output_tokens": total_out,
            "cost_usd": cost,
            "checkpoint": "synthesize_answer",
        }
    except Exception as e:
        return {
            **state,
            "error": f"synthesize_answer failed: {e}",
            "checkpoint": "synthesize_answer",
        }


def node_finalize(state: AnalysisState) -> AnalysisState:
    """Write the completed query_run row to SQLite."""
    try:
        from data_analysis.db.session import create_db_session
        from data_analysis.db.models import QueryRun

        with create_db_session() as session:
            run = session.get(QueryRun, state.get("query_run_id"))
            if run:
                run.answer_text = state.get("answer_text")
                run.plotly_chart_json = (
                    json.dumps(state.get("plotly_chart"))
                    if state.get("plotly_chart")
                    else None
                )
                run.code_steps_json = json.dumps(state.get("execution_history", []))
                run.iterations_used = state.get("iteration", 0)
                run.input_tokens = state.get("input_tokens", 0)
                run.output_tokens = state.get("output_tokens", 0)
                run.cost_usd = state.get("cost_usd", 0.0)
                run.status = "completed"
                run.completed_at = datetime.now(timezone.utc)
    except Exception as e:
        # Non-fatal — log and continue
        try:
            import structlog
            structlog.get_logger().warning("finalize_db_write_failed", error=str(e))
        except Exception:
            pass

    _emit(state, "done", {"type": "done"})
    return {**state, "checkpoint": "finalize"}


def node_handle_error(state: AnalysisState) -> AnalysisState:
    """Handle fatal errors: update DB, emit error SSE event."""
    error_msg = state.get("error", "Unknown error")

    try:
        from data_analysis.db.session import create_db_session
        from data_analysis.db.models import QueryRun

        with create_db_session() as session:
            run = session.get(QueryRun, state.get("query_run_id"))
            if run:
                run.status = "failed"
                run.error_message = error_msg
                run.completed_at = datetime.now(timezone.utc)
    except Exception:
        pass

    _emit(state, "error", {"type": "error", "message": error_msg})
    _emit(state, "done", {"type": "done"})
    return {**state, "checkpoint": "handle_error"}


def node_stream_clarification(state: AnalysisState) -> AnalysisState:
    """Stream a clarification question to the user."""
    _emit(
        state,
        "clarification",
        {
            "type": "clarification",
            "question": state.get(
                "clarification_question", "Could you clarify your question?"
            ),
        },
    )
    _emit(state, "done", {"type": "done"})
    return {**state, "checkpoint": "stream_clarification"}


def _load_prompt(filename: str) -> str:
    """Load a prompt from src/data_analysis/prompts/<filename>."""
    prompt_dir = Path(__file__).parent.parent / "prompts"
    path = prompt_dir / filename
    if path.exists():
        return path.read_text()
    return ""


def _parse_json_response(text: str) -> dict:
    """Parse JSON from LLM response, stripping markdown fences if present."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json or ```) and last line (```)
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        text = "\n".join(inner)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find a JSON object in the text
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {}
