"""
Retry Handler Module
====================

Implements retry-with-exponential-backoff for any callable.  This is critical
for handling unstable environments where transient failures (network hiccups,
slow DOM updates, momentary stale elements) would otherwise break tests.

Two public APIs are provided:

* ``with_retry`` – A decorator that wraps a function with automatic retry logic.
* ``retry_call`` – A standalone helper for one-off retries without decorating.

Both support configurable attempt counts, backoff multipliers, jitter, and
an optional callback that fires before each retry (useful for logging or
taking screenshots).
"""

from __future__ import annotations

import functools
import random
import time
from typing import Any, Callable, Optional, Tuple, Type

from core.logger_config import get_logger

logger = get_logger(__name__)


def with_retry(
    max_attempts: int = 3,
    backoff_factor: float = 1.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None,
):
    """Decorator that retries a function on failure with exponential backoff.

    The wait between attempts follows the formula::

        wait = backoff_factor * (2 ** (attempt - 1))  [+ random jitter]

    This means with defaults the waits are roughly 1 s, 2 s, 4 s, …

    Args:
        max_attempts:   Total number of tries (including the first).
        backoff_factor: Base seconds for the exponential delay.
        jitter:         If True, add ±25 % randomness to avoid thundering-herd.
        exceptions:     Tuple of exception types that trigger a retry.
                        Exceptions *not* in this tuple propagate immediately.
        on_retry:       Optional callback ``(attempt_number, exception) -> None``
                        invoked right before sleeping.  Useful for screenshots
                        or extra logging.

    Returns:
        The decorated function's return value on the first successful attempt.

    Raises:
        The last captured exception if all attempts are exhausted.

    Example::

        @with_retry(max_attempts=3, backoff_factor=0.5)
        def click_add_to_cart(page):
            page.locator("#addToCart").click()
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_error: Optional[Exception] = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_error = exc
                    if attempt < max_attempts:
                        wait = backoff_factor * (2 ** (attempt - 1))
                        if jitter:
                            wait *= 1 + random.uniform(-0.25, 0.25)
                        logger.warning(
                            "Attempt %d/%d for '%s' failed: %s — retrying in %.2fs",
                            attempt,
                            max_attempts,
                            func.__name__,
                            exc,
                            wait,
                        )
                        if on_retry:
                            on_retry(attempt, exc)
                        time.sleep(wait)
                    else:
                        logger.error(
                            "All %d attempts exhausted for '%s'. Last error: %s",
                            max_attempts,
                            func.__name__,
                            exc,
                        )

            raise last_error  # type: ignore[misc]

        return wrapper

    return decorator


def retry_call(
    func: Callable,
    *args: Any,
    max_attempts: int = 3,
    backoff_factor: float = 1.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None,
    **kwargs: Any,
) -> Any:
    """Execute ``func(*args, **kwargs)`` with retry logic (non-decorator form).

    Useful when you need retry behaviour for a single call site without
    permanently decorating the function.

    Args:
        func:           The callable to invoke.
        *args:          Positional arguments forwarded to *func*.
        max_attempts:   Total tries (including the first).
        backoff_factor: Base seconds for exponential delay.
        jitter:         Add ±25 % randomness to the delay.
        exceptions:     Exception types that trigger a retry.
        on_retry:       Optional pre-retry callback.
        **kwargs:       Keyword arguments forwarded to *func*.

    Returns:
        The return value of *func* on success.

    Raises:
        The last exception if all attempts fail.
    """
    decorated = with_retry(
        max_attempts=max_attempts,
        backoff_factor=backoff_factor,
        jitter=jitter,
        exceptions=exceptions,
        on_retry=on_retry,
    )(func)
    return decorated(*args, **kwargs)
