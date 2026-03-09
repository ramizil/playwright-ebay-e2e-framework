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
    # Smart Locators — Tiered strategy
    # ------------------------------------------------------------------

    # Tier 2: Auto-generated ID → CSS by aria-label, XPath fallback
    PRICE_MIN_INPUT = SmartLocator(
        name="price_filter_min",
        strategies=[
            LocatorStrategy("css", "input[aria-label*='Minimum Value']", "price min by aria-label"),
            LocatorStrategy("xpath", "//input[contains(@aria-label, 'Minimum')]", "price min by XPath attr"),
        ],
    )

    # Tier 2: Auto-generated ID → CSS by aria-label, XPath fallback
    PRICE_MAX_INPUT = SmartLocator(
        name="price_filter_max",
        strategies=[
            LocatorStrategy("css", "input[aria-label*='Maximum Value']", "price max by aria-label"),
            LocatorStrategy("xpath", "//input[contains(@aria-label, 'Maximum')]", "price max by XPath attr"),
        ],
    )

    # Tier 3: No ID → role-based, XPath by aria-label fallback
    PRICE_SUBMIT_BUTTON = SmartLocator(
        name="price_filter_submit",
        strategies=[
            LocatorStrategy("role", "button, name=Submit price range", "price submit by role"),
            LocatorStrategy("xpath", "//button[@aria-label='Submit price range']", "price submit by XPath attr"),
        ],
    )

    # Tier 3: No ID → CSS by class + data-attr, XPath fallback
    RESULT_ITEMS = SmartLocator(
        name="search_result_items",
        strategies=[
            LocatorStrategy("css", "li.s-card[data-viewport]", "result card by class + data-attr"),
            LocatorStrategy("xpath", "//ul[contains(@class,'srp-results')]//li[@data-viewport]", "result card by XPath"),
        ],
    )

    # Tier 3: No ID → CSS by class, XPath fallback
    NEXT_PAGE_BUTTON = SmartLocator(
        name="next_page_button",
        strategies=[
            LocatorStrategy("css", "a.pagination__next", "next page by class"),
            LocatorStrategy("xpath", "//a[contains(@class, 'pagination__next')]", "next page by XPath class"),
        ],
    )

    # Tier 3: No ID → CSS by class + href, XPath by href + text fallback
    BUY_IT_NOW_FILTER = SmartLocator(
        name="buy_it_now_filter",
        strategies=[
            LocatorStrategy("css", "a[href*='LH_BIN'].x-refine__single-select-link", "Buy It Now by class + href"),
            LocatorStrategy("xpath", "//a[contains(@href,'LH_BIN') and contains(.,'Buy It Now')]", "Buy It Now by XPath href + text"),
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

        eBay's current DOM uses ``li.s-card[data-viewport]`` for each
        result card, with:
        * ``a.s-card__link`` for the item URL.
        * ``.s-card__price`` for the display price.

        Items whose price cannot be parsed or exceeds ``max_price`` are
        skipped with a warning.

        Args:
            max_price: Price ceiling for inclusion.

        Returns:
            List of qualifying item URLs found on this page.
        """
        urls: List[str] = []
        self.wait(1_000)

        # Use .first to avoid strict-mode violation on multi-element locators
        item_locator = self.page.locator("li.s-card[data-viewport]")
        try:
            item_locator.first.wait_for(state="visible", timeout=10_000)
        except Exception:
            item_locator = self.page.locator("ul.srp-results li[data-viewport]")
            try:
                item_locator.first.wait_for(state="visible", timeout=5_000)
            except Exception:
                self.logger.warning("No result items found on page")
                return urls

        items = item_locator.all()
        self.logger.info("Found %d item cards on page", len(items))

        for idx, item in enumerate(items):
            try:
                price_el = item.locator(".s-card__price").first
                if not price_el.is_visible(timeout=1_000):
                    continue
                price_text = price_el.inner_text(timeout=2_000)
                price = self._parse_price(price_text)

                if price is None:
                    continue

                if price > max_price:
                    continue

                link_el = item.locator("a.s-card__link").first
                if not link_el.count():
                    link_el = item.locator("a[href*='/itm/']").first
                href = link_el.get_attribute("href", timeout=2_000)
                if href and "ebay.com" in href and "/itm/123456" not in href:
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
        * ``'$29.99'``  /  ``'US $29.99'``
        * ``'$12.00 to $18.00'`` → takes the lower bound
        * ``'$1,299.00'`` → strips comma
        * ``'ILS 171.25'``  /  ``'GBP 41.35'``  /  ``'EUR 29.99'``

        Args:
            text: Raw price string from the DOM.

        Returns:
            The price as a float, or ``None`` if parsing fails.
        """
        if not text:
            return None

        match = re.search(r"[\$£€]?\s?([0-9,]+\.?\d*)", text.strip())
        if match:
            value = match.group(1).replace(",", "")
            if value:
                return float(value)

        # Fallback: grab first decimal number in the string
        match = re.search(r"([0-9,]+\.\d{2})", text)
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
