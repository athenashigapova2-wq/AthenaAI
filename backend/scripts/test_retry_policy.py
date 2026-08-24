"""Offline checks for transient retries and read/write retry boundaries."""

import sys
from pathlib import Path
from unittest.mock import patch

import httpx
from gigachat.exceptions import ResponseError as GigaChatResponseError
from langchain_core.tools import StructuredTool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.common.tool_executor import _invoke_tool  # noqa: E402
from app.config import settings  # noqa: E402
from app.model_routing import ModelSelection  # noqa: E402
from app.resilience import (  # noqa: E402
    http_status_code,
    is_transient_error,
    retry_after_seconds,
    retry_transient,
)
from app.services import agent_traces  # noqa: E402


def _state() -> dict:
    return {
        "user_id": "user-id",
        "run_id": None,
        "locale": "ru",
        "messages": [],
        "route": "nutrition",
    }


def assert_retry_schedule() -> None:
    attempts = 0

    def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.ConnectError("temporary network failure")
        return "ok"

    with (
        patch("app.resilience.time.sleep") as sleep,
        patch("app.resilience.random.uniform", side_effect=[0.1, 0.2]),
    ):
        assert retry_transient(flaky, operation_name="test.read") == "ok"

    assert attempts == 3
    assert [call.args[0] for call in sleep.call_args_list] == [0.6, 1.2]


def assert_non_transient_failure_is_not_retried() -> None:
    attempts = 0

    def invalid() -> None:
        nonlocal attempts
        attempts += 1
        raise ValueError("invalid request")

    try:
        retry_transient(invalid, operation_name="test.invalid")
    except ValueError:
        pass
    else:
        raise AssertionError("A permanent failure must propagate")
    assert attempts == 1


def assert_status_classification() -> None:
    request = httpx.Request("GET", "https://example.test")
    assert is_transient_error(
        httpx.HTTPStatusError(
            "rate limited",
            request=request,
            response=httpx.Response(429, request=request),
        )
    )
    assert not is_transient_error(
        httpx.HTTPStatusError(
            "unauthorized",
            request=request,
            response=httpx.Response(401, request=request),
        )
    )

    rate_limited = GigaChatResponseError(
        "https://gigachat.example/chat/completions",
        429,
        b'{"status":429}',
        {"Retry-After": "3"},
    )
    assert http_status_code(rate_limited) == 429
    assert retry_after_seconds(rate_limited) == 3
    assert is_transient_error(rate_limited)
    assert is_transient_error(
        GigaChatResponseError("https://gigachat.example", 500, b"error", {})
    )
    assert not is_transient_error(
        GigaChatResponseError("https://gigachat.example", 401, b"unauthorized", {})
    )

    unrelated = ValueError("not an HTTP exception", 429)
    assert http_status_code(unrelated) is None
    assert not is_transient_error(unrelated)


def assert_gigachat_rate_limit_is_retried() -> None:
    attempts = 0

    def rate_limited_then_ok() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 4:
            raise GigaChatResponseError(
                "https://gigachat.example",
                429,
                b"limited",
                {"Retry-After": "3"},
            )
        return "ok"

    with (
        patch("app.resilience.time.sleep") as sleep,
        patch("app.resilience.random.uniform", return_value=0.0),
        patch.object(settings, "safe_retry_rate_limit_max_attempts", 4),
        patch.object(settings, "safe_retry_rate_limit_base_delay_seconds", 2.0),
        patch.object(settings, "safe_retry_rate_limit_max_delay_seconds", 30.0),
    ):
        assert retry_transient(rate_limited_then_ok, operation_name="llm.test") == "ok"
    assert attempts == 4
    assert [call.args[0] for call in sleep.call_args_list] == [3.0, 4.0, 8.0]


def assert_llm_is_retried() -> None:
    class FlakyLLM:
        attempts = 0

        def invoke(self, messages):
            self.attempts += 1
            if self.attempts < 3:
                raise httpx.ReadTimeout("provider timeout")
            return "answer"

    llm = FlakyLLM()
    with (
        patch("app.resilience.time.sleep"),
        patch.object(settings, "llm_circuit_breaker_enabled", False),
    ):
        assert agent_traces.invoke_llm(
            llm,
            ["hello"],
            run_id=None,
            node_name="router",
            purpose="test",
            model_tier="small",
        ) == "answer"
    assert llm.attempts == 3


def assert_only_read_tools_are_retried() -> None:
    read_attempts = 0

    def read_tool() -> dict:
        nonlocal read_attempts
        read_attempts += 1
        if read_attempts < 3:
            raise httpx.ConnectError("read failed")
        return {"status": "ok"}

    read = StructuredTool.from_function(
        func=read_tool,
        name="read_tool",
        description="Read test data.",
        metadata={"read_only": True},
    )
    call = {"id": "read-call", "name": "read_tool", "args": {}}
    with patch("app.resilience.time.sleep"):
        assert _invoke_tool(_state(), call, {read.name: read}) == {"status": "ok"}
    assert read_attempts == 3

    write_attempts = 0

    def write_tool() -> dict:
        nonlocal write_attempts
        write_attempts += 1
        raise httpx.ConnectError("write outcome is unknown")

    write = StructuredTool.from_function(
        func=write_tool,
        name="write_tool",
        description="Write test data.",
        metadata={"read_only": False},
    )
    call = {"id": "write-call", "name": "write_tool", "args": {}}
    try:
        _invoke_tool(_state(), call, {write.name: write})
    except httpx.ConnectError:
        pass
    else:
        raise AssertionError("A write failure must propagate without retry")
    assert write_attempts == 1


def assert_each_llm_attempt_is_traced() -> None:
    class FlakyLLM:
        attempts = 0

        def invoke(self, messages):
            self.attempts += 1
            if self.attempts < 3:
                raise httpx.ReadTimeout("provider timeout")
            return "answer"

    selection = ModelSelection(
        provider="gigachat",
        requested_model_tier="small",
        model_tier="main",
        model_name="GigaChat-2",
        matched_rule="router.route_classification",
        selection_reason="matched router rule",
        is_fallback=True,
        fallback_reason="small model is not configured",
    )
    with (
        patch("app.resilience.time.sleep"),
        patch.object(settings, "llm_circuit_breaker_enabled", False),
        patch(
            "app.services.agent_traces.create_llm_call",
            side_effect=["call-1", "call-2", "call-3"],
        ) as create_call,
        patch("app.services.agent_traces.fail_llm_call") as fail_call,
        patch("app.services.agent_traces.succeed_llm_call") as succeed_call,
    ):
        assert agent_traces.invoke_llm(
            FlakyLLM(),
            ["hello"],
            run_id="run-id",
            node_name="router",
            purpose="route_classification",
            model_tier="main",
            model_selection=selection,
        ) == "answer"

    assert create_call.call_count == 3
    create_kwargs = [call.kwargs for call in create_call.call_args_list]
    assert [values["attempt_number"] for values in create_kwargs] == [1, 2, 3]
    assert [values["retry_reason"] for values in create_kwargs] == [
        None,
        "ReadTimeout",
        "ReadTimeout",
    ]
    invocation_ids = {values["invocation_id"] for values in create_kwargs}
    assert len(invocation_ids) == 1
    assert all(values["model_selection"] is selection for values in create_kwargs)
    assert fail_call.call_count == 2
    succeed_call.assert_called_once()
    assert succeed_call.call_args.args[0] == "call-3"


def assert_gigachat_retry_reason_is_traced() -> None:
    class RateLimitedLLM:
        attempts = 0

        def invoke(self, messages):
            self.attempts += 1
            if self.attempts == 1:
                raise GigaChatResponseError(
                    "https://gigachat.example",
                    429,
                    b"limited",
                    {},
                )
            return "answer"

    with (
        patch("app.resilience.time.sleep"),
        patch.object(settings, "llm_circuit_breaker_enabled", False),
        patch(
            "app.services.agent_traces.create_llm_call",
            side_effect=["call-1", "call-2"],
        ) as create_call,
        patch("app.services.agent_traces.fail_llm_call"),
        patch("app.services.agent_traces.succeed_llm_call"),
    ):
        assert agent_traces.invoke_llm(
            RateLimitedLLM(),
            ["hello"],
            run_id="run-id",
            node_name="general",
            purpose="answer",
            model_tier="main",
        ) == "answer"

    create_kwargs = [call.kwargs for call in create_call.call_args_list]
    assert [values["retry_reason"] for values in create_kwargs] == [
        None,
        "ResponseError:http_429",
    ]


def assert_successful_llm_is_not_retried_when_tracing_fails() -> None:
    class SuccessfulLLM:
        attempts = 0

        def invoke(self, messages):
            self.attempts += 1
            return "answer"

    llm = SuccessfulLLM()
    with (
        patch("app.resilience.time.sleep") as sleep,
        patch.object(settings, "llm_circuit_breaker_enabled", False),
        patch(
            "app.services.agent_traces.create_llm_call",
            return_value="call-1",
        ) as create_call,
        patch(
            "app.services.agent_traces.succeed_llm_call",
            side_effect=httpx.RemoteProtocolError("Supabase disconnected"),
        ) as succeed_call,
        patch("app.services.agent_traces.logger.warning") as warning,
    ):
        result = agent_traces.invoke_llm(
            llm,
            ["hello"],
            run_id="run-id",
            node_name="general",
            purpose="answer",
            model_tier="main",
        )

    assert result == "answer"
    assert llm.attempts == 1
    create_call.assert_called_once()
    succeed_call.assert_called_once()
    warning.assert_called_once()
    sleep.assert_not_called()


def assert_llm_runs_when_trace_creation_fails() -> None:
    class SuccessfulLLM:
        attempts = 0

        def invoke(self, messages):
            self.attempts += 1
            return "answer"

    llm = SuccessfulLLM()
    with (
        patch.object(settings, "llm_circuit_breaker_enabled", False),
        patch(
            "app.services.agent_traces.create_llm_call",
            side_effect=httpx.RemoteProtocolError("Supabase disconnected"),
        ) as create_call,
        patch("app.services.agent_traces.succeed_llm_call") as succeed_call,
        patch("app.services.agent_traces.logger.warning") as warning,
    ):
        result = agent_traces.invoke_llm(
            llm,
            ["hello"],
            run_id="run-id",
            node_name="general",
            purpose="answer",
            model_tier="main",
        )

    assert result == "answer"
    assert llm.attempts == 1
    create_call.assert_called_once()
    succeed_call.assert_not_called()
    warning.assert_called_once()


def assert_trace_failure_does_not_mask_provider_failure() -> None:
    class InvalidLLM:
        attempts = 0

        def invoke(self, messages):
            self.attempts += 1
            raise ValueError("provider rejected the request")

    llm = InvalidLLM()
    with (
        patch.object(settings, "llm_circuit_breaker_enabled", False),
        patch("app.services.agent_traces.create_llm_call", return_value="call-1"),
        patch(
            "app.services.agent_traces.fail_llm_call",
            side_effect=httpx.RemoteProtocolError("Supabase disconnected"),
        ) as fail_call,
        patch("app.services.agent_traces.logger.warning") as warning,
    ):
        try:
            agent_traces.invoke_llm(
                llm,
                ["hello"],
                run_id="run-id",
                node_name="general",
                purpose="answer",
                model_tier="main",
            )
        except ValueError as error:
            assert str(error) == "provider rejected the request"
        else:
            raise AssertionError("The original provider failure must propagate")

    assert llm.attempts == 1
    fail_call.assert_called_once()
    warning.assert_called_once()


if __name__ == "__main__":
    # Retry checks are offline; shared admission control has its own fake-Redis
    # test module and must never connect to the developer's Redis here.
    with (
        patch.object(settings, "llm_provider", "gigachat"),
        patch.object(settings, "llm_rate_limiter_enabled", False),
    ):
        assert_retry_schedule()
        assert_non_transient_failure_is_not_retried()
        assert_status_classification()
        assert_gigachat_rate_limit_is_retried()
        assert_llm_is_retried()
        assert_only_read_tools_are_retried()
        assert_each_llm_attempt_is_traced()
        assert_gigachat_retry_reason_is_traced()
        assert_successful_llm_is_not_retried_when_tracing_fails()
        assert_llm_runs_when_trace_creation_fails()
        assert_trace_failure_does_not_mask_provider_failure()
    print("Retry policy checks passed")
