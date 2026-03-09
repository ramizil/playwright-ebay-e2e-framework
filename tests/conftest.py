"""
Test-Level conftest.py — Browser & Page Fixtures
=================================================

Provides the Playwright browser, context, and page fixtures used by every
test function.  Key design decisions:

* **Session isolation** – each test gets its own ``BrowserContext`` so
  cookies, storage, and sessions never leak between tests.  This is
  critical for reliable parallel execution.
* **Tracing** – when enabled in config, Playwright records a trace for
  every test.  On failure, the trace ZIP is attached to the Allure report
  for full replay debugging.
* **Automatic screenshots on failure** – the ``auto_screenshot`` fixture
  detects test outcomes and captures a screenshot + attaches it to Allure.
* **HTML report generation** – a self-contained HTML report with embedded
  screenshots is generated automatically after each scenario completes.
* **Browser parametrisation** – tests can be run across multiple browsers
  by setting ``EBAY_BROWSERS=chromium,firefox`` or via ``pytest -k``.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Generator

import allure
import pytest
from playwright.sync_api import (
    Browser,
    BrowserContext,
    BrowserType,
    Page,
    Playwright,
    sync_playwright,
)

from config.settings import load_settings, Settings, BrowserProfile, resolve_browser_profile
from core.logger_config import get_logger
from utils.screenshot_manager import capture_on_failure
from utils.step_collector import collector
from utils.html_report_generator import generate_scenario_report, generate_run_summary

logger = get_logger(__name__)

TRACES_DIR = Path(__file__).resolve().parent.parent / "traces"
TRACES_DIR.mkdir(parents=True, exist_ok=True)

AUTH_STATE_FILE = Path(__file__).resolve().parent.parent / "auth_state.json"


# ------------------------------------------------------------------
# Session-scoped: Playwright instance + browser
# ------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Load framework settings once per session.

    Returns:
        The global ``Settings`` object.
    """
    return load_settings()


@pytest.fixture(scope="session")
def playwright_instance() -> Generator[Playwright, None, None]:
    """Start and stop the Playwright server once per test session.

    Yields:
        A ``Playwright`` instance that can launch browsers.
    """
    with sync_playwright() as pw:
        yield pw


@pytest.fixture(scope="session")
def browser_profile(test_settings: Settings) -> BrowserProfile:
    """Resolve the browser profile for this session.

    Reads ``EBAY_BROWSER`` env var first (set by CI matrix or Docker),
    falls back to the first entry in ``config.yaml → browsers``.
    The profile name is mapped to a Playwright engine + optional channel
    (e.g. ``'msedge'`` → ``chromium`` engine with ``channel='msedge'``).

    Returns:
        A ``BrowserProfile`` with ``browser_type`` and optional ``channel``.
    """
    name = os.environ.get("EBAY_BROWSER", test_settings.browsers[0])
    profile = resolve_browser_profile(name)
    logger.info(
        "Browser profile: %s (engine=%s, channel=%s)",
        profile.id, profile.browser_type, profile.channel or "default",
    )
    return profile


@pytest.fixture(scope="session")
def browser(
    playwright_instance: Playwright,
    browser_profile: BrowserProfile,
    test_settings: Settings,
) -> Generator[Browser, None, None]:
    """Launch a browser instance that persists for the whole session.

    Uses the resolved ``BrowserProfile`` to select the engine and channel,
    plus settings from ``config.yaml`` for headless mode and slow_mo.
    Channels allow launching branded builds like Chrome or Edge instead
    of the bundled open-source Chromium.

    Yields:
        A Playwright ``Browser`` instance.
    """
    browser_type: BrowserType = getattr(playwright_instance, browser_profile.browser_type)
    launch_opts: dict = {
        "headless": test_settings.browser_options.headless,
        "slow_mo": test_settings.browser_options.slow_mo,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--no-first-run",
            "--no-default-browser-check",
        ],
    }
    if browser_profile.channel:
        launch_opts["channel"] = browser_profile.channel

    br = browser_type.launch(**launch_opts)
    logger.info(
        "Browser launched: %s (channel=%s, headless=%s)",
        browser_profile.browser_type,
        browser_profile.channel or "bundled",
        test_settings.browser_options.headless,
    )
    yield br
    br.close()
    logger.info("Browser closed: %s", browser_profile.id)


# ------------------------------------------------------------------
# Function-scoped: isolated context + page per test
# ------------------------------------------------------------------

@pytest.fixture()
def context(
    browser: Browser,
    test_settings: Settings,
) -> Generator[BrowserContext, None, None]:
    """Create an isolated browser context for a single test.

    Each test gets a fresh context with:
    * Its own cookies and local storage (session isolation).
    * The configured viewport size.
    * Optional tracing enabled for post-mortem debugging.
    * Saved auth state loaded when ``auth_state.json`` exists,
      so the browser appears as a returning logged-in user
      (reduces CAPTCHA / bot detection triggers).

    Yields:
        A ``BrowserContext`` that is destroyed after the test.
    """
    ctx_opts: dict = {
        "viewport": {
            "width": test_settings.viewport.width,
            "height": test_settings.viewport.height,
        },
        "locale": "en-US",
        "timezone_id": "America/New_York",
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
    }

    if AUTH_STATE_FILE.exists():
        ctx_opts["storage_state"] = str(AUTH_STATE_FILE)
        logger.info("Loading saved auth state from %s", AUTH_STATE_FILE.name)

    ctx = browser.new_context(**ctx_opts)

    if test_settings.tracing_enabled:
        ctx.tracing.start(screenshots=True, snapshots=True)
        logger.debug("Tracing started for test context")

    yield ctx

    ctx.close()
    logger.debug("Browser context closed")


@pytest.fixture()
def page(context: BrowserContext) -> Generator[Page, None, None]:
    """Open a new page (tab) within the isolated context.

    This is the primary fixture that tests and page objects interact with.

    Yields:
        A Playwright ``Page`` object.
    """
    pg = context.new_page()
    logger.info("New page opened")
    yield pg
    pg.close()


# ------------------------------------------------------------------
# Automatic screenshot & trace on failure
# ------------------------------------------------------------------

@pytest.fixture(autouse=True)
def auto_screenshot_on_failure(
    request: pytest.FixtureRequest,
    page: Page,
    context: BrowserContext,
    test_settings: Settings,
) -> Generator[None, None, None]:
    """Automatically capture evidence when a test fails.

    This ``autouse`` fixture wraps every test.  After the test body
    executes, it checks the outcome:

    * **On failure**: saves a screenshot and (if tracing is on) a trace
      ZIP, both attached to the Allure report.
    * **On success**: discards the trace to save disk space.

    Yields:
        Control to the test function.
    """
    yield

    if hasattr(request.node, "rep_call") and request.node.rep_call.failed:
        logger.error("TEST FAILED: %s", request.node.name)

        if test_settings.screenshot_on_failure:
            try:
                capture_on_failure(page, request.node.name)
            except Exception as exc:
                logger.warning("Failed to capture failure screenshot: %s", exc)

        if test_settings.tracing_enabled:
            try:
                trace_path = TRACES_DIR / f"trace_{request.node.name}_{int(time.time())}.zip"
                context.tracing.stop(path=str(trace_path))
                allure.attach.file(
                    str(trace_path),
                    name="Playwright Trace",
                    attachment_type=allure.attachment_type.TEXT,
                )
                logger.info("Trace saved: %s", trace_path)
            except Exception as exc:
                logger.warning("Failed to save trace: %s", exc)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call):
    """Pytest hook that stores the test outcome on the request node.

    This makes the pass/fail status available to the ``auto_screenshot``
    fixture above via ``request.node.rep_call``.

    Also triggers HTML report generation when the test call phase completes.

    Args:
        item: The test item being reported on.
        call: The call phase (setup / call / teardown).
    """
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)

    if rep.when == "call":
        _generate_html_report_for_completed_scenario()


def _generate_html_report_for_completed_scenario() -> None:
    """Check if a scenario just completed and generate its HTML report."""
    completed = collector.completed
    if not completed:
        return
    latest = completed[-1]
    if getattr(latest, "_report_generated", False):
        return
    try:
        path = generate_scenario_report(latest)
        latest._report_generated = True  # type: ignore[attr-defined]
        logger.info("HTML report generated: %s", path)
    except Exception as exc:
        logger.warning("Failed to generate HTML report: %s", exc)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Generate a run-level summary report after all tests complete."""
    completed = collector.completed
    if not completed:
        return
    try:
        settings = load_settings()
        path = generate_run_summary(completed, run_id=settings.run_id)
        logger.info("HTML summary report generated: %s", path)
    except Exception as exc:
        logger.warning("Failed to generate summary report: %s", exc)
