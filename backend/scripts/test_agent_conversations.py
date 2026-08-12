"""Offline checks for user-scoped conversation history persistence."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import agent_conversations  # noqa: E402


def main() -> None:
    query = Mock()
    query.table.return_value = query
    query.select.return_value = query
    query.insert.return_value = query
    query.eq.return_value = query
    query.order.return_value = query
    query.limit.return_value = query
    query.execute.side_effect = [
        SimpleNamespace(data=[{"id": "conversation-id"}]),
        SimpleNamespace(
            data=[
                {"role": "assistant", "content": "Previous answer"},
                {"role": "user", "content": "Previous question"},
            ]
        ),
    ]

    with patch("app.services.agent_conversations.get_supabase", return_value=query):
        conversation_id, history = agent_conversations.prepare_conversation(
            user_id="user-id",
            conversation_id="conversation-id",
            message="Current question",
            locale="en",
        )

    assert conversation_id == "conversation-id"
    assert history == [
        {"role": "user", "content": "Previous question"},
        {"role": "assistant", "content": "Previous answer"},
    ]
    filters = [call.args for call in query.eq.call_args_list]
    assert ("id", "conversation-id") in filters
    assert ("user_id", "user-id") in filters

    query.reset_mock()
    query.execute.side_effect = None
    query.table.return_value = query
    query.insert.return_value = query
    query.execute.return_value = SimpleNamespace(data=[{"id": "message-id"}])
    with patch("app.services.agent_conversations.get_supabase", return_value=query):
        agent_conversations.save_turn("conversation-id", "Question", "Answer")

    assert query.insert.call_args.args[0] == [
        {"conversation_id": "conversation-id", "role": "user", "content": "Question"},
        {"conversation_id": "conversation-id", "role": "assistant", "content": "Answer"},
    ]
    print("Agent conversation checks passed")


if __name__ == "__main__":
    main()
