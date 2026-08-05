"""Проверка инструмента get_profile на реальных данных."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tools.profile import get_profile  # noqa: E402
from app.config import settings  # noqa: E402

USER_ID = settings.test_user_id

if __name__ == "__main__":
    import json
    print(json.dumps(get_profile(USER_ID), ensure_ascii=False, indent=2))