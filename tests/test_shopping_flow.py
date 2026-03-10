"""
Shopping Flow E2E Test
=======================

Data-driven end-to-end test class modelled after the TestNG ``@Test``
annotation style used in the CES Java framework.  Each step is a
separate test method with a clear description and dependency chain::

    @Test(priority=0, description="Sign in to eBay")
    @Test(priority=1, dependsOn="login", description="Search and collect")
    @Test(priority=2, dependsOn="search", description="Add items to cart")
    @Test(priority=3, dependsOn="add_to_cart", description="Validate cart")

If a step fails, all subsequent dependent steps are **automatically
skipped** (equivalent to TestNG ``dependsOnMethods``).

State is shared across steps through a class-scoped ``ShoppingFlowState``
DTO (from ``models/``) — similar to Java instance fields like ``this.urls``.

Each scenario is parametrised from ``data/search_data.json`` so new
test cases can be added without touching code.

Markers:
    ``@pytest.mark.e2e``        -- Full shopping flow.
    ``@pytest.mark.parallel``   -- Safe for parallel execution via xdist.
"""

from __future__ import annotations

import os

import pytest
import allure
from playwright.sync_api import Page

from business_steps import (
    login,
    search_items_by_name_under_price,
    add_items_to_cart,
    assert_cart_total_not_exceeds,
)
from models import ShoppingFlowState
from utils.data_loader import load_test_scenarios, get_scenario_ids
from utils.allure_helper import attach_json
from utils.step_collector import collector
from core.logger_config import get_logger

logger = get_logger(__name__)

_scenarios = load_test_scenarios("search_data.json")
_scenario_ids = get_scenario_ids(_scenarios)


# --- Test Class ---

@allure.epic("eBay E2E Shopping")
@allure.feature("Search, Add to Cart, Validate Total")
@pytest.mark.e2e
@pytest.mark.parallel
@pytest.mark.parametrize("scenario_data", _scenarios, ids=_scenario_ids, indirect=True)
class TestEbayShoppingFlow:
    """
    eBay Shopping Flow — End-to-End
    ================================

    Description:
        Automated shopping flow that searches eBay for products under a
        price ceiling, adds qualifying items to the cart, and validates
        the cart total stays within budget.

    Steps to reproduce (manual):
        1. Open eBay and sign in (optional)
        2. Search for products by keyword
        3. Filter by "Buy It Now" and apply max-price range
        4. Collect the first N qualifying items
        5. Open each item and add to cart (select random variants if needed)
        6. Go to cart and verify subtotal ≤ budget_per_item × item_count

    Expected:
        All items added successfully and cart total does not exceed the
        calculated budget.
    """

    # Fixture overrides — map function-scoped names to class-scoped versions

    @pytest.fixture
    def page(self, class_page: Page) -> Page:
        return class_page

    @pytest.fixture
    def context(self, class_context):
        return class_context

    # @BeforeClass — shared flow context

    @pytest.fixture(autouse=True, scope="class")
    def setup_flow(self, request, class_page, test_settings, scenario_data):
        """Initialise the flow: page, settings, scenario, and reporting.

        Equivalent to ``@BeforeTest`` in TestNG.
        """
        request.cls._page = class_page
        request.cls._context = class_page.context
        request.cls.page = class_page
        request.cls.settings = test_settings
        request.cls.scenario = scenario_data
        request.cls.state = ShoppingFlowState()

        scenario_id = scenario_data.get("id", scenario_data["query"].replace(" ", "_"))
        browser_name = os.environ.get("EBAY_BROWSER", "chromium")

        allure.dynamic.title(
            f"Shopping flow: {scenario_data['query']}"
            f" (≤${scenario_data['max_price']}, limit={scenario_data['limit']})"
        )
        attach_json("Test Scenario", scenario_data)

        collector.start_scenario(
            scenario_id,
            query=scenario_data["query"],
            max_price=scenario_data["max_price"],
            browser=browser_name,
            description=scenario_data.get("description", ""),
            expected_results=scenario_data.get("expected_results", ""),
            manual_steps=scenario_data.get("manual_steps", []),
        )

        yield

        # @AfterClass — finalise reporting
        nid = request.node.nodeid
        status = request.config._flow_statuses.get(nid, "pass")   # type: ignore[attr-defined]
        error = request.config._flow_errors.get(nid, "")           # type: ignore[attr-defined]
        collector.finish_scenario(status, error=error)

    # @Test methods (executed in definition order)

    @allure.step("Step 0 — Sign in to eBay")
    def test_step_00_login(self):
        """
        @Test(priority=0, description="Sign in to eBay")

        Authenticate with eBay credentials.
        Automatically skipped if EBAY_USERNAME / EBAY_PASSWORD are not set.
        """
        login(self.page)

    @allure.step("Step 1 — Search and collect items under budget")
    def test_step_01_search_and_collect(self):
        """
        @Test(priority=1, dependsOn="login",
              description="Search and collect items under price ceiling")

        Search for products matching the query, apply 'Buy It Now' and
        price filters, then collect up to N qualifying item URLs with
        pagination support.
        """
        self.state.urls = search_items_by_name_under_price(
            page=self.page,
            base_url=self.settings.base_url,
            query=self.scenario["query"],
            max_price=self.scenario["max_price"],
            limit=self.scenario["limit"],
            screenshots_dir=self.settings.screenshots_dir_for_run,
        )

        if not self.state.urls:
            collector.add_step(
                "No Items Found", "search_items_by_name_under_price()", "skip",
                detail=f"No items found for '{self.scenario['query']}'"
                       f" under ${self.scenario['max_price']}",
            )
            pytest.skip(
                f"No items found for '{self.scenario['query']}'"
                f" under ${self.scenario['max_price']}"
            )

    @allure.step("Step 2 — Add items to cart")
    def test_step_02_add_to_cart(self):
        """
        @Test(priority=2, dependsOn="search_and_collect",
              description="Add collected items to shopping cart")

        Open each collected item URL and add it to the cart.
        Handles size / colour / quantity variant selection when required.
        """
        self.state.added_count = add_items_to_cart(
            self.page, self.state.urls,
            screenshots_dir=self.settings.screenshots_dir_for_run,
        )

        if self.state.added_count == 0:
            collector.add_step(
                "No Items Added", "add_items_to_cart()", "skip",
                detail="No items could be added to cart",
            )
            pytest.skip("No items could be added to cart")

    @allure.step("Step 3 — Validate cart total against budget")
    def test_step_03_validate_cart(self):
        """
        @Test(priority=3, dependsOn="add_to_cart",
              description="Assert cart total does not exceed budget")

        Open the shopping cart and assert:
            subtotal ≤ budget_per_item × items_count
        """
        assert_cart_total_not_exceeds(
            self.page,
            self.scenario["budget_per_item"],
            self.state.added_count,
            screenshots_dir=self.settings.screenshots_dir_for_run,
        )
