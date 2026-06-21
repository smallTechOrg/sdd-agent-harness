# Brief B2 — relational task agent (SQLite)

> Exercises the `python-fastapi-sqlite` recipe + an agent loop with a tool + persistence.

## The brief (paste as the opening `/build` message)

"Build me a little task tracker I can talk to. I want to say things like 'add a task to call the
bank tomorrow' or 'what's on my list?' and have an agent create, list, and complete tasks that
persist between sessions. A simple web page is fine. Local only; I'll give you an LLM key."

## Capabilities the running app must demonstrate (quality coverage)

- Create / list / complete tasks via natural language, through an agent loop with tools.
- Tasks persist across restarts (SQLite, the shipped store).
- A session id ties a conversation to its tasks.
- Runs fully offline in stub mode for tests; real LLM behind the key.
- Stub mode is banner-labelled in the UI.

## Notes for scoring

- Relational/transactional → SQLite recipe is the correct stack choice.
- The tool-calling agent loop must be eval-covered (behaviour, not just plumbing).
- Frontend (the page) is a parallel step built with its backend, not bolted on at the end.
