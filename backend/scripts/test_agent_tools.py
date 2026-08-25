"""Проверка, умеет ли модель выбирать правильный инструмент.

Три сценария разной сложности:
  1. справочник      -> search_food
  2. дневник         -> get_daily_intake
  3. цепочка         -> search_food, затем log_meal
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langchain_core.messages import (  # noqa: E402
    AIMessage, HumanMessage, SystemMessage, ToolMessage,
)

from app.config import settings  # noqa: E402
from app.ai_execution import ai_execution_service  # noqa: E402
from app.tools.registry import build_tools  # noqa: E402

SYSTEM = (
    "Ты — Athena, помощник по питанию и тренировкам.\n"
    "Правила:\n"
    "- Для персональных данных вызывай get_my_profile.\n"
    "- Пищевую ценность продукта бери из search_food, НИКОГДА не выдумывай.\n"
    "- Если search_food вернул not_found, честно скажи, что продукта нет в базе.\n"
    "- Записывай еду через log_meal только если пользователь прямо просит записать.\n"
    "Отвечай на русском, кратко."
)

CASES = [
    "Сколько калорий в куриной грудке?",
    "Сколько я уже съела сегодня?",
    "Я съела 200 грамм варёного риса, запиши это в дневник",
]

MAX_STEPS = 5


def run_case(question: str) -> None:
    print("\n" + "=" * 60)
    print("ВОПРОС:", question)

    tools = build_tools(settings.test_user_id)
    tools_by_name = {t.name: t for t in tools}
    prepared = ai_execution_service.prepare(
        node_name="diagnostic",
        purpose="agent_tools",
    )
    llm = prepared.model.bind_tools(tools, tool_choice="auto")

    messages = [SystemMessage(content=SYSTEM), HumanMessage(content=question)]

    for step in range(MAX_STEPS):
        ai_msg: AIMessage = ai_execution_service.invoke_prepared(
            prepared,
            messages=messages,
            model=llm,
        )
        messages.append(ai_msg)

        if not ai_msg.tool_calls:
            print(f"\nОТВЕТ (шагов: {step}):")
            print(ai_msg.content)
            return

        for call in ai_msg.tool_calls:
            print(f"  [{step + 1}] вызов {call['name']}({call['args']})")
            tool = tools_by_name.get(call["name"])
            if tool is None:
                result = {"status": "error", "message": "нет такого инструмента"}
            else:
                result = tool.invoke(call["args"])
            messages.append(
                ToolMessage(content=str(result), tool_call_id=call["id"])
            )

    print("\nЛИМИТ ШАГОВ ИСЧЕРПАН — модель зациклилась")


if __name__ == "__main__":
    for case in CASES:
        run_case(case)
