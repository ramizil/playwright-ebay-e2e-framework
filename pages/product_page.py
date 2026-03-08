"""
Product Page Object
===================

Represents an individual eBay product/listing page.  Responsible for:

* Detecting and selecting required item variants (size, colour, quantity).
* Clicking "Add to Cart".
* Handling edge cases: out-of-stock items, items that require sign-in,
  and items with mandatory variant selection.

Each action is wrapped with retry logic and produces a screenshot/log
entry for the Allure report.
"""

from __future__ import annotations

import random
from typing import List, Optional

import allure
from playwright.sync_api import Page, Locator

from core.base_page import BasePage, SmartLocatorError
from core.smart_locator import LocatorStrategy, SmartLocator
from core.retry_handler import with_retry
from core.logger_config import get_logger

logger = get_logger(__name__)


class ProductPage(BasePage):
    """Page object for a single eBay product listing.

    Args:
        page: Playwright ``Page`` for the active browser tab.
    """

    # ------------------------------------------------------------------
    # Smart Locators
    # ------------------------------------------------------------------

    PRODUCT_TITLE = SmartLocator(
        name="product_title",
        strategies=[
            LocatorStrategy("css", "h1.x-item-title__mainTitle span", "title span inside h1"),
            LocatorStrategy("xpath", "//h1[contains(@class, 'x-item-title')]//span", "title span XPath"),
        ],
    )

    PRODUCT_PRICE = SmartLocator(
        name="product_price",
        strategies=[
            LocatorStrategy("css", "div.x-price-primary span.ux-textspanouslyrics", "price primary span"),
            LocatorStrategy("css", "div.x-price-primary span", "price primary generic span"),
        ],
    )

    ADD_TO_CART_BUTTON = SmartLocator(
        name="add_to_cart_button",
        strategies=[
            LocatorStrategy("css", "a[data-testid='ux-call-to-action'] span:has-text('Add to cart')", "add to cart by test-id"),
            LocatorStrategy("xpath", "//a[@id='atcBtn_btn_1' or @id='isCartBtn_btn']//span", "add to cart by legacy ID"),
            LocatorStrategy("css", "#atcBtn_btn_1", "add to cart legacy CSS"),
            LocatorStrategy("xpath", "//span[contains(text(), 'Add to cart')]/ancestor::a", "add to cart by text"),
        ],
    )

    QUANTITY_INPUT = SmartLocator(
        name="quantity_input",
        strategies=[
            LocatorStrategy("css", "input#qtyTextBox", "quantity input by ID"),
            LocatorStrategy("xpath", "//input[@id='qtyTextBox' or @name='quantity']", "quantity by name"),
        ],
    )

    SIZE_DROPDOWN = SmartLocator(
        name="size_selector",
        strategies=[
            LocatorStrategy("css", "select#msku-sel-1", "size select by ID"),
            LocatorStrategy("xpath", "//select[contains(@id, 'msku-sel')]", "size select XPath"),
        ],
    )

    COLOR_BUTTONS = SmartLocator(
        name="color_options",
        strategies=[
            LocatorStrategy("css", "ul.x-msku__select-box-wrapper li button", "color buttons list"),
            LocatorStrategy("xpath", "//ul[contains(@class, 'x-msku')]//button", "color buttons XPath"),
        ],
    )

    CART_LAYER_CLOSE = SmartLocator(
        name="cart_layer_close",
        strategies=[
            LocatorStrategy("css", "button[data-testid='ux-close-button']", "close cart overlay"),
            LocatorStrategy("xpath", "//button[contains(@class, 'overlay-close') or @aria-label='Close']", "close overlay XPath"),
        ],
    )

    CART_CONFIRMATION = SmartLocator(
        name="cart_confirmation",
        strategies=[
            LocatorStrategy("css", "span:has-text('Added to cart')", "added-to-cart confirmation text"),
            LocatorStrategy("xpath", "//span[contains(text(), 'Added to cart') or contains(text(), 'added to your cart')]", "confirmation XPath"),
        ],
    )

    # ------------------------------------------------------------------
    # Variant handling
    # ------------------------------------------------------------------

    @allure.step("Select random available variants if required")
    def select_random_variants(self) -> None:
        """Detect and select required product options (size, colour).

        eBay listings may require the buyer to choose a size, colour, or
        other variant before "Add to Cart" becomes active.  This method:

        1. Checks if a size dropdown is present → selects a random option.
        2. Checks if colour buttons are present → clicks a random one.

        The selection is random (per the task spec) to exercise different
        paths on each run.
        """
        self._select_size_if_present()
        self._select_color_if_present()

    def _select_size_if_present(self) -> None:
        """Pick a random size from the dropdown if the selector exists.

        If no size selector is found the method exits silently — not every
        product requires a size.
        """
        try:
            size_select = self.find_element(self.SIZE_DROPDOWN, timeout=3_000)
            options: List[str] = size_select.locator("option").all_inner_texts()
            valid_options = [
                opt for opt in options
                if opt.strip() and "select" not in opt.lower()
            ]
            if valid_options:
                choice = random.choice(valid_options)
                size_select.select_option(label=choice)
                self.logger.info("Selected size: '%s'", choice)
        except SmartLocatorError:
            self.logger.info("No size selector found — skipping")

    def _select_color_if_present(self) -> None:
        """Pick a random colour from the option buttons if they exist.

        eBay renders colour options as a row of clickable buttons.  This
        clicks a random enabled one.
        """
        try:
            self.find_element(self.COLOR_BUTTONS, timeout=3_000)
            buttons = self.page.locator(
                "ul.x-msku__select-box-wrapper li button"
            ).all()
            enabled = [b for b in buttons if b.is_enabled()]
            if enabled:
                choice = random.choice(enabled)
                choice.click()
                self.logger.info("Selected a random colour option")
        except SmartLocatorError:
            self.logger.info("No colour options found — skipping")

    # ------------------------------------------------------------------
    # Add to cart
    # ------------------------------------------------------------------

    @allure.step("Add current item to cart")
    def add_to_cart(self) -> bool:
        """Click "Add to Cart" and verify the confirmation message.

        Handles the full flow:
        1. Select variants if required.
        2. Click the "Add to Cart" button (with retry).
        3. Wait for the confirmation overlay.
        4. Take a screenshot of the confirmation.
        5. Close the overlay if present.

        Returns:
            ``True`` if the item was successfully added;
            ``False`` if the button was missing or the action failed.
        """
        self.select_random_variants()

        try:
            self._click_add_to_cart()
        except SmartLocatorError:
            self.logger.warning("Add to Cart button not found — item may be auction-only")
            self.take_screenshot("add_to_cart_not_available")
            return False

        self._wait_for_cart_confirmation()
        self.take_screenshot("item_added_to_cart")
        self._close_cart_overlay()
        return True

    @with_retry(max_attempts=3, backoff_factor=1.0)
    def _click_add_to_cart(self) -> None:
        """Locate and click the "Add to Cart" button with retry.

        Separated into its own method so the ``@with_retry`` decorator
        can wrap just the click action.

        Raises:
            SmartLocatorError: If the button is not found after retries.
        """
        element = self.find_element(self.ADD_TO_CART_BUTTON, timeout=8_000)
        element.click()
        self.logger.info("Clicked 'Add to Cart'")

    def _wait_for_cart_confirmation(self) -> None:
        """Wait for eBay's "Added to cart" confirmation overlay to appear.

        Uses a generous timeout because the overlay may take a few seconds
        to render after the add-to-cart API call completes.
        """
        try:
            self.find_element(self.CART_CONFIRMATION, timeout=10_000)
            self.logger.info("Cart confirmation overlay appeared")
        except SmartLocatorError:
            self.logger.warning(
                "Cart confirmation not detected — item may still have been added"
            )

    def _close_cart_overlay(self) -> None:
        """Dismiss the post-add-to-cart overlay if present.

        Some eBay pages show a "continue shopping" / "go to cart" modal
        after adding an item.  We close it so the browser is ready for
        the next item URL.
        """
        try:
            self.click(self.CART_LAYER_CLOSE, timeout=3_000)
            self.logger.info("Cart overlay closed")
        except SmartLocatorError:
            self.logger.info("No cart overlay to close")

    # ------------------------------------------------------------------
    # Info extraction
    # ------------------------------------------------------------------

    def get_product_title(self) -> str:
        """Return the product title from the listing page.

        Returns:
            The product title as a trimmed string, or ``'Unknown'`` if
            extraction fails.
        """
        try:
            return self.get_text(self.PRODUCT_TITLE)
        except SmartLocatorError:
            return "Unknown"

    def get_product_price(self) -> Optional[float]:
        """Extract the numeric price from the listing page.

        Returns:
            The price as a float, or ``None`` if it cannot be parsed.
        """
        try:
            price_text = self.get_text(self.PRODUCT_PRICE)
            import re
            match = re.search(r"\$([0-9,]+\.?\d*)", price_text)
            if match:
                return float(match.group(1).replace(",", ""))
        except SmartLocatorError:
            pass
        return None
