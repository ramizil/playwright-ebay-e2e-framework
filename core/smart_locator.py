"""
Smart Locator Module
====================

Defines multiple locator strategies per UI element — when the primary fails
(due to DOM
changes, A/B tests, or layout shifts), the framework automatically falls
back to alternative locators — keeping tests stable without manual fixes.

Architecture:
    LocatorStrategy  – A single way to find an element (css, xpath, text, etc.)
    SmartLocator     – Groups multiple LocatorStrategy instances for one element.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class LocatorStrategy:
    """Represents one way to locate a DOM element.

    Attributes:
        method:      The Playwright locator method to use.
                     Supported values: 'css', 'xpath', 'text', 'role', 'test_id'.
        value:       The selector string passed to the locator method.
        description: Human-readable label used in logs so failures are easy
                     to diagnose (e.g. 'search input by id').
    """

    method: str
    value: str
    description: str = ""

    def __post_init__(self) -> None:
        """Validate that the locator method is one Playwright can resolve."""
        allowed = {"css", "xpath", "text", "role", "test_id", "placeholder", "label"}
        if self.method not in allowed:
            raise ValueError(
                f"Unknown locator method '{self.method}'. Must be one of: {allowed}"
            )


@dataclass
class SmartLocator:
    """Groups two or more locator strategies for a single UI element.

    The framework tries strategies in order: primary first, then each fallback.
At least two strategies per element keep test code free of fallback logic.

    Attributes:
        name:       A descriptive element name used in logs and screenshots
                    (e.g. 'search_button', 'price_filter_max').
        strategies: Ordered list of LocatorStrategy objects.  The first entry
                    is the primary; the rest are fallbacks.

    Raises:
        ValueError: If fewer than two strategies are provided.

    Example:

        search_input = SmartLocator(
            name="search_input",
            strategies=[
                LocatorStrategy("css", "#gh-ac-box2", "by element ID"),
                LocatorStrategy("xpath", "//input[@name='_nkw']", "by name attribute"),
            ],
        )
    """

    name: str
    strategies: List[LocatorStrategy] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Require at least two strategies."""
        if len(self.strategies) < 2:
            raise ValueError(
                f"SmartLocator '{self.name}' requires at least 2 strategies, "
                f"got {len(self.strategies)}."
            )

    @property
    def primary(self) -> LocatorStrategy:
        """Return the preferred (first) locator strategy."""
        return self.strategies[0]

    @property
    def fallbacks(self) -> List[LocatorStrategy]:
        """Return every strategy except the primary, in priority order."""
        return self.strategies[1:]

    def __repr__(self) -> str:
        """Concise representation showing name and strategy count."""
        return f"SmartLocator(name='{self.name}', strategies={len(self.strategies)})"
