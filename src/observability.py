"""Observability — one span() context manager → Span rows → the /traces viewer.

OTel-GenAI span names: invoke_agent (INTERNAL), chat <model> (LLM), execute_tool.<name> (TOOL).
The mutable yield is the contract: enrich `sp` in the block (tokens, args, result preview) and it lands in
`attributes`. harness/patterns/observability-and-evals.md.
"""
import time
import uuid
from contextlib import asynccontextmanager

from .db import Span, get_sessionmaker


@asynccontextmanager
async def span(run_id: str, name: str, kind: str = "INTERNAL", **attrs):
    start = time.time()
    try:
        yield attrs
    except Exception as exc:                      # record then re-raise — never swallow
        attrs["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        end = time.time()
        async with get_sessionmaker()() as s:
            s.add(Span(
                id=str(uuid.uuid4()), run_id=run_id, name=name, kind=kind,
                attributes=attrs,
                start_ms=int(start * 1000), end_ms=int(end * 1000),
                duration_ms=int((end - start) * 1000),
            ))
            await s.commit()
