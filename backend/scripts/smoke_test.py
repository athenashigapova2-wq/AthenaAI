"""Дымовой тест: проверяем, что Python достучался до GigaChat."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402
from app.ai_execution import ai_execution_service  # noqa: E402


def main() -> None:
    response = ai_execution_service.invoke(
        messages=[
            SystemMessage(content="Ты — краткий помощник. Отвечай одним предложением."),
            HumanMessage(content="Сколько белка примерно в 100 г куриной грудки?"),
        ],
        node_name="diagnostic",
        purpose="smoke_test",
    )
    print("Ответ модели:", response.content)
    print("Токены:", response.response_metadata.get("token_usage"))


if __name__ == "__main__":
    main()
