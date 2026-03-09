"""
Base Page Module
================

The foundation of the Page Object Model (POM).  Every page class in the
framework inherits from ``BasePage``, which encapsulates:

* **Smart locator resolution** – tries multiple locator strategies per element
  and logs which one succeeded or failed.
* **Automatic retries** – wraps interactions with exponential backoff so
  transient DOM instability doesn't break tests.
* **Screenshot capture** – takes a timestamped screenshot on any element
  lookup failure and attaches it to the Allure report.
* **Logging** – every action (click, type, navigate) is logged with timing
  information for easy debugging.

Design Decisions:
    - Uses Playwright's **synchronous** API for simpler pytest integration.
    - Locator resolution lives here (not in tests) so tests stay declarative.
    - Screenshots are saved to ``screenshots/`` AND attached to Allure.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import List, Optional

import allure
from playwright.sync_api import Locator, Page, TimeoutError as PwTimeout

from core.logger_config import get_logger
from core.retry_handler import with_retry
from core.smart_locator import LocatorStrategy, SmartLocator
from utils.step_collector import collector

SCREENSHOT_DIR = Path(__file__).resolve().parent.parent / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

LIVE_VIEW_ENABLED = os.environ.get("EBAY_LIVE_VIEW", "").lower() in ("1", "true", "yes")
LIVE_VIEW_PATH = SCREENSHOT_DIR / "_live_view.png"


class SmartLocatorError(Exception):
    """Raised when every locator strategy for an element has been exhausted."""


class CaptchaDetectedError(Exception):
    """Raised when eBay's bot verification / CAPTCHA page is detected.

    This is not a framework bug — it means eBay has flagged the session
    as potentially automated.  Mitigations:
    1. Run ``python save_auth_state.py`` to create a logged-in session.
    2. Enable stealth browser args in config.
    3. Reduce test speed (increase ``slow_mo``).
    """


class BasePage:
    """Abstract base for all page objects.

    Subclasses define ``SmartLocator`` instances as class or instance
    attributes and call ``self.find_element(locator)`` to interact with
    them.  The retry / fallback / logging machinery is invisible to tests.

    Args:
        page:            Playwright ``Page`` object for the current browser tab.
        default_timeout: Milliseconds to wait for each locator attempt
                         before trying the next strategy.  Defaults to
                         10 000 ms (10 s).
    """

    def __init__(self, page: Page, default_timeout: int = 10_000) -> None:
        self.page = page
        self.default_timeout = default_timeout
        self.logger = get_logger(self.__class__.__name__)

    @staticmethod
    def _retry_callback(action_name: str, target_name: str):
        """Return an ``on_retry`` callback that records the retry as a sub-step."""
        def _on_retry(attempt: int, exc: Exception) -> None:
            collector.add_sub_step(
                "retry", target_name, status="retry",
                detail=f"{action_name} attempt {attempt} failed: {type(exc).__name__}",
            )
        return _on_retry

    # ------------------------------------------------------------------
    # Locator resolution
    # ------------------------------------------------------------------

    def _create_playwright_locator(self, strategy: LocatorStrategy) -> Locator:
        """Convert a ``LocatorStrategy`` into a Playwright ``Locator``.

        Playwright supports several selector engines; this method maps our
        generic ``method`` field to the correct API call.

        Args:
            strategy: The locator strategy to resolve.

        Returns:
            A lazy Playwright ``Locator`` (no network call yet).

        Raises:
            ValueError: If the strategy method is unrecognised.
        """
        match strategy.method:
            case "css":
                return self.page.locator(strategy.value)
            case "xpath":
                return self.page.locator(f"xpath={strategy.value}")
            case "text":
                return self.page.get_by_text(strategy.value)
            case "role":
                role_name, kwargs = self._parse_role_value(strategy.value)
                return self.page.get_by_role(role_name, **kwargs)
            case "test_id":
                return self.page.get_by_test_id(strategy.value)
            case "placeholder":
                return self.page.get_by_placeholder(strategy.value)
            case "label":
                return self.page.get_by_label(strategy.value)
            case _:
                raise ValueError(f"Unsupported locator method: {strategy.method}")

    @staticmethod
    def _parse_role_value(value: str) -> tuple:
        """Parse a role strategy value like ``'button, name=Search'``.

        The format is ``role_name[, key=value ...]``.  This lets us store
        role-based locators as plain strings in ``LocatorStrategy``.

        Args:
            value: e.g. ``"button, name=Search"`` or just ``"button"``.

        Returns:
            A tuple of ``(role_name, kwargs_dict)`` ready for
            ``page.get_by_role(role_name, **kwargs)``.
        """
        parts = [p.strip() for p in value.split(",")]
        role_name = parts[0]
        kwargs = {}
        for part in parts[1:]:
            if "=" in part:
                k, v = part.split("=", 1)
                kwargs[k.strip()] = v.strip()
        return role_name, kwargs

    def find_element(
        self,
        smart_locator: SmartLocator,
        timeout: Optional[int] = None,
        state: str = "visible",
        optional: bool = False,
    ) -> Locator:
        """Locate an element using the smart-locator fallback chain.

        Iterates through each ``LocatorStrategy`` in order.  The first
        strategy whose element becomes *visible* (or the requested *state*)
        within *timeout* wins.  Every attempt is logged.

        On total failure a screenshot is taken, attached to Allure, and a
        ``SmartLocatorError`` is raised.

        Args:
            smart_locator: A ``SmartLocator`` defining ≥ 2 strategies.
            timeout:       Per-strategy wait in ms.  Falls back to
                           ``self.default_timeout``.
            state:         Playwright element state to wait for
                           (``'visible'``, ``'attached'``, ``'hidden'``).
            optional:      If ``True``, a miss is expected and harmless.
                           The sub-step is recorded as ``"warn"`` instead
                           of ``"fail"``, and no failure screenshot is taken.

        Returns:
            The Playwright ``Locator`` from the first successful strategy.

        Raises:
            SmartLocatorError: If all strategies are exhausted.
        """
        timeout = timeout or self.default_timeout
        last_error: Optional[Exception] = None
        collector.begin_sub_step()

        for idx, strategy in enumerate(smart_locator.strategies, start=1):
            try:
                locator = self._create_playwright_locator(strategy)
                locator.wait_for(state=state, timeout=timeout)
                self.logger.info(
                    "✓ [%s] Strategy #%d succeeded: %s",
                    smart_locator.name,
                    idx,
                    strategy.description or strategy.value,
                )
                collector.add_sub_step(
                    "find_element", smart_locator.name, "pass",
                    detail=f"Strategy #{idx}: {strategy.description or strategy.value}",
                )
                return locator

            except (PwTimeout, Exception) as exc:
                last_error = exc
                self.logger.warning(
                    "✗ [%s] Strategy #%d failed (%s): %s",
                    smart_locator.name,
                    idx,
                    strategy.description or strategy.value,
                    str(exc)[:120],
                )

        if optional:
            self.logger.info(
                "[%s] Not found (optional) — skipping", smart_locator.name,
            )
            collector.add_sub_step(
                "find_element", smart_locator.name, "warn",
                detail=f"Not found (optional) — {len(smart_locator.strategies)} strategies tried",
            )
        else:
            screenshot_path = self.take_screenshot(f"FAIL_{smart_locator.name}")
            collector.add_sub_step(
                "find_element", smart_locator.name, "fail",
                detail=f"All {len(smart_locator.strategies)} strategies exhausted",
            )
        raise SmartLocatorError(
            f"All {len(smart_locator.strategies)} strategies exhausted for "
            f"'{smart_locator.name}'."
        ) from last_error

    # ------------------------------------------------------------------
    # High-level actions (click, fill, get_text, etc.)
    # ------------------------------------------------------------------

    def click(
        self,
        smart_locator: SmartLocator,
        timeout: Optional[int] = None,
    ) -> None:
        """Find an element via smart locator and click it.

        Wrapped with retry logic so transient overlay/animation issues
        are handled automatically.

        Args:
            smart_locator: The target element's smart locator.
            timeout:       Per-strategy wait in ms.
        """
        collector.begin_sub_step()

        @with_retry(max_attempts=3, backoff_factor=0.5, exceptions=(Exception,),
                    on_retry=self._retry_callback("click", smart_locator.name))
        def _click() -> None:
            element = self.find_element(smart_locator, timeout=timeout)
            element.click()
            self.logger.info("Clicked '%s'", smart_locator.name)

        _click()
        collector.add_sub_step("click", smart_locator.name)
        self._update_live_view()

    def fill(
        self,
        smart_locator: SmartLocator,
        text: str,
        timeout: Optional[int] = None,
    ) -> None:
        """Clear an input and type new text.

        Args:
            smart_locator: The target input's smart locator.
            text:          Value to type.
            timeout:       Per-strategy wait in ms.
        """
        collector.begin_sub_step()

        @with_retry(max_attempts=3, backoff_factor=0.5, exceptions=(Exception,),
                    on_retry=self._retry_callback("fill", smart_locator.name))
        def _fill() -> None:
            element = self.find_element(smart_locator, timeout=timeout)
            element.fill(text)
            self.logger.info("Filled '%s' with '%s'", smart_locator.name, text)

        _fill()
        collector.add_sub_step("fill", smart_locator.name, detail=f"'{text}'")
        self._update_live_view()

    def type_text(
        self,
        smart_locator: SmartLocator,
        text: str,
        delay: int = 50,
        timeout: Optional[int] = None,
    ) -> None:
        """Type text character-by-character (simulates real keystrokes).

        Useful for search inputs that trigger autocomplete on each keystroke.

        Args:
            smart_locator: The target input's smart locator.
            text:          Value to type.
            delay:         Milliseconds between keystrokes.
            timeout:       Per-strategy wait in ms.
        """
        collector.begin_sub_step()
        element = self.find_element(smart_locator, timeout=timeout)
        element.click()
        element.fill("")
        element.type(text, delay=delay)
        self.logger.info("Typed '%s' into '%s'", text, smart_locator.name)
        collector.add_sub_step("type_text", smart_locator.name, detail=f"'{text}'")
        self._update_live_view()

    def get_text(
        self,
        smart_locator: SmartLocator,
        timeout: Optional[int] = None,
    ) -> str:
        """Return the visible text content of the element.

        Args:
            smart_locator: The target element's smart locator.
            timeout:       Per-strategy wait in ms.

        Returns:
            The trimmed inner text of the element.
        """
        collector.begin_sub_step()
        element = self.find_element(smart_locator, timeout=timeout)
        text = (element.inner_text() or "").strip()
        self.logger.info("Got text from '%s': '%s'", smart_locator.name, text[:80])
        collector.add_sub_step("get_text", smart_locator.name, detail=f"→ '{text[:60]}'")
        return text

    def get_attribute_value(
        self,
        smart_locator: SmartLocator,
        attribute: str,
        timeout: Optional[int] = None,
    ) -> Optional[str]:
        """Read an HTML attribute from the located element.

        Args:
            smart_locator: The target element's smart locator.
            attribute:     Attribute name (e.g. ``'href'``, ``'value'``).
            timeout:       Per-strategy wait in ms.

        Returns:
            The attribute value, or ``None`` if not present.
        """
        element = self.find_element(smart_locator, timeout=timeout)
        value = element.get_attribute(attribute)
        self.logger.info(
            "Attribute '%s' of '%s' = '%s'",
            attribute,
            smart_locator.name,
            str(value)[:80],
        )
        return value

    def is_element_visible(
        self,
        smart_locator: SmartLocator,
        timeout: int = 3_000,
    ) -> bool:
        """Check whether an element is visible without raising on failure.

        Useful for conditional logic (e.g. "if the cookie banner is visible,
        dismiss it").

        Args:
            smart_locator: The element to check.
            timeout:       How long to wait before returning False.

        Returns:
            ``True`` if any strategy finds a visible element, else ``False``.
        """
        try:
            self.find_element(smart_locator, timeout=timeout)
            return True
        except SmartLocatorError:
            return False

    def wait_for_element_hidden(
        self,
        smart_locator: SmartLocator,
        timeout: Optional[int] = None,
    ) -> None:
        """Wait until the element is no longer visible.

        Useful after dismissing modals, banners, or loading spinners.

        Args:
            smart_locator: The element expected to disappear.
            timeout:       Maximum wait in ms.
        """
        timeout = timeout or self.default_timeout
        strategy = smart_locator.primary
        locator = self._create_playwright_locator(strategy)
        locator.wait_for(state="hidden", timeout=timeout)
        self.logger.info("Element '%s' is now hidden", smart_locator.name)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def navigate(self, url: str, wait_until: str = "domcontentloaded") -> None:
        """Navigate the page to a URL and wait for it to load.

        After navigation, checks for eBay's bot verification page and
        raises ``CaptchaDetectedError`` if found.

        Args:
            url:        Full URL to navigate to.
            wait_until: Playwright load state — ``'domcontentloaded'``,
                        ``'load'``, or ``'networkidle'``.

        Raises:
            CaptchaDetectedError: If the page is a CAPTCHA / verification gate.
        """
        collector.begin_sub_step()
        self.logger.info("Navigating to %s", url)
        self.page.goto(url, wait_until=wait_until)
        self.logger.info("Navigation complete: %s", self.page.url)
        collector.add_sub_step("navigate", url[:80], detail=f"wait_until={wait_until}")
        self._check_for_captcha()
        self._update_live_view()

    def _check_for_captcha(self) -> None:
        """Detect eBay's bot verification / CAPTCHA page and fail fast.

        Checks for known indicators that eBay has redirected to a
        verification gate.  Failing fast with a clear error is much
        better than timing out on missing elements for minutes.

        Raises:
            CaptchaDetectedError: If verification page is detected.
        """
        captcha_signals = [
            "Please verify yourself",
            "verify yourself to continue",
            "blocked",
        ]
        try:
            title = self.page.title().lower()
            body_text = self.page.locator("body").first.inner_text(timeout=2_000)[:500].lower()
        except Exception:
            return

        for signal in captcha_signals:
            if signal.lower() in title or signal.lower() in body_text:
                self.take_screenshot("CAPTCHA_detected")
                self.logger.error(
                    "CAPTCHA / bot verification page detected! "
                    "Run 'python save_auth_state.py' to create a "
                    "valid session."
                )
                raise CaptchaDetectedError(
                    "eBay bot verification page detected. "
                    "Automated tests cannot solve CAPTCHAs. "
                    "Run 'python save_auth_state.py' to log in manually "
                    "and save your session, then re-run the tests."
                )

    def get_current_url(self) -> str:
        """Return the browser's current URL.

        Returns:
            The full URL as a string.
        """
        return self.page.url

    # ------------------------------------------------------------------
    # Screenshots & tracing
    # ------------------------------------------------------------------

    def _update_live_view(self) -> None:
        """Capture a viewport screenshot for the GUI live-view panel.

        Only active when ``EBAY_LIVE_VIEW`` env var is truthy.  Writes to
        a single file that the Flask GUI polls, keeping it small (viewport
        only, not full page) for fast transfer.
        """
        if not LIVE_VIEW_ENABLED:
            return
        try:
            self.page.screenshot(path=str(LIVE_VIEW_PATH), full_page=False)
        except Exception:
            pass

    def take_screenshot(self, name: str = "screenshot") -> str:
        """Capture a full-page screenshot and attach it to the Allure report.

        Args:
            name: A descriptive name (used in the filename and Allure label).

        Returns:
            The absolute path to the saved screenshot file.
        """
        collector.begin_sub_step()
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{name}_{timestamp}.png"
        filepath = SCREENSHOT_DIR / filename

        self.page.screenshot(path=str(filepath), full_page=True)
        self.logger.info("Screenshot saved: %s", filepath)

        allure.attach.file(
            str(filepath),
            name=name,
            attachment_type=allure.attachment_type.PNG,
        )
        collector.add_sub_step("screenshot", name, screenshot_path=str(filepath))
        self._update_live_view()
        return str(filepath)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def wait(self, milliseconds: int) -> None:
        """Explicit sleep — use sparingly, only when no better wait exists.

        Args:
            milliseconds: Time to sleep.
        """
        self.page.wait_for_timeout(milliseconds)
        collector.add_sub_step("wait", f"{milliseconds}ms")

    def scroll_to_bottom(self) -> None:
        """Scroll to the very bottom of the page to trigger lazy-loaded content."""
        self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        self.logger.info("Scrolled to bottom of page")
        collector.add_sub_step("scroll", "bottom")

    def press_key(self, key: str) -> None:
        """Press a keyboard key (e.g. ``'Enter'``, ``'Escape'``).

        Args:
            key: The Playwright key identifier.
        """
        collector.begin_sub_step()
        self.page.keyboard.press(key)
        self.logger.info("Pressed key: %s", key)
        collector.add_sub_step("press_key", key)
        self._update_live_view()

    def accept_cookies_if_present(self) -> None:
        """Dismiss cookie banners and overlay dialogs that appear on first visit.

        eBay may show a GDPR cookie banner and/or a "Ship to" address dialog.
        Both block interaction with the page.  Pressing Escape first clears
        any modal overlay, then we look for the cookie banner.
        """
        self.page.keyboard.press("Escape")
        self.wait(500)
        collector.add_sub_step("dismiss_dialogs", "Escape + cookie banner")

        try:
            gdpr = self.page.locator("#gdpr-banner-accept")
            if gdpr.is_visible():
                gdpr.click()
                self.logger.info("Cookie banner dismissed")
        except Exception:
            pass
