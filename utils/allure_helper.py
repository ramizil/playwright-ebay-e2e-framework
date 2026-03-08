"""
Allure Helper Module
====================

Utility functions that make it easy to enrich Allure reports from anywhere
in the framework.  Provides wrappers around ``allure.attach`` and
``allure.step`` so that:

* Tests get automatic environment metadata (browser, OS, base URL).
* Each high-level action (search, add-to-cart) appears as a named step.
* Arbitrary text, HTML, or JSON can be attached for debugging.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import allure

from core.logger_config import get_logger

logger = get_logger(__name__)


def attach_text(name: str, body: str) -> None:
    """Attach a plain-text blob to the current Allure report step.

    Useful for logging API responses, extracted data, or diagnostic info.

    Args:
        name: Label shown in the Allure UI.
        body: The text content to attach.
    """
    allure.attach(body, name=name, attachment_type=allure.attachment_type.TEXT)
    logger.debug("Allure text attachment: %s (%d chars)", name, len(body))


def attach_json(name: str, data: Any) -> None:
    """Attach a JSON-serialised object to the Allure report.

    Args:
        name: Label shown in the Allure UI.
        data: Any JSON-serialisable Python object.
    """
    body = json.dumps(data, indent=2, ensure_ascii=False)
    allure.attach(body, name=name, attachment_type=allure.attachment_type.JSON)
    logger.debug("Allure JSON attachment: %s", name)


def attach_html(name: str, html: str) -> None:
    """Attach an HTML fragment to the Allure report.

    Args:
        name: Label shown in the Allure UI.
        html: Raw HTML string.
    """
    allure.attach(html, name=name, attachment_type=allure.attachment_type.HTML)


def write_allure_environment(
    results_dir: str,
    browser: str,
    base_url: str,
    extra: Dict[str, str] | None = None,
) -> None:
    """Write an ``environment.properties`` file into the Allure results folder.

    Allure reads this file to display environment metadata (browser version,
    base URL, OS) on the report's overview tab.

    Args:
        results_dir: Path to the ``allure-results`` directory.
        browser:     Browser name (e.g. ``'chromium'``).
        base_url:    The site under test.
        extra:       Optional additional key-value pairs.
    """
    props = {
        "Browser": browser,
        "Base URL": base_url,
        "Framework": "Playwright + pytest",
        "Language": "Python 3.12",
    }
    if extra:
        props.update(extra)

    results_path = Path(results_dir)
    results_path.mkdir(parents=True, exist_ok=True)

    env_file = results_path / "environment.properties"
    with open(env_file, "w", encoding="utf-8") as fh:
        for key, value in props.items():
            fh.write(f"{key}={value}\n")

    logger.info("Allure environment.properties written to %s", env_file)
