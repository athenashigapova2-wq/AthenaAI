"""Проверка инструментов питания напрямую, без модели."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.tools import nutrition  # noqa: E402

USER_ID = settings.test_user_id


def show(title: str, data: dict) -> None:
    print(f"\n--- {title} ---")
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    show("search_food('куриная грудка')", nutrition.search_food("куриная грудка"))
    show("get_daily_intake()", nutrition.get_daily_intake(USER_ID))