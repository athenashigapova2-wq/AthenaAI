"""Shared pytest configuration and a hard safety gate for live evaluations."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
SCRIPTS = BACKEND / "scripts"
for import_root in (BACKEND, SCRIPTS):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

LIVE_ENV = "ATHENA_RUN_LIVE_EVALS"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-live-evals",
        action="store_true",
        default=False,
        help=(
            "Allow tests/live_evals to run. Also requires "
            f"{LIVE_ENV}=1 in the current process."
        ),
    )


def _is_live_eval(item: pytest.Item) -> bool:
    return "live_evals" in Path(str(item.path)).parts


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    live_items = [item for item in items if _is_live_eval(item)]
    if not live_items:
        return

    for item in live_items:
        item.add_marker(pytest.mark.live)

    flag_enabled = bool(config.getoption("--run-live-evals"))
    env_enabled = os.getenv(LIVE_ENV) == "1"
    if flag_enabled and not env_enabled:
        raise pytest.UsageError(
            f"Live eval flag was provided, but {LIVE_ENV}=1 is missing."
        )

    if not (flag_enabled and env_enabled):
        reason = (
            "live evals are disabled; explicitly select tests/live_evals, pass "
            f"--run-live-evals, and set {LIVE_ENV}=1"
        )
        for item in live_items:
            item.add_marker(pytest.mark.skip(reason=reason))
