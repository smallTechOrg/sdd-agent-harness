"""ONE registry. ONE schema method (schemas_for) for every provider. Dispatch
never raises — it returns the JSON error envelope so the ReAct loop can recover."""
from __future__ import annotations

import json

from tools.base import BaseTool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def schemas_for(self, provider: str) -> list[dict]:
        """Emit the provider-shaped tool list. The ONLY schema method — no
        per-provider aliases. Returns [] when there are no tools."""
        if not self._tools:
            return []
        if provider == "anthropic":
            return [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                for t in self._tools.values()
            ]
        if provider == "gemini":
            # Gemini function declarations live under a single tool entry.
            return [
                {
                    "function_declarations": [
                        {
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.input_schema,
                        }
                        for t in self._tools.values()
                    ]
                }
            ]
        raise ValueError(f"Unknown provider for tool schemas: {provider!r}")

    def dispatch(self, name: str, args: dict) -> str:
        """Run a tool by name. NEVER raises — every failure becomes the JSON
        error envelope {ok:false, code, hint} fed back to the model."""
        tool = self._tools.get(name)
        if tool is None:
            return _envelope("UNKNOWN_TOOL", f"No tool named {name!r}. Available: {self.names()}")
        if tool.requires_confirmation:
            # Least-privilege: refuse by default. Interactive approval is a slot.
            return _envelope(
                "CONFIRMATION_REQUIRED",
                f"Tool {name!r} needs human confirmation, which is not wired in the baseline.",
            )
        try:
            return tool.run(**(args or {}))
        except Exception as exc:  # noqa: BLE001 — tools must never crash the loop
            return _envelope("TOOL_ERROR", f"{name} failed: {exc}")


def _envelope(code: str, hint: str) -> str:
    return json.dumps({"ok": False, "code": code, "hint": hint})


def default_registry() -> ToolRegistry:
    """The registry the agent uses. Builtins are registered here; MCP tools
    (when AGENT_MCP_SERVER_URL is set) are added on top."""
    reg = ToolRegistry()
    from tools.builtins.calculator import CalculatorTool
    reg.register(CalculatorTool())
    # MCP consumption — config-gated; adds remote tools into THIS registry.
    from tools.mcp import register_mcp_tools
    register_mcp_tools(reg)
    return reg
