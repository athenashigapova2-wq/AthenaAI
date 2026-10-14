from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid5

from app.services import agent_conversations

JOB_ID = "11111111-1111-4111-8111-111111111111"


def test_new_conversation_uses_job_id_during_redelivery() -> None:
    client = MagicMock()
    query = client.table.return_value
    query.upsert.return_value.execute.return_value = SimpleNamespace(data=[])
    history = query.select.return_value.eq.return_value.order.return_value.limit.return_value
    history.execute.return_value = SimpleNamespace(data=[])

    with patch("app.services.agent_conversations.get_supabase", return_value=client):
        conversation_id, messages = agent_conversations.prepare_conversation(
            "user-1",
            None,
            "Hello",
            "en",
            job_id=JOB_ID,
        )

    assert conversation_id == JOB_ID
    assert messages == []
    query.upsert.assert_called_once_with(
        {
            "id": JOB_ID,
            "user_id": "user-1",
            "agent_name": "athena_multi_agent",
            "title": "Hello",
            "metadata": {"locale": "en"},
        },
        on_conflict="id",
        ignore_duplicates=True,
    )


def test_turn_messages_have_stable_ids_for_redelivery() -> None:
    client = MagicMock()
    query = client.table.return_value
    query.upsert.return_value.execute.return_value = SimpleNamespace(data=[])

    with patch("app.services.agent_conversations.get_supabase", return_value=client):
        agent_conversations.save_turn(
            "conversation-1",
            "Question",
            "Answer",
            job_id=JOB_ID,
        )

    namespace = UUID(JOB_ID)
    query.upsert.assert_called_once_with(
        [
            {
                "id": str(uuid5(namespace, "user")),
                "conversation_id": "conversation-1",
                "role": "user",
                "content": "Question",
            },
            {
                "id": str(uuid5(namespace, "assistant")),
                "conversation_id": "conversation-1",
                "role": "assistant",
                "content": "Answer",
            },
        ],
        on_conflict="id",
        ignore_duplicates=True,
    )
