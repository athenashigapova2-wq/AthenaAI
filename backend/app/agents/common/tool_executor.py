"""Validated, traced execution of specialist tools."""

from time import perf_counter
from typing import Any

from langchain_core.tools import BaseTool

from app.agents.state import AgentState
from app.resilience import retry_transient
from app.services import agent_jobs, agent_traces
from app.services.write_confirmations import stage_write_action
from app.tools.registry import is_read_only_tool


def _normalize_tool_call_keys(value: Any) -> Any:
    """Strip accidental whitespace from model-produced keys before validation."""
    if isinstance(value, dict):
        normalized: dict[Any, Any] = {}
        for key, item in value.items():
            normalized_key = key.strip() if isinstance(key, str) else key
            if normalized_key in normalized:
                raise ValueError(
                    f"Duplicate tool argument key after whitespace normalization: {normalized_key!r}"
                )
            normalized[normalized_key] = _normalize_tool_call_keys(item)
        return normalized
    if isinstance(value, list):
        return [_normalize_tool_call_keys(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_normalize_tool_call_keys(item) for item in value)
    return value


def _trace_safe_result(result: Any) -> Any:
    """Never pass confirmation credentials into observability payloads."""
    if not isinstance(result, dict) or result.get("status") != "confirmation_required":
        return result
    action = result.get("write_action") or {}
    return {
        "status": "confirmation_required",
        "write_action": {
            "action_id": action.get("action_id"),
            "tool_name": action.get("tool_name"),
            "expires_at": action.get("expires_at"),
        },
    }


def _invoke_tool(
    state: AgentState,
    call: dict[str, Any],
    tools_by_name: dict[str, BaseTool],
    tool_step: int = 1,
) -> Any:
    """Invoke one tool and trace it when this graph turn has a run id."""
    normalized_args = _normalize_tool_call_keys(call.get("args", {}))
    agent_jobs.publish_current_job_progress("tool_call", tool_name=call["name"])
    tool = tools_by_name.get(call["name"])
    run_id = state.get("trace_id")
    if tool is None:
        error = ValueError(f"Unknown tool: {call['name']}")
        if run_id is not None:
            tool_call_id = agent_traces.create_tool_call(
                run_id=run_id,
                tool_name=call["name"],
                tool_args=normalized_args,
                tool_step=tool_step,
            )
            agent_traces.fail_tool_call(
                tool_call_id=tool_call_id,
                run_id=run_id,
                error=error,
                latency_ms=0,
            )
        return {"status": "error", "message": str(error)}

    def invoke() -> Any:
        if is_read_only_tool(tool):
            return retry_transient(
                lambda: tool.invoke(normalized_args),
                operation_name=f"tool.{tool.name}",
            )
        return stage_write_action(
            user_id=state["user_id"],
            trace_id=run_id,
            conversation_id=state.get("conversation_id"),
            locale=state["locale"],
            tool_name=tool.name,
            tool_args=normalized_args,
        )

    if run_id is None:
        return invoke()

    tool_call_id = agent_traces.create_tool_call(
        run_id=run_id,
        tool_name=call["name"],
        tool_args=normalized_args,
        tool_step=tool_step,
    )
    started_at = perf_counter()
    try:
        result = invoke()
    except Exception as exc:
        agent_traces.fail_tool_call(
            tool_call_id=tool_call_id,
            run_id=run_id,
            error=exc,
            latency_ms=agent_traces.elapsed_ms(started_at),
        )
        raise

    agent_traces.succeed_tool_call(
        tool_call_id=tool_call_id,
        run_id=run_id,
        tool_result=_trace_safe_result(result),
        latency_ms=agent_traces.elapsed_ms(started_at),
    )
    return result
