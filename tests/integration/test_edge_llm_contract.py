"""Security contract for browser-triggered Edge LLM tasks."""

from pathlib import Path

import pytest


pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
EDGE_FUNCTIONS = ROOT / "supabase" / "functions"
CLIENT = ROOT / "src" / "lib" / "athenaTasks.js"


def test_legacy_generic_llm_gateway_is_removed() -> None:
    assert not (EDGE_FUNCTIONS / "invoke-llm" / "index.ts").exists()
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "src").rglob("*.js*")
    )
    assert "invokeLLM" not in source
    assert "response_json_schema" not in source
    assert "functions.invoke('invoke-llm'" not in source


def test_narrow_task_endpoint_owns_security_controls() -> None:
    edge = (EDGE_FUNCTIONS / "athena-task" / "index.ts").read_text(encoding="utf-8")
    client = CLIENT.read_text(encoding="utf-8")

    assert "functions.invoke('athena-task'" in client
    assert "body: { prompt" not in client
    assert "response_json_schema" not in client
    assert "MAX_REQUEST_BYTES" in edge
    assert "ALLOWED_ORIGINS" in edge
    assert "auth.getUser()" in edge
    assert "consume_edge_llm_quota" in edge
    assert "Unsupported use case" in edge
    assert "exactKeys(body, ['use_case', 'input'])" in edge
