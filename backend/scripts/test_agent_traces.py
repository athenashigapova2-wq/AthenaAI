"""Offline checks for Supabase agent-run payloads and ownership filters."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import agent_traces  # noqa: E402


def main() -> None:
    query = Mock()
    query.table.return_value = query
    query.insert.return_value = query
    query.update.return_value = query
    query.eq.return_value = query
    query.execute.return_value = SimpleNamespace(data=[{"id": "run-id"}])

    with patch("app.services.agent_traces.get_supabase", return_value=query):
        run_id = agent_traces.create_agent_run("user-id", "Что я сегодня съела?")
        assert run_id == "run-id"
        insert_payload = query.insert.call_args.args[0]
        assert insert_payload["user_id"] == "user-id"
        assert insert_payload["status"] == "started"
        assert insert_payload["input_text"] == "Что я сегодня съела?"

        query.eq.reset_mock()
        agent_traces.succeed_agent_run(
            run_id="run-id",
            user_id="user-id",
            route="nutrition",
            output_text="Ответ",
            latency_ms=120,
        )

    filters = [call.args for call in query.eq.call_args_list]
    assert ("id", "run-id") in filters
    assert ("user_id", "user-id") in filters
    update_payload = query.update.call_args.args[0]
    assert update_payload["status"] == "succeeded"
    assert update_payload["route"] == "nutrition"
    assert update_payload["latency_ms"] == 120
    print("Agent trace checks passed")


if __name__ == "__main__":
    main()
