"""
Settings Module
===============

Loads the framework configuration from ``config/config.yaml`` and merges
in any environment-variable overrides.  This gives us a single ``Settings``
object that every module can import to get the current run's configuration.

Override hierarchy (highest wins):
    1. Environment variables  (``EBAY_BASE_URL``, ``EBAY_HEADLESS``, etc.)
    2. ``config/config.yaml``
    3. Hard-coded defaults in this module

This design lets the same codebase run locally, in Docker, and in CI/CD
without editing any files — just set env vars in your pipeline.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Any, Optional

from utils.data_loader import load_yaml
from core.logger_config import get_logger

logger = get_logger(__name__)

# Maps user-friendly profile names to (playwright_browser_type, channel).
# Channels let Playwright launch branded browser builds (Chrome, Edge)
# instead of the bundled open-source Chromium/Firefox.
BROWSER_PROFILE_MAP: Dict[str, tuple[str, Optional[str]]] = {
    "chromium": ("chromium", None),
    "firefox": ("firefox", None),
    "webkit": ("webkit", None),
    "chrome": ("chromium", "chrome"),
    "chrome-beta": ("chromium", "chrome-beta"),
    "chrome-canary": ("chromium", "chrome-canary"),
    "msedge": ("chromium", "msedge"),
    "msedge-beta": ("chromium", "msedge-beta"),
    "msedge-canary": ("chromium", "msedge-canary"),
}


@dataclass(frozen=True)
class BrowserProfile:
    """Resolved browser profile ready for Playwright launch.

    Attributes:
        id:           The profile name as specified in config (e.g. ``'msedge'``).
        browser_type: Playwright browser engine (``'chromium'``, ``'firefox'``, ``'webkit'``).
        channel:      Optional branded channel passed to ``browser.launch(channel=...)``.
    """
    id: str
    browser_type: str
    channel: Optional[str] = None


def resolve_browser_profile(name: str) -> BrowserProfile:
    """Convert a profile name to a ``BrowserProfile``.

    Looks up the name in ``BROWSER_PROFILE_MAP``.  Unknown names are
    treated as raw Playwright browser types with no channel.

    Args:
        name: Profile name from config or ``EBAY_BROWSER`` env var.

    Returns:
        A ``BrowserProfile`` with the resolved engine and channel.
    """
    browser_type, channel = BROWSER_PROFILE_MAP.get(name, (name, None))
    channel_override = os.environ.get("EBAY_CHANNEL")
    if channel_override:
        channel = channel_override
    return BrowserProfile(id=name, browser_type=browser_type, channel=channel)


@dataclass
class TimeoutSettings:
    """Timeout values used across the framework (all in milliseconds).

    Attributes:
        default:    Standard element-wait timeout.
        navigation: Page-load timeout.
        action:     Timeout for individual user actions (click, fill).
    """
    default: int = 15_000
    navigation: int = 30_000
    action: int = 5_000


@dataclass
class RetrySettings:
    """Configuration for the retry / back-off mechanism.

    Attributes:
        max_attempts:   Total number of tries (including the first).
        backoff_factor: Base delay in seconds.  Doubles each retry.
        jitter:         If True, add ±25 % randomness to the delay.
    """
    max_attempts: int = 3
    backoff_factor: float = 1.0
    jitter: bool = True


@dataclass
class BrowserSettings:
    """Browser launch configuration.

    Attributes:
        headless: Run without a visible browser window.
        slow_mo:  Extra delay (ms) between Playwright actions.
    """
    headless: bool = True
    slow_mo: int = 0


@dataclass
class ViewportSettings:
    """Browser viewport dimensions.

    Attributes:
        width:  Viewport width in pixels.
        height: Viewport height in pixels.
    """
    width: int = 1920
    height: int = 1080


@dataclass
class Settings:
    """Root configuration object for the entire framework.

    Created once at startup by ``load_settings()`` and imported wherever
    config values are needed.

    Attributes:
        base_url:         Target e-commerce site URL.
        browsers:         List of browser profile names for parallel execution.
        timeouts:         Timeout settings.
        retry:            Retry/backoff settings.
        browser_options:  Headless mode, slow_mo, etc.
        viewport:         Browser viewport size.
        allure_results:   Base output directory for Allure JSON results.
        screenshot_on_failure: Capture screenshots on test failure.
        tracing_enabled:  Record Playwright traces.
        log_level:        Logging verbosity.
        run_id:           Unique identifier for this test run (timestamp-based).
    """
    base_url: str = "https://www.ebay.com"
    browsers: List[str] = field(default_factory=lambda: ["chromium"])
    timeouts: TimeoutSettings = field(default_factory=TimeoutSettings)
    retry: RetrySettings = field(default_factory=RetrySettings)
    browser_options: BrowserSettings = field(default_factory=BrowserSettings)
    viewport: ViewportSettings = field(default_factory=ViewportSettings)
    allure_results: str = "allure-results"
    screenshot_on_failure: bool = True
    tracing_enabled: bool = True
    log_level: str = "INFO"
    run_id: str = field(default_factory=lambda: os.environ.get(
        "EBAY_RUN_ID", time.strftime("%Y%m%d_%H%M%S")
    ))

    @property
    def allure_results_for_run(self) -> str:
        """Return a timestamped allure results path: ``allure-results/run_<id>``."""
        return os.path.join(self.allure_results, f"run_{self.run_id}")


def load_settings() -> Settings:
    """Build a ``Settings`` instance from YAML config + environment overrides.

    The function reads ``config/config.yaml``, maps its keys into the
    ``Settings`` dataclass, then checks for environment variables that
    should override specific values.

    Environment variable mapping:
        ``EBAY_BASE_URL``    → ``base_url``
        ``EBAY_HEADLESS``    → ``browser_options.headless``  (``'true'``/``'false'``)
        ``EBAY_BROWSERS``    → ``browsers``  (comma-separated, e.g. ``'chromium,firefox'``)
        ``EBAY_LOG_LEVEL``   → ``log_level``
        ``EBAY_TIMEOUT``     → ``timeouts.default``

    Returns:
        A fully-populated ``Settings`` object.
    """
    try:
        cfg: Dict[str, Any] = load_yaml("config.yaml")
    except FileNotFoundError:
        logger.warning("config.yaml not found — using defaults")
        cfg = {}

    timeouts_cfg = cfg.get("timeouts", {})
    retry_cfg = cfg.get("retry", {})
    browser_opts = cfg.get("browser_options", {})
    viewport_cfg = cfg.get("viewport", {})
    reporting_cfg = cfg.get("reporting", {})
    logging_cfg = cfg.get("logging", {})

    settings = Settings(
        base_url=cfg.get("base_url", Settings.base_url),
        browsers=cfg.get("browsers", ["chromium"]),
        timeouts=TimeoutSettings(
            default=timeouts_cfg.get("default", 15_000),
            navigation=timeouts_cfg.get("navigation", 30_000),
            action=timeouts_cfg.get("action", 5_000),
        ),
        retry=RetrySettings(
            max_attempts=retry_cfg.get("max_attempts", 3),
            backoff_factor=retry_cfg.get("backoff_factor", 1.0),
            jitter=retry_cfg.get("jitter", True),
        ),
        browser_options=BrowserSettings(
            headless=browser_opts.get("headless", True),
            slow_mo=browser_opts.get("slow_mo", 0),
        ),
        viewport=ViewportSettings(
            width=viewport_cfg.get("width", 1920),
            height=viewport_cfg.get("height", 1080),
        ),
        allure_results=reporting_cfg.get("allure_results_dir", "allure-results"),
        screenshot_on_failure=cfg.get("screenshots", {}).get("on_failure", True),
        tracing_enabled=cfg.get("tracing", {}).get("enabled", True),
        log_level=logging_cfg.get("level", "INFO"),
    )

    _apply_env_overrides(settings)
    logger.info("Settings loaded — base_url=%s, browsers=%s", settings.base_url, settings.browsers)
    return settings


def _apply_env_overrides(settings: Settings) -> None:
    """Overwrite settings fields from environment variables when present.

    This is separated into its own function for testability and clarity.

    Supported variables:
        ``EBAY_BASE_URL``  → ``base_url``
        ``EBAY_HEADLESS``  → ``browser_options.headless``
        ``EBAY_BROWSERS``  → ``browsers`` (comma-separated profile names)
        ``EBAY_CHANNEL``   → resolved at profile level via ``resolve_browser_profile``
        ``EBAY_LOG_LEVEL`` → ``log_level``
        ``EBAY_TIMEOUT``   → ``timeouts.default``
        ``EBAY_RUN_ID``    → ``run_id`` (auto-generated if not set)

    Args:
        settings: The ``Settings`` object to mutate in-place.
    """
    if url := os.environ.get("EBAY_BASE_URL"):
        settings.base_url = url

    if headless := os.environ.get("EBAY_HEADLESS"):
        settings.browser_options.headless = headless.lower() == "true"

    if browsers := os.environ.get("EBAY_BROWSERS"):
        settings.browsers = [b.strip() for b in browsers.split(",")]

    if log_level := os.environ.get("EBAY_LOG_LEVEL"):
        settings.log_level = log_level.upper()

    if timeout := os.environ.get("EBAY_TIMEOUT"):
        settings.timeouts.default = int(timeout)

    if run_id := os.environ.get("EBAY_RUN_ID"):
        settings.run_id = run_id

    # Publish run_id so xdist workers and subprocesses share it
    os.environ.setdefault("EBAY_RUN_ID", settings.run_id)
