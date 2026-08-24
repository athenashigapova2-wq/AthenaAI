"""Deterministic local chat model for test contours.

The mock never contacts an external provider and intentionally does not emulate
answer quality. It only exercises the agent graph, queues, persistence and
delivery layers with reproducible responses.
"""

from __future__ import annotations

from collections.abc import Sequence
import re
from time import sleep
from typing import Any

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class AthenaMockChatModel(BaseChatModel):
    """Small deterministic BaseChatModel implementation used only on opt-in."""

    model_name: str = "athena-mock-v1"
    node_name: str = "general"
    purpose: str = "answer"
    latency_ms: int = 0
    bound_tool_names: tuple[str, ...] = ()

    @property
    def _llm_type(self) -> str:
        return "athena-mock"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "node_name": self.node_name,
            "purpose": self.purpose,
            "latency_ms": self.latency_ms,
        }

    def bind_tools(
        self,
        tools: Sequence[Any],
        **kwargs: Any,
    ) -> "AthenaMockChatModel":
        """Accept the production tool-binding contract without calling tools."""
        del kwargs
        names = tuple(filter(None, (_tool_name(tool) for tool in tools)))
        return self.model_copy(update={"bound_tool_names": names})

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        if self.latency_ms:
            sleep(self.latency_ms / 1_000)

        calorie_decision = "submit_calorie_decision" in self.bound_tool_names
        message = AIMessage(
            content="" if calorie_decision else self._response(messages),
            tool_calls=(
                [
                    {
                        "name": "submit_calorie_decision",
                        "args": {
                            "action": "keep",
                            "proposed_calories": _current_calorie_target(messages),
                            "rationale": "Deterministic mock decision based on server facts.",
                        },
                        "id": "mock-calorie-decision",
                    }
                ]
                if calorie_decision
                else []
            ),
            response_metadata={
                "model_provider": "mock",
                "model_name": self.model_name,
            },
            usage_metadata={
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            },
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _response(self, messages: list[BaseMessage]) -> str:
        if self.node_name == "router" or self.purpose == "route_classification":
            return _route_for_text(_last_human_text(messages))

        language = _language(messages)
        return _RESPONSES.get(language, _RESPONSES["ru"]).format(
            node=self.node_name,
        )


def _last_human_text(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if getattr(message, "type", None) == "human":
            return str(message.content)
    return ""


def _route_for_text(text: str) -> str:
    """Use the same deterministic fallback policy as the production router."""
    from app.agents.router import route_with_keywords

    return route_with_keywords(text)


def _language(messages: list[BaseMessage]) -> str:
    system_text = "\n".join(
        str(message.content)
        for message in messages
        if getattr(message, "type", None) == "system"
    )
    for language, marker in {
        "en": "user's language is English",
        "fr": "user's language is French",
        "es": "user's language is Spanish",
        "zh": "user's language is Chinese",
        "ru": "user's language is Russian",
    }.items():
        if marker in system_text:
            return language
    return "ru"


def _tool_name(tool: Any) -> str:
    if isinstance(tool, dict):
        function = tool.get("function") or {}
        return str(function.get("name") or tool.get("name") or "")
    return str(getattr(tool, "name", None) or getattr(tool, "__name__", ""))


def _current_calorie_target(messages: list[BaseMessage]) -> float:
    text = "\n".join(str(message.content) for message in messages)
    match = re.search(r'"calorie_target"\s*:\s*(\d+(?:\.\d+)?)', text)
    return float(match.group(1)) if match else 1_200.0


_RESPONSES = {
    "ru": "[MOCK:{node}] Детерминированный тестовый ответ. Внешний LLM не вызывался.",
    "en": "[MOCK:{node}] Deterministic test response. No external LLM was called.",
    "fr": "[MOCK:{node}] Réponse de test déterministe. Aucun LLM externe n'a été appelé.",
    "es": "[MOCK:{node}] Respuesta de prueba determinista. No se llamó a un LLM externo.",
    "zh": "[MOCK:{node}] 确定性的测试响应。未调用外部 LLM。",
}
