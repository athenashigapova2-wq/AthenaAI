"""Core retry, circuit-breaker, and admission-control regressions."""

from unittest.mock import patch

import pytest

from app.config import settings
from scripts import test_circuit_breaker as circuit_checks
from scripts import test_rate_limiter as limiter_checks
from scripts import test_retry_policy as retry_checks


pytestmark = pytest.mark.unit


RETRY_CHECKS = (
    retry_checks.assert_retry_schedule,
    retry_checks.assert_non_transient_failure_is_not_retried,
    retry_checks.assert_status_classification,
    retry_checks.assert_gigachat_rate_limit_is_retried,
    retry_checks.assert_llm_is_retried,
    retry_checks.assert_only_read_tools_are_retried,
    retry_checks.assert_each_llm_attempt_is_traced,
    retry_checks.assert_gigachat_retry_reason_is_traced,
    retry_checks.assert_successful_llm_is_not_retried_when_tracing_fails,
    retry_checks.assert_llm_runs_when_trace_creation_fails,
    retry_checks.assert_trace_failure_does_not_mask_provider_failure,
)

CIRCUIT_CHECKS = (
    circuit_checks.check_open_circuit_short_circuits,
    circuit_checks.check_transient_failure_is_recorded_after_retries,
    circuit_checks.check_gigachat_429_is_recorded_once_after_retries,
    circuit_checks.check_half_open_allows_one_successful_probe,
    circuit_checks.check_non_transient_probe_releases_breaker,
    circuit_checks.check_redis_failure_is_fail_open,
    circuit_checks.check_atomic_scripts_use_redis_time,
    circuit_checks.check_rate_limiter_runs_before_every_provider_attempt,
    circuit_checks.check_local_rate_limit_timeout_does_not_mutate_circuit,
)

LIMITER_CHECKS = (
    limiter_checks.check_immediate_permit,
    limiter_checks.check_wait_then_permit,
    limiter_checks.check_timeout_does_not_call_provider_limiter_again,
    limiter_checks.check_redis_failure_is_fail_open,
    limiter_checks.check_atomic_script_uses_redis_time,
)


@pytest.mark.parametrize("check", RETRY_CHECKS, ids=lambda check: check.__name__)
def test_retry_policy(check) -> None:
    with (
        patch.object(settings, "llm_provider", "gigachat"),
        patch.object(settings, "llm_rate_limiter_enabled", False),
    ):
        check()


@pytest.mark.parametrize("check", CIRCUIT_CHECKS, ids=lambda check: check.__name__)
def test_circuit_breaker(check) -> None:
    with (
        patch.object(settings, "llm_circuit_breaker_enabled", True),
        patch.object(settings, "llm_rate_limiter_enabled", False),
    ):
        check()


@pytest.mark.parametrize("check", LIMITER_CHECKS, ids=lambda check: check.__name__)
def test_rate_limiter(check) -> None:
    with (
        patch.object(settings, "llm_rate_limiter_enabled", True),
        patch.object(settings, "llm_rate_limit_requests_per_second", 4.0),
        patch.object(settings, "llm_rate_limit_burst", 4),
        patch.object(settings, "llm_rate_limit_acquire_timeout_seconds", 30.0),
    ):
        check()
