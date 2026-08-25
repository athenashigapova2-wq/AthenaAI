"""Persistence helpers for agent-run observability in Supabase."""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any, TypeVar
from uuid import uuid4

from app.circuit_breaker import call_with_circuit_breaker
from app.config import settings
from app.model_routing import ModelSelection, model_name_for_tier
from app.resilience import http_status_code
from app.services.agent_jobs import publish_current_job_progress
from app.services.supabase import get_supabase
from app.trace_privacy import (
    REDACTION_VERSION,
    payload_expiry,
    payload_mode_for_run,
    protect_mapping,
    protect_payload,
    safe_error,
)

logger = logging.getLogger(__name__)
_TraceResult = TypeVar("_TraceResult")


def _model_name(model_tier: str = "main") -> str:
    return model_name_for_tier(model_tier)


def _model_provider(model_selection: ModelSelection | None = None) -> str:
    if model_selection is not None:
        return model_selection.provider
    return settings.llm_provider


def elapsed_ms(started_at: float) -> int:
    """Return elapsed monotonic time in whole milliseconds."""
    return max(0, round((perf_counter() - started_at) * 1_000))


def _completed_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_agent_run(
    user_id: str,
    input_text: str,
    conversation_id: str | None = None,
) -> str:
    """Create a started run and return its database id."""
    run_id = str(uuid4())
    payload_mode = payload_mode_for_run(run_id)
    response = (
        get_supabase()
        .table("agent_runs")
        .insert(
            {
                "id": run_id,
                "user_id": user_id,
                "route": "general",
                "model_provider": _model_provider(),
                "model_name": _model_name(),
                "input_text": protect_payload(input_text, payload_mode),
                "conversation_id": conversation_id,
                "status": "started",
                "resolution_mode": "main_llm",
                "baseline_version": settings.agent_baseline_version,
                "payload_mode": payload_mode,
                "redaction_version": REDACTION_VERSION,
                "raw_payload_expires_at": payload_expiry(payload_mode),
            }
        )
        .execute()
    )
    if not response.data:
        raise RuntimeError("Supabase не вернул созданный agent_run")
    return run_id


def succeed_agent_run(
    run_id: str,
    user_id: str,
    route: str,
    output_text: str,
    latency_ms: int,
    resolution_mode: str = "main_llm",
    routing_fallback_reason: str | None = None,
) -> None:
    """Mark one user-owned run as successfully completed."""
    payload_mode = payload_mode_for_run(run_id)
    values: dict[str, Any] = {
        "route": route,
        "output_text": protect_payload(output_text, payload_mode),
        "status": "succeeded",
        "latency_ms": latency_ms,
        "resolution_mode": resolution_mode,
        "completed_at": _completed_at(),
    }
    if routing_fallback_reason is not None:
        values["routing_fallback_reason"] = routing_fallback_reason
    _update_owned_run(
        run_id,
        user_id,
        values,
    )


def fail_agent_run(
    run_id: str,
    user_id: str,
    error: Exception,
    latency_ms: int,
) -> None:
    """Mark one user-owned run as failed without storing a traceback."""
    payload_mode = payload_mode_for_run(run_id)
    error_message = safe_error(error, payload_mode)
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


def record_routing_fallback(
    *,
    run_id: str | None,
    user_id: str | None,
    reason: str,
) -> None:
    """Best-effort persistence for a degraded Router Agent decision."""
    if run_id is None or user_id is None:
        return
    try:
        _update_owned_run(
            run_id,
            user_id,
            {"routing_fallback_reason": reason[:250]},
        )
    except Exception:
        logger.warning(
            "Could not persist routing fallback reason for run %s",
            run_id,
            exc_info=True,
        )


def create_tool_call(
    run_id: str,
    tool_name: str,
    tool_args: dict[str, Any],
    tool_step: int = 1,
) -> str:
    """Create a started tool-call trace linked to its parent agent run."""
    payload_mode = payload_mode_for_run(run_id)
    response = (
        get_supabase()
        .table("agent_tool_calls")
        .insert(
            {
                "run_id": run_id,
                "tool_name": tool_name,
                "tool_args": protect_mapping(tool_args, payload_mode),
                "tool_step": tool_step,
                "status": "started",
            }
        )
        .execute()
    )
    if not response.data:
        raise RuntimeError("Supabase не вернул созданный agent_tool_call")
    return str(response.data[0]["id"])


def create_llm_call(
    run_id: str,
    node_name: str,
    purpose: str,
    model_tier: str,
    model_name: str | None = None,
    *,
    invocation_id: str | None = None,
    attempt_number: int = 1,
    model_selection: ModelSelection | None = None,
    retry_reason: str | None = None,
) -> str:
    """Create one row for one actual provider attempt."""
    selection_payload = _model_selection_payload(
        model_selection=model_selection,
        model_tier=model_tier,
        model_name=model_name,
    )
    response = (
        get_supabase()
        .table("agent_llm_calls")
        .insert(
            {
                "run_id": run_id,
                "node_name": node_name,
                "purpose": purpose,
                "model_provider": _model_provider(model_selection),
                **selection_payload,
                "invocation_id": invocation_id or str(uuid4()),
                "attempt_number": attempt_number,
                "retry_reason": retry_reason,
                "status": "started",
            }
        )
        .execute()
    )
    if not response.data:
        raise RuntimeError("Supabase не вернул созданный agent_llm_call")
    return str(response.data[0]["id"])


def _model_selection_payload(
    *,
    model_selection: ModelSelection | None,
    model_tier: str,
    model_name: str | None,
) -> dict[str, Any]:
    if model_selection is not None:
        return {
            "model_name": model_selection.model_name,
            "model_tier": model_selection.model_tier,
            "requested_model_tier": model_selection.requested_model_tier,
            "routing_rule": model_selection.matched_rule,
            "selection_reason": model_selection.selection_reason,
            "is_fallback": model_selection.is_fallback,
            "fallback_reason": model_selection.fallback_reason,
        }
    return {
        "model_name": model_name or _model_name(model_tier),
        "model_tier": model_tier,
        "requested_model_tier": model_tier,
        "routing_rule": "legacy",
        "selection_reason": "model supplied without routing metadata",
        "is_fallback": False,
        "fallback_reason": None,
    }


def token_usage(message: Any) -> dict[str, int | bool]:
    """Normalize LangChain provider token metadata without guessing missing values."""
    usage = getattr(message, "usage_metadata", None) or {}
    response_metadata = getattr(message, "response_metadata", {})
    response_usage = response_metadata.get("token_usage") or response_metadata.get("usage") or {}
    input_tokens = int(
        usage.get("input_tokens")
        or response_usage.get("input_tokens")
        or response_usage.get("prompt_tokens")
        or 0
    )
    output_tokens = int(
        usage.get("output_tokens")
        or response_usage.get("output_tokens")
        or response_usage.get("completion_tokens")
        or 0
    )
    cached = int(
        usage.get("input_token_details", {}).get("cache_read")
        or response_usage.get("cached_tokens")
        or 0
    )
    total = int(usage.get("total_tokens") or response_usage.get("total_tokens") or input_tokens + output_tokens)
    return {
        "token_usage_available": bool(usage or response_usage),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_input_tokens": cached,
        "total_tokens": total,
    }


def succeed_llm_call(llm_call_id: str, run_id: str, message: Any, latency_ms: int) -> None:
    _update_run_llm_call(
        llm_call_id,
        run_id,
        {
            **token_usage(message),
            "status": "succeeded",
            "latency_ms": latency_ms,
            "completed_at": _completed_at(),
        },
    )


def fail_llm_call(llm_call_id: str, run_id: str, error: Exception, latency_ms: int) -> None:
    payload_mode = payload_mode_for_run(run_id)
    _update_run_llm_call(
        llm_call_id,
        run_id,
        {
            "status": "failed",
            "error_message": safe_error(error, payload_mode),
            "latency_ms": latency_ms,
            "completed_at": _completed_at(),
        },
    )


def _best_effort_llm_trace(
    operation: Callable[[], _TraceResult],
    *,
    action: str,
) -> _TraceResult | None:
    """Run LLM observability work without changing the provider outcome."""
    try:
        return operation()
    except Exception:
        logger.warning(
            "LLM tracing %s failed; preserving the provider outcome",
            action,
            exc_info=True,
        )
        return None


def invoke_llm(
    llm: Any,
    messages: list[Any],
    *,
    run_id: str | None,
    node_name: str,
    purpose: str,
    model_tier: str,
    model_name: str | None = None,
    model_selection: ModelSelection | None = None,
) -> Any:
    """Invoke an LLM and persist every actual provider attempt."""
    invocation_id = str(uuid4())
    attempt_number = 0
    retry_reason: str | None = None

    def invoke_attempt() -> Any:
        nonlocal attempt_number, retry_reason
        publish_current_job_progress("generating", node=node_name, purpose=purpose)
        attempt_number += 1
        if run_id is None:
            return llm.invoke(messages)

        llm_call_id = _best_effort_llm_trace(
            lambda: create_llm_call(
                run_id,
                node_name,
                purpose,
                model_tier,
                model_name=model_name,
                invocation_id=invocation_id,
                attempt_number=attempt_number,
                model_selection=model_selection,
                retry_reason=retry_reason,
            ),
            action="create",
        )
        started_at = perf_counter()
        try:
            message = llm.invoke(messages)
        except Exception as error:
            if llm_call_id is not None:
                failed_call_id = llm_call_id
                failed_error = error
                _best_effort_llm_trace(
                    lambda: fail_llm_call(
                        failed_call_id,
                        run_id,
                        failed_error,
                        elapsed_ms(started_at),
                    ),
                    action="mark_failed",
                )
            retry_reason = _retry_reason(error)
            raise
        if llm_call_id is not None:
            _best_effort_llm_trace(
                lambda: succeed_llm_call(
                    llm_call_id,
                    run_id,
                    message,
                    elapsed_ms(started_at),
                ),
                action="mark_succeeded",
            )
        return message

    provider = _model_provider(model_selection)
    if provider == "mock":
        return invoke_attempt()

    return call_with_circuit_breaker(
        invoke_attempt,
        circuit_name=provider,
        operation_name=f"llm.{node_name}.{purpose}",
    )


def _retry_reason(error: BaseException) -> str:
    status = http_status_code(error)
    if status is not None:
        return f"{type(error).__name__}:http_{status}"
    return type(error).__name__


def succeed_tool_call(
    tool_call_id: str,
    run_id: str,
    tool_result: Any,
    latency_ms: int,
) -> None:
    """Mark a tool call as succeeded and store its structured result."""
    payload_mode = payload_mode_for_run(run_id)
    protected_result = protect_payload(tool_result, payload_mode)
    _update_run_tool_call(
        tool_call_id,
        run_id,
        {
            "tool_result": {} if protected_result is None else protected_result,
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
    payload_mode = payload_mode_for_run(run_id)
    error_message = safe_error(error, payload_mode)
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


def export_user_traces(user_id: str) -> dict[str, Any]:
    """Export the authenticated user's bounded trace history."""
    client = get_supabase()
    runs_response = (
        client.table("agent_runs")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(settings.trace_export_max_runs + 1)
        .execute()
    )
    runs = list(runs_response.data or [])
    truncated = len(runs) > settings.trace_export_max_runs
    runs = runs[: settings.trace_export_max_runs]
    run_ids = [str(run["id"]) for run in runs]
    tool_calls: list[dict[str, Any]] = []
    llm_calls: list[dict[str, Any]] = []
    if run_ids:
        tool_calls = _export_child_traces(client, "agent_tool_calls", run_ids)
        llm_calls = _export_child_traces(client, "agent_llm_calls", run_ids)
    return {
        "exported_at": _completed_at(),
        "truncated": truncated,
        "runs": runs,
        "tool_calls": tool_calls,
        "llm_calls": llm_calls,
    }


def delete_user_traces(user_id: str) -> int:
    """Delete all runs owned by one user; child rows cascade in PostgreSQL."""
    client = get_supabase()
    owned = (
        client.table("agent_runs")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    count = int(owned.count or 0)
    if count:
        client.table("agent_runs").delete().eq("user_id", user_id).execute()
    return count


def _export_child_traces(
    client: Any,
    table_name: str,
    run_ids: list[str],
) -> list[dict[str, Any]]:
    """Export every child row for a bounded run set without PostgREST truncation."""
    exported: list[dict[str, Any]] = []
    page_size = 1_000
    for batch_start in range(0, len(run_ids), 100):
        batch = run_ids[batch_start : batch_start + 100]
        page_start = 0
        while True:
            response = (
                client.table(table_name)
                .select("*")
                .in_("run_id", batch)
                .order("created_at")
                .range(page_start, page_start + page_size - 1)
                .execute()
            )
            rows = list(response.data or [])
            exported.extend(rows)
            if len(rows) < page_size:
                break
            page_start += page_size
    return exported


def enforce_trace_retention() -> None:
    """Purge expired payloads first, then delete expired structured records."""
    client = get_supabase()
    client.rpc("purge_expired_agent_trace_payloads").execute()
    before = datetime.now(timezone.utc) - timedelta(
        days=settings.trace_record_retention_days
    )
    client.rpc(
        "purge_expired_agent_traces",
        {"p_before": before.isoformat()},
    ).execute()


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


def _update_run_llm_call(
    llm_call_id: str,
    run_id: str,
    values: dict[str, Any],
) -> None:
    (
        get_supabase()
        .table("agent_llm_calls")
        .update(values)
        .eq("id", llm_call_id)
        .eq("run_id", run_id)
        .execute()
    )
