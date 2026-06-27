"""LLM-driven MCP capability generation (the 5-stage sync pipeline) + granular mutations.

- Full sync: ``run_sync`` + ``apply_sync_result`` (regenerate all, soft-delete dropped).
- Granular Phase-B mutations: ``add_tool``/``update_tool``/``add_prompt``/``update_prompt``/
  ``add_resource``/``update_resource`` (apply one capability + additive downstream cascade).
"""
from data_analysis_agent.tools.sync.pipeline import (
    PartialResult,
    SyncResult,
    ValidationError,
    active_entity_tables,
    add_prompt,
    add_resource,
    add_tool,
    apply_sync_result,
    delete_prompt,
    delete_resource,
    delete_tool,
    run_sync,
    update_prompt,
    update_resource,
    update_tool,
)

__all__ = [
    "SyncResult", "PartialResult", "ValidationError",
    "run_sync", "apply_sync_result", "active_entity_tables",
    "add_tool", "update_tool", "delete_tool",
    "add_prompt", "update_prompt", "delete_prompt",
    "add_resource", "update_resource", "delete_resource",
]
