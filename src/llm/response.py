from dataclasses import dataclass, field


@dataclass
class ToolCall:
    """A tool the model wants to run. `id` ties the result back to the call
    (Anthropic supplies it; Gemini has none, so we synthesise one)."""
    id: str
    name: str
    args: dict


@dataclass
class LLMResponse:
    text: str
    tokens_in: int
    tokens_out: int
    model: str
    cost_usd: float
    # Populated when the model asks to call tools (ReAct act phase). Empty on a
    # plain text answer — that's the loop's stop condition.
    tool_calls: list[ToolCall] = field(default_factory=list)
