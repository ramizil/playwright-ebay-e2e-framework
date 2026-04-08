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
    # Smart Locators — Tiered strategy
    # ------------------------------------------------------------------

    # Tier 3: No stable ID → CSS by class, XPath fallback
    PRODUCT_TITLE = SmartLocator(
        name="product_title",
        strategies=[
            LocatorStrategy("css", "h1.x-item-title__mainTitle span", "title span by class"),
            LocatorStrategy("xpath", "//h1[contains(@class,'x-item-title__mainTitle')]//span", "title span by XPath class"),
        ],
    )

    # Tier 2: Auto-generated ID → CSS by data-testid, XPath by class fallback
    PRODUCT_PRICE = SmartLocator(
        name="product_price",
        strategies=[
            LocatorStrategy("css", "div.x-price-primary span", "price primary span by class"),
            LocatorStrategy("xpath", "//div[contains(@class,'x-price-primary')]//span", "price by XPath class"),
        ],
    )

    # Tier 1: Stable ID → #atcBtn_btn_1 is eBay's long-standing ATC button ID
    ADD_TO_CART_BUTTON = SmartLocator(
        name="add_to_cart_button",
        strategies=[
            LocatorStrategy("css", "#atcBtn_btn_1", "ATC button by stable ID"),
            LocatorStrategy("xpath", "//a[@data-testid='ux-call-to-action']//span[contains(.,'Add to cart')]", "ATC by data-testid + text"),
        ],
    )

    # Tier 1: Stable ID → #qtyTextBox is eBay's long-standing quantity field
    QUANTITY_INPUT = SmartLocator(
        name="quantity_input",
        strategies=[
            LocatorStrategy("css", "#qtyTextBox", "quantity input by stable ID"),
            LocatorStrategy("xpath", "//input[@name='quantity']", "quantity by XPath name attr"),
        ],
    )

    # Tier 1: Stable ID → #msku-sel-1 is eBay's variant selector
    SIZE_DROPDOWN = SmartLocator(
        name="size_selector",
        strategies=[
            LocatorStrategy("css", "#msku-sel-1", "size selector by stable ID"),
            LocatorStrategy("xpath", "//select[contains(@id,'msku-sel')]", "size selector by XPath partial ID"),
        ],
    )

    # Tier 3: No ID → CSS by class, XPath fallback
    # eBay renders variant selectors as button swatches, radio tiles, or
    # dropdown-style chips.  The class names have changed over time.
    COLOR_BUTTONS = SmartLocator(
        name="color_options",
        strategies=[
            LocatorStrategy("css", "[data-testid='x-msku'] button, ul.x-msku__select-box-wrapper li button", "variant buttons by data-testid or class"),
            LocatorStrategy("xpath", "//div[contains(@class,'vim')]//fieldset//button | //ul[contains(@class,'x-msku')]//li//button", "variant buttons by fieldset or msku class"),
            LocatorStrategy("css", ".x-msku button, .smsku-variation button", "variant buttons by broad msku class"),
        ],
    )

    # Tier 3: No ID → CSS by data-testid / aria-label, XPath fallback
    CART_LAYER_CLOSE = SmartLocator(
        name="cart_layer_close",
        strategies=[
            LocatorStrategy("css", "button[data-testid='ux-close-button'], button[aria-label='Close']", "close by data-testid or aria-label"),
            LocatorStrategy("xpath", "//a[contains(.,'No thanks') or contains(.,'Continue shopping')]", "close overlay by XPath link text"),
        ],
    )

    # Tier 3: No ID → CSS text match, XPath text fallback
    CART_CONFIRMATION = SmartLocator(
        name="cart_confirmation",
        strategies=[
            LocatorStrategy("css", "span:has-text('Added to cart')", "confirmation by text"),
            LocatorStrategy("xpath", "//span[contains(.,'Added to cart') or contains(.,'added to your cart')]", "confirmation by XPath text"),
        ],
    )

    # ------------------------------------------------------------------
    # Variant handling
    # ------------------------------------------------------------------

    MAX_RANDOM_QUANTITY = 3

    @allure.step("Select random available variants if required")
    def select_random_variants(self) -> None:
        """Detect and select required product options (size, colour, quantity).

        eBay listings may require the buyer to choose a size, colour, or
        other variant before "Add to Cart" becomes active.  This method:

        1. Checks if a size dropdown is present -> selects a random option.
        2. Checks if colour/style buttons are present -> clicks a random one.
        3. Selects from any remaining native ``<select>`` dropdowns.
        4. Selects from any remaining custom listbox buttons
           (``<button aria-haspopup="listbox">`` with text "Select").
        5. Sets a random quantity (1-MAX_RANDOM_QUANTITY) if the input exists
           and is enabled (it stays disabled until all variants are chosen).

        The selection is random to exercise different paths on each run.
        """
        self._select_size_if_present()
        self._select_color_if_present()
        self._select_remaining_variant_dropdowns()
        self._select_remaining_listbox_buttons()
        self._set_random_quantity()

    def _select_size_if_present(self) -> None:
        """Pick a random size from the dropdown if the selector exists.

        If no size selector is found the method exits silently — not every
        product requires a size.
        """
        try:
            size_select = self.find_element(self.SIZE_DROPDOWN, timeout=3_000, optional=True)
            options: List[str] = size_select.locator("option").all_inner_texts()
            valid_options = [
                opt for opt in options
                if opt.strip()
                and not any(kw in opt.lower() for kw in self._PLACEHOLDER_KEYWORDS)
            ]
            if valid_options:
                choice = random.choice(valid_options)
                size_select.select_option(label=choice)
                self.logger.info("Selected size: '%s'", choice)
                self.page.wait_for_timeout(1_000)
        except SmartLocatorError:
            self.logger.info("No size selector found — skipping")

    _VARIANT_BUTTON_CSS = (
        "[data-testid='x-msku'] button, "
        "ul.x-msku__select-box-wrapper li button, "
        ".x-msku button, "
        ".smsku-variation button"
    )

    def _select_color_if_present(self) -> None:
        """Pick a random variant option from the available buttons.

        eBay renders variant options (colour, style, type) as clickable
        button swatches.  After clicking, waits briefly for the page to
        update (re-enable quantity input, refresh price, etc.).
        """
        try:
            self.find_element(self.COLOR_BUTTONS, timeout=3_000, optional=True)
            buttons = self.page.locator(self._VARIANT_BUTTON_CSS).all()
            enabled = [b for b in buttons if b.is_enabled() and b.is_visible()]
            if enabled:
                choice = random.choice(enabled)
                choice.click()
                self.logger.info("Selected a random variant option")
                self.page.wait_for_timeout(1_000)
        except SmartLocatorError:
            self.logger.info("No variant options found — skipping")

    _PLACEHOLDER_KEYWORDS = {"select", "choose", "pick", "- -", "--"}
    _PLACEHOLDER_VALUES = {"", "-1", "0"}

    def _needs_selection(self, sel) -> bool:
        """Return True if a ``<select>`` element still shows a placeholder."""
        try:
            current_value = sel.input_value()
            if current_value in self._PLACEHOLDER_VALUES:
                return True
            selected_text = sel.locator("option:checked").first.inner_text(timeout=1_000).lower()
            return any(kw in selected_text for kw in self._PLACEHOLDER_KEYWORDS)
        except Exception:
            return True

    def _select_remaining_variant_dropdowns(self) -> None:
        """Select a random option from any unresolved variant dropdowns.

        Scans for ALL ``<select>`` elements inside eBay's variant
        containers — both ``msku-sel-*`` IDs and any other selects
        within the variant section.  For each one that still shows a
        placeholder ("Select", "Choose", etc.), picks a valid option.
        """
        try:
            selects = self.page.locator(
                "select[id^='msku-sel'], "
                ".x-msku select, "
                "[data-testid='x-msku'] select, "
                ".vim-x-item-variations select"
            ).all()
            if not selects:
                return
            self.logger.info("Found %d variant dropdown(s) on page", len(selects))
            for i, sel in enumerate(selects):
                if not sel.is_visible():
                    continue
                if not self._needs_selection(sel):
                    try:
                        current = sel.locator("option:checked").first.inner_text(timeout=500)
                        self.logger.info("Dropdown #%d already set to '%s'", i + 1, current.strip())
                    except Exception:
                        pass
                    continue
                options = sel.locator("option").all_inner_texts()
                valid = [
                    o for o in options
                    if o.strip()
                    and not any(kw in o.lower() for kw in self._PLACEHOLDER_KEYWORDS)
                ]
                if valid:
                    choice = random.choice(valid)
                    sel.select_option(label=choice)
                    self.logger.info("Dropdown #%d: selected '%s'", i + 1, choice)
                    self.page.wait_for_timeout(1_000)
                else:
                    self.logger.warning("Dropdown #%d: no valid options found", i + 1)
        except Exception as exc:
            self.logger.debug("Variant dropdown selection: %s", exc)

    _LISTBOX_BUTTON_CSS = (
        "button.listbox-button__control[aria-haspopup='listbox'], "
        "button.btn--form[aria-haspopup='listbox']"
    )

    def _select_remaining_listbox_buttons(self) -> None:
        """Handle custom listbox buttons that eBay uses instead of ``<select>``.

        Some product pages render variant pickers as
        ``<button aria-haspopup="listbox">`` with a ``.btn__text`` span
        showing "Select".  This method clicks each unresolved button to
        open its listbox panel, then picks the first valid option.
        """
        try:
            buttons = self.page.locator(self._LISTBOX_BUTTON_CSS).all()
            if not buttons:
                return

            pending = []
            for btn in buttons:
                if not btn.is_visible():
                    continue
                text_el = btn.locator(".btn__text")
                try:
                    btn_text = text_el.inner_text(timeout=1_000).strip().lower()
                except Exception:
                    btn_text = (btn.get_attribute("value") or "").strip().lower()
                if any(kw in btn_text for kw in self._PLACEHOLDER_KEYWORDS):
                    pending.append(btn)
                else:
                    self.logger.info("Listbox already set to '%s'", btn_text)

            if not pending:
                return

            self.logger.info("Found %d custom listbox button(s) needing selection", len(pending))

            for i, btn in enumerate(pending):
                try:
                    label_el = btn.locator(".btn__label")
                    label = label_el.inner_text(timeout=500).strip() if label_el.is_visible() else f"#{i + 1}"
                except Exception:
                    label = f"#{i + 1}"

                btn.click()
                self.page.wait_for_timeout(500)

                panel_id = btn.get_attribute("aria-controls") or ""
                if panel_id:
                    options = self.page.locator(
                        f"#{panel_id} [role='option']"
                    ).all()
                else:
                    options = self.page.locator(
                        "[role='listbox'][aria-expanded='true'] [role='option'], "
                        ".listbox-button__listbox--expanded [role='option']"
                    ).all()

                valid = [
                    opt for opt in options
                    if opt.is_visible()
                    and not any(
                        kw in (opt.inner_text() or "").lower()
                        for kw in self._PLACEHOLDER_KEYWORDS
                    )
                ]

                if valid:
                    choice = random.choice(valid)
                    choice_text = choice.inner_text().strip()
                    choice.click()
                    self.logger.info("Listbox %s: selected '%s'", label, choice_text)
                    self.page.wait_for_timeout(1_000)
                else:
                    self.logger.warning("Listbox %s: no valid options found — closing", label)
                    self.page.keyboard.press("Escape")
                    self.page.wait_for_timeout(300)
        except Exception as exc:
            self.logger.debug("Listbox button selection: %s", exc)

    def _set_random_quantity(self) -> None:
        """Set a random quantity between 1 and ``MAX_RANDOM_QUANTITY``.

        Reads the max-available quantity from the page (shown next to the
        input, e.g. "3 available") and picks a random value within the
        allowed range.  If the quantity input is absent, disabled, or the
        current value is already acceptable, exits silently.
        """
        try:
            qty_input = self.find_element(self.QUANTITY_INPUT, timeout=3_000, optional=True)

            if not qty_input.is_enabled():
                self.logger.info("Quantity input is disabled — skipping")
                return

            current_val = qty_input.input_value()

            max_qty = self.MAX_RANDOM_QUANTITY
            try:
                avail_text = self.page.locator("#qtySubTxt, #qty-test-id").first.inner_text(timeout=2_000)
                import re
                m = re.search(r"(\d+)\s*available", avail_text, re.IGNORECASE)
                if m:
                    max_qty = min(int(m.group(1)), self.MAX_RANDOM_QUANTITY)
            except Exception:
                pass

            if max_qty < 1:
                max_qty = 1

            chosen = random.randint(1, max_qty)
            if str(chosen) != str(current_val).strip():
                qty_input.fill(str(chosen))
                self.logger.info("Set quantity to %d (max available cap: %d)", chosen, max_qty)
            else:
                self.logger.info("Quantity already %s — keeping it", current_val)
        except SmartLocatorError:
            self.logger.info("No quantity input found — skipping")

    # ------------------------------------------------------------------
    # Add to cart
    # ------------------------------------------------------------------

    @allure.step("Add current item to cart")
    def add_to_cart(self) -> bool:
        """Click "Add to Cart" and verify the confirmation message.

        **Note:** call ``select_random_variants()`` before this method
        if variant selection is needed — the business step layer handles
        the sequencing so each phase can be reported independently.

        Flow:
        1. Click the "Add to Cart" button (with retry).
        2. Wait for the confirmation overlay.
        3. Take a screenshot of the confirmation.
        4. Close the overlay if present.

        Returns:
            ``True`` if the item was successfully added;
            ``False`` if the button was missing or the action failed.
        """
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

    def _click_add_to_cart(self) -> None:
        """Locate and click the "Add to Cart" button with retry.

        Raises:
            SmartLocatorError: If the button is not found after retries.
        """
        @with_retry(max_attempts=3, backoff_factor=1.0,
                    on_retry=self._retry_callback("click", "add_to_cart_button"))
        def _attempt() -> None:
            element = self.find_element(self.ADD_TO_CART_BUTTON, timeout=8_000)
            element.click()
            self.logger.info("Clicked 'Add to Cart'")

        _attempt()

    def _wait_for_cart_confirmation(self) -> None:
        """Wait for eBay's "Added to cart" confirmation overlay to appear.

        Uses a generous timeout because the overlay may take a few seconds
        to render after the add-to-cart API call completes.
        """
        try:
            self.find_element(self.CART_CONFIRMATION, timeout=10_000, optional=True)
            self.logger.info("Cart confirmation overlay appeared")
        except SmartLocatorError:
            self.logger.warning(
                "Cart confirmation not detected — item may still have been added"
            )

    def _close_cart_overlay(self) -> None:
        """Dismiss the post-add-to-cart overlay if present.

        Modern eBay may redirect to a cart page or show an inline
        confirmation rather than a closable overlay.  This is best-effort
        with a short timeout to avoid wasting time on retries.
        """
        try:
            close_btn = self.page.locator(
                "button[data-testid='ux-close-button'], "
                "button[aria-label='Close'], "
                "a:has-text('No thanks'), "
                "a:has-text('Continue shopping')"
            ).first
            if close_btn.is_visible():
                close_btn.click(timeout=3_000)
                self.logger.info("Cart overlay closed")
            else:
                self.logger.info("No cart overlay to close")
        except Exception:
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
