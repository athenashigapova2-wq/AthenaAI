"""Redis-backed token-bucket limiter shared by all LLM workers."""

from __future__ import annotations

import logging
import math
import re
import time
from functools import lru_cache

from redis import Redis
from redis.exceptions import RedisError

from app.config import settings

logger = logging.getLogger(__name__)

_KEY_PREFIX = "athena:rate-limit:"

# GCRA is a token-bucket equivalent that needs only one timestamp. Redis TIME
# keeps the decision consistent across processes and hosts, and the Lua script
# makes admission atomic for every Celery thread/container.
_ACQUIRE_SCRIPT = r"""
local key = KEYS[1]
local interval_ms = tonumber(ARGV[1])
local burst = tonumber(ARGV[2])
local ttl_ms = tonumber(ARGV[3])
local redis_time = redis.call("TIME")
local now_ms = tonumber(redis_time[1]) * 1000 + math.floor(tonumber(redis_time[2]) / 1000)
local tat_ms = tonumber(redis.call("GET", key) or tostring(now_ms))
local earliest_ms = tat_ms - ((burst - 1) * interval_ms)

if now_ms < earliest_ms then
    return {0, math.ceil(earliest_ms - now_ms)}
end

local next_tat_ms = math.max(tat_ms, now_ms) + interval_ms
redis.call("SET", key, next_tat_ms, "PX", ttl_ms)
return {1, 0}
"""


class RateLimitAcquireTimeout(RuntimeError):
    """Raised locally when a provider permit cannot be obtained in time."""

    def __init__(self, name: str, retry_after_seconds: float) -> None:
        self.name = name
        self.retry_after_seconds = max(0.0, retry_after_seconds)
        super().__init__(
            f"Rate limiter {name!r} could not grant a permit within the "
            f"configured timeout; retry after {self.retry_after_seconds:.2f}s"
        )


@lru_cache(maxsize=1)
def redis_client() -> Redis:
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
        health_check_interval=30,
    )


def _key(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9:_-]+", "-", name.strip().lower()).strip("-")
    if not normalized:
        raise ValueError("Rate limiter name must not be empty")
    return f"{_KEY_PREFIX}{normalized}"


def _interval_ms() -> int:
    return max(1, math.ceil(1_000 / settings.llm_rate_limit_requests_per_second))


def _state_ttl_ms() -> int:
    bucket_seconds = (
        settings.llm_rate_limit_burst
        / settings.llm_rate_limit_requests_per_second
    )
    minimum = bucket_seconds + settings.llm_rate_limit_acquire_timeout_seconds + 60
    return math.ceil(max(settings.llm_rate_limit_state_ttl_seconds, minimum) * 1_000)


def acquire_rate_limit(name: str) -> None:
    """Wait for one shared provider permit, or fail open if Redis is down."""
    if not settings.llm_rate_limiter_enabled:
        return

    timeout = settings.llm_rate_limit_acquire_timeout_seconds
    deadline = time.monotonic() + timeout
    while True:
        try:
            result = redis_client().eval(
                _ACQUIRE_SCRIPT,
                1,
                _key(name),
                _interval_ms(),
                settings.llm_rate_limit_burst,
                _state_ttl_ms(),
            )
        except RedisError as error:
            logger.warning(
                "Rate limiter Redis check failed; allowing %s call: %s",
                name,
                type(error).__name__,
            )
            return

        if bool(int(result[0])):
            return

        retry_after_seconds = max(0.001, float(result[1]) / 1_000)
        remaining_seconds = max(0.0, deadline - time.monotonic())
        if retry_after_seconds > remaining_seconds:
            raise RateLimitAcquireTimeout(name, retry_after_seconds)
        time.sleep(retry_after_seconds)
