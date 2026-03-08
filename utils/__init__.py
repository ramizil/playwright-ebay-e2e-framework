"""
Utils Module
============

Shared helpers for data loading, screenshots, and Allure integration.
"""

from utils.data_loader import load_json, load_yaml, load_test_scenarios, get_scenario_ids
from utils.screenshot_manager import capture_screenshot, capture_on_failure
from utils.allure_helper import attach_text, attach_json, attach_html

__all__ = [
    "load_json",
    "load_yaml",
    "load_test_scenarios",
    "get_scenario_ids",
    "capture_screenshot",
    "capture_on_failure",
    "attach_text",
    "attach_json",
    "attach_html",
]
