"""Offline checks for load stages, token rotation and Locust CSV analysis."""

from __future__ import annotations

import os
import sys
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from load_tests.analyze_results import evaluate, read_flow_stats  # noqa: E402
from load_tests.config import (  # noqa: E402
    LoadSettings,
    LoadTestConfigurationError,
    TokenPool,
    load_stages,
)


def check_stages() -> None:
    stages = load_stages(
        '[{"name":"warmup","duration_seconds":10,"users":2,"spawn_rate":1},'
        '{"name":"overload","duration_seconds":20,"users":8,"spawn_rate":4}]'
    )
    assert [stage.name for stage in stages] == ["warmup", "overload"]
    assert sum(stage.duration_seconds for stage in stages) == 30
    try:
        load_stages('[{"name":"broken","users":2,"spawn_rate":1}]')
    except LoadTestConfigurationError:
        pass
    else:
        raise AssertionError("Invalid stages must fail before traffic starts")


def check_settings_guard() -> None:
    with patch.dict(os.environ, {}, clear=True):
        try:
            LoadSettings.from_env()
        except LoadTestConfigurationError as exc:
            assert "ACKNOWLEDGE" in str(exc)
        else:
            raise AssertionError("Provider-cost acknowledgement must be mandatory")
    with patch.dict(
        os.environ,
        {
            "LOAD_TEST_ACKNOWLEDGE_PROVIDER_COSTS": "true",
            "LOAD_TEST_MIN_THINK_SECONDS": "0",
            "LOAD_TEST_MAX_THINK_SECONDS": "0",
        },
        clear=True,
    ):
        settings = LoadSettings.from_env()
    assert settings.locale == "ru"
    assert settings.min_think_time_seconds == 0


def check_token_pool() -> None:
    pool = TokenPool(("token-a", "token-b"))
    assert [pool.next(), pool.next(), pool.next()] == ["token-a", "token-b", "token-a"]
    assert pool.size == 2


def check_slo_analysis() -> None:
    rows = [
        {"stage": "steady", "requests": 10, "error_percent": 1.0, "p95_ms": 20_000, "p99_ms": 40_000},
        {"stage": "overload", "requests": 10, "error_percent": 25.0, "p95_ms": 90_000, "p99_ms": 120_000},
        {"stage": "recovery", "requests": 10, "error_percent": 0.0, "p95_ms": 18_000, "p99_ms": 30_000},
    ]
    assert not evaluate(
        rows,
        asserted_stages={"steady", "recovery"},
        max_error_percent=5,
        max_p95_ms=30_000,
        max_p99_ms=60_000,
    )
    failures = evaluate(
        rows,
        asserted_stages={"overload"},
        max_error_percent=5,
        max_p95_ms=30_000,
        max_p99_ms=60_000,
    )
    assert len(failures) == 3

    with TemporaryDirectory() as directory:
        stats_path = Path(directory) / "agent_stats.csv"
        stats_path.write_text(
            "Type,Name,Request Count,Failure Count,Median Response Time,Requests/s,50%,95%,99%\n"
            "FLOW,agent_chat_e2e [steady],10,1,1000,0.5,1000,2000,3000\n",
            encoding="utf-8",
        )
        parsed = read_flow_stats(stats_path)
    assert parsed == [
        {
            "stage": "steady",
            "requests": 10,
            "failures": 1,
            "error_percent": 10.0,
            "rps": 0.5,
            "p50_ms": 1000,
            "p95_ms": 2000,
            "p99_ms": 3000,
        }
    ]


def main() -> None:
    check_stages()
    check_settings_guard()
    check_token_pool()
    check_slo_analysis()
    print("Load-test configuration checks passed")


if __name__ == "__main__":
    main()
