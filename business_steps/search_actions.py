"""
Search Actions
==============

Business-level function that implements the task-spec requirement
``searchItemsByNameUnderPrice``.  Orchestrates the Home Page and
Search Results page objects into a single reusable action.

This module is imported by test files and can also be called from
the GUI runner or any future test scenario that needs search + collect.
"""

from __future__ import annotations

from playwright.sync_api import Page

from pages.home_page import HomePage
from pages.search_results_page import SearchResultsPage
from utils.step_collector import collector
from utils.screenshot_manager import capture_screenshot
from core.logger_config import get_logger

logger = get_logger(__name__)


def search_items_by_name_under_price(
    page: Page,
    base_url: str,
    query: str,
    max_price: float,
    limit: int = 5,
) -> list[str]:
    """Search eBay for items matching *query* that cost <= *max_price*.

    Implements the task-spec function ``searchItemsByNameUnderPrice``.

    Flow:
        1. Open eBay home page.
        2. Submit a search for *query*.
        3. Filter to "Buy It Now" listings (skip auctions).
        4. Apply the site's price filter (min=0, max=max_price).
        5. Iterate through result cards, collecting URLs where price <= max_price.
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
    collector.begin_step()
    home = HomePage(page)
    home.open(base_url)
    screenshot = capture_screenshot(page, "01_home_page", full_page=False)
    collector.add_step(
        "Open eBay Home Page", "HomePage.open()", "pass",
        detail=f"Navigated to {base_url}",
        screenshot_path=screenshot,
    )

    collector.begin_step()
    home.search(query)
    screenshot = capture_screenshot(page, "02_search_results", full_page=False)
    collector.add_step(
        f"Search for '{query}'", f"HomePage.search('{query}')", "pass",
        detail="Entered search term and submitted",
        screenshot_path=screenshot,
    )

    search_results = SearchResultsPage(page)

    collector.begin_step()
    search_results.filter_buy_it_now()
    screenshot = capture_screenshot(page, "03_buy_it_now_filter", full_page=False)
    collector.add_step(
        "Apply 'Buy It Now' Filter", "SearchResultsPage.filter_buy_it_now()", "pass",
        detail="Filtered results to fixed-price listings only",
        screenshot_path=screenshot,
    )

    collector.begin_step()
    search_results.apply_price_filter(max_price)
    screenshot = capture_screenshot(page, "04_price_filter", full_page=False)
    collector.add_step(
        f"Apply Price Filter ($0\u2013${max_price:.0f})",
        f"SearchResultsPage.apply_price_filter({max_price})", "pass",
        detail=f"Set price range: $0 \u2013 ${max_price:.2f}",
        screenshot_path=screenshot,
    )

    collector.begin_step()
    urls = search_results.collect_items_under_price(
        max_price=max_price,
        limit=limit,
    )
    screenshot = capture_screenshot(page, "05_collected_items", full_page=False)
    collector.add_step(
        f"Collect Items (found {len(urls)}/{limit})",
        f"SearchResultsPage.collect_items_under_price(max_price={max_price}, limit={limit})",
        "pass" if urls else "warn",
        detail=f"Collected {len(urls)} item URLs under ${max_price:.2f}",
        screenshot_path=screenshot,
    )
    collector.set_items(found=len(urls))

    logger.info("searchItemsByNameUnderPrice returned %d URLs", len(urls))
    return urls
