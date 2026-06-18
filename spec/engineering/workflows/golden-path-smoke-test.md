# Golden-Path UI Smoke Test

**Mandatory before Phase 1 passes** for any project with a UI or HTTP surface.

## What it is

An automated test that walks the **full primary user journey** end-to-end through the HTTP/UI layer, asserting not only status codes but also that **rendered content actually looks correct** to a human.

A test that checks `response.status_code == 200` and nothing else is not a smoke test. It lets bugs through where the server returns 200 but shows three empty bullets where an article should be.

## Why it exists

Unit tests on the repository layer prove the DB works. Status-code assertions prove routes are wired up. Neither proves the user-visible result is sensible. The smoke test closes that gap.

Bugs this test catches that other tests miss:
- Real LLM output rendered in the wrong shape (outline bullets shown where an article body belongs)
- API/serialization mismatches (the frontend expects a field the backend never sends)
- Forms/requests that succeed but render an empty list afterward because the query is wrong
- Redirects or navigations that land on a page which then errors

## Required test structure

Pick the single most important user flow (the one from `spec/product/01-vision.md` § Success Criteria). Exercise it end-to-end:

1. **GET** every page on the happy path. Assert each returns 200 and the page contains nav/layout markers proving the template rendered.
2. **POST** each form. Assert 303 and follow the `Location` header.
3. **GET** the final artifact page (e.g. the article detail). Assert:
   - Status 200
   - The user's input is reflected (topic, name, etc.)
   - The **rendered body has real structure** — for article-like content, assert `<p>`, `<h2>`, or paragraph breaks are present. Bare `<ul>` is not enough.
   - The page length passes a sanity threshold (e.g. `len(page) > 600`)
4. **GET** list/index pages to confirm the new artifact appears there.

### For agents with multi-turn sessions (chat, iterative Q&A)

The smoke test **must** exercise at least two follow-up questions on the same session:

5. **POST** a second question to the same session. Assert 200 and a non-empty answer. A single-question golden-path test misses the most common failure mode: session-scoped resources (DataFrames, parsed files, vector indexes) that are released after Q1 and unavailable for Q2.

If the second question returns any error — `SESSION_DATA_LOST`, 410, 500 — the Phase 1 gate has not passed, regardless of whether Q1 succeeds.

### Reasoning trace requirements (agent outputs)

For any agent that returns a `reasoning_trace` or `action_history`, the smoke test must assert:

- Each trace entry has a `description` field containing a **plain-English sentence** (not raw code, SQL, or a Python expression).
- The `description` is not empty and is not identical to the raw `action` expression.

Raw-code reasoning traces are a UX bug. Non-technical users cannot interpret `df.groupby("region")["sales"].sum()` — the agent must narrate what it is doing in plain English alongside any code it generates.

## Python / FastAPI reference

```python
from fastapi.testclient import TestClient

def test_golden_path_ui_flow(db):
    client = TestClient(create_app())
    # 1. home renders
    assert "Voices" in client.get("/").text

    # 2. create parent entity
    r = client.post("/voices", data={...}, follow_redirects=False)
    assert r.status_code == 303

    # 3. form lists the new entity
    form = client.get("/writers/new").text
    assert "V1" in form

    # 4. generate the artifact and follow the redirect
    r = client.post("/articles", data={...}, follow_redirects=False)
    assert r.status_code == 303, r.text
    article_id = r.headers["location"].rsplit("/", 1)[-1]

    # 5. the detail page must render the artifact, not just 200
    page = client.get(f"/articles/{article_id}").text
    assert "<article>" in page
    assert "<p>" in page or "<h2" in page  # paragraph/heading structure
    assert len(page) > 600                  # sanity
```

## Running the live server as part of the smoke

For Phase 1 sign-off the agent must **also** start the server with `uv run python -m <pkg>` and hit `/health` plus at least one page with `curl` to prove the app boots in a real process — not only via `TestClient`. Report the curl exit codes in the session log.

## Browser-level end-to-end (client-rendered UI)

`TestClient` returns the server's HTML **before any JavaScript runs**. If the page renders content client-side — interactive charts (Plotly/D3), an SPA, htmx swaps, streamed/typed-out tokens — the HTML assertion above proves the markup was *sent*, not that the user *sees* anything. A `<div class="plotly-chart" data-spec="…">` that `TestClient` confirms is present can still render blank if the chart script throws.

For any UI with client-side rendering, add a browser-driven E2E test (**Playwright is the default** — it works for both Python and Node). Drive a real browser to the page, wait for the element the client script is supposed to build (e.g. the chart's rendered `svg`), and assert the **post-JavaScript** state: the element exists, has visible content (not blank), and **no console error fired** (subscribe to the browser's console events and fail on any error). Run it against the live server, never `TestClient`.

## Where it lives

- Golden-path (server-side): `tests/integration/test_pipeline.py` (or a dedicated `test_golden_path.py`), runs as part of `uv run pytest`
- Browser E2E (client-side): `tests/e2e/` (`uv run pytest tests/e2e/` or `npx playwright test`)
- Runs against the **real model** — the API key is set (locally from `.env`, in CI from a secret); assert loosely (structure + non-empty) to absorb output variance, never on exact LLM text
