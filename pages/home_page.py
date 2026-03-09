"""
Home Page Object
================

Represents the eBay landing page (``https://www.ebay.com``).  Responsible
for:

* Performing product searches via the search bar.
* Dismissing any cookie / GDPR banners that appear on first visit.

Every interactable element is defined as a ``SmartLocator`` with at least
two strategies so the framework can survive minor DOM changes.
"""

from __future__ import annotations

import allure
from playwright.sync_api import Page

from core.base_page import BasePage
from core.smart_locator import LocatorStrategy, SmartLocator


class HomePage(BasePage):
    """Page object for the eBay home / landing page.

    Args:
        page: Playwright ``Page`` for the active browser tab.
    """

    # ------------------------------------------------------------------
    # Smart Locators — Tiered strategy: stable ID first, relative XPath fallback
    # ------------------------------------------------------------------

    # Tier 1: Stable ID → #gh-ac has been stable for years
    SEARCH_INPUT = SmartLocator(
        name="search_input",
        strategies=[
            LocatorStrategy("css", "#gh-ac", "search input by stable ID"),
            LocatorStrategy("xpath", "//input[@name='_nkw' and @type='text']", "search input by name attr"),
        ],
    )

    # Tier 1: Stable ID → #gh-btn has been stable for years
    SEARCH_BUTTON = SmartLocator(
        name="search_button",
        strategies=[
            LocatorStrategy("css", "#gh-btn", "search button by stable ID"),
            LocatorStrategy("xpath", "//input[@type='submit' and @value='Search']", "search button by value attr"),
        ],
    )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @allure.step("Open eBay home page")
    def open(self, base_url: str = "https://www.ebay.com") -> "HomePage":
        """Navigate to the eBay home page and dismiss popups.

        Args:
            base_url: The root URL of the eBay site.

        Returns:
            ``self`` for fluent chaining (e.g. ``home.open().search(...)``).
        """
        self.navigate(base_url)
        self.accept_cookies_if_present()
        self.logger.info("eBay home page loaded")
        return self

    @allure.step("Search for '{query}'")
    def search(self, query: str) -> None:
        """Type a search query and submit the search form.

        Types character-by-character then presses **Escape** to dismiss
        eBay's autocomplete dropdown before pressing Enter.  Without the
        Escape, Enter may select an autocomplete suggestion instead of
        submitting the raw query, which leads to unexpected result pages.

        Args:
            query: The product search term (e.g. ``'wireless headphones'``).
        """
        self.logger.info("Searching for: '%s'", query)
        self.type_text(self.SEARCH_INPUT, query, delay=30)
        self.page.wait_for_timeout(300)
        self.press_key("Escape")
        self.page.wait_for_timeout(200)
        self.press_key("Enter")
        self.page.wait_for_load_state("domcontentloaded")
        self.logger.info("Search submitted for: '%s'", query)
