"""Retry helpers for operations that are safe to execute more than once."""

from __future__ import annotations

import logging
import random
import ssl
import time
from collections.abc import Callable, Iterator
from typing import TypeVar

import httpx
from gigachat.exceptions import ResponseError as GigaChatResponseError

from app.config import settings

logger = logging.getLogger(__name__)

_TRANSIENT_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
T = TypeVar("T")


def _exception_chain(error: BaseException) -> Iterator[BaseException]:
    """Yield an exception and its causes without looping over malformed chains."""
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def http_status_code(error: BaseException) -> int | None:
    """Extract a validated HTTP status from supported client exceptions."""
    status = getattr(error, "status_code", None)
    if status is None:
        response = getattr(error, "response", None)
        status = getattr(response, "status_code", None)

    # GigaChat SDK exposes ResponseError as
    # ResponseError(url, status_code, body, headers) without status_code or
    # response attributes. Restrict positional extraction to that concrete
    # exception so arbitrary exceptions with an integer argument are not
    # misclassified as HTTP failures.
    if status is None and isinstance(error, GigaChatResponseError):
        arguments = getattr(error, "args", ())
        if len(arguments) > 1:
            status = arguments[1]

    try:
        normalized = int(status) if status is not None else None
    except (TypeError, ValueError):
        return None
    return normalized if normalized is not None and 100 <= normalized <= 599 else None


def retry_after_seconds(error: BaseException) -> float | None:
    """Extract a numeric Retry-After value from a supported HTTP exception."""
    for item in _exception_chain(error):
        response = getattr(item, "response", None)
        headers = getattr(response, "headers", None)
        if headers is None and isinstance(item, GigaChatResponseError):
            arguments = getattr(item, "args", ())
            if len(arguments) > 3:
                headers = arguments[3]
        if not headers:
            continue
        value = next(
            (
                header_value
                for header_name, header_value in headers.items()
                if str(header_name).lower() == "retry-after"
            ),
            None,
        )
        try:
            delay = float(value) if value is not None else None
        except (TypeError, ValueError):
            continue
        if delay is not None and delay >= 0:
            return delay
    return None


def _status_code_in_chain(error: BaseException) -> int | None:
    for item in _exception_chain(error):
        status = http_status_code(item)
        if status is not None:
            return status
    return None


def is_transient_error(error: BaseException) -> bool:
    """Return whether retrying this failure is likely to succeed later."""
    for item in _exception_chain(error):
        if isinstance(
            item,
            (
                TimeoutError,
                ConnectionError,
                ssl.SSLError,
                httpx.TimeoutException,
                httpx.NetworkError,
            ),
        ):
            return True
        if http_status_code(item) in _TRANSIENT_STATUS_CODES:
            return True
    return False


def retry_transient(
    operation: Callable[[], T],
    *,
    operation_name: str,
) -> T:
    """Retry a declared-safe operation with capped exponential backoff and jitter."""
    attempt = 1
    while True:
        try:
            return operation()
        except Exception as error:
            is_rate_limit = _status_code_in_chain(error) == 429
            max_attempts = (
                settings.safe_retry_rate_limit_max_attempts
                if is_rate_limit
                else settings.safe_retry_max_attempts
            )
            if attempt >= max_attempts or not is_transient_error(error):
                raise

            base_delay = (
                settings.safe_retry_rate_limit_base_delay_seconds
                if is_rate_limit
                else settings.safe_retry_base_delay_seconds
            )
            max_delay = (
                settings.safe_retry_rate_limit_max_delay_seconds
                if is_rate_limit
                else settings.safe_retry_max_delay_seconds
            )
            backoff = min(
                max_delay,
                base_delay * (2 ** (attempt - 1)),
            )
            jitter = random.uniform(0.0, backoff * settings.safe_retry_jitter_ratio)
            delay = min(max_delay, backoff + jitter)
            if is_rate_limit:
                provider_delay = retry_after_seconds(error)
                if provider_delay is not None:
                    delay = min(max_delay, max(delay, provider_delay))
            logger.warning(
                "Transient %s failure (%s%s); retrying in %.2fs (attempt %d/%d)",
                operation_name,
                type(error).__name__,
                ", HTTP 429" if is_rate_limit else "",
                delay,
                attempt + 1,
                max_attempts,
            )
            time.sleep(delay)
            attempt += 1
