"""
Screenshot Manager Module
==========================

Screenshot utilities used by fixtures and hooks to capture evidence
at key moments:

* **On test failure** – automatic screenshot attached to the Allure report.
* **On explicit request** – e.g. after adding each item to the cart.
* **Full-page vs viewport** – choose the right capture mode.

All screenshots are saved under ``screenshots/`` with a timestamp so
parallel workers never collide on filenames.
"""

from __future__ import annotations

import time
from pathlib import Path

import allure
from playwright.sync_api import Page

from core.logger_config import get_logger

logger = get_logger(__name__)

SCREENSHOT_DIR = Path(__file__).resolve().parent.parent / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def capture_screenshot(
    page: Page,
    name: str = "screenshot",
    full_page: bool = True,
    attach_to_allure: bool = True,
    output_dir: Path | None = None,
) -> str:
    """Capture a browser screenshot and optionally attach it to Allure.

    Args:
        page:              Playwright ``Page`` to screenshot.
        name:              Descriptive label for the file and Allure attachment.
        full_page:         If ``True``, capture the entire scrollable page.
                           If ``False``, capture only the current viewport.
        attach_to_allure:  If ``True``, auto-attach the image to the running
                           Allure report step.
        output_dir:        Optional per-run directory.  Defaults to the global
                           ``screenshots/`` folder.

    Returns:
        The absolute filesystem path of the saved PNG file.
    """
    dest = output_dir or SCREENSHOT_DIR
    dest.mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{name}_{timestamp}.png"
    filepath = dest / filename

    page.screenshot(path=str(filepath), full_page=full_page)
    logger.info("Screenshot saved: %s", filepath)

    if attach_to_allure:
        allure.attach.file(
            str(filepath),
            name=name,
            attachment_type=allure.attachment_type.PNG,
        )

    return str(filepath)


def capture_on_failure(
    page: Page,
    test_name: str,
    output_dir: Path | None = None,
) -> str:
    """Specialised screenshot for test failures — always full-page, always attached.

    Called from the ``pytest_runtest_makereport`` hook in ``conftest.py``.

    Args:
        page:       Playwright ``Page`` from the failing test's fixture.
        test_name:  ``request.node.name`` — used in the filename for traceability.
        output_dir: Optional per-run screenshots directory.

    Returns:
        Path to the saved screenshot.
    """
    safe_name = test_name.replace("[", "_").replace("]", "_").replace("/", "_")
    return capture_screenshot(
        page, name=f"FAILURE_{safe_name}", full_page=True, output_dir=output_dir,
    )
