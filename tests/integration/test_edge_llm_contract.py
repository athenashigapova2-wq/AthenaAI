"""Architecture contract: Edge Functions never perform model inference."""

from collections.abc import Iterable, Iterator
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
EDGE_FUNCTIONS = ROOT / "supabase" / "functions"
CLIENT = ROOT / "src" / "lib" / "athenaTasks.js"
LEGACY_AI_FUNCTIONS = (
    "invoke-llm",
    "athena-task",
    "chat-with-coach",
    "analyze-habits",
    "estimate-meal",
)
FRONTEND_ROOTS = (
    ROOT / "src",
    ROOT / "public",
)
FRONTEND_ENTRYPOINTS = (
    ROOT / "index.html",
)


def _files_below(root: Path) -> Iterator[Path]:
    return (path for path in root.rglob("*") if path.is_file())


def _assert_bytes_absent(paths: Iterable[Path], forbidden: tuple[str, ...]) -> None:
    encoded = tuple((token, token.casefold().encode("utf-8")) for token in forbidden)
    for path in paths:
        source = path.read_bytes().lower()
        for token, needle in encoded:
            assert needle not in source, f"{path} contains forbidden {token}"


def test_legacy_generic_llm_gateway_is_removed() -> None:
    for function_name in LEGACY_AI_FUNCTIONS:
        assert not (EDGE_FUNCTIONS / function_name / "index.ts").exists()
    frontend_paths = [
        *(
            path
            for frontend_root in FRONTEND_ROOTS
            for path in _files_below(frontend_root)
        ),
        *(path for path in FRONTEND_ENTRYPOINTS if path.is_file()),
    ]
    _assert_bytes_absent(
        frontend_paths,
        (
            "invokeLLM",
            "response_json_schema",
            "invoke-llm",
            "estimate-meal",
            "analyze-habits",
            "chat-with-coach",
            "athena-task",
        ),
    )


def test_browser_ai_tasks_use_authenticated_fastapi() -> None:
    client = CLIENT.read_text(encoding="utf-8")

    assert "/api/v1/ai/tasks/" in client
    assert "supabase.auth.getSession()" in client
    assert "Authorization: `Bearer ${token}`" in client
    assert "supabase.functions.invoke" not in client
    assert "body: { prompt" not in client
    assert "response_json_schema" not in client


def test_edge_functions_have_no_llm_provider_knowledge() -> None:
    forbidden = (
        "GIGACHAT_AUTH_KEY",
        "GIGACHAT_MODEL",
        "api.giga.chat",
        "ngw.devices.sberbank.ru",
        "chat/completions",
        "langchain_gigachat",
        "openai",
    )
    sources = list(_files_below(EDGE_FUNCTIONS))
    assert sources, "Expected at least one deterministic Edge Function"
    _assert_bytes_absent(sources, forbidden)


def test_backend_llm_calls_enter_the_execution_layer() -> None:
    allowed = {
        ROOT / "backend/app/ai_execution/gateway.py",
        ROOT / "backend/app/llm.py",
        ROOT / "backend/app/services/agent_traces.py",
    }
    for path in (ROOT / "backend/app").rglob("*.py"):
        if path in allowed:
            continue
        source = path.read_text(encoding="utf-8")
        assert "get_routed_llm" not in source, f"{path} bypasses AIExecutionService"
        assert "agent_traces.invoke_llm" not in source, f"{path} bypasses AIExecutionService"


def test_llm_module_is_provider_factory_only() -> None:
    source = (ROOT / "backend/app/llm.py").read_text(encoding="utf-8")

    assert "create_provider_model" in source
    assert "select_model(" not in source
    assert "call_with_circuit_breaker" not in source
    assert ".invoke(" not in source


def test_migrated_use_cases_depend_on_ai_execution_service() -> None:
    paths = (
        ROOT / "backend/app/agents/specialists.py",
        ROOT / "backend/app/services/meal_estimation.py",
        ROOT / "backend/app/services/habit_analytics.py",
        ROOT / "backend/app/services/ai_tasks.py",
    )
    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert "ai_execution_service" in source, f"{path} misses canonical control plane"
        assert "from app.llm" not in source, f"{path} imports provider factory directly"
