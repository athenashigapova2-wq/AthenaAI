"""Privacy regressions at the final Supabase trace-persistence boundary."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.config import settings
from app.services import agent_traces


def _query() -> Mock:
    query = Mock()
    query.table.return_value = query
    query.insert.return_value = query
    query.update.return_value = query
    query.eq.return_value = query
    query.execute.return_value = SimpleNamespace(data=[{"id": "trace-id"}])
    return query


def test_sensitive_fields_never_enter_trace_persistence(monkeypatch) -> None:
    query = _query()
    monkeypatch.setattr(settings, "trace_content_mode", "redacted")
    monkeypatch.setattr(settings, "trace_raw_payload_retention_days", 7)

    with patch("app.services.agent_traces.get_supabase", return_value=query):
        agent_traces.create_agent_run(
            "user-id",
            "Меня зовут Анна, вес 72.5 кг, диагноз диабет",
        )
        run_payload = query.insert.call_args.args[0]
        assert run_payload["input_text"] == "[SENSITIVE_CONTENT_REDACTED]"
        assert run_payload["input_data_classification"] == "sensitive"

        agent_traces.create_tool_call(
            "run-id",
            "update_profile",
            {
                "weight": 72.5,
                "calories": 1_800,
                "medical_condition": "diabetes",
                "authorization": "Bearer private-token",
            },
        )
        tool_payload = query.insert.call_args.args[0]

    serialized = str({"run": run_payload, "tool": tool_payload})
    for sensitive_value in ("72.5", "1800", "diabetes", "private-token"):
        assert sensitive_value not in serialized
    assert tool_payload["arg_data_classification"] == "sensitive"
    assert tool_payload["arg_count"] == 4


def test_trace_retention_purges_content_before_records(monkeypatch) -> None:
    client = Mock()
    first_rpc = Mock()
    second_rpc = Mock()
    first_rpc.execute.return_value = SimpleNamespace(data=1)
    second_rpc.execute.return_value = SimpleNamespace(data=2)
    client.rpc.side_effect = [first_rpc, second_rpc]
    monkeypatch.setattr(settings, "trace_record_retention_days", 90)

    with patch("app.services.agent_traces.get_supabase", return_value=client):
        agent_traces.enforce_trace_retention()

    assert client.rpc.call_args_list[0].args == ("purge_expired_agent_trace_payloads",)
    assert client.rpc.call_args_list[1].args[0] == "purge_expired_agent_traces"
    assert "p_before" in client.rpc.call_args_list[1].args[1]


def test_http_trace_id_and_slo_metadata_enter_run_without_content(monkeypatch) -> None:
    query = _query()
    monkeypatch.setattr(settings, "trace_content_mode", "off")

    with patch("app.services.agent_traces.get_supabase", return_value=query):
        returned = agent_traces.create_agent_run(
            "user-id",
            "private conversation",
            run_id="22222222-2222-4222-8222-222222222222",
            job_id="11111111-1111-4111-8111-111111111111",
            queue_latency_ms=87,
        )

    payload = query.insert.call_args.args[0]
    assert returned == "22222222-2222-4222-8222-222222222222"
    assert payload["id"] == returned
    assert payload["job_id"] == "11111111-1111-4111-8111-111111111111"
    assert payload["queue_latency_ms"] == 87
    assert payload["input_text"] == ""
    assert "private conversation" not in str(payload)


def test_rag_metrics_are_metadata_only() -> None:
    query = _query()
    with patch("app.services.agent_traces.get_supabase", return_value=query):
        agent_traces.record_rag_metrics(
            run_id="trace-id",
            attempted=True,
            retrieved_chunk_count=4,
            retrieval_latency_ms=38,
            top_similarity=0.91,
            context_chars=1_204,
        )

    metrics = query.update.call_args.args[0]
    assert metrics == {
        "rag_attempted": True,
        "rag_retrieved_chunk_count": 4,
        "rag_retrieval_latency_ms": 38,
        "rag_top_similarity": 0.91,
        "rag_context_chars": 1_204,
    }
