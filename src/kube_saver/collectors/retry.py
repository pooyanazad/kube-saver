"""Retry helpers for transient Kubernetes API failures.

C2.1c introduces ``is_transient(exc, retry_config)`` which decides whether a
given exception is worth retrying. It recognises:

- ``ApiException`` with a retryable HTTP status code (429, 5xx by default)
- ``TimeoutError`` (request deadline exceeded)
- ``ConnectionError`` (network reset / refused)

Everything else (4xx other than 429, generic exceptions) is treated as
non-transient so we fail fast instead of burning retry budget on errors
that will never succeed on the second try.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from typing import TypeVar

from kube_saver.config import RetryConfig

logger = logging.getLogger(__name__)

T = TypeVar("T")

try:
    from kubernetes.client.rest import ApiException  # type: ignore[import-untyped]

    _K8S_AVAILABLE = True
except ImportError:
    _K8S_AVAILABLE = False

    class ApiException(Exception):  # type: ignore[no-redef]  # noqa: N818
        """Fallback when the kubernetes package is not installed."""

        status: int | None = None


def is_transient(exc: BaseException, retry_config: RetryConfig | None = None) -> bool:
    """Return True if ``exc`` is a transient, retryable error.

    Args:
        exc: The exception raised by the API call.
        retry_config: Retry policy whose ``retryable_status_codes`` set is
            consulted for ``ApiException`` instances. When None, the default
            RetryConfig is used (429 + 5xx).

    Returns:
        True for retryable HTTP status codes, timeouts, and connection
        errors; False for everything else (including non-ApiException
        errors that are not TimeoutError/ConnectionError).
    """
    cfg = retry_config or RetryConfig()
    if isinstance(exc, ApiException):
        status = getattr(exc, "status", None)
        if status is None:
            return False
        try:
            return int(status) in cfg.retryable_status_codes
        except (TypeError, ValueError):
            return False
    return isinstance(exc, (TimeoutError, ConnectionError))


def _backoff_ms(attempt: int, cfg: RetryConfig) -> float:
    """Return the backoff in milliseconds for a given attempt (1-indexed).

    Exponential growth capped at ``max_backoff_ms``. ``attempt=1`` is the
    first retry, so the wait is ``initial_backoff_ms``. Each subsequent
    retry doubles the base.

    Args:
        attempt: Retry attempt number, starting at 1.
        cfg: Retry policy supplying backoff bounds.

    Returns:
        Capped backoff in milliseconds.
    """
    base = cfg.initial_backoff_ms * (2 ** max(attempt - 1, 0))
    return float(min(base, cfg.max_backoff_ms))


def _reason(exc: BaseException) -> str:
    """Return a short, stable reason string for an exception.

    For ``ApiException`` we include the HTTP status so the log line stays
    useful even when the exception's own ``str()`` is unhelpful. For
    timeouts and connection errors we use the exception name plus any
    message. Falls back to ``repr`` for unknown types.

    Args:
        exc: The exception raised by the API call.

    Returns:
        A short human-readable reason string suitable for log records.
    """
    if isinstance(exc, ApiException):
        status = getattr(exc, "status", None)
        reason = getattr(exc, "reason", None) or ""
        if status is not None:
            return f"http {status}".strip() if not reason else f"http {status}: {reason}".strip()
        return reason or type(exc).__name__
    msg = str(exc).strip()
    return f"{type(exc).__name__}: {msg}" if msg else type(exc).__name__


def retry_call(
    fn: Callable[[], T],
    *,
    operation: str,
    retry_config: RetryConfig | None = None,
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[float, float], float] = random.uniform,
) -> T:
    """Call ``fn()`` with bounded retries on transient failures.

    Args:
        fn: Zero-argument callable producing the result.
        operation: Human-readable operation name used in log messages.
        retry_config: Retry policy. When None, the default RetryConfig is
            used. The config is normalized first so invalid values cannot
            disable retries.
        sleep: Sleep function used for backoff waits (injectable for tests).
        jitter: Function returning a random float in ``[lo, hi)`` used to
            jitter the backoff (injectable for tests).

    Returns:
        The value returned by ``fn`` on a successful attempt.

    Raises:
        Exception: The last exception raised by ``fn`` if all attempts
            fail (or immediately if the failure is non-transient).
    """
    cfg = (retry_config or RetryConfig()).normalized()
    last_exc: BaseException | None = None
    for attempt in range(1, cfg.max_attempts + 1):
        try:
            result = fn()
            if attempt > 1:
                logger.info(
                    "operation %s succeeded on attempt %d", operation, attempt
                )
            return result
        except Exception as exc:
            last_exc = exc
            if not is_transient(exc, cfg) or attempt >= cfg.max_attempts:
                if is_transient(exc, cfg):
                    logger.error(
                        "operation %s failed after %d attempts: %s",
                        operation,
                        attempt,
                        exc,
                    )
                else:
                    logger.error(
                        "operation %s failed on attempt %d (non-transient): %s",
                        operation,
                        attempt,
                        exc,
                    )
                raise
            wait_ms = _backoff_ms(attempt, cfg)
            wait_jittered = jitter(0.0, wait_ms)
            logger.warning(
                "operation %s attempt %d failed: %s; retrying in %.2fms",
                operation,
                attempt,
                exc,
                wait_jittered,
            )
            sleep(wait_jittered / 1_000.0)
    # Unreachable: loop raises on the final attempt. Kept for type safety.
    assert last_exc is not None
    raise last_exc


__all__ = ["ApiException", "is_transient", "retry_call"]
