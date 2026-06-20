# Pattern: Retrieval / RAG (Layer 5)

Ground answers in a corpus the model doesn't know. **Generate fresh at build time**, pinning the *current*
embeddings client + vector lib (a guessed/old version 404s — verify latest before pinning).

## When it earns its place
ON only when **answers depend on a corpus** the runtime LLM can't hold or be trusted to recall: docs,
tickets, a knowledge base, the user's uploaded files. If the task is self-contained reasoning or the
context fits the prompt, **skip it** — retrieval adds an index, drift, and a failure mode. Toggle in
`spec/agent.md`; the corpus + freshness expectations live in `spec/product.md` (domain).

Retrieval surfaces as **one tool** the ReAct loop calls — `search_docs` in the proven `agent/tools.py`
(→ `patterns/tools-and-mcp.md`). This file makes that tool real instead of a stub.

## The pipeline (five moving parts)
1. **Chunk** — split source docs into ~512-token windows with ~15% overlap; keep `source`/`title` metadata.
2. **Embed** — one model for ingest *and* query (same dims, same model — mismatched vectors are silently wrong).
3. **Store** — vectors + text + metadata in a vector store (ladder below).
4. **Hybrid retrieve** — BM25 (keyword/exact) **+** vector (semantic), fused by Reciprocal Rank Fusion.
   Hybrid beats either alone — vectors miss IDs/error-codes/rare nouns; BM25 misses paraphrase.
5. **Rerank** — a cross-encoder or LLM judge re-scores the top ~20 → keep top ~5. Cheap, big precision win.

## Store ladder (local-first → prod, mirrors the DB ladder)
| Stage | Store | Why |
|-------|-------|-----|
| Local / demo | **sqlite-vec** (`vec0` virtual table in the same SQLite file) | Zero infra, one file, matches local-first. |
| Prod | **pgvector** (asyncpg, on the Postgres you already deploy) | One database; HNSW index; `<=>` cosine distance. |
| Scale | **Qdrant / Weaviate** (dedicated) | Filtered search, sharding, hot reindex — earns its place at corpus scale. |

Move up only when the lower rung hurts. Same chunk/embed/rerank code each rung — only the store swaps.

## Code — `agent/retrieval.py` (sqlite-vec, local-first)
Proven-shaped; pin current `sqlite-vec`, `langchain` (or your embeddings SDK), `rank-bm25`.
```python
import json, sqlite_vec
from langchain.embeddings import init_embeddings   # one model, ingest == query
from rank_bm25 import BM25Okapi
from .config import get_settings
from .observability import span                     # patterns/observability-and-evals.md

_EMB = init_embeddings("openai:text-embedding-3-small")   # set in spec/tech-stack.md; verify model id
DIM = 1536

def _db():
    import sqlite3
    con = sqlite3.connect(get_settings().database_url.rsplit("///", 1)[-1])
    con.enable_load_extension(True); sqlite_vec.load(con); con.enable_load_extension(False)
    con.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(embedding float[{DIM}])")
    con.execute("CREATE TABLE IF NOT EXISTS chunks(id INTEGER PRIMARY KEY, text TEXT, meta TEXT)")
    return con

def chunk(text, size=512, overlap=80):
    words, out, i = text.split(), [], 0
    while i < len(words):
        out.append(" ".join(words[i:i + size])); i += size - overlap
    return out

async def ingest(docs):                              # docs: list[{"text","source","title"}]
    con = _db()
    for d in docs:
        for piece in chunk(d["text"]):
            vec = (await _EMB.aembed_query(piece))
            cur = con.execute("INSERT INTO chunks(text, meta) VALUES (?,?)",
                              (piece, json.dumps({"source": d["source"], "title": d.get("title")})))
            con.execute("INSERT INTO vec_chunks(rowid, embedding) VALUES (?,?)",
                        (cur.lastrowid, sqlite_vec.serialize_float32(vec)))
    con.commit(); con.close()

def _rrf(rankings, k=60):                             # Reciprocal Rank Fusion of multiple id-rankings
    scores = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking):
            scores[cid] = scores.get(cid, 0) + 1 / (k + rank)
    return sorted(scores, key=scores.get, reverse=True)

async def retrieve(query, k=5, pool=20):
    con = _db()
    rows = con.execute("SELECT id, text, meta FROM chunks").fetchall()
    if not rows:
        con.close(); return []
    ids, texts, metas = zip(*rows)
    # vector arm
    qv = sqlite_vec.serialize_float32(await _EMB.aembed_query(query))
    vec_ids = [r[0] for r in con.execute(
        "SELECT rowid FROM vec_chunks WHERE embedding MATCH ? ORDER BY distance LIMIT ?", (qv, pool))]
    # keyword arm
    bm25 = BM25Okapi([t.lower().split() for t in texts])
    order = sorted(range(len(texts)), key=lambda i: bm25.get_scores(query.lower().split())[i], reverse=True)
    bm25_ids = [ids[i] for i in order[:pool]]
    con.close()
    fused = _rrf([vec_ids, bm25_ids])[:pool]
    by_id = {ids[i]: {"text": texts[i], "meta": json.loads(metas[i])} for i in range(len(ids))}
    return [by_id[c] for c in fused if c in by_id][:k]   # rerank() refines this top-pool → top-k
```

## Rerank (precision pass — keep it, it's cheap)
Re-score the fused pool against the query, keep the best `k`. A cross-encoder is fastest/cheapest; an LLM
judge needs no extra model. Use the **cheap runtime model** (→ `patterns/model-and-providers.md`), never a frontier one.
```python
async def rerank(query, candidates, model, k=5):     # model = get_model() from agent/llm.py
    if len(candidates) <= k:
        return candidates
    listing = "\n".join(f"[{i}] {c['text'][:300]}" for i, c in enumerate(candidates))
    prompt = (f"Query: {query}\nReturn the {k} most relevant passage numbers as a JSON list, best first.\n{listing}")
    picks = json.loads((await model.ainvoke(prompt)).content)   # tolerate junk in prod
    return [candidates[i] for i in picks if 0 <= i < len(candidates)][:k]
```

## Wire it to the agent's tool (the only integration point)
`search_docs` becomes a thin call into `retrieve` (+ optional `rerank`), wrapped in a span like every tool
(→ `patterns/react-agent.md`, `tools-and-mcp.md`). **Always return the `source` with each passage** so the
agent can cite — uncited corpus answers are unverifiable.
```python
from langchain_core.tools import tool
from .retrieval import retrieve, rerank
from .llm import get_model

@tool
async def search_docs(query: str) -> str:
    """Search the indexed corpus for passages relevant to the query."""
    hits = await rerank(query, await retrieve(query, k=8), get_model(), k=4)
    return "\n\n".join(f"[{h['meta']['source']}] {h['text']}" for h in hits) or "no relevant passages"
```
Ingest runs **out of band** (a `scripts/ingest.py` / CLI, not per-request) so the index is warm before a run.

## Gate (prove retrieval works, mechanically → `workflows/gates.md`)
Retrieval makes the **outcome eval honest**: a question whose answer lives *only* in the corpus must pass
**with** the index and **fail** with it empty — that proves the answer came from retrieval, not the LLM's
memory. Add a unit gate too (no LLM key needed):
- `ingest` a tiny fixed corpus; `retrieve("<exact rare term>")` returns the chunk holding it (BM25 arm) **and**
  a paraphrase query returns it too (vector arm) — proving hybrid, not one arm.
- Embeddings are deterministic per model → assert the top hit by `source`, not by float scores.
EARS criteria in `spec/capabilities/*.md` ("WHEN asked about X the system SHALL cite the source doc") drive
the trajectory eval — assert `search_docs` was actually called (the span exists), not just that text matched.
