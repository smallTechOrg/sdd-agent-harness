# Golden-Path UI Smoke Test

**Mandatory before Phase 2 passes** for any project with a UI or HTTP surface.

## What it is

An automated test that walks the **full primary user journey** end-to-end through the HTTP/UI layer, asserting not only status codes but also that **rendered content actually looks correct** to a human.

A test that checks `response.status_code == 200` and nothing else is not a smoke test. It lets bugs through where the server returns 200 but shows three empty bullets where an article should be.

## Why it exists

Unit tests on the repository layer prove the DB works. Status-code assertions prove routes are wired up. Neither proves the user-visible result is sensible. The smoke test closes that gap.

Bugs this test catches that other tests miss:
- Stub LLM output that looks nothing like the real thing (outline bullets rendered as an article body)
- Template engine signature changes (e.g. Starlette 1.0 `TemplateResponse(request, name, ctx)` vs. the older `TemplateResponse(name, {...})`)
- Forms that POST successfully but render an empty list afterward because the query is wrong
- Redirects that go to a page which then 500s

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

For Phase 2 sign-off the agent must **also** start the server with `uv run python -m <pkg>` and hit `/health` plus at least one page with `curl` to prove the app boots in a real process — not only via `TestClient`. Report the curl exit codes in the session log.

## Browser-level end-to-end (client-rendered UI)

`TestClient` returns the server's HTML **before any JavaScript runs**. If the page renders content client-side — interactive charts (Plotly/D3), an SPA, htmx swaps, streamed/typed-out tokens — the HTML assertion above proves the markup was *sent*, not that the user *sees* anything. A `<div class="plotly-chart" data-spec="…">` that `TestClient` confirms is present can still render blank if the chart script throws.

For any UI with client-side rendering, add a browser-driven E2E test. **Playwright is the default** (works for both Python and Node):

```python
from playwright.sync_api import sync_playwright

def test_chart_renders_in_browser(live_server):  # live_server = real running app, not TestClient
    with sync_playwright() as p:
        page = p.chromium.launch().new_page()
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(f"{live_server}/ask?q=sales+by+region")
        page.wait_for_selector(".plotly-chart .plotly")   # JS actually painted the chart
        assert page.locator(".plotly svg").count() > 0     # rendered, not blank
        assert not errors, f"console errors: {errors}"
```

Assert the **post-JavaScript** state: the element the script was supposed to build exists, has visible content, and **no console error fired**. Run it against the live server, never `TestClient`.

## Where it lives

- Golden-path (server-side): `tests/integration/test_pipeline.py` (or a dedicated `test_golden_path.py`), runs as part of `uv run pytest`
- Browser E2E (client-side): `tests/e2e/` (`uv run pytest tests/e2e/` or `npx playwright test`)
- No LLM API key required — uses the stub provider
