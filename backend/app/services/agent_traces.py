"""Persistence helpers for agent-run observability in Supabase."""

from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from app.config import settings
from app.services.supabase import get_supabase


def _model_name() -> str:
    if settings.llm_provider.lower() == "anthropic":
        return settings.anthropic_model
    return settings.gigachat_model


def elapsed_ms(started_at: float) -> int:
    """Return elapsed monotonic time in whole milliseconds."""
    return max(0, round((perf_counter() - started_at) * 1_000))


def _completed_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_agent_run(user_id: str, input_text: str) -> str:
    """Create a started run and return its database id."""
    response = (
        get_supabase()
        .table("agent_runs")
        .insert(
            {
                "user_id": user_id,
                "route": "general",
                "model_provider": settings.llm_provider,
                "model_name": _model_name(),
                "input_text": input_text,
                "status": "started",
            }
        )
        .execute()
    )
    if not response.data:
        raise RuntimeError("Supabase не вернул созданный agent_run")
    return str(response.data[0]["id"])


def succeed_agent_run(
    run_id: str,
    user_id: str,
    route: str,
    output_text: str,
    latency_ms: int,
) -> None:
    """Mark one user-owned run as successfully completed."""
    _update_owned_run(
        run_id,
        user_id,
        {
            "route": route,
            "output_text": output_text,
            "status": "succeeded",
            "latency_ms": latency_ms,
            "completed_at": _completed_at(),
        },
    )


def fail_agent_run(
    run_id: str,
    user_id: str,
    error: Exception,
    latency_ms: int,
) -> None:
    """Mark one user-owned run as failed without storing a traceback."""
    error_message = f"{type(error).__name__}: {error}"[:1_000]
    _update_owned_run(
        run_id,
        user_id,
        {
            "status": "failed",
            "error_message": error_message,
            "latency_ms": latency_ms,
            "completed_at": _completed_at(),
        },
    )


def create_tool_call(run_id: str, tool_name: str, tool_args: dict[str, Any]) -> str:
    """Create a started tool-call trace linked to its parent agent run."""
    response = (
        get_supabase()
        .table("agent_tool_calls")
        .insert(
            {
                "run_id": run_id,
                "tool_name": tool_name,
                "tool_args": tool_args,
                "status": "started",
            }
        )
        .execute()
    )
    if not response.data:
        raise RuntimeError("Supabase не вернул созданный agent_tool_call")
    return str(response.data[0]["id"])


def succeed_tool_call(
    tool_call_id: str,
    run_id: str,
    tool_result: Any,
    latency_ms: int,
) -> None:
    """Mark a tool call as succeeded and store its structured result."""
    _update_run_tool_call(
        tool_call_id,
        run_id,
        {
            "tool_result": tool_result,
            "status": "succeeded",
            "latency_ms": latency_ms,
            "completed_at": _completed_at(),
        },
    )


def fail_tool_call(
    tool_call_id: str,
    run_id: str,
    error: Exception,
    latency_ms: int,
) -> None:
    """Mark a tool call as failed without persisting a traceback."""
    error_message = f"{type(error).__name__}: {error}"[:1_000]
    _update_run_tool_call(
        tool_call_id,
        run_id,
        {
            "status": "failed",
            "error_message": error_message,
            "latency_ms": latency_ms,
            "completed_at": _completed_at(),
        },
    )


def _update_owned_run(run_id: str, user_id: str, values: dict[str, Any]) -> None:
    """Update by both id and user_id because the server client bypasses RLS."""
    (
        get_supabase()
        .table("agent_runs")
        .update(values)
        .eq("id", run_id)
        .eq("user_id", user_id)
        .execute()
    )


def _update_run_tool_call(
    tool_call_id: str,
    run_id: str,
    values: dict[str, Any],
) -> None:
    """Scope tool-call updates to both the call and its trusted parent run."""
    (
        get_supabase()
        .table("agent_tool_calls")
        .update(values)
        .eq("id", tool_call_id)
        .eq("run_id", run_id)
        .execute()
    )
