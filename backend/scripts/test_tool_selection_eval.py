"""Verify multi-step tool eval follows read calls without executing real tools."""

import sys
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import AIMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import eval_tool_selection  # noqa: E402


class FakeBoundModel:
    def __init__(self) -> None:
        self.responses = iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[{"name": "get_my_profile", "args": {}, "id": "read-1"}],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "log_workout",
                            "args": {"workout_type": "lower_body"},
                            "id": "write-1",
                        }
                    ],
                ),
            ]
        )

    def bind_tools(self, tools, tool_choice="auto"):
        return self

    def invoke(self, messages):
        return next(self.responses)


class FakeExecutionService:
    def __init__(self) -> None:
        self.model = FakeBoundModel()

    def prepare(self, **kwargs):
        return SimpleNamespace(model=self.model)

    def invoke_prepared(self, prepared, *, messages, model=None):
        return (model or prepared.model).invoke(messages)


def main() -> None:
    original_service = eval_tool_selection.ai_execution_service
    eval_tool_selection.ai_execution_service = FakeExecutionService()
    try:
        selected = eval_tool_selection.select_tools(
            {
                "route": "workout",
                "locale": "ru",
                "query": "Запиши тренировку",
                "expected_tools": ["log_workout"],
                "forbidden_tools": [],
            }
        )
    finally:
        eval_tool_selection.ai_execution_service = original_service

    assert selected == ["get_my_profile", "log_workout"]
    print("Tool selection eval checks passed")


if __name__ == "__main__":
    main()
