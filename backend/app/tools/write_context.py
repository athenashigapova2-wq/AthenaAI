"""Process-local context for an authenticated, confirmed write execution."""

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator


_idempotency_key: ContextVar[str | None] = ContextVar(
    "confirmed_write_idempotency_key",
    default=None,
)


@contextmanager
def confirmed_write_context(idempotency_key: str) -> Iterator[None]:
    token = _idempotency_key.set(idempotency_key)
    try:
        yield
    finally:
        _idempotency_key.reset(token)


def require_idempotency_key() -> str:
    key = _idempotency_key.get()
    if not key:
        raise PermissionError(
            "write tool execution requires an authenticated confirmation and idempotency key"
        )
    return key
