"""
Flow State DTOs
================

Mutable state objects shared across ordered test steps within a single
test-class flow.  Equivalent to Java instance fields in a TestNG test
class (e.g. ``this.urls``, ``this.addedCount``).

Each DTO is a ``@dataclass`` stored on the test class via
``request.cls.state`` so every ``test_step_*`` method can read and write
through ``self.state``.

Pattern (Java equivalent)::

    // Java — TestNG test class
    public class CES_WLS_Basic_Flow {
        private List<String> urls;      // shared across @Test methods
        private int addedCount;
    }

    # Python — pytest test class
    @dataclass
    class ShoppingFlowState:
        urls: list[str]
        added_count: int
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ShoppingFlowState:
    """State shared across the E2E shopping flow steps.

    Attributes:
        urls:        Item URLs collected during the search-and-collect step.
        added_count: Number of items successfully added to the cart.
    """

    urls: list[str] = field(default_factory=list)
    added_count: int = 0


@dataclass
class SmokeFlowState:
    """State shared across the smoke test steps.

    Attributes:
        urls: Search result URLs found during the verify-results step.
    """

    urls: list[str] = field(default_factory=list)
