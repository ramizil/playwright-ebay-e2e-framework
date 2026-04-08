"""
Locator Validator
=================

Validates all SmartLocator definitions against the live eBay site
without running any tests. Shows which strategies work and which don't.

Usage:
    python validate_locators.py
    python validate_locators.py --page search    # only SearchResultsPage
    python validate_locators.py --headed         # show browser
"""

from __future__ import annotations

import argparse
import sys

from playwright.sync_api import sync_playwright, Page

from core.smart_locator import SmartLocator, LocatorStrategy


# --- Collect all SmartLocators from page objects ---

def _get_locators_from_class(cls) -> list[tuple[str, SmartLocator]]:
    results = []
    for attr_name in dir(cls):
        attr = getattr(cls, attr_name, None)
        if isinstance(attr, SmartLocator):
            results.append((f"{cls.__name__}.{attr_name}", attr))
    return results


def _resolve_locator(page: Page, strategy: LocatorStrategy):
    match strategy.method:
        case "css":
            return page.locator(strategy.value)
        case "xpath":
            return page.locator(f"xpath={strategy.value}")
        case "text":
            return page.get_by_text(strategy.value)
        case "role":
            parts = [p.strip() for p in strategy.value.split(",")]
            role = parts[0]
            kwargs = {}
            for p in parts[1:]:
                if "=" in p:
                    k, v = p.split("=", 1)
                    kwargs[k.strip()] = v.strip()
            return page.get_by_role(role, **kwargs)
        case "test_id":
            return page.get_by_test_id(strategy.value)
        case "placeholder":
            return page.get_by_placeholder(strategy.value)
        case "label":
            return page.get_by_label(strategy.value)
        case _:
            raise ValueError(f"Unknown method: {strategy.method}")


def validate_page(page: Page, locators: list[tuple[str, SmartLocator]], timeout: int = 3000):
    total = 0
    passed = 0
    failed = 0

    for qualified_name, smart_loc in locators:
        print(f"\n  {qualified_name}  ({smart_loc.name})")
        for idx, strategy in enumerate(smart_loc.strategies, 1):
            total += 1
            label = f"    Strategy #{idx} [{strategy.method}] {strategy.description or strategy.value}"
            try:
                locator = _resolve_locator(page, strategy)
                locator.first.wait_for(state="visible", timeout=timeout)
                count = locator.count()
                print(f"    \033[92m OK \033[0m  Strategy #{idx} [{strategy.method}] "
                      f"{strategy.description or strategy.value}  ({count} match{'es' if count != 1 else ''})")
                passed += 1
            except Exception:
                print(f"    \033[91mFAIL\033[0m  Strategy #{idx} [{strategy.method}] "
                      f"{strategy.description or strategy.value}")
                failed += 1

    return total, passed, failed


def main():
    parser = argparse.ArgumentParser(description="Validate SmartLocators against live eBay")
    parser.add_argument("--page", choices=["home", "search", "product", "cart", "all"],
                        default="all", help="Which page to validate")
    parser.add_argument("--headed", action="store_true", help="Show browser window")
    parser.add_argument("--query", default="laptop", help="Search query for search/product pages")
    args = parser.parse_args()

    from pages.home_page import HomePage
    from pages.search_results_page import SearchResultsPage
    from pages.product_page import ProductPage
    from pages.cart_page import CartPage

    page_map = {
        "home": [(HomePage, "https://www.ebay.com", None)],
        "search": [(SearchResultsPage, None, "search")],
        "product": [(ProductPage, None, "product")],
        "cart": [(CartPage, "https://cart.ebay.com", None)],
    }

    if args.page == "all":
        pages_to_check = ["home", "search"]
    else:
        pages_to_check = [args.page]

    grand_total = grand_passed = grand_failed = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        for page_key in pages_to_check:
            if page_key == "home":
                cls = HomePage
                print(f"\n{'='*60}")
                print(f"  HomePage — https://www.ebay.com")
                print(f"{'='*60}")
                page.goto("https://www.ebay.com", wait_until="domcontentloaded")
                page.keyboard.press("Escape")
                page.wait_for_timeout(1000)

            elif page_key == "search":
                cls = SearchResultsPage
                print(f"\n{'='*60}")
                print(f"  SearchResultsPage — search for '{args.query}'")
                print(f"{'='*60}")
                if "ebay.com/sch" not in page.url:
                    page.goto("https://www.ebay.com", wait_until="domcontentloaded")
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(500)
                    search_input = page.locator("#gh-ac")
                    search_input.click()
                    search_input.type(args.query, delay=30)
                    page.keyboard.press("Enter")
                    page.wait_for_load_state("domcontentloaded")
                    page.wait_for_timeout(2000)

            elif page_key == "product":
                cls = ProductPage
                print(f"\n{'='*60}")
                print(f"  ProductPage — first search result")
                print(f"{'='*60}")
                if "ebay.com/sch" not in page.url:
                    page.goto("https://www.ebay.com", wait_until="domcontentloaded")
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(500)
                    page.locator("#gh-ac").type(args.query, delay=30)
                    page.keyboard.press("Enter")
                    page.wait_for_load_state("domcontentloaded")
                    page.wait_for_timeout(2000)
                first_link = page.locator("a[href*='/itm/']").first
                href = first_link.get_attribute("href")
                if href:
                    page.goto(href, wait_until="domcontentloaded")
                    page.wait_for_timeout(2000)

            elif page_key == "cart":
                cls = CartPage
                print(f"\n{'='*60}")
                print(f"  CartPage — https://cart.ebay.com")
                print(f"{'='*60}")
                page.goto("https://cart.ebay.com", wait_until="domcontentloaded")
                page.wait_for_timeout(2000)

            locators = _get_locators_from_class(cls)
            t, p, f = validate_page(page, locators)
            grand_total += t
            grand_passed += p
            grand_failed += f

        browser.close()

    print(f"\n{'='*60}")
    print(f"  RESULTS: {grand_passed}/{grand_total} strategies passed, "
          f"{grand_failed} failed")
    print(f"{'='*60}\n")

    sys.exit(1 if grand_failed > 0 else 0)


if __name__ == "__main__":
    main()
