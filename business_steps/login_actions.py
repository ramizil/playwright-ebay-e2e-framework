"""
Login Actions
=============

Business-level function that implements the task-spec requirement
for **Identification (Login)**.  Orchestrates the LoginPage page object
into a reusable sign-in action.

Credentials are read from environment variables:
    ``EBAY_USERNAME``  — eBay account email or username
    ``EBAY_PASSWORD``  — eBay account password

When both variables are set the login step executes automatically.
When either is missing the step is **skipped** (not failed), allowing
the framework to run without authentication for public browsing flows.
"""

from __future__ import annotations

import os

from playwright.sync_api import Page

from pages.login_page import LoginPage
from utils.step_collector import collector
from utils.screenshot_manager import capture_screenshot
from core.logger_config import get_logger

logger = get_logger(__name__)


def login(page: Page) -> bool:
    """Sign in to eBay using credentials from environment variables.

    Implements the task-spec function **Identification (Login)**.

    Flow:
        1. Read ``EBAY_USERNAME`` and ``EBAY_PASSWORD`` from env.
        2. Navigate to the eBay sign-in page.
        3. Enter username (handle the optional Continue step).
        4. Enter password and submit.
        5. Verify the signed-in greeting is visible.

    Returns:
        ``True``  if login succeeded or was skipped (no creds configured).
        ``False`` if login was attempted but failed.
    """
    username = os.environ.get("EBAY_USERNAME", "")
    password = os.environ.get("EBAY_PASSWORD", "")

    if not username or not password:
        collector.begin_step()
        collector.add_step(
            "Login (Skipped)", "login()",
            "skip",
            detail="EBAY_USERNAME / EBAY_PASSWORD not set — running without authentication",
        )
        logger.info("Login skipped — credentials not configured")
        return True

    collector.begin_step()
    login_page = LoginPage(page)

    try:
        success = login_page.login(username, password)
        screenshot = capture_screenshot(page, "00_login_result", full_page=False)

        if success:
            collector.add_step(
                "Login to eBay", "LoginPage.login()", "pass",
                detail=f"Signed in as {username[:3]}***",
                screenshot_path=screenshot,
            )
            logger.info("Login succeeded for %s***", username[:3])
        else:
            collector.add_step(
                "Login to eBay", "LoginPage.login()", "fail",
                detail="Sign-in greeting not detected after login attempt",
                screenshot_path=screenshot,
            )
            logger.warning("Login may have failed — greeting not detected")

        return success

    except Exception as exc:
        screenshot = capture_screenshot(page, "00_login_FAIL", full_page=False)
        collector.add_step(
            "Login to eBay", "LoginPage.login()", "fail",
            detail=f"Login error: {str(exc)[:200]}",
            screenshot_path=screenshot,
        )
        logger.error("Login failed: %s", exc)
        return False
