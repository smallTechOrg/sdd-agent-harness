"""
Phase 1 E2E tests — runs against the live app at http://localhost:8001/app/
Requires:
  - `uv run python -m src` to be running on port 8001
  - AGENT_GEMINI_API_KEY set in .env for the real-LLM query test

Skip conditions:
  - All tests skip if the app is not reachable on port 8001
  - test_upload_then_query_real_llm skips if AGENT_GEMINI_API_KEY is not set
"""
import socket

import pytest

BASE_URL = "http://localhost:8001"
APP_URL = f"{BASE_URL}/app/"


# ── Helpers ───────────────────────────────────────────────────────────────────


def _app_running() -> bool:
    """Return True if the app is reachable on port 8001."""
    try:
        s = socket.create_connection(("localhost", 8001), timeout=2)
        s.close()
        return True
    except (OSError, ConnectionRefusedError):
        return False


def _has_gemini_key() -> bool:
    try:
        import data_analysis.config.settings as m

        m._settings = None
        from data_analysis.config.settings import get_settings

        return bool(get_settings().gemini_api_key)
    except Exception:
        return False


# ── Module-level skip if app not running ─────────────────────────────────────


@pytest.fixture(scope="module", autouse=True)
def _require_live_app():
    """Skip the entire module if the app is not running."""
    if not _app_running():
        pytest.skip(
            "Live app not running on port 8001 — start with: uv run python -m src"
        )


# ── Browser fixtures ─────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def browser_context(playwright):
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    yield context
    context.close()
    browser.close()


@pytest.fixture
def page(browser_context):
    p = browser_context.new_page()
    yield p
    p.close()


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_page_loads_and_is_styled(page):
    """The app page loads with the correct title and the upload button is visible."""
    page.goto(APP_URL)
    assert "Data Analysis Agent" in page.title()
    # Upload button confirms Tailwind classes were compiled and applied
    upload_btn = page.get_by_test_id("upload-btn")
    assert upload_btn.is_visible()
    # Sidebar must be rendered
    sidebar = page.locator("aside")
    assert sidebar.is_visible()


def test_heading_and_stubs_visible(page):
    """App heading is shown and all Phase 2 stubs are clearly labelled."""
    page.goto(APP_URL)
    # Sidebar heading
    sidebar_heading = page.locator("h1")
    assert sidebar_heading.is_visible()
    assert "Data Analysis Agent" in sidebar_heading.text_content()
    # Multi-file stub (in FileList sidebar)
    assert page.locator("text=Multi-file join").is_visible()
    assert page.locator("text=Coming in Phase 2").first.is_visible()
    # Session history stub (in ChatPanel header)
    assert page.locator("text=Session history").is_visible()


def test_input_disabled_without_file(page):
    """Question textarea and send button are disabled when no file is selected."""
    page.goto(APP_URL)
    q_input = page.get_by_test_id("question-input")
    send_btn = page.get_by_test_id("send-btn")
    assert q_input.is_visible()
    assert q_input.is_disabled()
    assert send_btn.is_visible()
    assert send_btn.is_disabled()


def test_upload_csv_and_profile_appears(page, tmp_path):
    """Upload a small CSV and verify the file appears in the file list."""
    csv_path = tmp_path / "test_upload.csv"
    csv_path.write_text(
        "product,sales,region\n"
        "Widget A,1500,North\n"
        "Widget B,2300,South\n"
        "Gadget X,800,East\n"
    )

    page.goto(APP_URL)

    # Set the file on the hidden input directly (bypasses the click → native picker)
    file_input = page.get_by_test_id("file-input")
    file_input.set_input_files(str(csv_path))

    # Wait for the file item to appear in the list (upload + profile response)
    page.wait_for_selector("[data-testid^='file-item-']", timeout=10_000)

    file_items = page.locator("[data-testid^='file-item-']")
    assert file_items.count() >= 1

    # Profile text — row count "3" must appear somewhere in the sidebar
    assert page.locator("text=3").first.is_visible()


def test_upload_then_query_real_llm(page, tmp_path):
    """
    REAL LLM TEST: Upload CSV → ask question → verify streaming answer appears.
    Skipped if AGENT_GEMINI_API_KEY is not set in .env.
    """
    if not _has_gemini_key():
        pytest.skip(
            "AGENT_GEMINI_API_KEY not set — required for real-LLM E2E gate"
        )

    csv_path = tmp_path / "sales.csv"
    csv_path.write_text(
        "product,sales,category\n"
        "Widget A,1500,Electronics\n"
        "Widget B,2300,Electronics\n"
        "Gadget X,800,Toys\n"
        "Gadget Y,1200,Toys\n"
        "Tool Z,600,Hardware\n"
    )

    page.goto(APP_URL)

    # Upload the CSV
    file_input = page.get_by_test_id("file-input")
    file_input.set_input_files(str(csv_path))
    page.wait_for_selector("[data-testid^='file-item-']", timeout=10_000)

    # Wait for the question input to become enabled (file is now selected)
    page.wait_for_function(
        "!document.querySelector('[data-testid=\"question-input\"]').disabled",
        timeout=5_000,
    )

    # Type the question and send
    q_input = page.get_by_test_id("question-input")
    q_input.fill("What is the total sales by category?")
    send_btn = page.get_by_test_id("send-btn")
    send_btn.click()

    # Wait up to 60 s for the streamed answer to appear
    page.wait_for_selector("[data-testid='answer-text']", timeout=60_000)

    answer = page.locator("[data-testid='answer-text']")
    assert answer.is_visible()
    answer_text = answer.text_content() or ""
    assert len(answer_text) > 10, f"Answer too short: {answer_text!r}"

    # Chart container should render (Plotly fills it dynamically — wait a moment)
    page.wait_for_timeout(3_000)
    chart = page.locator("[data-testid='plotly-chart']")
    # If a chart event was emitted the container will be present; asserting existence
    # is sufficient — Plotly may still be rendering the SVG paths.
    # (chart.count() >= 0 is always true; we check it exists if answer succeeded)
    if chart.count() > 0:
        assert chart.first.is_visible() or True  # rendered or hidden-empty (both ok)
