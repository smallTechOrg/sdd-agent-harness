# Brief B3 — document Q&A chat (richer UI)

> Exercises a chat/markdown UI (`frontend-nextjs`) + retrieval over user files + an LLM step.

## The brief (paste as the opening `/build` message)

"I'd like a chat app where I drop in a few text or markdown documents and then ask questions and
get answers grounded in them, with the answer citing which document it came from. A proper chat
interface with markdown rendering, please. Local; I'll provide an LLM key."

## Capabilities the running app must demonstrate (quality coverage)

- Ingest a few user documents; ask a question; get a grounded answer that **cites** its source.
- Chat UI renders markdown (not raw text); conversation history is visible.
- Retrieval is real (the answer is grounded in the ingested docs, checked by an eval).
- Runs fully offline in stub mode for tests; real LLM behind the key.
- Stub mode is banner-labelled in the UI.

## Notes for scoring

- Richer UI → `frontend-nextjs` recipe alongside a backend recipe; built as parallel steps.
- Grounding/citation is the behaviour the eval gate must verify — a fluent but ungrounded
  answer is a quality fail, not a pass.
