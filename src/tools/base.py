"""The ONE Tool type. Local tools, builtins, and MCP-sourced tools are all
BaseTool subclasses registered in the same ToolRegistry — there is no second
tool abstraction anywhere in the codebase."""
from __future__ import annotations

from abc import ABC, abstractmethod


class BaseTool(ABC):
    name: str
    description: str
    input_schema: dict          # JSON Schema for the tool's arguments
    requires_confirmation: bool = False   # least-privilege flag (guardrails reads this)

    @abstractmethod
    def run(self, **kwargs) -> str:
        """Execute the tool and return a string result. Raising is fine — the
        registry's dispatch() catches it into the JSON error envelope."""
        raise NotImplementedError
