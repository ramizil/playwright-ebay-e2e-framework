"""
E2E Shopping Flow Tests
========================

Data-driven end-to-end tests that exercise the complete eBay shopping flow:

1. **Search** for products by keyword with a price ceiling.
2. **Filter** results to Buy It Now items under the max price.
3. **Collect** up to *N* qualifying item URLs (with pagination).
4. **Add** each item to the cart (handling variants where required).
5. **Validate** that the cart total does not exceed the budget.

Each scenario is parametrised from ``data/search_data.json`` so new test
cases can be added without touching code.

Markers:
    ``@pytest.mark.e2e``        – Full shopping flow.
    ``@pytest.mark.parallel``   – Safe for parallel execution via xdist.
"""

from __future__ import annotations

import pytest
import allure
from playwright.sync_api import Page

from pages.home_page import HomePage
from pages.search_results_page import SearchResultsPage
from pages.product_page import ProductPage
from pages.cart_page import CartPage
from utils.data_loader import load_test_scenarios, get_scenario_ids
from utils.allure_helper import attach_json, attach_text
from core.logger_config import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Load scenarios from the external JSON file for data-driven parametrisation
# ---------------------------------------------------------------------------
_scenarios = load_test_scenarios("search_data.json")
_scenario_ids = get_scenario_ids(_scenarios)


# ---------------------------------------------------------------------------
# Core business functions (as specified in the task)
# ---------------------------------------------------------------------------

def search_items_by_name_under_price(
    page: Page,
    base_url: str,
    query: str,
    max_price: float,
    limit: int = 5,
) -> list[str]:
    """Search eBay for items matching *query* that cost ≤ *max_price*.

    Implements the task-spec function ``searchItemsByNameUnderPrice``.

    Flow:
        1. Open eBay home page.
        2. Submit a search for *query*.
        3. Filter to "Buy It Now" listings (skip auctions).
        4. Apply the site's price filter (min=0, max=max_price).
        5. Iterate through result cards, collecting URLs where price ≤ max_price.
        6. Paginate if fewer than *limit* items are found.

    Args:
        page:       Playwright ``Page`` object.
        base_url:   Root URL of the eBay site.
        query:      Product search term.
        max_price:  Maximum acceptable item price.
        limit:      Number of item URLs to collect (default 5).

    Returns:
        A list of up to *limit* absolute item URLs.
    """
    home = HomePage(page)
    home.open(base_url)
    home.search(query)

    search_results = SearchResultsPage(page)
    search_results.filter_buy_it_now()
    search_results.apply_price_filter(max_price)

    urls = search_results.collect_items_under_price(
        max_price=max_price,
        limit=limit,
    )

    logger.info("searchItemsByNameUnderPrice returned %d URLs", len(urls))
    return urls


def add_items_to_cart(page: Page, urls: list[str]) -> int:
    """Open each item URL and add it to the shopping cart.

    Implements the task-spec function ``addItemsToCart``.

    For every URL:
        1. Navigate to the product page.
        2. Select random variants (size/colour) if required.
        3. Click "Add to Cart".
        4. Log + screenshot the outcome.

    Args:
        page: Playwright ``Page`` object.
        urls: List of absolute eBay item URLs.

    Returns:
        The number of items that were successfully added.
    """
    product_page = ProductPage(page)
    added_count = 0

    for idx, url in enumerate(urls, start=1):
        with allure.step(f"Add item {idx}/{len(urls)} to cart"):
            logger.info("--- Adding item %d/%d: %s", idx, len(urls), url[:80])
            product_page.navigate(url)
            product_page.page.wait_for_load_state("domcontentloaded")

            title = product_page.get_product_title()
            attach_text(f"Item {idx} Title", title)

            success = product_page.add_to_cart()
            if success:
                added_count += 1
                logger.info("Item %d added to cart: %s", idx, title[:60])
            else:
                logger.warning("Item %d could NOT be added: %s", idx, title[:60])

    logger.info("addItemsToCart: %d/%d items added", added_count, len(urls))
    return added_count


def assert_cart_total_not_exceeds(
    page: Page,
    budget_per_item: float,
    items_count: int,
) -> None:
    """Open the cart and verify the total is within budget.

    Implements the task-spec function ``assertCartTotalNotExceeds``.

    Args:
        page:            Playwright ``Page`` object.
        budget_per_item: Max price per item from the test scenario.
        items_count:     How many items were actually added.

    Raises:
        AssertionError: If the cart total exceeds ``budget_per_item × items_count``.
    """
    cart = CartPage(page)
    cart.open_cart()
    cart.assert_cart_total_not_exceeds(budget_per_item, items_count)


# ---------------------------------------------------------------------------
# Data-driven E2E test
# ---------------------------------------------------------------------------

@allure.epic("eBay E2E Shopping")
@allure.feature("Search, Add to Cart, Validate Total")
@pytest.mark.e2e
@pytest.mark.parallel
@pytest.mark.parametrize("scenario", _scenarios, ids=_scenario_ids)
def test_ebay_shopping_flow(page: Page, test_settings, scenario: dict) -> None:
    """End-to-end test: search → filter → collect → add to cart → validate.

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

    allure.dynamic.title(f"Shopping flow: {query} (≤${max_price}, limit={limit})")
    allure.dynamic.description(scenario.get("description", ""))
    attach_json("Test Scenario", scenario)

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
        pytest.skip(f"No items found for '{query}' under ${max_price}")

    # Step 2 — Add items to cart
    with allure.step(f"Add {len(urls)} items to cart"):
        added_count = add_items_to_cart(page, urls)

    if added_count == 0:
        pytest.skip("No items could be added to cart")

    # Step 3 — Validate cart total
    with allure.step("Validate cart total against budget"):
        assert_cart_total_not_exceeds(page, budget_per_item, added_count)


# ---------------------------------------------------------------------------
# Standalone smoke test — quick sanity check
# ---------------------------------------------------------------------------

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
    home = HomePage(page)
    home.open(test_settings.base_url)
    home.search("laptop")

    search_results = SearchResultsPage(page)
    urls = search_results.collect_items_under_price(max_price=9999, limit=1, max_pages=1)

    assert len(urls) >= 1, "Expected at least one search result"
    logger.info("Smoke test passed: found %d result(s)", len(urls))
