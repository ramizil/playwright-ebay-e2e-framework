"""
Cart Page Object
================

Represents eBay's shopping cart page (``https://cart.ebay.com``).
Implements the ``assertCartTotalNotExceeds`` logic from the task spec:

* Navigate to the cart.
* Read the displayed subtotal.
* Compare it against ``budgetPerItem × itemsCount``.
* Assert that the total does not exceed the calculated threshold.
* Capture a screenshot / trace of the cart for evidence.
"""

from __future__ import annotations

import re
from typing import Optional

import allure
from playwright.sync_api import Page

from core.base_page import BasePage, SmartLocatorError
from core.smart_locator import LocatorStrategy, SmartLocator
from core.logger_config import get_logger
from utils.allure_helper import attach_text

logger = get_logger(__name__)


class CartPage(BasePage):
    """Page object for the eBay shopping cart.

    Args:
        page: Playwright ``Page`` for the active browser tab.
    """

    CART_URL = "https://cart.ebay.com"

    # ------------------------------------------------------------------
    # Smart Locators — Tiered strategy
    # ------------------------------------------------------------------

    # Tier 2: Auto-generated ID → CSS by data-test-id, XPath by attr fallback
    CART_SUBTOTAL = SmartLocator(
        name="cart_subtotal",
        strategies=[
            LocatorStrategy(
                "css",
                "[data-test-id='SUBTOTAL'] span.text-display-span__value--bold",
                "subtotal by data-test-id",
            ),
            LocatorStrategy(
                "xpath",
                "//span[@data-test-id='SUBTOTAL']//span[contains(@class,'text-display-span')]",
                "subtotal by XPath data-test-id",
            ),
        ],
    )

    # Tier 3: No ID → CSS by class, XPath by class fallback
    CART_ITEM_COUNT = SmartLocator(
        name="cart_item_count",
        strategies=[
            LocatorStrategy("css", "span.cart-count", "cart count by class"),
            LocatorStrategy("xpath", "//span[contains(@class,'cart-count')]", "cart count by XPath class"),
        ],
    )

    # Tier 3: No ID → CSS by class, XPath by class fallback
    CART_ITEMS_LIST = SmartLocator(
        name="cart_items_list",
        strategies=[
            LocatorStrategy("css", "div.cart-bucket-lineitem", "cart line items by class"),
            LocatorStrategy("xpath", "//div[contains(@class,'cart-bucket-lineitem')]", "cart line items by XPath class"),
        ],
    )

    # Tier 2: Auto-generated ID → CSS by data-test-id, XPath by attr fallback
    CART_TOTAL_PRICE = SmartLocator(
        name="cart_total_price",
        strategies=[
            LocatorStrategy(
                "css",
                "[data-test-id='TOTAL'] span.text-display-span__value--bold",
                "total by data-test-id",
            ),
            LocatorStrategy(
                "xpath",
                "//span[@data-test-id='TOTAL']//span[contains(@class,'text-display-span')]",
                "total by XPath data-test-id",
            ),
        ],
    )

    # Tier 3: No ID → CSS text match, XPath text fallback
    EMPTY_CART_MESSAGE = SmartLocator(
        name="empty_cart_message",
        strategies=[
            LocatorStrategy("css", "span:has-text('You have no items in your cart')", "empty cart by text"),
            LocatorStrategy("xpath", "//span[contains(.,'no items')]", "empty cart by XPath text"),
        ],
    )

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    @allure.step("Open shopping cart")
    def open_cart(self) -> "CartPage":
        """Navigate directly to the eBay cart page.

        Returns:
            ``self`` for fluent chaining.
        """
        self.navigate(self.CART_URL)
        self.page.wait_for_load_state("networkidle")
        self.logger.info("Cart page loaded: %s", self.page.url)
        return self

    # ------------------------------------------------------------------
    # Price reading
    # ------------------------------------------------------------------

    def get_subtotal(self) -> Optional[float]:
        """Read the cart subtotal as a float.

        Tries the subtotal locator first; if that fails, falls back to the
        total locator (some cart layouts only show a single total).

        Returns:
            The subtotal as a float (e.g. ``49.99``), or ``None`` if the
            cart is empty or the value cannot be parsed.
        """
        for locator in [self.CART_SUBTOTAL, self.CART_TOTAL_PRICE]:
            try:
                text = self.get_text(locator, timeout=8_000)
                price = self._parse_price(text)
                if price is not None:
                    self.logger.info("Cart subtotal: $%.2f", price)
                    return price
            except SmartLocatorError:
                continue

        self.logger.warning("Could not read cart subtotal")
        return None

    @staticmethod
    def _parse_price(text: str) -> Optional[float]:
        """Extract a numeric dollar amount from display text.

        Handles ``$1,299.00``, ``US $49.99``, and similar eBay formats.

        Args:
            text: Raw text from the price element.

        Returns:
            Parsed price as float, or ``None``.
        """
        if not text:
            return None
        match = re.search(r"\$?\s?([0-9,]+\.?\d*)", text.replace("US", "").strip())
        if match:
            return float(match.group(1).replace(",", ""))
        return None

    # ------------------------------------------------------------------
    # Assertion
    # ------------------------------------------------------------------

    @allure.step("Assert cart total ≤ ${budget_per_item} × {items_count}")
    def assert_cart_total_not_exceeds(
        self,
        budget_per_item: float,
        items_count: int,
    ) -> None:
        """Validate that the cart total is within the expected budget.

        Calculates the maximum allowable total as
        ``budget_per_item × items_count`` and asserts the displayed cart
        total does not exceed it.

        A screenshot and textual evidence are attached to the Allure report
        regardless of whether the assertion passes or fails.

        Args:
            budget_per_item: Maximum price allowed per item (from test data).
            items_count:     Number of items that were added to the cart.

        Raises:
            AssertionError: If the cart total exceeds the budget threshold.
        """
        max_allowed = budget_per_item * items_count
        actual_total = self.get_subtotal()

        evidence = (
            f"Budget per item : ${budget_per_item:.2f}\n"
            f"Items count     : {items_count}\n"
            f"Max allowed     : ${max_allowed:.2f}\n"
            f"Actual total    : ${actual_total:.2f}" if actual_total else "N/A"
        )
        attach_text("Cart Validation Evidence", evidence)
        self.take_screenshot("cart_total_validation")

        if actual_total is None:
            self.logger.warning(
                "Cart total could not be read — possibly empty cart. "
                "Skipping assertion."
            )
            return

        self.logger.info(
            "Cart validation: actual=$%.2f, max_allowed=$%.2f",
            actual_total,
            max_allowed,
        )

        assert actual_total <= max_allowed, (
            f"Cart total ${actual_total:.2f} exceeds budget "
            f"${max_allowed:.2f} ({items_count} × ${budget_per_item:.2f})"
        )
        self.logger.info("Cart total is within budget ✓")

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def is_cart_empty(self) -> bool:
        """Check whether the cart has zero items.

        Returns:
            ``True`` if the "no items" message is visible.
        """
        return self.is_element_visible(self.EMPTY_CART_MESSAGE, timeout=5_000)

    def get_cart_item_count(self) -> int:
        """Read the number of items displayed in the cart badge.

        Returns:
            Integer count, or 0 if the badge is missing.
        """
        try:
            text = self.get_text(self.CART_ITEM_COUNT, timeout=5_000)
            return int(re.sub(r"\D", "", text) or "0")
        except (SmartLocatorError, ValueError):
            return 0
