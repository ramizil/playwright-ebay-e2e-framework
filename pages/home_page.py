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
    # Smart Locators — each element has ≥ 2 strategies
    # ------------------------------------------------------------------

    SEARCH_INPUT = SmartLocator(
        name="search_input",
        strategies=[
            LocatorStrategy("css", "input.gh-tb[type='text']", "search input by class"),
            LocatorStrategy("xpath", "//input[@type='text' and @name='_nkw']", "search input by name attr"),
        ],
    )

    SEARCH_BUTTON = SmartLocator(
        name="search_button",
        strategies=[
            LocatorStrategy("css", "input#gh-btn[type='submit']", "search submit button by ID"),
            LocatorStrategy("xpath", "//input[@type='submit' and @value='Search']", "search submit by value"),
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

        Uses ``type_text`` (character-by-character) so eBay's autocomplete
        doesn't hijack the input.  After typing, presses Enter as a more
        reliable submit mechanism than clicking the button (which may be
        obscured by autocomplete dropdown).

        Args:
            query: The product search term (e.g. ``'wireless headphones'``).
        """
        self.logger.info("Searching for: '%s'", query)
        self.type_text(self.SEARCH_INPUT, query, delay=30)
        self.press_key("Enter")
        self.page.wait_for_load_state("domcontentloaded")
        self.logger.info("Search submitted for: '%s'", query)
