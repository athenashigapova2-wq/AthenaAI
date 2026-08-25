"""Architecture contract: Edge Functions never perform model inference."""

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


def test_legacy_generic_llm_gateway_is_removed() -> None:
    for function_name in LEGACY_AI_FUNCTIONS:
        assert not (EDGE_FUNCTIONS / function_name / "index.ts").exists()
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "src").rglob("*.js*")
    )
    assert "invokeLLM" not in source
    assert "response_json_schema" not in source
    assert "functions.invoke('invoke-llm'" not in source
    assert "functions.invoke('estimate-meal'" not in source
    assert "functions.invoke('analyze-habits'" not in source
    assert "functions.invoke('chat-with-coach'" not in source

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
    sources = list(EDGE_FUNCTIONS.rglob("*.ts"))
    assert sources, "Expected at least one deterministic Edge Function"
    for path in sources:
        source = path.read_text(encoding="utf-8").casefold()
        for token in forbidden:
            assert token.casefold() not in source, f"{path} contains forbidden {token}"


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
        assert "get_routed_llm" not in source, f"{path} bypasses AIExecutionLayer"
        assert "agent_traces.invoke_llm" not in source, f"{path} bypasses AIExecutionLayer"
