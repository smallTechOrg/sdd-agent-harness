"""MCP consumption (USB-C for tools) — LABELLED SLOT. The wiring is real
(settings URL → BaseTool in the registry, server_param() emits the connector
shape); the network hop is a stub. Swap MCPTool.run / list_tools to go live.
"""
from __future__ import annotations

from config.settings import get_settings
from tools.base import BaseTool
from tools.registry import ToolRegistry


class MCPTool(BaseTool):
    def __init__(self, name, description, input_schema):
        self.name, self.description, self.input_schema = name, description, input_schema

    def run(self, **kwargs) -> str:  # STUB — replace with a real MCP call
        return f"[mcp stub] {self.name} called with {kwargs}"


def server_param() -> dict | None:
    """Connector shape for a provider's mcp_servers= field, or None if unset."""
    s = get_settings()
    if not s.mcp_server_url:
        return None
    p = {"type": "url", "url": s.mcp_server_url, "name": s.mcp_server_name or "mcp"}
    if s.mcp_auth_token:
        p["authorization_token"] = s.mcp_auth_token
    return p


def list_tools() -> list[BaseTool]:
    """Discover remote tools as BaseTool instances. STUB: one echo tool."""
    if not get_settings().mcp_server_url:
        return []
    return [MCPTool("mcp_echo", "Echo text via the configured MCP server (stub).",
                    {"type": "object", "properties": {"text": {"type": "string"}},
                     "required": ["text"]})]


def register_mcp_tools(registry: ToolRegistry) -> None:
    for tool in list_tools():
        registry.register(tool)
