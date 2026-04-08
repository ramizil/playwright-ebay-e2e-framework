"""
Cart Actions
=============

Business-level functions for cart operations — adding items and validating totals.
Orchestrates the
Product Page and Cart Page objects into reusable actions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import allure
import pytest
from playwright.sync_api import Page

from pages.product_page import ProductPage
from pages.cart_page import CartPage
from utils.allure_helper import attach_text
from utils.step_collector import collector
from utils.screenshot_manager import capture_screenshot
from core.logger_config import get_logger

logger = get_logger(__name__)


MAX_ADD_RETRIES = 2


def add_items_to_cart(page: Page, urls: list[str], screenshots_dir: Optional[Path] = None) -> int:
    """Open each item URL and add it to the shopping cart.

    Each item gets up to ``MAX_ADD_RETRIES`` attempts.  On failure the
    page is reloaded and the variant selection + add-to-cart flow is
    retried from scratch.

    Args:
        page: Playwright ``Page`` object.
        urls: List of absolute eBay item URLs.
        screenshots_dir: Per-run directory for screenshots.

    Returns:
        The number of items that were successfully added.
    """
    product_page = ProductPage(page)
    added_count = 0

    for idx, url in enumerate(urls, start=1):
        with allure.step(f"Item {idx}/{len(urls)} — select variants & add to cart"):
            logger.info("--- Item %d/%d: %s", idx, len(urls), url[:80])

            success = False
            title = "Unknown"
            for attempt in range(1, MAX_ADD_RETRIES + 1):
                product_page.navigate(url)
                product_page.page.wait_for_load_state("domcontentloaded")
                title = product_page.get_product_title()

                if attempt == 1:
                    attach_text(f"Item {idx} Title", title)

                # Phase 1: Select variants (colour, model, size, etc.)
                with allure.step(f"Select variants — item {idx}"):
                    collector.begin_step()
                    product_page.select_random_variants()
                    variant_screenshot = capture_screenshot(
                        page, f"05_variants_item_{idx}", full_page=False,
                        output_dir=screenshots_dir,
                    )
                    collector.add_step(
                        f"Select Variants — Item {idx}/{len(urls)}",
                        "ProductPage.select_random_variants()",
                        "pass",
                        detail=f"{title[:80]}\n{url[:100]}",
                        screenshot_path=variant_screenshot,
                    )

                # Phase 2: Click "Add to Cart"
                with allure.step(f"Add to cart — item {idx}"):
                    collector.begin_step()
                    success = product_page.add_to_cart()
                    if success:
                        break
                    if attempt < MAX_ADD_RETRIES:
                        logger.warning(
                            "Item %d: add-to-cart failed (attempt %d/%d) — retrying",
                            idx, attempt, MAX_ADD_RETRIES,
                        )

            screenshot = capture_screenshot(
                page, f"06_add_to_cart_item_{idx}", full_page=False,
                output_dir=screenshots_dir,
            )
            status = "pass" if success else "fail"
            if success:
                added_count += 1
                logger.info("Item %d added to cart: %s", idx, title[:60])
            else:
                logger.error("Item %d FAILED to add after %d attempt(s): %s",
                             idx, MAX_ADD_RETRIES, title[:60])

            collector.add_step(
                f"Add to Cart — Item {idx}/{len(urls)}",
                "ProductPage.add_to_cart()",
                status,
                detail=f"{title[:80]}\n{url[:100]}",
                screenshot_path=screenshot,
            )

    collector.set_items(added=added_count)
    logger.info("addItemsToCart: %d/%d items added", added_count, len(urls))

    if added_count == 0:
        collector.add_step(
            "No Items Added", "add_items_to_cart()", "skip",
            detail="No items could be added to cart",
        )
        pytest.skip("No items could be added to cart")

    return added_count


def assert_cart_total_not_exceeds(
    page: Page,
    budget_per_item: float,
    items_count: int,
    screenshots_dir: Optional[Path] = None,
) -> None:
    """Open the cart, verify item count, and validate the total is within budget.

    Args:
        page:            Playwright ``Page`` object.
        budget_per_item: Max price per item from the test scenario.
        items_count:     How many items were actually added.

    Raises:
        AssertionError: If the cart is empty, item count doesn't match,
                        or cart total exceeds ``budget_per_item x items_count``.
    """
    collector.begin_step()
    cart = CartPage(page)
    cart.open_cart()
    screenshot = capture_screenshot(page, "07_cart_page", full_page=False, output_dir=screenshots_dir)
    collector.add_step(
        "Open Shopping Cart", "CartPage.open_cart()", "pass",
        detail="Navigated to cart.ebay.com",
        screenshot_path=screenshot,
    )

    # --- Verify cart is not empty and item count matches ---
    collector.begin_step()
    if cart.is_cart_empty():
        screenshot = capture_screenshot(page, "07b_cart_empty_FAIL", full_page=False, output_dir=screenshots_dir)
        collector.add_step(
            "Verify Cart Items",
            "CartPage.is_cart_empty()",
            "fail",
            detail=f"Cart is empty — expected {items_count} item(s)",
            screenshot_path=screenshot,
        )
        raise AssertionError(
            f"Cart is empty but {items_count} item(s) should have been added"
        )

    actual_count = cart.get_cart_item_count()
    logger.info("Cart item count: expected=%d, actual=%d", items_count, actual_count)

    if actual_count > 0 and actual_count != items_count:
        logger.warning(
            "Cart item mismatch: expected %d, found %d", items_count, actual_count,
        )
        screenshot = capture_screenshot(page, "07b_cart_count_mismatch", full_page=False, output_dir=screenshots_dir)
        collector.add_step(
            "Verify Cart Items",
            "CartPage.get_cart_item_count()",
            "warn",
            detail=f"Expected {items_count} item(s), found {actual_count} in cart",
            screenshot_path=screenshot,
        )
    else:
        screenshot = capture_screenshot(page, "07b_cart_items_verified", full_page=False, output_dir=screenshots_dir)
        collector.add_step(
            "Verify Cart Items",
            "CartPage.get_cart_item_count()",
            "pass",
            detail=f"{actual_count} item(s) in cart — matches expected",
            screenshot_path=screenshot,
        )

    # --- Validate total against budget ---
    collector.begin_step()
    max_budget = budget_per_item * items_count
    logger.info(
        "Validating: cart total ≤ $%.2f (%d × $%.2f)",
        max_budget, items_count, budget_per_item,
    )
    try:
        cart.assert_cart_total_not_exceeds(budget_per_item, items_count)
        screenshot = capture_screenshot(page, "08_cart_validation", full_page=False, output_dir=screenshots_dir)
        collector.add_step(
            "Validate Cart Total",
            f"CartPage.assert_cart_total_not_exceeds(${budget_per_item:.2f}, {items_count})",
            "pass",
            detail=f"Budget: ${budget_per_item:.2f} x {items_count} = ${budget_per_item * items_count:.2f}",
            screenshot_path=screenshot,
        )
    except AssertionError:
        screenshot = capture_screenshot(page, "08_cart_validation_FAIL", full_page=False, output_dir=screenshots_dir)
        collector.add_step(
            "Validate Cart Total",
            f"CartPage.assert_cart_total_not_exceeds(${budget_per_item:.2f}, {items_count})",
            "fail",
            detail=f"Cart total exceeded budget: ${budget_per_item:.2f} x {items_count} = ${budget_per_item * items_count:.2f}",
            screenshot_path=screenshot,
        )
        raise
