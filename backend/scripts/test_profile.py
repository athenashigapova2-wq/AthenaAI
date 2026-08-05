"""Проверка инструмента get_profile на реальных данных."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tools.profile import get_profile  # noqa: E402

USER_ID = "4c58346d-801f-4241-a349-02a2736361f0"

if __name__ == "__main__":
    import json
    print(json.dumps(get_profile(USER_ID), ensure_ascii=False, indent=2))