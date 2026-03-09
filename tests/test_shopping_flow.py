"""
Shopping Flow E2E Test
=======================

Data-driven end-to-end test that exercises the complete eBay shopping flow:

1. **Search** for products by keyword with a price ceiling.
2. **Filter** results to Buy It Now items under the max price.
3. **Collect** up to *N* qualifying item URLs (with pagination).
4. **Add** each item to the cart (handling variants where required).
5. **Validate** that the cart total does not exceed the budget.

Each scenario is parametrised from ``data/search_data.json`` so new test
cases can be added without touching code.

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
from utils.data_loader import load_test_scenarios, get_scenario_ids
from utils.allure_helper import attach_json
from utils.step_collector import collector
from core.logger_config import get_logger

logger = get_logger(__name__)

_scenarios = load_test_scenarios("search_data.json")
_scenario_ids = get_scenario_ids(_scenarios)


@allure.epic("eBay E2E Shopping")
@allure.feature("Search, Add to Cart, Validate Total")
@pytest.mark.e2e
@pytest.mark.parallel
@pytest.mark.parametrize("scenario", _scenarios, ids=_scenario_ids)
def test_ebay_shopping_flow(page: Page, test_settings, scenario: dict) -> None:
    """End-to-end test: search -> filter -> collect -> add to cart -> validate.

    This is the main test function.  It is **parametrised** by the scenarios
    in ``data/search_data.json``, so each scenario (different query, price,
    limit) runs as a separate test case with its own Allure entry.

    Steps:
        1. Search for items under the budget.
        2. Add found items to the cart.
        3. Assert the cart total is within budget.

    Args:
        page:          Playwright ``Page`` fixture (isolated per test).
        test_settings: Framework ``Settings`` fixture.
        scenario:      A single scenario dict from the JSON data file.
    """
    query = scenario["query"]
    max_price = scenario["max_price"]
    limit = scenario["limit"]
    budget_per_item = scenario["budget_per_item"]
    scenario_id = scenario.get("id", query.replace(" ", "_"))

    allure.dynamic.title(f"Shopping flow: {query} (\u2264${max_price}, limit={limit})")
    allure.dynamic.description(scenario.get("description", ""))
    attach_json("Test Scenario", scenario)

    browser_name = os.environ.get("EBAY_BROWSER", "chromium")
    collector.start_scenario(
        scenario_id, query=query, max_price=max_price, browser=browser_name,
        description=scenario.get("description", ""),
        expected_results=scenario.get("expected_results", ""),
        manual_steps=scenario.get("manual_steps", []),
    )

    try:
        # Step 0 — Login (skipped automatically if credentials not configured)
        with allure.step("Sign in to eBay"):
            login(page)

        # Step 1 — Search and collect item URLs
        with allure.step(f"Search for '{query}' under ${max_price}"):
            urls = search_items_by_name_under_price(
                page=page,
                base_url=test_settings.base_url,
                query=query,
                max_price=max_price,
                limit=limit,
            )

        if not urls:
            collector.add_step("No Items Found", "search_items_by_name_under_price()", "skip",
                               detail=f"No items found for '{query}' under ${max_price}")
            collector.finish_scenario("skip")
            pytest.skip(f"No items found for '{query}' under ${max_price}")

        with allure.step(f"Add {len(urls)} items to cart"):
            added_count = add_items_to_cart(page, urls)

        if added_count == 0:
            collector.add_step("No Items Added", "add_items_to_cart()", "skip",
                               detail="No items could be added to cart")
            collector.finish_scenario("skip")
            pytest.skip("No items could be added to cart")

        with allure.step("Validate cart total against budget"):
            assert_cart_total_not_exceeds(page, budget_per_item, added_count)

        collector.finish_scenario("pass")

    except pytest.skip.Exception:
        raise
    except Exception as exc:
        collector.finish_scenario("fail", error=str(exc))
        raise
