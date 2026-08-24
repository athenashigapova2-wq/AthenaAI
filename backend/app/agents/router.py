"""Router Agent: chooses the specialist agent for the next turn."""

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, ValidationError

from app.agents.prompts import ROUTER_SYSTEM
from app.agents.state import AgentName, AgentState
from app.llm import get_routed_llm
from app.services import agent_traces

logger = logging.getLogger(__name__)


class RoutingDecision(BaseModel):
    """Strict structured contract returned by the LLM router."""

    model_config = ConfigDict(extra="forbid")

    route: AgentName

_PROGRESS_MARKERS = (
    "прогресс",
    "результат",
    "динамик",
    "изменени",
    "продвига",
    "сдвиг",
    "progress",
    "result",
    "how am i doing",
    "improv",
    "progrès",
    "résultat",
    "évolution",
    "progreso",
    "resultado",
    "evolución",
    "进展",
    "进步",
    "变化",
    "效果",
    "结果",
)

_KEYWORDS: dict[AgentName, tuple[str, ...]] = {
    "nutrition": (
        "калор", "кбжу", "бел", "жир", "углев", "еда", "съел", "питани",
        "meal", "food", "protein", "calorie", " ate ",
        "repas", "aliment", "protéin", "calorie",
        "comida", "alimento", "proteína", "caloría",
        "食物", "吃", "卡路里", "蛋白质", "碳水", "脂肪",
    ),
    "workout": (
        "трен", "зал", "упраж", "подход", "присед", "выпад",
        "workout", "gym", "exercise", "sets", "reps",
        "entraînement", "exercice", "salle", "série",
        "entrenamiento", "ejercicio", "gimnasio", "serie",
        "训练", "健身房", "运动", "组数", "重复",
    ),
    "recovery": (
        "сон", "спал", "спала", "устал", "цикл", "вес", "болит", "болят",
        "sleep", "fatigue", "cycle", "sore", "weight",
        "sommeil", "fatigu", "poids", "douleur", "récupération",
        "sueño", "fatiga", "ciclo", "peso", "dolor", "recuperación",
        "睡眠", "疲劳", "月经", "周期", "体重", "疼", "恢复",
    ),
}


def _last_user_text(state: AgentState) -> str:
    for message in reversed(state["messages"]):
        if getattr(message, "type", None) == "human":
            return str(message.content)
    return ""


def is_progress_request(text: str) -> bool:
    """Return whether the user is asking to assess their longitudinal progress."""
    lowered = text.casefold()
    return any(marker in lowered for marker in _PROGRESS_MARKERS)


def route_with_keywords(text: str) -> AgentName:
    """Deterministic fallback used when the LLM router is unavailable."""
    if is_progress_request(text):
        return "recovery"
    lowered = text.lower()
    scores = {
        route: sum(1 for keyword in keywords if keyword in lowered)
        for route, keywords in _KEYWORDS.items()
    }
    best_route, best_score = max(scores.items(), key=lambda item: item[1])
    return best_route if best_score > 0 else "general"


def _parse_routing_decision(response: Any) -> RoutingDecision:
    """Validate the complete router payload instead of trusting its first token."""
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return RoutingDecision.model_validate_json(content.strip())
    return RoutingDecision.model_validate(content)


def _routing_fallback_reason(error: Exception) -> str:
    if isinstance(error, ValidationError):
        errors = error.errors()
        error_type = str(errors[0].get("type", "validation_error")) if errors else "validation_error"
        return f"structured_output_validation:{error_type}"
    return f"router_llm_exception:{type(error).__name__}"


def router_node(state: AgentState) -> dict[str, object]:
    """LangGraph node that writes `route` into the state."""
    text = _last_user_text(state)
    try:
        llm, selection = get_routed_llm(
            node_name="router",
            purpose="route_classification",
            default_tier="small",
            temperature=0.0,
        )
        response = agent_traces.invoke_llm(
            llm,
            [SystemMessage(content=ROUTER_SYSTEM), HumanMessage(content=text)],
            run_id=state.get("run_id"),
            node_name="router",
            purpose="route_classification",
            model_tier=selection.model_tier,
            model_selection=selection,
        )
        decision = _parse_routing_decision(response)
        return {"route": decision.route, "routing_fallback_reason": None}
    except Exception as error:
        reason = _routing_fallback_reason(error)
        fallback_route = route_with_keywords(text)
        logger.warning(
            "Router LLM degraded; using keyword fallback",
            extra={
                "run_id": state.get("run_id"),
                "routing_fallback_reason": reason,
                "fallback_route": fallback_route,
            },
            exc_info=True,
        )
        agent_traces.record_routing_fallback(
            run_id=state.get("run_id"),
            user_id=state.get("user_id"),
            reason=reason,
        )
        return {
            "route": fallback_route,
            "routing_fallback_reason": reason,
        }
