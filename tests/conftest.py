"""
Test-Level conftest.py — Browser & Page Fixtures
=================================================

Provides the Playwright browser, context, and page fixtures used by every
test function.

* **Session isolation** – each test gets its own BrowserContext (no shared
  cookies/storage between tests) for reliable parallel execution.
* **Class-scoped flow** – multi-step test classes share one BrowserContext +
  Page so cart/session state persists between steps (TestNG-style).
* **Step-skip on failure** – when a step fails, subsequent step methods in
  the same class are automatically skipped (dependsOnMethods equivalent).
* **Tracing** – Playwright records a trace on failure, attached to Allure.
* **Auto screenshots** – captured and attached to Allure on failure.
* **HTML reports** – self-contained report per scenario, plus run summary.
* **Browser matrix** – run across Chromium, Firefox, Edge, Chrome via
  ``EBAY_BROWSER`` env var or ``config.yaml``.
"""

from __future__ import annotations

import os
import subprocess
import sys
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


# --- Session-scoped: Playwright instance + browser ---

@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Load framework settings once per session."""
    return load_settings()


@pytest.fixture(scope="session")
def playwright_instance() -> Generator[Playwright, None, None]:
    """Start and stop the Playwright server once per test session."""
    with sync_playwright() as pw:
        yield pw


@pytest.fixture(scope="session")
def browser_profile(test_settings: Settings) -> BrowserProfile:
    """Resolve the browser profile for this session.

    Reads ``EBAY_BROWSER`` env var first (set by CI matrix or Docker),
    falls back to the first entry in ``config.yaml → browsers``.
    """
    name = os.environ.get("EBAY_BROWSER", test_settings.browsers[0])
    profile = resolve_browser_profile(name)
    logger.info(
        "Browser profile: %s (engine=%s, channel=%s)",
        profile.id, profile.browser_type, profile.channel or "default",
    )
    return profile


def _kill_browser_background_processes(channel: str) -> None:
    """Kill background browser processes that interfere with Playwright launch.

    Edge and Chrome "Startup Boost" / Windows Widgets / WebView2 hosts can
    keep browser processes alive in the background.  When Playwright launches
    a new instance via ``--remote-debugging-pipe`` it detects the running one,
    delegates to it and exits immediately (exitCode=0) → ``TargetClosedError``.

    Kill-then-verify loop ensures all background processes are gone before
    returning.  PyCharm may trigger Edge restarts after the initial kill,
    so we verify with ``tasklist`` between attempts.
    """
    exe_map = {
        "msedge": "msedge.exe",
        "chrome": "chrome.exe",
        "chrome-beta": "chrome.exe",
        "chrome-dev": "chrome.exe",
        "chrome-canary": "chrome.exe",
        "msedge-beta": "msedge.exe",
        "msedge-dev": "msedge.exe",
    }
    exe_name = exe_map.get(channel)
    if not exe_name or sys.platform != "win32":
        return

    def _is_running() -> bool:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {exe_name}", "/NH"],
            capture_output=True, text=True, timeout=5,
        )
        return exe_name.lower() in result.stdout.lower()

    for attempt in range(3):
        if not _is_running():
            break
        logger.info(
            "Killing background %s processes (attempt %d)", exe_name, attempt + 1,
        )
        subprocess.run(
            ["taskkill", "/F", "/IM", exe_name, "/T"],
            capture_output=True, timeout=5,
        )
        time.sleep(1.5)

    if _is_running():
        logger.warning("%s processes still running after 3 kill attempts", exe_name)
    else:
        logger.info("No background %s processes remain", exe_name)


@pytest.fixture(scope="session")
def browser(
    playwright_instance: Playwright,
    browser_profile: BrowserProfile,
    test_settings: Settings,
) -> Generator[Browser, None, None]:
    """Launch a browser instance that persists for the whole session."""
    browser_type: BrowserType = getattr(playwright_instance, browser_profile.browser_type)

    launch_opts: dict = {
        "headless": test_settings.browser_options.headless,
        "slow_mo": test_settings.browser_options.slow_mo,
    }
    if browser_profile.channel:
        launch_opts["channel"] = browser_profile.channel
        # Kill lingering background processes for channel browsers.
        # Edge/Chrome "Startup Boost" keeps background processes alive even
        # after all windows are closed.  When Playwright launches a new
        # instance it detects the running one, delegates, and exits (code 0),
        # which causes TargetClosedError.
        _kill_browser_background_processes(browser_profile.channel)
    else:
        launch_opts["args"] = [
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
        ]

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


# --- Function-scoped: isolated context + page per test ---

def _make_context_opts(test_settings: Settings) -> dict:
    """Build the common BrowserContext options dict."""
    opts: dict = {
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
        opts["storage_state"] = str(AUTH_STATE_FILE)
        logger.info("Loading saved auth state from %s", AUTH_STATE_FILE.name)
    return opts


@pytest.fixture()
def context(
    browser: Browser,
    test_settings: Settings,
) -> Generator[BrowserContext, None, None]:
    """Create an isolated browser context for a single test function."""
    ctx = browser.new_context(**_make_context_opts(test_settings))

    if test_settings.tracing_enabled:
        ctx.tracing.start(screenshots=True, snapshots=True)
        logger.debug("Tracing started for test context")

    yield ctx
    try:
        ctx.close()
    except Exception:
        pass
    logger.debug("Browser context closed")


@pytest.fixture()
def page(context: BrowserContext) -> Generator[Page, None, None]:
    """Open a new page (tab) within the isolated context."""
    pg = context.new_page()
    logger.info("New page opened")
    yield pg
    try:
        pg.close()
    except Exception:
        pass


# --- Class-scoped: shared context + page for multi-step flow tests ---

@pytest.fixture(scope="class")
def class_context(
    browser: Browser,
    test_settings: Settings,
) -> Generator[BrowserContext, None, None]:
    """Class-scoped browser context shared across all step methods.

    Equivalent to a TestNG test class whose ``@Test`` methods share one
    session — the cart, cookies, and login state persist between steps.
    """
    ctx = browser.new_context(**_make_context_opts(test_settings))

    if test_settings.tracing_enabled:
        ctx.tracing.start(screenshots=True, snapshots=True)

    yield ctx
    try:
        ctx.close()
    except Exception:
        pass
    logger.debug("Class-scoped browser context closed")


@pytest.fixture(scope="class")
def class_page(class_context: BrowserContext) -> Generator[Page, None, None]:
    """Class-scoped page shared across all step methods in a flow class."""
    pg = class_context.new_page()
    logger.info("New class-scoped page opened")
    yield pg
    try:
        pg.close()
    except Exception:
        pass


@pytest.fixture(scope="class")
def scenario_data(request: pytest.FixtureRequest) -> dict:
    """Receive parametrised scenario dict for class-based tests.

    Used with ``@pytest.mark.parametrize("scenario_data", ..., indirect=True)``
    on a test class.
    """
    return request.param


# --- Step-failure tracking (dependsOnMethods equivalent) ---

def pytest_configure(config: pytest.Config) -> None:
    """Initialise flow-tracking containers on the config object."""
    config._failed_class_nodes: set[str] = set()      # type: ignore[attr-defined]
    config._flow_statuses: dict[str, str] = {}         # type: ignore[attr-defined]
    config._flow_errors: dict[str, str] = {}           # type: ignore[attr-defined]


def get_flow_status(config: pytest.Config, node_id: str) -> tuple[str, str]:
    """Return ``(status, error_message)`` for a class-based flow."""
    status = config._flow_statuses.get(node_id, "pass")   # type: ignore[attr-defined]
    error = config._flow_errors.get(node_id, "")           # type: ignore[attr-defined]
    return status, error


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Skip subsequent step methods after an earlier step in the same
    class-based flow has failed — equivalent to TestNG dependsOnMethods.
    """
    if item.cls and item.parent:
        parent_id = item.parent.nodeid
        if parent_id in item.config._failed_class_nodes:  # type: ignore[attr-defined]
            pytest.skip("Previous step failed — skipping dependent step")


# --- Automatic screenshot & trace on failure ---

@pytest.fixture(autouse=True)
def auto_screenshot_on_failure(
    request: pytest.FixtureRequest,
    test_settings: Settings,
) -> Generator[None, None, None]:
    """Capture screenshot and trace evidence when any test step fails.

    Works for both function-scoped tests (reads ``page`` fixture) and
    class-based flow tests (reads ``class_page`` via class attribute).
    """
    yield

    if not (hasattr(request.node, "rep_call") and request.node.rep_call.failed):
        return

    logger.error("TEST FAILED: %s", request.node.name)

    pg = None
    ctx = None

    if request.cls and hasattr(request.cls, "_page"):
        pg = request.cls._page
        ctx = getattr(request.cls, "_context", None)
    else:
        pg = request.funcargs.get("page")
        ctx = request.funcargs.get("context")

    if pg and test_settings.screenshot_on_failure:
        try:
            capture_on_failure(pg, request.node.name, output_dir=test_settings.screenshots_dir_for_run)
        except Exception as exc:
            logger.warning("Failed to capture failure screenshot: %s", exc)

    if ctx and test_settings.tracing_enabled:
        try:
            trace_path = TRACES_DIR / f"trace_{request.node.name}_{int(time.time())}.zip"
            ctx.tracing.stop(path=str(trace_path))
            allure.attach.file(
                str(trace_path),
                name="Playwright Trace",
                attachment_type=allure.attachment_type.TEXT,
            )
            logger.info("Trace saved: %s", trace_path)
        except Exception as exc:
            logger.warning("Failed to save trace: %s", exc)


# --- Hooks ---

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call):
    """Store test outcome on the item node and manage class-flow state.

    * Makes pass/fail available to ``auto_screenshot_on_failure``.
    * Tracks step failures for the dependsOnMethods skip logic.
    * Triggers HTML report generation when a scenario completes.
    """
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)

    if rep.when == "call":
        if rep.failed and item.cls and item.parent:
            parent_id = item.parent.nodeid
            item.config._failed_class_nodes.add(parent_id)      # type: ignore[attr-defined]
            item.config._flow_statuses[parent_id] = "fail"       # type: ignore[attr-defined]
            item.config._flow_errors[parent_id] = (              # type: ignore[attr-defined]
                rep.longreprtext[:500] if rep.longrepr else "Unknown error"
            )

        elif rep.skipped and item.cls and item.parent:
            parent_id = item.parent.nodeid
            if parent_id not in item.config._flow_statuses:      # type: ignore[attr-defined]
                item.config._flow_statuses[parent_id] = "skip"   # type: ignore[attr-defined]

    if rep.when in ("call", "teardown"):
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
        settings = load_settings()
        path = generate_scenario_report(latest, output_dir=settings.reports_dir_for_run)
        latest._report_generated = True  # type: ignore[attr-defined]
        logger.info("HTML report generated: %s", path)
    except Exception as exc:
        logger.warning("Failed to generate HTML report: %s", exc)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Generate run-level and worker-level summary reports.

    When running under pytest-xdist, each worker generates its own report
    listing the scenarios it executed.  The overall summary is only written
    by the controller (non-worker) process when 2+ scenarios completed.
    """
    completed = collector.completed
    if not completed:
        return

    try:
        settings = load_settings()
        worker_id = os.environ.get("PYTEST_XDIST_WORKER", "")

        if worker_id:
            path = generate_run_summary(
                completed,
                output_dir=settings.reports_dir_for_run,
                run_id=settings.run_id,
                worker_id=worker_id,
            )
            logger.info("Worker %s report generated: %s", worker_id, path)
        elif len(completed) >= 2:
            path = generate_run_summary(
                completed,
                output_dir=settings.reports_dir_for_run,
                run_id=settings.run_id,
            )
            logger.info("HTML summary report generated: %s", path)
    except Exception as exc:
        logger.warning("Failed to generate summary report: %s", exc)


