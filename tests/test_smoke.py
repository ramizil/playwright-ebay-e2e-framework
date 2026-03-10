"""
Smoke Test — eBay Reachability & Search
========================================

Lightweight sanity check modelled after the TestNG ``@Test`` annotation
style.  Each step is a separate test method so the report clearly shows
which phase passed or failed::

    @Test(priority=0, description="Open eBay home page")
    @Test(priority=1, dependsOn="open_ebay", description="Search for 'laptop'")
    @Test(priority=2, dependsOn="search", description="Verify search results")

If any step fails, dependent steps are **automatically skipped**.

Use this to gate CI pipelines before committing to the heavier E2E suite.

Markers:
    ``@pytest.mark.smoke``  -- Quick health check.
"""

from __future__ import annotations

import os

import pytest
import allure
from playwright.sync_api import Page

from models import SmokeFlowState
from pages.home_page import HomePage
from pages.search_results_page import SearchResultsPage
from utils.step_collector import collector
from utils.screenshot_manager import capture_screenshot
from core.logger_config import get_logger

logger = get_logger(__name__)


@allure.epic("eBay E2E Shopping")
@allure.feature("Smoke Test")
@pytest.mark.smoke
class TestSmokeCheck:
    """
    Smoke Test — eBay Reachability
    ===============================

    Description:
        Quick sanity check that eBay is reachable and the search
        flow returns at least one result.  Does NOT exercise the full
        add-to-cart / validation ceremony.

    Steps to reproduce (manual):
        1. Open https://www.ebay.com
        2. Type 'laptop' in the search bar and press Enter
        3. Verify at least one product listing appears

    Expected:
        Search results page loads and contains ≥ 1 item for query 'laptop'.
    """

    # Fixture overrides

    @pytest.fixture
    def page(self, class_page: Page) -> Page:
        return class_page

    @pytest.fixture
    def context(self, class_context):
        return class_context

    # @BeforeClass — initialise smoke test context

    @pytest.fixture(autouse=True, scope="class")
    def setup_smoke(self, request, class_page, test_settings):
        """Prepare page, settings, and reporting for the smoke test.

        Equivalent to ``@BeforeTest`` in TestNG.
        """
        request.cls._page = class_page
        request.cls._context = class_page.context
        request.cls.page = class_page
        request.cls.settings = test_settings
        request.cls.state = SmokeFlowState()

        collector.start_scenario(
            "smoke_test", query="laptop", max_price=9999,
            browser=os.environ.get("EBAY_BROWSER", "chromium"),
            description=(
                "Lightweight sanity check: verify eBay is reachable "
                "and the search flow returns at least one result."
            ),
            expected_results=(
                "Search results page loads and contains at least "
                "1 item for query 'laptop'."
            ),
            manual_steps=[
                "Open https://www.ebay.com",
                "Type 'laptop' in the search bar and press Enter",
                "Verify the search results page loads with at least one product listing",
            ],
        )

        yield

        # @AfterClass — finalise reporting
        nid = request.node.nodeid
        status = request.config._flow_statuses.get(nid, "pass")   # type: ignore[attr-defined]
        error = request.config._flow_errors.get(nid, "")           # type: ignore[attr-defined]
        if status == "pass" and not request.cls.state.urls:
            status = "fail"
            error = "No search results collected"
        collector.finish_scenario(status, error=error)

    # @Test methods (executed in definition order)

    @allure.step("Step 0 — Open eBay home page")
    def test_step_00_open_ebay(self):
        """
        @Test(priority=0, description="Navigate to eBay home page")

        Open the eBay home page, dismiss any cookie banners or overlays.
        """
        collector.begin_step()
        home = HomePage(self.page)
        home.open(self.settings.base_url)
        ss_dir = self.settings.screenshots_dir_for_run
        screenshot = capture_screenshot(self.page, "smoke_01_home", full_page=False, output_dir=ss_dir)
        collector.add_step(
            "Open eBay", "HomePage.open()", "pass",
            screenshot_path=screenshot,
        )

    @allure.step("Step 1 — Search for 'laptop'")
    def test_step_01_search(self):
        """
        @Test(priority=1, dependsOn="open_ebay",
              description="Search for 'laptop'")

        Type 'laptop' in the search bar and submit the search form.
        """
        collector.begin_step()
        home = HomePage(self.page)
        home.search("laptop")
        ss_dir = self.settings.screenshots_dir_for_run
        screenshot = capture_screenshot(self.page, "smoke_02_search", full_page=False, output_dir=ss_dir)
        collector.add_step(
            "Search for 'laptop'", "HomePage.search('laptop')", "pass",
            screenshot_path=screenshot,
        )

    @allure.step("Step 2 — Verify search results")
    def test_step_02_verify_results(self):
        """
        @Test(priority=2, dependsOn="search",
              description="Verify search results contain ≥ 1 item")

        Collect search results and assert at least one product was found.
        """
        collector.begin_step()
        search_results = SearchResultsPage(self.page)
        self.state.urls = search_results.collect_items_under_price(
            max_price=9999, limit=1, max_pages=1,
        )
        ss_dir = self.settings.screenshots_dir_for_run
        screenshot = capture_screenshot(self.page, "smoke_03_results", full_page=False, output_dir=ss_dir)
        collector.add_step(
            f"Collect Results (found {len(self.state.urls)})",
            "SearchResultsPage.collect_items_under_price()",
            "pass" if self.state.urls else "fail",
            detail=f"Found {len(self.state.urls)} result(s)",
            screenshot_path=screenshot,
        )

        assert len(self.state.urls) >= 1, "Expected at least one search result"
        logger.info("Smoke test passed: found %d result(s)", len(self.state.urls))
