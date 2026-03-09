"""
Core Module
===========

Framework internals: base page, smart locators, retry logic, and logging.
"""

from core.base_page import BasePage, SmartLocatorError, CaptchaDetectedError
from core.smart_locator import SmartLocator, LocatorStrategy
from core.retry_handler import with_retry, retry_call
from core.logger_config import get_logger, setup_logging

__all__ = [
    "BasePage",
    "SmartLocatorError",
    "CaptchaDetectedError",
    "SmartLocator",
    "LocatorStrategy",
    "with_retry",
    "retry_call",
    "get_logger",
    "setup_logging",
]
