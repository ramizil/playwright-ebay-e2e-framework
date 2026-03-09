"""
Smoke Test
==========

Lightweight sanity check that verifies eBay is reachable and the search
flow returns at least one result.  Runs quickly and does **not** exercise
the full add-to-cart / validation flow.

Use this to gate CI pipelines before committing to the heavier E2E suite.

Markers:
    ``@pytest.mark.smoke``  -- Quick health check.
"""

from __future__ import annotations

import os

import pytest
import allure
from playwright.sync_api import Page

from pages.home_page import HomePage
from pages.search_results_page import SearchResultsPage
from utils.step_collector import collector
from utils.screenshot_manager import capture_screenshot
from core.logger_config import get_logger

logger = get_logger(__name__)


@allure.epic("eBay E2E Shopping")
@allure.feature("Smoke Test")
@pytest.mark.smoke
def test_ebay_search_returns_results(page: Page, test_settings) -> None:
    """Smoke test: verify that searching on eBay returns at least one result.

    This lightweight test runs quickly and validates that the site is
    accessible and the search flow works end-to-end without the full
    add-to-cart / validation ceremony.

    Args:
        page:          Playwright ``Page`` fixture.
        test_settings: Framework ``Settings`` fixture.
    """
    collector.start_scenario(
        "smoke_test", query="laptop", max_price=9999,
        browser=os.environ.get("EBAY_BROWSER", "chromium"),
        description="Lightweight sanity check: verify eBay is reachable and the search flow returns at least one result.",
        expected_results="Search results page loads and contains at least 1 item for query 'laptop'.",
        manual_steps=[
            "Open https://www.ebay.com",
            "Type 'laptop' in the search bar and press Enter",
            "Verify the search results page loads with at least one product listing",
        ],
    )

    try:
        collector.begin_step()
        home = HomePage(page)
        home.open(test_settings.base_url)
        screenshot = capture_screenshot(page, "smoke_01_home", full_page=False)
        collector.add_step("Open eBay", "HomePage.open()", "pass", screenshot_path=screenshot)

        collector.begin_step()
        home.search("laptop")
        screenshot = capture_screenshot(page, "smoke_02_search", full_page=False)
        collector.add_step("Search for 'laptop'", "HomePage.search('laptop')", "pass", screenshot_path=screenshot)

        collector.begin_step()
        search_results = SearchResultsPage(page)
        urls = search_results.collect_items_under_price(max_price=9999, limit=1, max_pages=1)
        screenshot = capture_screenshot(page, "smoke_03_results", full_page=False)
        collector.add_step(
            f"Collect Results (found {len(urls)})",
            "SearchResultsPage.collect_items_under_price()",
            "pass" if urls else "fail",
            detail=f"Found {len(urls)} result(s)",
            screenshot_path=screenshot,
        )

        assert len(urls) >= 1, "Expected at least one search result"
        logger.info("Smoke test passed: found %d result(s)", len(urls))
        collector.finish_scenario("pass")

    except Exception as exc:
        collector.finish_scenario("fail", error=str(exc))
        raise
