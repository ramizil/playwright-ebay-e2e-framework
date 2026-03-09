"""
Step Collector
==============

Thread-safe collector that records test steps, sub-steps, screenshots,
and metadata during test execution.  The collected data is consumed by
the HTML report generator after each test scenario completes.

Two-level hierarchy:
    **Step** — high-level action (e.g. "Launch", "Search", "Add to Cart")
    **SubStep** — granular browser action (e.g. "click search_button",
                  "fill search_input", "navigate to https://...")

Page-object methods in ``BasePage`` automatically append sub-steps to the
currently active step via ``collector.add_sub_step()``.
"""

from __future__ import annotations

import base64
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class SubStep:
    """A single browser-level action within a high-level step."""
    action: str          # "click", "fill", "navigate", "type_text", "press_key", "wait", "screenshot", "find_element", "retry"
    target: str          # element name or URL
    status: str = "pass" # "pass", "fail", "warn", "retry"
    detail: str = ""     # extra info (typed text, key name, etc.)
    duration: float = 0.0
    timestamp: str = ""
    screenshot_path: str = ""


@dataclass
class StepRecord:
    """One high-level step within a test scenario."""
    name: str
    method: str
    status: str  # "pass", "fail", "skip", "warn"
    duration: float = 0.0
    detail: str = ""
    screenshot_path: str = ""
    timestamp: str = ""
    sub_steps: List[SubStep] = field(default_factory=list)


@dataclass
class ScenarioRecord:
    """Full record for one test scenario."""
    id: str
    query: str = ""
    max_price: float = 0.0
    status: str = "running"
    started_at: float = 0.0
    finished_at: float = 0.0
    steps: List[StepRecord] = field(default_factory=list)
    browser: str = ""
    items_found: int = 0
    items_added: int = 0
    error_message: str = ""
    description: str = ""
    expected_results: str = ""
    manual_steps: List[str] = field(default_factory=list)


class StepCollector:
    """Thread-safe singleton that accumulates step data for report generation."""

    def __init__(self):
        self._lock = threading.Lock()
        self._current: Optional[ScenarioRecord] = None
        self._completed: List[ScenarioRecord] = []
        self._step_start: float = 0.0
        self._sub_step_start: float = 0.0

    def start_scenario(self, scenario_id: str, query: str = "",
                       max_price: float = 0.0, browser: str = "",
                       description: str = "", expected_results: str = "",
                       manual_steps: Optional[List[str]] = None) -> None:
        with self._lock:
            self._current = ScenarioRecord(
                id=scenario_id,
                query=query,
                max_price=max_price,
                started_at=time.time(),
                browser=browser,
                description=description,
                expected_results=expected_results,
                manual_steps=manual_steps or [],
            )

    def begin_step(self) -> None:
        """Mark the beginning of a step (for duration tracking)."""
        self._step_start = time.time()

    def add_step(self, name: str, method: str, status: str,
                 detail: str = "", screenshot_path: str = "",
                 duration: float = 0.0) -> None:
        with self._lock:
            if not self._current:
                return
            if duration == 0.0 and self._step_start:
                duration = round(time.time() - self._step_start, 2)
                self._step_start = 0.0
            self._current.steps.append(StepRecord(
                name=name,
                method=method,
                status=status,
                duration=duration,
                detail=detail,
                screenshot_path=screenshot_path,
                timestamp=time.strftime("%H:%M:%S"),
            ))

    # ------------------------------------------------------------------
    # Sub-step API — called from BasePage actions
    # ------------------------------------------------------------------

    def begin_sub_step(self) -> None:
        """Mark the start of a sub-step for duration tracking."""
        self._sub_step_start = time.time()

    def add_sub_step(self, action: str, target: str, status: str = "pass",
                     detail: str = "", screenshot_path: str = "",
                     duration: float = 0.0) -> None:
        """Append a sub-step to the most recent high-level step."""
        with self._lock:
            if not self._current or not self._current.steps:
                return
            if duration == 0.0 and self._sub_step_start:
                duration = round(time.time() - self._sub_step_start, 3)
                self._sub_step_start = 0.0
            self._current.steps[-1].sub_steps.append(SubStep(
                action=action,
                target=target,
                status=status,
                detail=detail,
                duration=duration,
                timestamp=time.strftime("%H:%M:%S"),
                screenshot_path=screenshot_path,
            ))

    # ------------------------------------------------------------------

    def set_items(self, found: int = 0, added: int = 0) -> None:
        with self._lock:
            if self._current:
                if found:
                    self._current.items_found = found
                if added:
                    self._current.items_added = added

    def finish_scenario(self, status: str, error: str = "") -> ScenarioRecord:
        with self._lock:
            if not self._current:
                return ScenarioRecord(id="unknown")
            self._current.status = status
            self._current.finished_at = time.time()
            self._current.error_message = error
            record = self._current
            self._completed.append(record)
            self._current = None
            return record

    @property
    def current(self) -> Optional[ScenarioRecord]:
        return self._current

    @property
    def completed(self) -> List[ScenarioRecord]:
        return list(self._completed)

    def reset(self) -> None:
        with self._lock:
            self._current = None
            self._completed.clear()


def screenshot_to_base64(path: str) -> str:
    """Read a PNG screenshot and return a base64 data URI."""
    p = Path(path)
    if not p.exists():
        return ""
    data = p.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:image/png;base64,{b64}"


# Global singleton
collector = StepCollector()
