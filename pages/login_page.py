"""
Login Page Object
=================

Represents eBay's sign-in page (``https://signin.ebay.com``).  Responsible
for:

* Entering credentials (username / password).
* Submitting the sign-in form.
* Handling the two-step flow where eBay asks for the username first,
  then shows a separate password field on the next screen.

Credentials are **never** hard-coded.  They are read from environment
variables ``EBAY_USERNAME`` and ``EBAY_PASSWORD`` (or passed in by the
calling business step).
"""

from __future__ import annotations

import allure
from playwright.sync_api import Page

from core.base_page import BasePage, SmartLocatorError
from core.smart_locator import LocatorStrategy, SmartLocator
from core.logger_config import get_logger

logger = get_logger(__name__)


class LoginPage(BasePage):
    """Page object for eBay's sign-in / authentication page.

    Args:
        page: Playwright ``Page`` for the active browser tab.
    """

    SIGN_IN_URL = "https://signin.ebay.com/ws/eBayISAPI.dll?SignIn"

    # ------------------------------------------------------------------
    # Smart Locators — Tiered strategy
    # ------------------------------------------------------------------

    # Tier 1: Stable ID → #userid has been stable for years
    USERNAME_INPUT = SmartLocator(
        name="username_input",
        strategies=[
            LocatorStrategy("css", "#userid", "username by stable ID"),
            LocatorStrategy("xpath", "//input[@name='userid' or @id='userid']", "username by XPath name/id"),
        ],
    )

    # Tier 1: Stable ID → #pass has been stable for years
    PASSWORD_INPUT = SmartLocator(
        name="password_input",
        strategies=[
            LocatorStrategy("css", "#pass", "password by stable ID"),
            LocatorStrategy("xpath", "//input[@name='pass' or @id='pass']", "password by XPath name/id"),
        ],
    )

    # Tier 1: Stable ID → #sgnBt is eBay's long-standing sign-in button
    SIGN_IN_BUTTON = SmartLocator(
        name="sign_in_button",
        strategies=[
            LocatorStrategy("css", "#sgnBt", "sign-in button by stable ID"),
            LocatorStrategy("xpath", "//button[@id='sgnBt' or @name='sgnBt']", "sign-in button by XPath id/name"),
        ],
    )

    # Tier 3: No stable ID → CSS text match, XPath text fallback
    CONTINUE_BUTTON = SmartLocator(
        name="continue_button",
        strategies=[
            LocatorStrategy("css", "button#signin-continue-btn", "continue by ID"),
            LocatorStrategy("xpath", "//button[contains(.,'Continue') or @id='signin-continue-btn']", "continue by XPath text/ID"),
        ],
    )

    # Tier 1: Stable ID → #gh-ug is eBay's logged-in username greeting
    SIGNED_IN_GREETING = SmartLocator(
        name="signed_in_greeting",
        strategies=[
            LocatorStrategy("css", "#gh-ug, #gh-un, button[title*='Hi']", "greeting by stable IDs"),
            LocatorStrategy("xpath", "//span[@id='gh-ug' or @id='gh-un'] | //button[contains(@title,'Hi')]", "greeting by XPath IDs"),
        ],
    )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @allure.step("Navigate to eBay sign-in page")
    def open_login(self) -> "LoginPage":
        """Navigate to the eBay sign-in page.

        Returns:
            ``self`` for fluent chaining.
        """
        self.navigate(self.SIGN_IN_URL)
        self.page.wait_for_load_state("domcontentloaded")
        self.logger.info("Sign-in page loaded")
        return self

    @allure.step("Enter username")
    def enter_username(self, username: str) -> None:
        """Type the username/email into the sign-in form.

        eBay may show username and password on the same page, or
        require clicking "Continue" after entering the username to
        reveal the password field.

        Args:
            username: eBay account email or username.
        """
        self.fill(self.USERNAME_INPUT, username)
        self.logger.info("Entered username: %s", username[:3] + "***")

        try:
            self.click(self.CONTINUE_BUTTON, timeout=3_000)
            self.page.wait_for_load_state("domcontentloaded")
            self.logger.info("Clicked Continue after username")
        except SmartLocatorError:
            self.logger.info("No Continue button — password field likely visible already")

    @allure.step("Enter password and submit")
    def enter_password_and_submit(self, password: str) -> None:
        """Type the password and click the Sign In button.

        Args:
            password: eBay account password.
        """
        self.fill(self.PASSWORD_INPUT, password)
        self.logger.info("Entered password: ****")
        self.click(self.SIGN_IN_BUTTON)
        self.page.wait_for_load_state("domcontentloaded")
        self.logger.info("Sign-in form submitted")

    @allure.step("Sign in to eBay")
    def login(self, username: str, password: str) -> bool:
        """Complete the full sign-in flow.

        Args:
            username: eBay account email or username.
            password: eBay account password.

        Returns:
            ``True`` if sign-in succeeded (greeting visible on home page),
            ``False`` otherwise.
        """
        self.open_login()
        self.take_screenshot("login_01_signin_page")
        self.enter_username(username)
        self.enter_password_and_submit(password)
        self.take_screenshot("login_02_after_submit")

        self.wait(2_000)
        return self.is_signed_in()

    def is_signed_in(self) -> bool:
        """Check if the user is currently signed in.

        Looks for the "Hi <username>" greeting in the top navigation bar.

        Returns:
            ``True`` if the greeting element is visible.
        """
        return self.is_element_visible(self.SIGNED_IN_GREETING, timeout=5_000)
