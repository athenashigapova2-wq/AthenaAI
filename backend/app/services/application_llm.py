"""Compatibility facade for the canonical AI Execution Layer."""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel

from app.ai_execution.gateway import AIExecutionLayer, ai_execution_layer


StructuredResult = TypeVar("StructuredResult", bound=BaseModel)
def invoke_structured_application_llm(
    *,
    response_model: type[StructuredResult],
    node_name: str,
    purpose: str,
    system_prompt: str,
    input_payload: dict[str, Any],
    run_id: str | None = None,
) -> StructuredResult:
    """Invoke the routed provider and validate its complete JSON response.

    Application services use this function instead of constructing provider
    clients. This keeps routing, retries, rate limiting and circuit breaking on
    the same path as agent calls.
    """
    return ai_execution_layer.invoke_structured(
        response_model=response_model,
        node_name=node_name,
        purpose=purpose,
        system_prompt=system_prompt,
        input_payload=input_payload,
        run_id=run_id,
    )


def _parse_structured_response(
    response_model: type[StructuredResult],
    content: Any,
) -> StructuredResult:
    return AIExecutionLayer._parse_structured(response_model, content)
