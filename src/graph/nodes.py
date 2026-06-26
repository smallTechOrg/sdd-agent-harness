import time
from pathlib import Path

import guardrails
import memory
from config.settings import get_settings
from graph.state import AgentState, NodeTrace
from llm.client import LLMClient
from llm.router import get_router
from observability.events import get_logger
from tools.registry import default_registry

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_log = get_logger("nodes")


def _load_prompt(filename: str = "transform.md") -> str:
    return (_PROMPTS_DIR / filename).read_text(encoding="utf-8").strip()


def _enter(state: AgentState, node: str) -> float:
    _log.info("node.start", run_id=state.get("run_id"), node=node)
    return time.monotonic()


def _exit(state: AgentState, node: str, t0: float) -> list[NodeTrace]:
    duration_ms = round((time.monotonic() - t0) * 1000, 2)
    _log.info("node.end", run_id=state.get("run_id"), node=node, duration_ms=duration_ms)
    trace = list(state.get("node_trace") or [])
    trace.append(NodeTrace(node=node, duration_ms=duration_ms))
    return trace


def transform_text(state: AgentState) -> AgentState:
    t0 = _enter(state, "transform_text")
    try:
        prompt_template = _load_prompt()
        # Route the capability work through the "tools" task. Blank route →
        # provider default (byte-identical to before); set AGENT_MODEL_TOOLS to
        # route this call to a specific tier. The react node (Phase 2) is where
        # routing earns its keep; here it proves the wiring end to end.
        response = LLMClient().call_model(
            f"{prompt_template}\n\nInput: {state['input_text']}",
            model=get_router().route("tools"),
        )
        _log.info(
            "llm.call",
            run_id=state.get("run_id"),
            model=response.model,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            cost_usd=response.cost_usd,
        )
        return {
            **state,
            "output_text": response.text,
            "tokens_in": (state.get("tokens_in") or 0) + response.tokens_in,
            "tokens_out": (state.get("tokens_out") or 0) + response.tokens_out,
            "cost_usd": (state.get("cost_usd") or 0.0) + response.cost_usd,
            "model": response.model,
            "node_trace": _exit(state, "transform_text", t0),
        }
    except Exception as exc:
        _log.error("node.error", run_id=state.get("run_id"), node="transform_text", error=str(exc))
        return {**state, "error": str(exc), "node_trace": _exit(state, "transform_text", t0)}


def _accumulate(state: AgentState, response) -> dict:
    """Fold an LLMResponse's usage into the cumulative observability counters."""
    _log.info(
        "llm.call", run_id=state.get("run_id"), model=response.model,
        tokens_in=response.tokens_in, tokens_out=response.tokens_out,
        cost_usd=response.cost_usd,
    )
    return {
        "tokens_in": (state.get("tokens_in") or 0) + response.tokens_in,
        "tokens_out": (state.get("tokens_out") or 0) + response.tokens_out,
        "cost_usd": (state.get("cost_usd") or 0.0) + response.cost_usd,
        "model": response.model,
    }


# --- Guard + memory seam nodes ----------------------------------------------

def guard_input(state: AgentState) -> AgentState:
    t0 = _enter(state, "guard_input")
    code, msg = guardrails.check_input(state.get("input_text", ""))
    patch = {"node_trace": _exit(state, "guard_input", t0)}
    if code:
        _log.warning("guard.input", run_id=state.get("run_id"), guard_code=code)
        patch.update(error=msg, guard_code=code)
    return {**state, **patch}


def load_memory(state: AgentState) -> AgentState:
    t0 = _enter(state, "load_memory")
    ctx = memory.load_session(state.get("conversation_id", ""))
    return {**state, "memory_context": ctx, "node_trace": _exit(state, "load_memory", t0)}


def react(state: AgentState) -> AgentState:
    """The agentic spine: think → act → observe, one model turn per visit.
    Self-loops (via after_react) while the model calls tools and the budget
    holds. transform_text remains the bare 0-tool slot; this is the active node.
    """
    t0 = _enter(state, "react")
    try:
        client = LLMClient()
        registry = default_registry()
        provider = client.provider_name

        # Seed the message history on the first visit.
        messages = list(state.get("messages") or [])
        if not messages:
            user_text = state["input_text"]
            ctx = state.get("memory_context") or ""
            content = f"{ctx}\n\n{user_text}" if ctx else user_text
            messages = [_user_turn(provider, content)]

        system = _load_prompt("react.md")
        response = client.call_model(
            "", system=system, model=get_router().route("tools"),
            tools=registry.schemas_for(provider), messages=messages,
        )
        patch = _accumulate(state, response)
        patch["iterations"] = state.get("iterations", 0) + 1
        patch["output_text"] = response.text
        messages.append(client.assistant_turn(response))

        if response.tool_calls:
            # ACT + OBSERVE: run each tool, append results, loop.
            results = [(tc.id, registry.dispatch(tc.name, tc.args)) for tc in response.tool_calls]
            names = [tc.name for tc in response.tool_calls]
            messages.append(client.tool_results_turn(results, names=names))
            # Budget meter blocks only when we'd otherwise loop again.
            code, msg = guardrails.budget_exceeded({**state, **patch})
            if code:
                _log.warning("guard.budget", run_id=state.get("run_id"), guard_code=code)
                patch.update(error=msg, guard_code=code)
        patch["messages"] = messages
        patch["node_trace"] = _exit(state, "react", t0)
        return {**state, **patch}
    except Exception as exc:
        _log.error("node.error", run_id=state.get("run_id"), node="react", error=str(exc))
        return {**state, "error": str(exc), "node_trace": _exit(state, "react", t0)}


def guard_output(state: AgentState) -> AgentState:
    t0 = _enter(state, "guard_output")
    code, msg = guardrails.check_output(state.get("output_text", "") or "")
    patch = {"node_trace": _exit(state, "guard_output", t0)}
    if code:
        _log.warning("guard.output", run_id=state.get("run_id"), guard_code=code)
        patch.update(error=msg, guard_code=code)
    return {**state, **patch}


def write_memory(state: AgentState) -> AgentState:
    t0 = _enter(state, "write_memory")
    cid = state.get("conversation_id", "")
    if cid:
        memory.append_turn(cid, "user", state.get("input_text", ""))
        memory.append_turn(cid, "assistant", state.get("output_text", "") or "")
    return {**state, "node_trace": _exit(state, "write_memory", t0)}


def _user_turn(provider: str, content: str) -> dict:
    if provider == "gemini":
        return {"role": "user", "parts": [{"text": content}]}
    return {"role": "user", "content": content}


def handle_error(state: AgentState) -> AgentState:
    t0 = _enter(state, "handle_error")
    _log.error("run.failed", run_id=state.get("run_id"),
               error=state.get("error"), guard_code=state.get("guard_code"))
    return {**state, "status": "failed", "node_trace": _exit(state, "handle_error", t0)}


def finalize(state: AgentState) -> AgentState:
    t0 = _enter(state, "finalize")
    _log.info(
        "run.complete",
        run_id=state.get("run_id"),
        tokens_in=state.get("tokens_in", 0),
        tokens_out=state.get("tokens_out", 0),
        cost_usd=state.get("cost_usd", 0.0),
        model=state.get("model"),
    )
    return {**state, "status": "completed", "node_trace": _exit(state, "finalize", t0)}
