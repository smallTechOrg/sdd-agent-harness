"""Primary-journey gate (harness/patterns/interface.md) — asserts the POST-JS DOM, not raw HTML.

Prereqs (the e2e runner brings these up): the agent server on :8001, a seeded dataset, and `next dev` on
:3000. The UI auto-selects the latest dataset, so the journey is: type a question → Run → a real grounded
answer appears → a trace deep-link is present. Run with: pytest tests/e2e -p playwright (browsers installed).
"""
from playwright.sync_api import expect


def test_user_gets_a_grounded_answer(page):
    page.goto("http://localhost:3001")
    page.get_by_role("textbox", name="goal").fill("Which category has the highest total sales?")
    page.get_by_role("button", name="Run").click()
    answer = page.get_by_test_id("answer")
    expect(answer).not_to_be_empty(timeout=60_000)            # post-JS DOM, after the real run completes
    expect(answer).to_contain_text("Electronics", timeout=60_000)
    expect(page.get_by_role("link", name="trace")).to_be_visible()
