"""Первый настоящий tool call: модель сама решает вызвать инструмент."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage  # noqa: E402
from app.ai_execution import ai_execution_service  # noqa: E402
from app.tools.registry import build_tools  # noqa: E402
from app.config import settings  # noqa: E402

USER_ID = settings.test_user_id

SYSTEM = (
    "Ты — Athena, помощник по питанию и тренировкам. "
    "Если для ответа нужны персональные данные пользователя — "
    "вызови инструмент get_my_profile, не выдумывай значения. "
    "Отвечай на русском, кратко и по делу."
)


def main() -> None:
    tools = build_tools(USER_ID)
    tools_by_name = {t.name: t for t in tools}

    prepared = ai_execution_service.prepare(
        node_name="diagnostic",
        purpose="tool_call",
    )
    llm = prepared.model.bind_tools(tools, tool_choice="auto")

    messages = [
        SystemMessage(content=SYSTEM),
        HumanMessage(content="Сколько мне нужно белка в день и почему столько?"),
    ]

    # Шаг 1: модель решает, нужен ли инструмент
    ai_msg = ai_execution_service.invoke_prepared(
        prepared,
        messages=messages,
        model=llm,
    )
    print("--- Решение модели ---")
    print("Текст:", ai_msg.content or "(пусто, модель хочет вызвать инструмент)")
    print("Вызовы:", ai_msg.tool_calls)

    if not ai_msg.tool_calls:
        print("\nМодель ответила без инструмента.")
        return

    messages.append(ai_msg)

    # Шаг 2: выполняем то, что она попросила
    for call in ai_msg.tool_calls:
        tool = tools_by_name[call["name"]]
        result = tool.invoke(call["args"])
        print(f"\n--- Результат {call['name']} ---")
        print(result)
        messages.append(
            ToolMessage(content=str(result), tool_call_id=call["id"])
        )

    # Шаг 3: модель формулирует ответ на основе данных
    final = ai_execution_service.invoke_prepared(
        prepared,
        messages=messages,
        model=llm,
    )
    print("\n--- Финальный ответ ---")
    print(final.content)


if __name__ == "__main__":
    main()
