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

import pytest

from core.logger_config import setup_logging, get_logger
from config.settings import load_settings
from utils.allure_helper import write_allure_environment

logger = get_logger(__name__)


def pytest_configure(config: pytest.Config) -> None:
    """Called once after command-line options have been parsed.

    Sets up logging and writes the Allure environment properties file
    so the generated report shows browser, URL, and framework metadata.

    Args:
        config: The pytest ``Config`` object.
    """
    setup_logging("INFO")
    logger.info("=== pytest session starting ===")

    settings = load_settings()
    write_allure_environment(
        results_dir=settings.allure_results,
        browser=", ".join(settings.browsers),
        base_url=settings.base_url,
    )


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
