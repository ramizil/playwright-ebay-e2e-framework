"""
Search Results Page Object
==========================

Represents the eBay search results listing.  Implements the core
``searchItemsByNameUnderPrice`` logic from the task specification:

1. Apply the site's price filter (min=0, max=maxPrice).
2. Iterate through result items and extract those whose price ≤ maxPrice.
3. If fewer than ``limit`` items are found, paginate via the "Next" button.
4. Return a list of item URLs meeting the criteria.

Paging, price extraction, and filtering all live here — keeping the test
file declarative and free of scraping logic.
"""

from __future__ import annotations

import re
from typing import List, Optional

import allure
from playwright.sync_api import Page

from core.base_page import BasePage, SmartLocatorError
from core.smart_locator import LocatorStrategy, SmartLocator
from core.retry_handler import with_retry
from core.logger_config import get_logger
from utils.allure_helper import attach_json

logger = get_logger(__name__)


class SearchResultsPage(BasePage):
    """Page object for eBay's search results / listing page.

    Args:
        page: Playwright ``Page`` for the active browser tab.
    """

    # ------------------------------------------------------------------
    # Smart Locators
    # ------------------------------------------------------------------

    PRICE_MIN_INPUT = SmartLocator(
        name="price_filter_min",
        strategies=[
            LocatorStrategy("css", "input.x-textrange__input--from", "price min by class"),
            LocatorStrategy("xpath", "//input[contains(@class, 'x-textrange__input--from')]", "price min XPath"),
        ],
    )

    PRICE_MAX_INPUT = SmartLocator(
        name="price_filter_max",
        strategies=[
            LocatorStrategy("css", "input.x-textrange__input--to", "price max by class"),
            LocatorStrategy("xpath", "//input[contains(@class, 'x-textrange__input--to')]", "price max XPath"),
        ],
    )

    PRICE_SUBMIT_BUTTON = SmartLocator(
        name="price_filter_submit",
        strategies=[
            LocatorStrategy("css", "button.x-textrange__button", "price submit by class"),
            LocatorStrategy(
                "xpath",
                "//button[contains(@class, 'x-textrange__button') or @aria-label='Submit price range']",
                "price submit XPath",
            ),
        ],
    )

    RESULT_ITEMS = SmartLocator(
        name="search_result_items",
        strategies=[
            LocatorStrategy("css", "li.s-item", "result items by li.s-item"),
            LocatorStrategy("xpath", "//li[contains(@class, 's-item')]", "result items XPath"),
        ],
    )

    NEXT_PAGE_BUTTON = SmartLocator(
        name="next_page_button",
        strategies=[
            LocatorStrategy("css", "a.pagination__next", "next page by class"),
            LocatorStrategy("xpath", "//a[contains(@class, 'pagination__next')]", "next page XPath"),
        ],
    )

    BUY_IT_NOW_FILTER = SmartLocator(
        name="buy_it_now_filter",
        strategies=[
            LocatorStrategy("css", "a.srp-format-tabs-h2__link[href*='LH_BIN']", "Buy It Now tab link"),
            LocatorStrategy("xpath", "//a[contains(@href, 'LH_BIN') and contains(text(), 'Buy It Now')]", "Buy It Now XPath"),
        ],
    )

    # ------------------------------------------------------------------
    # Price filter
    # ------------------------------------------------------------------

    @allure.step("Apply price filter: $0 – ${max_price}")
    def apply_price_filter(self, max_price: float) -> None:
        """Use eBay's price range filter to narrow results.

        Types "0" into the min field and ``max_price`` into the max field,
        then submits the filter form.  Falls back gracefully if the filter
        UI is absent (some categories don't have it).

        Args:
            max_price: Upper bound for the price filter (inclusive).
        """
        try:
            self.scroll_to_price_filter()
            self.fill(self.PRICE_MIN_INPUT, "0")
            self.fill(self.PRICE_MAX_INPUT, str(int(max_price)))
            self.click(self.PRICE_SUBMIT_BUTTON)
            self.page.wait_for_load_state("domcontentloaded")
            self.logger.info("Price filter applied: $0 – $%s", max_price)
        except SmartLocatorError:
            self.logger.warning(
                "Price filter UI not found — will filter items programmatically"
            )

    def scroll_to_price_filter(self) -> None:
        """Scroll down the page to make the price filter panel visible.

        eBay's left sidebar filters may be below the fold on large result
        sets.  This scrolls incrementally until the filter appears or we
        reach the bottom.
        """
        for _ in range(5):
            self.page.evaluate("window.scrollBy(0, 400)")
            self.wait(300)
            try:
                self.find_element(self.PRICE_MIN_INPUT, timeout=2_000)
                return
            except SmartLocatorError:
                continue
        self.logger.info("Price filter not found after scrolling — proceeding")

    # ------------------------------------------------------------------
    # "Buy It Now" filter (skip auction items)
    # ------------------------------------------------------------------

    @allure.step("Filter to 'Buy It Now' listings only")
    def filter_buy_it_now(self) -> None:
        """Click the 'Buy It Now' format tab to exclude auction listings.

        Auction items cannot be added to cart directly, so filtering to
        Buy It Now ensures every collected URL supports the add-to-cart flow.
        If the filter tab is not visible the step is skipped gracefully.
        """
        try:
            self.click(self.BUY_IT_NOW_FILTER)
            self.page.wait_for_load_state("domcontentloaded")
            self.logger.info("Filtered to Buy It Now listings")
        except SmartLocatorError:
            self.logger.warning("Buy It Now filter not found — skipping")

    # ------------------------------------------------------------------
    # Item collection with paging
    # ------------------------------------------------------------------

    @allure.step("Collect up to {limit} items under ${max_price}")
    def collect_items_under_price(
        self,
        max_price: float,
        limit: int = 5,
        max_pages: int = 5,
    ) -> List[str]:
        """Scrape item URLs whose price is at or below ``max_price``.

        Iterates through search result cards on the current page, extracts
        price and URL, and keeps items that pass the price check.  If fewer
        than ``limit`` qualifying items are found, clicks "Next" to paginate
        and continues collecting.

        Args:
            max_price:  Maximum acceptable price (inclusive).
            limit:      Number of item URLs to collect (default 5).
            max_pages:  Safety cap on how many pages to traverse.

        Returns:
            A list of absolute URLs (up to ``limit``) for qualifying items.
        """
        collected_urls: List[str] = []
        current_page = 1

        while len(collected_urls) < limit and current_page <= max_pages:
            self.logger.info(
                "Scanning page %d — collected %d/%d so far",
                current_page,
                len(collected_urls),
                limit,
            )

            page_urls = self._extract_items_from_current_page(max_price)

            for url in page_urls:
                if len(collected_urls) >= limit:
                    break
                if url not in collected_urls:
                    collected_urls.append(url)

            if len(collected_urls) >= limit:
                break

            if not self._go_to_next_page():
                self.logger.info("No more pages available")
                break

            current_page += 1

        self.logger.info(
            "Collected %d item(s) under $%.2f", len(collected_urls), max_price
        )
        attach_json("collected_item_urls", collected_urls)
        return collected_urls

    def _extract_items_from_current_page(self, max_price: float) -> List[str]:
        """Parse all result cards on the current page and filter by price.

        Each eBay search result card (``li.s-item``) contains:
        * A link (``a.s-item__link``) with the item URL.
        * A price span (``span.s-item__price``) with the display price.

        Items whose price cannot be parsed or exceeds ``max_price`` are
        skipped with a warning.

        Args:
            max_price: Price ceiling for inclusion.

        Returns:
            List of qualifying item URLs found on this page.
        """
        urls: List[str] = []
        self.wait(1_000)

        try:
            items_locator = self.find_element(self.RESULT_ITEMS, timeout=10_000)
        except SmartLocatorError:
            self.logger.warning("No result items found on page")
            return urls

        items = self.page.locator("li.s-item").all()
        self.logger.info("Found %d item cards on page", len(items))

        for idx, item in enumerate(items):
            try:
                price_text = item.locator(".s-item__price").first.inner_text(timeout=2_000)
                price = self._parse_price(price_text)

                if price is None:
                    continue

                if price > max_price:
                    continue

                link_el = item.locator("a.s-item__link").first
                href = link_el.get_attribute("href", timeout=2_000)
                if href and "ebay.com" in href:
                    urls.append(href)
                    self.logger.info(
                        "  Item #%d: $%.2f — %s", idx, price, href[:80]
                    )

            except Exception as exc:
                self.logger.debug("Skipping item #%d: %s", idx, exc)
                continue

        return urls

    @staticmethod
    def _parse_price(text: str) -> Optional[float]:
        """Extract a numeric price from eBay's display text.

        Handles formats like:
        * ``'$29.99'``
        * ``'$12.00 to $18.00'`` → takes the lower bound
        * ``'$1,299.00'`` → strips comma

        Args:
            text: Raw price string from the DOM.

        Returns:
            The price as a float, or ``None`` if parsing fails.
        """
        if not text:
            return None

        match = re.search(r"\$([0-9,]+\.?\d*)", text)
        if match:
            return float(match.group(1).replace(",", ""))
        return None

    def _go_to_next_page(self) -> bool:
        """Click the "Next" pagination button if it exists.

        Returns:
            ``True`` if navigation succeeded; ``False`` if there is no next page.
        """
        try:
            self.click(self.NEXT_PAGE_BUTTON, timeout=5_000)
            self.page.wait_for_load_state("domcontentloaded")
            self.wait(1_000)
            self.logger.info("Navigated to next results page")
            return True
        except (SmartLocatorError, Exception):
            return False
