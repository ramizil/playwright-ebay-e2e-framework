"""
Root conftest.py — Framework-wide Fixtures and Hooks
=====================================================

This is the top-level pytest configuration file.  It runs before any test
module and is responsible for:

* Bootstrapping the logging system.
* Loading the global ``Settings`` object.
* Writing Allure environment metadata.
* Hooking into test outcomes for automatic failure screenshots.

Fixtures defined here are available to **all** test files without explicit
import.
"""

from __future__ import annotations

import os

import pytest

from core.logger_config import setup_logging, get_logger
from config.settings import load_settings, resolve_browser_profile
from utils.allure_helper import write_allure_environment

logger = get_logger(__name__)


def pytest_configure(config: pytest.Config) -> None:
    """Called once after command-line options have been parsed.

    Responsibilities:
    * Bootstrap logging.
    * Generate a unique ``run_id`` so every invocation writes Allure
      results into its own sub-folder (``allure-results/run_<id>/``).
    * Write Allure environment metadata (browser, URL, run_id).

    The ``--alluredir`` CLI argument is rewritten to include the run_id
    automatically, so callers don't need to construct the path themselves.

    Args:
        config: The pytest ``Config`` object.
    """
    setup_logging("INFO")
    logger.info("=== pytest session starting ===")

    settings = load_settings()
    browser_name = os.environ.get("EBAY_BROWSER", settings.browsers[0])
    profile = resolve_browser_profile(browser_name)

    # Rewrite alluredir to include run_id for unique-per-run reports
    allure_dir = getattr(config.option, "allure_report_dir", None)
    if allure_dir:
        unique_dir = os.path.join(allure_dir, f"run_{settings.run_id}")
        config.option.allure_report_dir = unique_dir
        logger.info("Allure results dir: %s", unique_dir)

    target_dir = getattr(config.option, "allure_report_dir", None) or settings.allure_results_for_run
    write_allure_environment(
        results_dir=target_dir,
        browser=profile.id,
        base_url=settings.base_url,
        run_id=settings.run_id,
    )
    logger.info("Run ID: %s", settings.run_id)


@pytest.fixture(scope="session")
def settings():
    """Session-scoped fixture that provides the loaded ``Settings`` object.

    All configuration values (URLs, timeouts, browser list) are accessible
    through this fixture.  Session scope means the YAML is read once and
    shared across all tests in the run.

    Yields:
        A ``Settings`` dataclass instance.
    """
    return load_settings()
