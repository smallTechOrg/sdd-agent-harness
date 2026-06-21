# Brief B1 — CSV analytics agent (DuckDB)

> Exercises the `python-fastapi-duckdb` recipe + a UI surface + an LLM step.

## The brief (paste as the opening `/build` message)

"I want a local web app where I can upload a CSV file and then ask questions about it in plain
English — like 'what were total sales by region last quarter' — and get back a table or a short
answer. It should show me the SQL it ran. Keep it local; I'll provide an LLM key."

## Capabilities the running app must demonstrate (quality coverage)

- Upload a CSV; it becomes a queryable dataset within the same session.
- A natural-language question is turned into SQL, executed against DuckDB, and the result
  rendered as an **HTML table** (not raw text).
- The executed SQL is shown to the user.
- Runs fully offline in stub mode (no key) for the test suite; real LLM behind the key.
- Stub mode is banner-labelled in the UI.

## Notes for scoring

- Analytics/columnar → DuckDB recipe is the correct stack choice (wrong recipe = quality miss).
- The renderer (HTML table) must ship in the same step-group as the query data — not deferred.
