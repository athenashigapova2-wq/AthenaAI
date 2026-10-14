"""Persist user-owned chat history around one agent turn."""

from typing import Any
from uuid import UUID, uuid5

from app.config import settings
from app.resilience import retry_transient
from app.services.supabase import get_supabase


def prepare_conversation(
    user_id: str,
    conversation_id: str | None,
    message: str,
    locale: str,
    *,
    job_id: str | None = None,
) -> tuple[str, list[dict[str, str]]]:
    client = get_supabase()
    if conversation_id:
        query = (
            client.table("agent_conversations")
            .select("id")
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .limit(1)
        )
        response = retry_transient(
            query.execute,
            operation_name="supabase.read.agent_conversation",
        )
        if not response.data:
            raise ValueError("Conversation not found")
    else:
        conversation = {
            "user_id": user_id,
            "agent_name": "athena_multi_agent",
            "title": message[:48],
            "metadata": {"locale": locale},
        }
        if job_id is not None:
            # A redelivered Celery task must resolve to the same conversation.
            # Job IDs are server-generated UUIDs, so they are safe deterministic IDs.
            conversation["id"] = str(UUID(job_id))
            response = (
                client.table("agent_conversations")
                .upsert(conversation, on_conflict="id", ignore_duplicates=True)
                .execute()
            )
            conversation_id = str(UUID(job_id))
        else:
            response = client.table("agent_conversations").insert(conversation).execute()
        if not response.data:
            if conversation_id is None:
                raise RuntimeError("Supabase did not return the created conversation")
        elif conversation_id is None:
            conversation_id = str(response.data[0]["id"])

    history_query = (
        client.table("agent_messages")
        .select("role, content")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=True)
        .limit(settings.agent_memory_recent_message_limit)
    )
    history_response = retry_transient(
        history_query.execute,
        operation_name="supabase.read.agent_messages",
    )
    rows: list[dict[str, Any]] = history_response.data or []
    history = [
        {"role": str(row["role"]), "content": str(row["content"])}
        for row in reversed(rows)
        if row.get("role") in {"user", "assistant"}
    ]
    return conversation_id, history


def save_turn(
    conversation_id: str,
    message: str,
    answer: str,
    *,
    job_id: str | None = None,
) -> None:
    rows = [
        {"conversation_id": conversation_id, "role": "user", "content": message},
        {"conversation_id": conversation_id, "role": "assistant", "content": answer},
    ]
    query = get_supabase().table("agent_messages")
    if job_id is not None:
        namespace = UUID(job_id)
        rows[0]["id"] = str(uuid5(namespace, "user"))
        rows[1]["id"] = str(uuid5(namespace, "assistant"))
        response = query.upsert(rows, on_conflict="id", ignore_duplicates=True).execute()
    else:
        response = query.insert(rows).execute()
    if response.data is None:
        raise RuntimeError("Supabase did not persist the agent turn")


def append_assistant_message(conversation_id: str, answer: str) -> None:
    response = (
        get_supabase()
        .table("agent_messages")
        .insert({"conversation_id": conversation_id, "role": "assistant", "content": answer})
        .execute()
    )
    if response.data is None:
        raise RuntimeError("Supabase did not persist the confirmation result")
