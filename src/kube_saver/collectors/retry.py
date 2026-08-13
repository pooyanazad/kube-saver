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

from kube_saver.config import RetryConfig

logger = logging.getLogger(__name__)

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


__all__ = ["ApiException", "is_transient"]
