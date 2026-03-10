"""
Logger Configuration Module
============================

Centralises logging setup so every module in the framework uses a consistent
format, level, and output destination.  Logs are written to both the console
(for live feedback during runs) and a rotating file (for post-run analysis).

The module exposes a single factory function ``get_logger`` that all other
modules should use instead of calling ``logging.getLogger`` directly.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOG_FORMAT = '%(asctime)s [%(levelname)-8s] %(name)-30s | %(message)s  File "%(pathname)s", line %(lineno)d'
_LOG_DATE_FMT = "%Y-%m-%d %H:%M:%S"
_CONFIGURED = False


def _ensure_log_dir() -> None:
    """Create the logs directory if it doesn't already exist."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging(level: str = "INFO") -> None:
    """Configure the root logger with console + file handlers.

    This is called once at framework startup (typically from conftest.py).
    Later calls are ignored so parallel workers don't add duplicate
    handlers.

    Args:
        level: Minimum log level as a string (DEBUG, INFO, WARNING, ERROR).
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    _ensure_log_dir()
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(numeric_level)

    console_handler = logging.StreamHandler(stream=sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(logging.Formatter(_LOG_FORMAT, _LOG_DATE_FMT))
    root.addHandler(console_handler)

    file_handler = RotatingFileHandler(
        filename=_LOG_DIR / "test_run.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(_LOG_FORMAT, _LOG_DATE_FMT))
    root.addHandler(file_handler)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger for the given module or class.

    Args:
        name: Typically ``__name__`` of the calling module, or a class name.

    Returns:
        A ``logging.Logger`` instance that inherits the root configuration
        set up by ``setup_logging``.

    Example:

        from core.logger_config import get_logger
        logger = get_logger(__name__)
        logger.info("Page loaded successfully")
    """
    return logging.getLogger(name)
