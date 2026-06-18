# Pattern: Retrieval & Knowledge (RAG)

**Canonical home for layer 5 (Retrieval / knowledge)**
([`../agentic-architecture.md`](../agentic-architecture.md)). How the agent grounds answers in a
corpus it can't hold in context.

---

## When to use retrieval (vs. a tool, vs. memory)

- **Retrieval** — the answer lives in a **static-ish corpus** (docs, a knowledge base, past tickets)
  too large for the context window. Pull the relevant slice in.
- **Tool / MCP** — the answer needs a **live action or query** (current weather, a DB row, an API). Use
  [`tools-and-mcp.md`](tools-and-mcp.md).
- **Memory** — the fact is about **this user/session's history**. Use
  [`memory-and-context.md`](memory-and-context.md) (long-term memory is itself vector-backed retrieval
  over `memory_records`).

## The pipeline

```
ingest:  documents → chunk → embed → upsert into vector DB (with metadata)
query:   user text → embed → vector search (top-k)
                            + keyword/BM25 search (hybrid)
                   → rerank (cross-encoder / LLM) → top-n
                   → into context assembly (memory-and-context.md)
```

- **Chunking** — semantic or fixed-size with overlap; store source + offsets in metadata for citations.
  Chunk size is a quality knob — too big dilutes, too small loses context.
- **Embeddings & vector DB** — pick from [`../tech-stack.md`](../tech-stack.md) § Agentic Stack Tech.
  `pgvector` (on the default Postgres) is the standard; `sqlite-vec` for demos; a dedicated vector DB
  when scale needs it.
- **Hybrid search** — combine dense (embeddings) + sparse (keyword/BM25); dense alone misses exact terms
  (names, IDs, error codes).
- **Rerank** — a cross-encoder or LLM reranker over the top-k sharply improves precision before the
  context budget is spent.
- **Cite sources** — carry chunk metadata through so the final answer can reference where it came from.

## Retrieval-as-tool vs. pre-retrieval

- **Pre-retrieval** — retrieve once up front, inject into context. Simple; good when the query is the
  user's question.
- **Retrieval-as-tool** — expose `search(query)` as a tool so the **agent decides** when and what to
  retrieve mid-loop (agentic RAG). Better for multi-hop questions; costs iterations. Default to
  pre-retrieval; escalate to retrieval-as-tool when single-shot retrieval misses.

## Evaluate retrieval quality

Retrieval is the most common silent failure ("right pipeline, wrong chunks"). Keep a small fixed eval
set of `query → expected-source` and assert recall@k in the eval harness
([`observability-and-evals.md`](observability-and-evals.md)) — a run can return 200 with a fluent,
wrong answer because retrieval missed.

## Phasing

**Earns its place** — retrieval is **not** in the Phase 1 baseline. Add it (real embeddings + vector
store + the retrieval eval hook, then hybrid + rerank) when answers depend on a corpus or knowledge
base, recorded in `02-architecture.md` § Agentic stack layers used. Authority:
[`../phases.md`](../phases.md) § Agentic layers by phase.
