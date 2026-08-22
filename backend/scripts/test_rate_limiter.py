"""Offline checks for the Redis-backed shared LLM rate limiter."""

import sys
from pathlib import Path
from unittest.mock import patch

from redis.exceptions import RedisError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.rate_limiter import (  # noqa: E402
    RateLimitAcquireTimeout,
    _ACQUIRE_SCRIPT,
    acquire_rate_limit,
)


class FakeRedis:
    def __init__(self, *results) -> None:
        self.results = list(results)
        self.eval_calls: list[tuple[str, int, tuple]] = []

    def eval(self, script: str, numkeys: int, *args):
        self.eval_calls.append((script, numkeys, args))
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def check_immediate_permit() -> None:
    client = FakeRedis([1, 0])
    with patch("app.rate_limiter.redis_client", return_value=client):
        acquire_rate_limit("gigachat")

    assert len(client.eval_calls) == 1
    _, numkeys, args = client.eval_calls[0]
    assert numkeys == 1
    assert args[0] == "athena:rate-limit:gigachat"
    assert args[1] == 250
    assert args[2] == 4


def check_wait_then_permit() -> None:
    client = FakeRedis([0, 250], [1, 0])
    with (
        patch("app.rate_limiter.redis_client", return_value=client),
        patch("app.rate_limiter.time.monotonic", side_effect=[0.0, 0.0]),
        patch("app.rate_limiter.time.sleep") as sleep,
    ):
        acquire_rate_limit("gigachat")

    sleep.assert_called_once_with(0.25)
    assert len(client.eval_calls) == 2


def check_timeout_does_not_call_provider_limiter_again() -> None:
    client = FakeRedis([0, 250])
    with (
        patch("app.rate_limiter.redis_client", return_value=client),
        patch("app.rate_limiter.time.monotonic", side_effect=[0.0, 0.0]),
        patch("app.rate_limiter.time.sleep") as sleep,
        patch.object(settings, "llm_rate_limit_acquire_timeout_seconds", 0.1),
    ):
        try:
            acquire_rate_limit("gigachat")
        except RateLimitAcquireTimeout as error:
            assert error.retry_after_seconds == 0.25
        else:
            raise AssertionError("The limiter must honor its acquire timeout")

    sleep.assert_not_called()
    assert len(client.eval_calls) == 1


def check_redis_failure_is_fail_open() -> None:
    client = FakeRedis(RedisError("redis unavailable"))
    with patch("app.rate_limiter.redis_client", return_value=client):
        acquire_rate_limit("gigachat")
    assert len(client.eval_calls) == 1


def check_atomic_script_uses_redis_time() -> None:
    assert 'redis.call("TIME")' in _ACQUIRE_SCRIPT
    assert 'redis.call("GET", key)' in _ACQUIRE_SCRIPT
    assert 'redis.call("SET", key' in _ACQUIRE_SCRIPT
    assert '"PX", ttl_ms' in _ACQUIRE_SCRIPT


if __name__ == "__main__":
    with (
        patch.object(settings, "llm_rate_limiter_enabled", True),
        patch.object(settings, "llm_rate_limit_requests_per_second", 4.0),
        patch.object(settings, "llm_rate_limit_burst", 4),
        patch.object(settings, "llm_rate_limit_acquire_timeout_seconds", 30.0),
    ):
        check_immediate_permit()
        check_wait_then_permit()
        check_timeout_does_not_call_provider_limiter_again()
        check_redis_failure_is_fail_open()
        check_atomic_script_uses_redis_time()
    print("Rate limiter checks passed")
