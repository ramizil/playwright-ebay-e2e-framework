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
from playwright.sync_api import Page

from pages.product_page import ProductPage
from pages.cart_page import CartPage
from utils.allure_helper import attach_text
from utils.step_collector import collector
from utils.screenshot_manager import capture_screenshot
from core.logger_config import get_logger

logger = get_logger(__name__)


def add_items_to_cart(page: Page, urls: list[str], screenshots_dir: Optional[Path] = None) -> int:
    """    Open each item URL and add it to the shopping cart.

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
            collector.begin_step()
            logger.info("--- Adding item %d/%d: %s", idx, len(urls), url[:80])
            product_page.navigate(url)
            product_page.page.wait_for_load_state("domcontentloaded")

            title = product_page.get_product_title()
            attach_text(f"Item {idx} Title", title)

            success = product_page.add_to_cart()
            screenshot = capture_screenshot(
                page, f"06_add_to_cart_item_{idx}", full_page=False,
                output_dir=screenshots_dir,
            )
            status = "pass" if success else "warn"
            if success:
                added_count += 1
                logger.info("Item %d added to cart: %s", idx, title[:60])
            else:
                logger.warning("Item %d could NOT be added: %s", idx, title[:60])

            collector.add_step(
                f"Add Item {idx}/{len(urls)} to Cart",
                "ProductPage.add_to_cart()",
                status,
                detail=f"{title[:80]}\n{url[:100]}",
                screenshot_path=screenshot,
            )

    collector.set_items(added=added_count)
    logger.info("addItemsToCart: %d/%d items added", added_count, len(urls))
    return added_count


def assert_cart_total_not_exceeds(
    page: Page,
    budget_per_item: float,
    items_count: int,
    screenshots_dir: Optional[Path] = None,
) -> None:
    """Open the cart and verify the total is within budget.

    Args:
        page:            Playwright ``Page`` object.
        budget_per_item: Max price per item from the test scenario.
        items_count:     How many items were actually added.

    Raises:
        AssertionError: If the cart total exceeds ``budget_per_item x items_count``.
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
